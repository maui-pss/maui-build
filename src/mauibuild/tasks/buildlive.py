# vim: et:ts=4:sw=4
# Copyright (C) 2013 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
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

import os, re, shutil, hashlib

from .. import buildutil
from .. import fileutil
from .. import jsonutil
from .. import libqa
from .. import taskset
from ..task import TaskDef
from ..snapshot import Snapshot
from ..subprocess_helpers import run_sync, run_sync_get_output

IMAGE_RETAIN_COUNT = 2

class TaskBuildLive(TaskDef):
    name = "buildlive"
    short_description = "Generate live images"
    after = ["build",]

    _VERSION_RE = re.compile(r'^(\d+)\.(\d+)$')
    _image_subdir = "images"

    def __init__(self, builtin, taskmaster, name, argv):
        TaskDef.__init__(self, builtin, taskmaster, name, argv)

    def execute(self):
        subworkdir = os.getcwd()

        base_image_dir = os.path.join(self.workdir, self._image_subdir)
        fileutil.ensure_dir(base_image_dir)

        builddb = self._get_result_db("build")

        self.latest_path = builddb.get_latest_path()
        self.build_version = builddb.parse_version_str(os.path.basename(self.latest_path))
        self.build_data = builddb.load_from_path(self.latest_path)

        self.imagesdir = os.path.join(self.workdir, "images")
        images_subdir = self.build_data["snapshot"]["images"].get("subdir", None)
        if images_subdir:
            self.imagesdir = os.path.join(self.imagesdir, images_subdir)

        target_image_dir = os.path.join(base_image_dir, self.build_version)
        if os.path.exists(target_image_dir):
            self.logger.info("Already created %s" % target_image_dir)
            return

        work_image_dir = os.path.join(subworkdir, "images")
        fileutil.ensure_dir(work_image_dir)

        targets = self.build_data["targets"]

        self.osname = self.build_data["snapshot"]["osname"]
        repo = self.build_data["snapshot"]["repo"]

        self.data = jsonutil.load_json(os.path.join(self.imagesdir, "live.json"))

        for target_name in targets:
            if not target_name.endswith("-runtime"):
                continue
            target_revision = self.build_data["targets"][target_name]
            squashed_name = target_name.replace("/", "_")

            m = re.match(r'^.+/.+/(.+)-(.+)$', target_name)
            if not m:
                self.logger.fatal("Target name \"%s\" is invalid" % target_name)
            (architecture, target) = m.groups()

            # Create working directory for this target
            work_dir = os.path.join(work_image_dir, squashed_name)

            # Copy ISO contents
            iso_dir = os.path.join(work_dir, "iso")
            iso_isolinux_dir = os.path.join(iso_dir, "isolinux")
            shutil.copytree(os.path.join(self.imagesdir, "live"), iso_dir)

            # Pull deploy the system and create SquashFS image
            self._pull_deploy(work_dir, target_name, target_revision)

            # Copy kernel and initramfs to the ISO directory
            deploy_dir = os.path.join(work_dir, "root-image")
            deploy_kernel_path = libqa._find_current_kernel(deploy_dir, self.osname)
            self.logger.debug("Found kernel: %s" % deploy_kernel_path)
            if not self.build_data["initramfs-images"].has_key(architecture):
                self.logger.fatal("No cached initramfs image found!")
            (kernel_release, initramfs_path) = self.build_data["initramfs-images"][architecture]
            self.logger.debug("Kernel release: %s" % kernel_release)
            self.logger.debug("Found initramfs: %s" % initramfs_path)
            shutil.copy2(deploy_kernel_path, os.path.join(iso_isolinux_dir, "vmlinuz"))
            shutil.copy2(initramfs_path, os.path.join(iso_isolinux_dir, "initramfs.img"))

            # Remove deployment
            #run_sync(["pkexec", "rm", "-rf", deploy_dir])

            disk_name = "%s-live.iso" % squashed_name
            diskpath = os.path.join(work_image_dir, disk_name)
            if os.path.exists(diskpath):
                os.unlink(diskpath)
            self._make_iso(architecture, diskpath, iso_dir)

        os.rename(work_image_dir, target_image_dir)

    def _pull_deploy(self, work_dir, target_name, target_revision):
        pull_deploy_program = os.path.join(self.libexecdir, "mauibuild-image-pull-deploy")
        run_sync(["pkexec", pull_deploy_program, work_dir,
                  self.repo, self.osname, target_name, target_revision])

        iso_os_dir = os.path.join(work_dir, "iso", "LiveOS")
        fileutil.ensure_dir(iso_os_dir)
        squash_image_path = os.path.join(work_dir, "squashfs.img")
        squash_md5_path = os.path.join(work_dir, "squashfs.img.md5")
        shutil.move(squash_image_path, iso_os_dir)
        shutil.move(squash_md5_path, iso_os_dir)

    def _make_iso(self, architecture, diskpath, iso_dir):
        iso_isolinux_dir = os.path.join(iso_dir, "isolinux")
        args = ["xorriso", "-as", "mkisofs", "-iso-level", "3", "-full-iso9660-filenames",
                "-volid", self.data["label"], "-appid", self.data["application"],
                "-publisher", self.data["publisher"], "-preparer", "prepared by mauibuild",
                "-eltorito-boot", "isolinux/isolinux.bin",
                "-eltorito-catalog", "isolinux/boot.cat",
                "-no-emul-boot", "-boot-load-size", "4", "-boot-info-table"]
        args += ["-isohybrid-mbr", os.path.join(iso_isolinux_dir, "isohdpfx.bin"),
                 "-output", diskpath, iso_dir]
        run_sync(args)

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

taskset.register(TaskBuildLive)