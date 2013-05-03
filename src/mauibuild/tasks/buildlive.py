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

        base_image_dir = os.path.join(self.workdir, self._image_subdir, "live")
        fileutil.ensure_dir(base_image_dir)
        current_image_link = os.path.join(base_image_dir, "current")
        previous_image_link = os.path.join(base_image_dir, "previous")

        builddb = self._get_result_db("build")

        self.latest_path = builddb.get_latest_path()
        self.build_version = builddb.parse_version_str(os.path.basename(self.latest_path))
        self.build_data = builddb.load_from_path(self.latest_path)

        self.supportdir = os.path.join(self.workdir, "support")
        support_subdir = self.build_data["snapshot"]["support"].get("subdir", None)
        if support_subdir:
            self.supportdir = os.path.join(self.supportdir, support_subdir)

        target_image_dir = os.path.join(base_image_dir, self.build_version)
        if os.path.exists(target_image_dir):
            self.logger.info("Already created %s" % target_image_dir)
            return

        work_image_dir = os.path.join(subworkdir, "images", "live")
        fileutil.ensure_dir(work_image_dir)

        targets = self.build_data["targets"]

        self.osname = self.build_data["snapshot"]["osname"]
        self.version = self.build_data["snapshot"]["version"]
        repo = self.build_data["snapshot"]["repo"]

        data_filename = os.path.join(self.supportdir, "images", "index.json")
        if not os.path.exists(data_filename):
            self.logger.fatal("Couldn't find support index file \"%s\"" % data_filename)
        self.data = jsonutil.load_json(data_filename)
        if not self.data.has_key("live"):
            self.logget.fatal("No live image definition found")
        for k in ("label", "application", "publisher"):
            if not self.data["live"].has_key(k):
                self.logger.fatal("Live image definition doesn't have \"%s\" key" % k)

        target_name = None
        for target in targets:
            if target.endswith("-live"):
                target_name = target
                break

        if target_name is None:
            self.logger.fatal("No images build, do you have a live target?")

        target_revision = self.build_data["targets"][target_name]
        squashed_name = target_name.replace("/", "_")

        m = re.match(r'^.+/.+/(.+)-(.+)$', target_name)
        if not m:
            self.logger.fatal("Target name \"%s\" is invalid" % target_name)
        (architecture, target) = m.groups()

        # Create working directory for this target
        work_dir = os.path.join(work_image_dir, squashed_name)
        fileutil.ensure_dir(work_dir)

        # Copy ISO contents from support files
        iso_dir = os.path.join(work_dir, "iso")
        iso_isolinux_dir = os.path.join(iso_dir, "isolinux")
        shutil.copytree(os.path.join(self.supportdir, "images", "live"), iso_dir)

        # Pull deploy the system and create SquashFS image
        self._pull_deploy(work_dir, target_name, target_revision)
        deploy_root_dir = os.path.join(work_dir, "root-image")

        # Copy files from deployment
        self._copy_files(deploy_root_dir, iso_dir)

        # Copy kernel and initramfs to the ISO directory
        deploy_kernel_path = libqa._find_current_kernel(deploy_root_dir, self.osname)
        kernel_release = libqa._parse_kernel_release(deploy_kernel_path)
        self.logger.debug("Found kernel release %s: %s" % (kernel_release, deploy_kernel_path))
        initramfs_path = os.path.join(iso_isolinux_dir, "initramfs.img")
        self._create_initramfs(work_dir, deploy_root_dir, kernel_release, initramfs_path)
        self.logger.debug("Created initramfs: %s" % initramfs_path)
        shutil.copy2(deploy_kernel_path, os.path.join(iso_isolinux_dir, "vmlinuz"))

        # Remove deployment
        run_sync(["pkexec", "rm", "-rf", deploy_dir])

        # Expand support files
        self._expand_support_files(iso_dir)

        # Make ISO image
        disk_name = "%s.iso" % squashed_name
        diskpath = os.path.join(work_image_dir, disk_name)
        if os.path.exists(diskpath):
            os.unlink(diskpath)
        self._make_iso(architecture, diskpath, iso_dir)

        os.rename(work_image_dir, target_image_dir)

        if os.path.exists(current_image_link):
            new_previous_tmppath = os.path.join(base_image_dir, "previous-new.tmp")
            current_link_target = ll
            shutil.rmtree(new_previous_tmppath)
            os.rename(new_previous_tmppath, previous_image_link)

        buildutil.atomic_symlink_swap(os.path.join(base_image_dir, "current"), target_image_dir)

        self._clean_old_versions(base_image_dir, IMAGE_RETAIN_COUNT)

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

    def _copy_files(self, deploy_root_dir, iso_dir):
        files = self.data["live"].get("copy-files", {})
        files.update({"usr/lib/syslinux/isolinux-debug.bin": "isolinux/isolinux.bin",
                      "usr/lib/syslinux/isohdpfx.bin": "isolinux/isohdpfx.bin"})
        for src_filename in files.keys():
            src_path = os.path.join(deploy_root_dir, "ostree", "deploy", self.osname, "current", src_filename)
            dst_path = os.path.join(iso_dir, files[src_filename])
            fileutil.ensure_dir(os.path.dirname(dst_path))
            shutil.copy(src_path, dst_path)

    def _create_initramfs(self, work_dir, deploy_root_dir, kernel_release, dest_path):
        deploy_dir = os.path.join(deploy_root_dir, "ostree", "deploy", self.osname, "current")

        subwork_dir = os.path.join(work_dir, "tmp-initramfs")
        var_tmp = os.path.join(subwork_dir, "var", "tmp")
        fileutil.ensure_dir(var_tmp)
        var_dir = os.path.join(subwork_dir, "var")
        tmp_dir = os.path.join(subwork_dir, "tmp")
        fileutil.ensure_dir(tmp_dir)
        initramfs_tmp = os.path.join(tmp_dir, "initramfs-ostree.img")

        dracut_modules = "dmsquash-live pollcdrom"
        dracut_drivers = "sr_mod sd_mod ide-cd cdrom ehci_hcd uhci_hcd ohci_hcd usb_storage usbhid"

        run_sync(["linux-user-chroot", "--mount-readonly", "/",
                  "--mount-proc", "/proc",
                  "--mount-bind", "/dev", "/dev",
                  "--mount-bind", var_dir, "/var",
                  "--mount-bind", tmp_dir, "/tmp",
                  deploy_dir,
                  "dracut", "--tmpdir=/tmp", "-f", "/tmp/initramfs-ostree.img",
                  "--add", dracut_modules, "--add-drivers", dracut_drivers,
                  kernel_release])

        shutil.move(initramfs_tmp, dest_path)
        shutil.rmtree(subwork_dir)

    def _expand_support_files(self, iso_dir):
        data = self.data["live"].copy()
        data.update({"osname": self.osname, "version": self.version})

        files = self.data["live"].get("replace-files", [])
        for filename in files:
            path = os.path.join(iso_dir, filename)
            if os.path.exists(path):
                f = open(path, "r")
                contents = f.read()
                f.close()
                f = open(path, "w")
                f.write(contents % data)
                f.close()

    def _make_iso(self, architecture, diskpath, iso_dir):
        iso_isolinux_dir = os.path.join(iso_dir, "isolinux")
        args = ["xorriso", "-as", "mkisofs", "-iso-level", "3",
                "-full-iso9660-filenames",
                "-volid", self.data["live"]["label"],
                "-appid", self.data["live"]["application"],
                "-publisher", self.data["live"]["publisher"],
                "-preparer", "prepared by mauibuild",
                "-eltorito-boot", "isolinux/isolinux.bin",
                "-eltorito-catalog", "isolinux/boot.cat",
                "-no-emul-boot", "-boot-load-size", "4",
                "-boot-info-table"]
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
