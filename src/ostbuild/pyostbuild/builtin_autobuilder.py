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
from . import snapshot
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
        self._build_diff_cache = {}
        self._updated_modules_queue = {}
        self._resolve_is_full = False
        self._resolve_timeout = 0

    def _status_is_success(self, estatus):
        return os.WIFEXITED(estatus) and os.WEXITSTATUS(estatus) == 0

    def _get_build_diff_for_task(self, task):
        if hasattr(task, 'build_diff'):
            return task.build_diff
        db = self.get_src_snapshot_db()
        meta_path = os.path.join(task.path, 'meta.json')
        f = open(meta_path)
        meta = json.load(f)
        f.close()
        snapshot_path = meta['version-path']
        prev_snapshot_path = db.get_previous_path(snapshot_path)
        if prev_snapshot_path is None:
            task.build_diff = None
        else:
            task.build_diff = snapshot.snapshot_diff(db.load_from_path(snapshot_path),
                                                     db.load_from_path(prev_snapshot_path))

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
        if self._resolve_is_full:
            log("scheduling next full resolve for %d seconds " % (self.resolve_poll_secs, ))
            self._resolve_timeout = self.loop.timeout_add(self.resolve_poll_secs*1000, self._fetch)
        if not self.build_needed:
            self.build_needed = self.prev_source_snapshot_path != self.source_snapshot_path
        if self.build_needed and self.build_proc is None:
            self._run_build()
        else:
            self._write_status()

        self._process_updated_modules_dir()

    def _fetch(self, components=[]):
        self._run_resolve(fetch=True, components=components)
        return False

    def _run_resolve(self, fetch=False, components=[]):
        assert self.resolve_proc is None
        t = self._resolve_taskset.start()
        workdir = t.path
        f = t.logfile_stream
        args = ['ostbuild', 'resolve', '--manifest=' + self.manifest]
        if fetch:
            args.append('--fetch')
            args.append('--fetch-keep-going')
            args.extend(components)
        self._resolve_is_full = len(components) == 0
        self.resolve_proc = subprocess.Popen(args, stdin=open('/dev/null'), stdout=f, stderr=f)
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
        t = self._build_taskset.start()
        workdir = t.path
        f = t.logfile_stream
        statusjson = os.path.join(workdir, 'status.json')
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

    def _buildhistory_to_json(self):
        history = self._build_taskset.get_history()
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
            data['diff'] = self._get_build_diff_for_task(item)
        return entries

    def _write_status(self):
        status = {'prefix': self.prefix}
        if self.source_snapshot_path is not None:
            src_db = self.get_src_snapshot_db()
            version = src_db.parse_version(os.path.basename(self.source_snapshot_path))
            status['version'] = version
            status['version-path'] = os.path.relpath(self.source_snapshot_path, self.snapshot_dir)
        else:
            status['version'] = ''
        
        status['build'] = self._buildhistory_to_json()
        
        if self.build_proc is not None:
            active_build = self._build_taskset.get_history()[-1]
            active_build_json = status['build'][-1]
            status_path = os.path.join(active_build.path, 'status.json')
            if os.path.isfile(status_path):
                f = open(status_path)
                build_status = json.load(f)
                f.close()
                active_build_json['build-status'] = build_status

        fileutil.write_json_file_atomic(self.status_path, status)

    def _on_updated_modules_dir_changed(self):
        updated = []
        for name in os.listdir(self.updated_modules_dir):
            if name not in self._updated_modules_queue:
                updated.append(name)
            path = os.path.join(self.updated_modules_dir, name)
            os.unlink(path)
        latest_snapshot = self.get_src_snapshot_db().get_latest()
        for name in updated:
            if (latest_snapshot is not None
                and self.find_component_in_snapshot(name, latest_snapshot) is None):
                continue
            log("Queuing fetch of %s from push notification" % (name, ))
            self._updated_modules_queue[name] = 1
        self._process_updated_modules_dir()
    
    def _process_updated_modules_dir(self):
        if (len(self._updated_modules_queue) > 0
            and self.resolve_proc is None):
            self._fetch(self._updated_modules_queue)
            self._updated_modules_queue = {}

    def execute(self, argv):
        parser = argparse.ArgumentParser(description=self.short_description)
        parser.add_argument('--prefix')
        parser.add_argument('--resolve-poll', type=int, default=10*60)
        parser.add_argument('--manifest', required=True)
        parser.add_argument('--updated-modules-dir')
        
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

        if args.updated_modules_dir:
            self.updated_modules_dir = args.updated_modules_dir
            filemonitor.FileMonitor.get().add(args.updated_modules_dir,
                                              self._on_updated_modules_dir_changed)

        self.loop.run()

builtins.register(OstbuildAutobuilder)
