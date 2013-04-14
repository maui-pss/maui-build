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

import os, sys, stat, argparse, json, types
import __builtin__

from .. import buildutil
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
        prog = "%s %s" % (os.path.basename(sys.argv[0]), self.name)
        self.parser = argparse.ArgumentParser(prog=prog, description=self.short_description)
        self.logger = Logger()
        self._workdir_initialized = False

    def _init_workdir(self, workdir):
        if self._workdir_initialized:
            return
        self._workdir_initialized = True
        if workdir is None:
            workdir = os.getcwd()

        buildutil.check_is_work_directory(workdir)

        self.workdir = workdir
        self.mirrordir = os.path.join(workdir, "src")
        if not os.path.isdir(self.mirrordir):
            os.makedirs(self.mirrordir)
        self.patchdir = os.path.join(workdir, "patches")
        self.libdir = __builtin__.__dict__["LIBDIR"]
        self.repo = os.path.join(workdir, "repo")

    def _init_snapshot(self, workdir, snapshot_path):
        self._init_workdir(workdir)
        snapshot_dir = os.path.join(workdir, "snapshots")
        if snapshot_path:
            path = os.path.abspath(snapshot_path)
            data = jsonutil.load_json(path)
        else:
            db = jsondb.JsonDB(snapshot_dir)
            path = db.get_latest_path()
            data = db.load_from_path(path)
        self._snapshot = Snapshot(data, path)

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
