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

import os, shutil

from .. import fileutil
from .. import taskset
from ..task import TaskDef
from ..subprocess_helpers import run_sync

IMAGE_RETAIN_COUNT = 2

class TaskBuildDisks(TaskDef):
    name = "builddisks"
    short_description = "Generate disk images"
    after = ["build",]

    _image_subdir = "images"
    _inherit_previous_disk = True

    def __init__(self, builtin, taskmaster, name, argv):
        TaskDef.__init__(self, builtin, taskmaster, name, argv)

    def execute(self, argv):
        subworkdir = os.getcwd()

        base_image_dir = os.path.join(self.workdir, self._image_subdir)
        fileutil.ensure_dir(base_image_dir)
        current_image_link = os.path.join(base_image_dir, "current")
        previous_image_link = os.path.join(base_image_dir, "previous")

        builddb = self._get_result_db("build")

        latest_path = builddb.get_latest_path()
        build_version = builddb.parse_version_str(os.path.basename(latest_path))
        build_data = builddb.load_from_path(latest_path)

        target_image_dir = os.path.join(base_image_dir, build_version)
        if os.path.exists(target_image_dir):
            self.logger.info("Already created %s" % target_image_dir)
            return

        work_image_dir = os.path.join(subworkdir, "images")
        fileutil.ensure_dir(work_image_dir)

        targets = build_data["targets"]

        osname = build_data["snapshot"]["osname"]
        repo = build_data["snapshot"]["repo"]

        for target_name in targets:
            if not target_name.endswith("-runtime"):
                continue
            target_revision = build_data["targets"][target_name]
            squashed_name = target_name.replace("\/", "_")
            disk_name = "%s-%s-disk.qcow2" % (osname, squashed_name)
            disk_path = os.path.join(work_image_dir, disk_name)
            prev_path = os.path.join(current_image_link, disk_name)
            if os.path.exists(disk_path):
                shutil.rmtree(disk_path)
            if self._inherit_previous_disk and os.path.exists(prev_path):
                libqa.copy_disk(prev_path, disk_path)
            else:
                libqa.create_disk(disk_path)
            mntdir = os.path.join(subworkdir, "mnt-%s-%s" % (osname, squashed_name))
            fileutil.ensure_dir(mntdir)

            gfmnt = GuestMount(disk_path, partition_opts=None, read_write=True)
            gfmnt.mount(mntdir)
            try:
                libqa.pull_deploy(mntdir, self.repo, osname, target_name, target_revision)
                libqa.configure_bootloader(mntdir, osname)
                if repo:
                    repo_dir = os.path.join(mntdir, "ostree", "repo")
                    run_sync(["ostree", "--repo=" + repo_dir, "remote", "add", osname, repo, target_name])
            finally:
                gfmnt.umount()
            libqa.bootloader_install(disk_path, subworkdir, osname)

            self._post_disk_creation(disk_path)

        os.rename(work_image_dir, target_image_dir)

        if os.path.exists(current_image_link):
            new_previous_tmppath = os.path.join(base_image_dir, "previous-new.tmp")
            current_link_target = ll
            shutil.rmtree(new_previous_tmppath)
            os.rename(new_previous_tmppath, previous_image_link)

        buildutil.atomic_symlink_swap(os.path.join(base_image_dir, "current"), target_image_dir)

        self._clean_old_versions(base_image_dir, IMAGE_RETAIN_COUNT)

    def _post_disk_creation(self, disk_path):
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
