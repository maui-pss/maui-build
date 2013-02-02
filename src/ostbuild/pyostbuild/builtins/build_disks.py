# vim: et:ts=4:sw=4
# Copyright (C) 2013 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
# Copyright (C) 2013 Colin Walters <walters@verbum.org>
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

import os, argparse, shutil

from .. import builtins
from .. import libqa
from .. import jsondb
from .. import fileutil
from .. import libqa
from ..subprocess_helpers import run_sync
from ..guestfish import GuestFish, GuestMount

class OstbuildBuildDisks(builtins.Builtin):
    name = "build-disks"
    short_description = "Generate disk images"

    def __init__(self):
        builtins.Builtin.__init__(self)

    def _disk_path_for_target(self, target_name, is_snap=False):
        squashed_name = target_name.replace("/", "_")
        if is_snap:
            suffix = "-snap.qcow2"
        else:
            suffix = "-disk.qcow2"

    def execute(self, argv):
        self.get_prefix()

        self.image_dir = os.path.join(self.workdir, "images", self.prefix)
        self.current_image_link = os.path.join(self.image_dir, "current")
        self.previous_image_link = os.path.join(self.image_dir, "previous")
        fileutil.ensure_dir(self.image_dir)

        buildresult_dir = os.path.join(self.workdir, "builds", self.prefix)
        builddb = jsondb.JsonDB(buildresult_dir)

        latest_path = builddb.get_latest_path()
        build_version = builddb.parse_version(os.path.basename(latest_path))
        self._build_data = builddb.load_from_path(latest_path)

        targets = self._build_data["targets"]

        # Special case the default target - we do a pull, then clone
        # that disk for further tests.  This is a speedup under the
        # assumption that the trees are relatively close, so we avoid
        # copying data via libguestfs repeatedly.
        default_target = self._build_data["snapshot"]["default-target"]
        default_revision = self._build_data["targets"][default_target]
        self._default_disk_path = self._disk_path_for_target(default_target, False)

        tmppath = os.path.abspath(os.path.join(self._default_disk_path, "..", os.path.basename(self._default_disk_path() + ".tmp")))
        shutil.rmtree(tmppath)

        if not os.path.exist(self._default_disk_path):
            libqa.create_disk(tmppath)
        else:
            libqa.copy_disk(self._default_disk_path, tmppath)

        osname = self._build_data["snapshot"]["osname"]

        run_sunc(["ostbuild", "qa-pull-deploy", tmppath, self.repo, osname,
                 default_target, default_revision])
        shutil.move(tmppath, self._default_disk_path)


        for target_name in targets:
            if target_name == default_target:
                continue
            target_revision = self._build_data["targets"][target_name]
            disk_path = self._disk_path_for_target(target_name, True)
            tmppath = os.path.abspath(os.path.join(disk_path, "..", os.path.basename(disk_path) + ".tmp"))
            shutil.rmtree(tmppath)
            libqa.create_disk_snapshot(self._default_disk_path, tmppath)
            run_sync(["ostbuild", "qa-pull-deploy", tmppath, self.repo, osname, target_name, target_revision])

        fileutil.file_linkcopy(latest_path, os.path.join(image_dir, os.path.basename(latest_path)), overwrite=True)

builtins.register(OstbuildBuildDisks)
