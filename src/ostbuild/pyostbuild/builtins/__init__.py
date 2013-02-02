# vim: et:ts=4:sw=4
# Copyright (C) 2012-2013 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
# Copyright (C) 2011 Colin Walters <walters@verbum.org>
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

import os
import sys
import stat
import argparse
import json

from .. import ostbuildrc
from .. import fileutil
from .. import jsondb
from ..logger import Logger
from ..snapshot import Snapshot
from ..subprocess_helpers import run_sync, run_sync_get_output

_all_builtins = {}

class Builtin(object):
    name = None
    short_description = None

    def __init__(self):
        self.logger = Logger()
        self._meta_cache = {}
        self.prefix = None
        self.manifest = None
        self.snapshot = None
        self.bin_snapshot = None
        self.repo = None
        self.ostree_dir = self.find_ostree_dir()
        (self.active_branch, self.active_branch_checksum) = self._find_active_branch()
        self._src_snapshots = None
        self._bin_snapshots = None

    def find_ostree_dir(self):
        for path in ['/ostree', '/sysroot/ostree']:
            if os.path.isdir(path):
                return path
        return None
        
    def _find_active_branch(self):
        if self.ostree_dir is None:
            return (None, None)
        current_path = os.path.realpath(os.path.join(self.ostree_dir, 'current'))
        if os.path.isdir(current_path):
            basename = os.path.basename(current_path)
            return basename.rsplit('-', 1)
        else:
            return (None, None)

    def get_component_from_cwd(self):
        cwd = os.getcwd()
        parent = os.path.dirname(cwd)
        parentparent = os.path.dirname(parent)
        return '%s/%s/%s' % tuple(map(os.path.basename, [parentparent, parent, cwd]))

    def parse_config(self):
        self.ostbuildrc = ostbuildrc

        self.mirrordir = os.path.expanduser(ostbuildrc.get_key('mirrordir'))
        fileutil.ensure_dir(self.mirrordir)
        self.workdir = os.path.expanduser(ostbuildrc.get_key('workdir'))
        fileutil.ensure_dir(self.workdir)
        self.snapshot_dir = os.path.join(self.workdir, 'snapshots')
        fileutil.ensure_dir(self.snapshot_dir)
        self.patchdir = os.path.join(self.workdir, 'patches')

    def get_component_snapshot(self, name):
        found = False
        for content in self.active_branch_contents['contents']:
            if content['name'] == name:
                found = True
                break
        if not found:
            self.logger.fatal("Unknown component '%s'" % (name, ))
        return content

    def get_component_meta_from_revision(self, revision):
        text = run_sync_get_output(['ostree', '--repo=' + self.repo,
                                    'cat', revision,
                                    '/_ostbuild-meta.json'])
        return json.loads(text)

    def find_component_in_snapshot(self, name, snapshot):
        for component in snapshot['components']:
            if component['name'] == name:
                return component
        if snapshot['base']['name'] == name:
            return snapshot['base']
        if snapshot['patches']['name'] == name:
            return snapshot['patches']
        return None

    def get_prefix(self):
        if self.prefix is None:
            path = os.path.expanduser('~/.config/ostbuild-prefix')
            if not os.path.exists(path):
                self.logger.fatal("No prefix set; use \"ostbuild prefix\" to set one")
            f = open(path)
            self.prefix = f.read().strip()
            f.close()
        return self.prefix

    def create_db(self, dbsuffix, prefix=None):
        if prefix is None:
            target_prefix = self.get_prefix()
        else:
            target_prefix = prefix
        name = '%s-%s' % (target_prefix, dbsuffix)
        fileutil.ensure_dir(self.snapshot_dir)
        return jsondb.JsonDB(self.snapshot_dir, prefix=name)

    def get_src_snapshot_db(self):
        if self._src_snapshots is None:
            self._src_snapshots = self.create_db('src-snapshot')
        return self._src_snapshots

    def get_bin_snapshot_db(self):
        if self._bin_snapshots is None:
            self._bin_snapshots = self.create_db('bin-snapshot')
        return self._bin_snapshots

    def init_repo(self):
        if self.repo is not None:
            return self.repo
        repo = ostbuildrc.get_key('override_repo', default=None)
        if repo is not None:
            self.repo = os.path.expanduser(repo)
        else:
            self.repo = os.path.join(self.workdir, 'repo')
            if not os.path.isdir(os.path.join(self.repo, 'objects')):
                fileutil.ensure_dir(self.repo)
                run_sync(['ostree', '--repo=' + self.repo, 'init', '--mode=archive-z2'])

    def parse_prefix(self, prefix):
        if prefix is not None:
            self.prefix = prefix
        else:
            self.prefix = self.get_prefix()

    def parse_snapshot(self, prefix, path):
        self.parse_prefix(prefix)
        self.init_repo()
        if path is None:
            latest_path = self.get_src_snapshot_db().get_latest_path()
            if latest_path is None:
                raise Exception("No source snapshot found for prefix %r" % (self.prefix, ))
            snapshot_path = latest_path
        else:
            snapshot_path = path
        snapshot_data = json.load(open(snapshot_path))
        self.snapshot = Snapshot(snapshot_data, snapshot_path)
        key = '00ostbuild-manifest-version'
        src_ver = self.snapshot.data[key]
        if src_ver != 0:
            self.logger.fatal("Unhandled %s version \"%d\", expected 0" % (key, src_ver, ))
        if self.prefix is None:
            self.prefix = self.snapshot.data['prefix']

    def parse_snapshot_from_current(self):
        if self.ostree_dir is None:
            self.logger.fatal("/ostree directory not found")
        repo_path = os.path.join(self.ostree_dir, 'repo')
        if not os.path.isdir(repo_path):
            self.logger.fatal("Repository '%s' doesn't exist" % (repo_path, ))
        if self.active_branch is None:
            self.logger.fatal("No \"current\" link found")
        tree_path = os.path.join(self.ostree_dir, "trees/", self.active_branch)
        self.parse_snapshot(None, os.path.join(tree_path, 'contents.json'))

    def execute(self, args):
        raise NotImplementedError()

def register(builtin):
    _all_builtins[builtin.name] = builtin

def get(name):
    builtin = _all_builtins.get(name)
    if builtin is not None:
        return builtin()
    return None

def get_all():
    return sorted(_all_builtins.itervalues(), lambda a, b: cmp(a.name, b.name))
