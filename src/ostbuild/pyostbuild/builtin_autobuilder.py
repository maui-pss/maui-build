# Copyright (C) 2012 Colin Walters <walters@verbum.org>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

import os,sys,subprocess,tempfile,re,shutil
import argparse
import time
import urlparse
import hashlib
import json
from StringIO import StringIO

from . import builtins
from .ostbuildlog import log, fatal
from .subprocess_helpers import run_sync, run_sync_get_output
from .subprocess_helpers import run_sync_monitor_log_file
from . import ostbuildrc
from . import buildutil
from . import mainloop
from . import fileutil
from . import kvfile
from . import filemonitor
from . import jsondb
from . import odict
from . import vcs
from . import task

class OstbuildAutobuilder(builtins.Builtin):
    name = "autobuilder"
    short_description = "Run resolve and build"

    def __init__(self):
        builtins.Builtin.__init__(self)
        self.resolve_proc = None
        self.build_proc = None
        self.loop = mainloop.Mainloop.get(None)
        self.prev_source_snapshot_path = None
        self.source_snapshot_path = None
        self.build_needed = True
        self.last_build_succeeded = True

    def _status_is_success(self, estatus):
        return os.WIFEXITED(estatus) and os.WEXITSTATUS(estatus) == 0

    def _on_resolve_exited(self, pid, status):
        self.resolve_proc = None
        success = self._status_is_success(status)
        self._resolve_taskset.finish(success)
        log("resolve exited success=%s" % (success, ))
        self.prev_source_snapshot_path = self.source_snapshot_path
        self.source_snapshot_path = self.get_src_snapshot_db().get_latest_path()
        changed = self.prev_source_snapshot_path != self.source_snapshot_path
        if changed:
            log("New version is %s" % (self.source_snapshot_path, ))
        log("scheduling next resolve for %d seconds " % (self.resolve_poll_secs, ))
        self.loop.timeout_add(self.resolve_poll_secs*1000, self._fetch)
        if not self.build_needed:
            self.build_needed = self.prev_source_snapshot_path != self.source_snapshot_path
        if self.build_needed and self.build_proc is None:
            self._run_build()
        else:
            self._write_status()

    def _fetch(self):
        self._run_resolve(True)
        return False

    def _run_resolve(self, fetch=False):
        assert self.resolve_proc is None
        workdir = self._resolve_taskset.start()
        f = open(os.path.join(workdir, 'log'), 'w')
        args = ['ostbuild', 'resolve', '--manifest=' + self.manifest]
        if fetch:
            args.append('--fetch')
            args.append('--fetch-keep-going')
        self.resolve_proc = subprocess.Popen(args, stdin=open('/dev/null'), stdout=f, stderr=f)
        f.close()
        log("started resolve: pid %d workdir: %s" % (self.resolve_proc.pid, workdir))
        self.loop.watch_pid(self.resolve_proc.pid, self._on_resolve_exited)
        self._write_status()

    def _on_build_exited(self, pid, status):
        self.build_proc = None
        success = self._status_is_success(status)
        self._build_taskset.finish(success)
        log("build exited success=%s" % (success, ))
        filemonitor.FileMonitor.get().remove(self.build_status_mon_id)
        self.build_status_mon_id = 0
        if self.build_needed:
            self._run_build()
        else:
            self._write_status()

    def _on_build_status_changed(self):
        self._write_status()

    def _run_build(self):
        assert self.build_proc is None
        assert self.build_needed
        self.build_needed = False
        workdir = self._build_taskset.start()
        statusjson = os.path.join(workdir, 'status.json')
        f = open(os.path.join(workdir, 'log'), 'w')
        args = ['ostbuild', 'build', '--skip-vcs-matches',
                '--src-snapshot=' + self.source_snapshot_path,
                '--status-json-path=' + statusjson]
        src_db = self.get_src_snapshot_db()
        version = src_db.parse_version(os.path.basename(self.source_snapshot_path))
        meta = {'version': version,
                'version-path': os.path.relpath(self.source_snapshot_path, self.snapshot_dir)} 
        meta_path = os.path.join(workdir, 'meta.json')
        fileutil.write_json_file_atomic(meta_path, meta)
        self.build_status_json_path = statusjson
        self.build_status_mon_id = filemonitor.FileMonitor.get().add(self.build_status_json_path,
                                                                     self._on_build_status_changed)
        self.build_proc = subprocess.Popen(args, stdin=open('/dev/null'), stdout=f, stderr=f)
        log("started build: pid %d workdir: %s" % (self.build_proc.pid, workdir))
        self.loop.watch_pid(self.build_proc.pid, self._on_build_exited)
        self._write_status()

    def _taskhistory_to_json(self, history):
        MAXITEMS = 5
        entries = []
        for item in history[-MAXITEMS:]:
            data = {'v': '%d.%d' % (item.major, item.minor),
                    'state': item.state,
                    'timestamp': item.timestamp}
            entries.append(data)
            meta_path = os.path.join(item.path, 'meta.json')
            if os.path.isfile(meta_path):
                f = open(meta_path)
                data['meta'] = json.load(f)
                f.close()
        return entries

    def _write_status(self):
        status = {}
        if self.source_snapshot_path is not None:
            src_db = self.get_src_snapshot_db()
            version = src_db.parse_version(os.path.basename(self.source_snapshot_path))
            status['version'] = version
            status['version-path'] = os.path.relpath(self.source_snapshot_path, self.snapshot_dir)
        else:
            status['version'] = ''
        
        status['resolve'] = self._taskhistory_to_json(self._resolve_taskset.get_history())
        build_history = self._build_taskset.get_history()
        status['build'] = self._taskhistory_to_json(build_history)
        
        if self.build_proc is not None:
            active_build = build_history[-1]
            active_build_json = status['build'][-1]
            status_path = os.path.join(active_build.path, 'status.json')
            if os.path.isfile(status_path):
                f = open(status_path)
                build_status = json.load(f)
                f.close()
                active_build_json['build-status'] = build_status

        fileutil.write_json_file_atomic(self.status_path, status)

    def execute(self, argv):
        parser = argparse.ArgumentParser(description=self.short_description)
        parser.add_argument('--prefix')
        parser.add_argument('--resolve-poll', type=int, default=10*60)
        parser.add_argument('--manifest', required=True)
        
        args = parser.parse_args(argv)
        self.manifest = args.manifest
        self.resolve_poll_secs = args.resolve_poll
        
        self.parse_config()
        self.parse_prefix(args.prefix)
        assert self.prefix is not None
        self.init_repo()
        self.source_snapshot_path = self.get_src_snapshot_db().get_latest_path()

        taskdir = task.TaskDir(os.path.join(self.workdir, 'tasks'))
        self._resolve_taskset = taskdir.get('%s-resolve' % (self.prefix, ))
        self._build_taskset = taskdir.get('%s-build' % (self.prefix, ))

        self.status_path = os.path.join(self.workdir, 'autobuilder-%s.json' % (self.prefix, ))
        
        self._run_resolve()
        self._run_build()

        self.loop.run()

builtins.register(OstbuildAutobuilder)
