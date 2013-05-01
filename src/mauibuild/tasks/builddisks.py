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

import os, re, shutil

from .. import buildutil
from .. import fileutil
from .. import libqa
from .. import taskset
from ..task import TaskDef
from ..guestfish import GuestMount
from ..subprocess_helpers import run_sync

IMAGE_RETAIN_COUNT = 2

class TaskBuildDisks(TaskDef):
    name = "builddisks"
    short_description = "Generate disk images"
    after = ["build",]

    _VERSION_RE = re.compile(r'^(\d+)\.(\d+)$')
    _image_subdir = "images"
    _inherit_previous_disk = True
    _only_tree_suffixes = ["-runtime"]

    def __init__(self, builtin, taskmaster, name, argv):
        TaskDef.__init__(self, builtin, taskmaster, name, argv)

    def execute(self):
        subworkdir = os.getcwd()

        base_image_dir = os.path.join(self.workdir, self._image_subdir)
        fileutil.ensure_dir(base_image_dir)
        current_image_link = os.path.join(base_image_dir, "current")
        previous_image_link = os.path.join(base_image_dir, "previous")

        builddb = self._get_result_db("build")

        latest_path = builddb.get_latest_path()
        build_version = builddb.parse_version_str(os.path.basename(latest_path))
        build_data = builddb.load_from_path(latest_path)

        target_image_dir = os.path.join(base_image_dir, "disk", build_version)
        if os.path.exists(target_image_dir):
            self.logger.info("Already created %s" % target_image_dir)
            return

        work_image_dir = os.path.join(subworkdir, "images", "disk")
        fileutil.ensure_dir(work_image_dir)

        targets = build_data["targets"]

        osname = build_data["snapshot"]["osname"]
        repo = build_data["snapshot"]["repo"]

        for target_name in targets:
            matched = False
            for suffix in self._only_tree_suffixes:
                if target_name.endswith(suffix):
                    matched = True
                    break
            if not matched:
                continue

            target_revision = build_data["targets"][target_name]
            squashed_name = target_name.replace("\/", "_")
            disk_name = "%s-disk.qcow2" % squashed_name
            diskpath = os.path.join(work_image_dir, disk_name)
            prev_path = os.path.join(current_image_link, disk_name)
            if os.path.exists(diskpath):
                os.unlink(diskpath)
            fileutil.ensure_parent_dir(diskpath)
            if self._inherit_previous_disk and os.path.exists(prev_path):
                libqa.copy_disk(prev_path, diskpath)
            else:
                libqa.create_disk(diskpath, osname)
            mntdir = os.path.join(subworkdir, "mnt-%s-%s" % (osname, squashed_name))
            fileutil.ensure_dir(mntdir)

            gfmnt = GuestMount(diskpath, partition_opts=libqa.DEFAULT_GF_PARTITION_OPTS, read_write=True)
            if not gfmnt.mount(mntdir):
                self.logger.fatal("Unable to mount %s on %s" % (diskpath, mntdir))
            try:
                libqa.pull_deploy(mntdir, self.repo, osname, target_name, target_revision)
                libqa.configure_bootloader(mntdir, osname)
                if repo:
                    repo_dir = os.path.join(mntdir, "ostree", "repo")
                    run_sync(["ostree", "--repo=" + repo_dir, "remote", "add", osname, repo, target_name])
            finally:
                gfmnt.umount()
            libqa.bootloader_install(diskpath, subworkdir, osname)

            self._post_disk_creation(diskpath)

        os.rename(work_image_dir, target_image_dir)

        if os.path.exists(current_image_link):
            new_previous_tmppath = os.path.join(base_image_dir, "previous-new.tmp")
            current_link_target = ll
            shutil.rmtree(new_previous_tmppath)
            os.rename(new_previous_tmppath, previous_image_link)

        buildutil.atomic_symlink_swap(os.path.join(base_image_dir, "current"), target_image_dir)

        self._clean_old_versions(base_image_dir, IMAGE_RETAIN_COUNT)

    def _post_disk_creation(self, diskpath):
        # Move along, this is for zdisks
        pass

    def _load_versions_from(self, path):
        results = []
        for name in os.listdir(path):
            if re.search(self._VERSION_RE, name):
                results.append(name)
        results.sort(cmp=buildutil.compare_versions)
        return results

    def _clean_old_versions(self, path, retain):
        versions = self._load_versions_from(path)
        while len(versions) > retain:
            child = os.path.join(path, versions.pop(0))
            if os.path.exists(child):
                shutil.rmtree(child)

taskset.register(TaskBuildDisks)
