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

    _VERSION_RE = re.compile(r'^(\d+)\.(\d+)$')
    _image_subdir = "images"

    def __init__(self, builtin, taskmaster, name, argv):
        TaskDef.__init__(self, builtin, taskmaster, name, argv)

        self.subparser.add_argument("-d", "--development", action="store_true",
                                    help="detailed version information")

    def execute(self):
        args = self.subparser.parse_args(self.argv)

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
        if args.development:
            self.version += "-" + self.build_version
        repo = self.build_data["snapshot"]["repo"]

        data_filename = os.path.join(self.supportdir, "images", "index.json")
        if not os.path.exists(data_filename):
            self.logger.fatal("Couldn't find support index file \"%s\"" % data_filename)
        data = jsonutil.load_json(data_filename)
        if not data.has_key("live"):
            self.logget.fatal("No live image definition found")
        self.data = data["live"]
        if not self.data.has_key("label"):
            self.logger.fatal("Missing label in live image definition")
        if args.development:
            import datetime
            self.data["label"] += "_%s" % datetime.datetime.now().strftime("%Y%m%d")

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
        self.work_dir = os.path.join(work_image_dir, squashed_name)
        fileutil.ensure_dir(self.work_dir)

        # Copy ISO contents from support files
        self.iso_dir = os.path.join(self.work_dir, "iso")
        self.iso_isolinux_dir = os.path.join(self.iso_dir, "isolinux")
        shutil.copytree(os.path.join(self.supportdir, "images", "live"), self.iso_dir)

        # Pull deploy the system and create SquashFS image
        self._pull_deploy(target_name, target_revision)
        self.deploy_root_dir = os.path.join(self.work_dir, "root-image")
        self.deploy_dir = os.path.join(self.deploy_root_dir, "ostree", "deploy", self.osname, "current")

        # Copy files from deployment
        self._copy_files()

        # Copy kernel and initramfs to the ISO directory
        deploy_kernel_path = libqa._find_current_kernel(self.deploy_root_dir, self.osname)
        kernel_release = libqa._parse_kernel_release(deploy_kernel_path)
        self.logger.debug("Found kernel release %s: %s" % (kernel_release, deploy_kernel_path))
        initramfs_path = os.path.join(self.iso_isolinux_dir, "initramfs.img")
        self._create_initramfs(kernel_release, initramfs_path)
        self.logger.debug("Created initramfs: %s" % initramfs_path)
        shutil.copy2(deploy_kernel_path, os.path.join(self.iso_isolinux_dir, "vmlinuz"))

        # Remove deployment
        self._pull_deploy_cleanup()

        # Expand support files
        self._expand_support_files()

        # UEFI support
        if architecture == "x86_64":
            if self._is_gummiboot_available():
                self._create_efi()
                self._create_efiboot()
            else:
                self.logger.warning("gummiboot not found on the host system, no UEFI support")

        # Make ISO image
        disk_name = "%s.iso" % squashed_name
        diskpath = os.path.join(work_image_dir, disk_name)
        if os.path.exists(diskpath):
            os.unlink(diskpath)
        self._make_iso(diskpath)

        # Remove working directory
        shutil.rmtree(self.work_dir)

        os.rename(work_image_dir, target_image_dir)

        if os.path.exists(current_image_link):
            new_previous_tmppath = os.path.join(base_image_dir, "previous-new.tmp")
            current_link_target = os.path.relpath(os.path.realpath(current_image_link), base_image_dir)
            if os.path.isdir(new_previous_tmppath):
                shutil.rmtree(new_previous_tmppath)
            os.symlink(current_link_target, new_previous_tmppath)
            os.rename(new_previous_tmppath, previous_image_link)

        buildutil.atomic_symlink_swap(os.path.join(base_image_dir, "current"), target_image_dir)

        self._clean_old_versions(base_image_dir, IMAGE_RETAIN_COUNT)

    def _pull_deploy(self, target_name, target_revision):
        pull_deploy_program = os.path.join(self.libexecdir, "mauibuild-image-pull-deploy")
        run_sync(["pkexec", pull_deploy_program, "makeimage", self.work_dir,
                  self.repo, self.osname, target_name, target_revision])

        iso_os_dir = os.path.join(self.iso_dir, "LiveOS")
        fileutil.ensure_dir(iso_os_dir)
        squash_image_path = os.path.join(self.work_dir, "squashfs.img")
        squash_md5_path = os.path.join(self.work_dir, "squashfs.img.md5")
        shutil.move(squash_image_path, iso_os_dir)
        shutil.move(squash_md5_path, iso_os_dir)

    def _pull_deploy_cleanup(self):
        pull_deploy_program = os.path.join(self.libexecdir, "mauibuild-image-pull-deploy")
        run_sync(["pkexec", pull_deploy_program, "cleanup", self.work_dir])

    def _copy_files(self):
        files = self.data.get("copy-files", {})
        files.update({"usr/share/syslinux/isolinux.bin": "isolinux/isolinux.bin",
                      "usr/share/syslinux/isohdpfx.bin": "isolinux/isohdpfx.bin"})
        for src_filename in files.keys():
            src_path = os.path.join(self.deploy_dir, src_filename)
            dst_path = os.path.join(self.iso_dir, files[src_filename])
            fileutil.ensure_dir(os.path.dirname(dst_path))
            shutil.copy(src_path, dst_path)

    def _create_initramfs(self, kernel_release, dest_path):
        subwork_dir = os.path.join(self.work_dir, "tmp-initramfs")
        var_tmp = os.path.join(subwork_dir, "var", "tmp")
        fileutil.ensure_dir(var_tmp)
        var_dir = os.path.join(subwork_dir, "var")
        tmp_dir = os.path.join(subwork_dir, "tmp")
        fileutil.ensure_dir(tmp_dir)
        initramfs_tmp = os.path.join(tmp_dir, "initramfs-ostree.img")

        dracut_modules = "dmsquash-live pollcdrom"
        dracut_drivers = "sr_mod sd_mod ide-cd cdrom ehci_hcd uhci_hcd ohci_hcd usb_storage usbhid"

        run_sync([self._linux_user_chroot_path,
                  "--mount-readonly", "/",
                  "--mount-proc", "/proc",
                  "--mount-bind", "/dev", "/dev",
                  "--mount-bind", var_dir, "/var",
                  "--mount-bind", tmp_dir, "/tmp",
                  self.deploy_dir,
                  "dracut", "--tmpdir=/tmp", "-f", "/tmp/initramfs-ostree.img",
                  "--add", dracut_modules, "--add-drivers", dracut_drivers,
                  kernel_release])

        shutil.move(initramfs_tmp, dest_path)
        shutil.rmtree(subwork_dir)

    def _expand_support_files(self):
        data = self.data.copy()
        data.update({"osname": self.osname, "version": self.version})

        files = self.data.get("replace-files", [])
        for filename in files:
            path = os.path.join(self.iso_dir, filename)
            if os.path.exists(path):
                f = open(path, "r")
                contents = f.read()
                f.close()
                f = open(path, "w")
                f.write(contents % data)
                f.close()

    def _is_gummiboot_available(self):
        gummiboot_path = os.path.join("usr", "lib", "gummiboot", "gummibootx64.efi")
        return os.path.exists(gummiboot_path)

    def _create_efi(self):
        path = os.path.join(self.iso_dir, "EFI", "boot")
        fileutil.ensure_dir(path)
        gummiboot_src_path = os.path.join("usr", "lib", "gummiboot", "gummibootx64.efi")
        gummiboot_dst_path = os.path.join(path, "bootx64.efi")
        shutil.copy2(gummiboot_src_path, gummiboot_dst_path)

    def _create_efiboot(self):
        mkefiboot_program = os.path.join(self.libexecdir, "mauibuild-mkefiboot")
        run_sync(["pkexec", mkefiboot_program, "create", self.work_dir])

        efiboot_path = os.path.join(self.iso_dir, "EFI", "mauibuild", "efiboot.img")

        path = os.path.join(mountpoint, "EFI", "mauibuild")
        fileutil.ensure_dir(path)
        kernel_path = os.path.join(self.iso_dir, "isolinux", "vmlinuz")
        initramfs_path = os.path.join(self.iso_dir, "isolinux", "initramfs.img")
        shutil.copy2(kernel_path, path)
        shutil.copy2(initramfs_path, path)

        path = os.path.join(mountpoint, "EFI", "boot")
        fileutil.ensure_dir(path)
        gummiboot_src_path = os.path.join("usr", "lib", "gummiboot", "gummibootx64.efi")
        gummiboot_dst_path = os.path.join(path, "bootx64.efi")
        shutil.copy2(gummiboot_src_path, gummiboot_dst_path)

        loader_conf = os.path.join(mountpoint, "loader", "loader.conf")
        fileutil.ensure_parent_dir(loader_conf)
        f = open(path, "w")
        f.write("timeout 10\n")
        f.write("default %s-x86_64\n" % self.osname)
        f.close()

        for i in range(1, 3):
            shell_conf = os.path.join(mountpoint, "loader", "entries", "uefi-shell-v%d-x86_64.conf" % i)
            fileutil.ensure_parent_dir(shell_conf)
            f = open(shell_conf, "w")
            f.write("title UEFI Shell x86_64 v%d\n" % i)
            f.write("efi /EFI/shellx64_v%d.efi\n" % i)
            f.close()

        conf_file = os.path.join(mountpoint, "loader", "entries", "%s-x86_64.conf" % self.osname)
        f = open(conf_file, "w")
        f.write("title %s x86_64\n" % self.osname)
        f.write("linux /isolinux/vmlinuz\n")
        f.write("initrd /isolinux/initramfs.img\n")
        f.write("options root=live:CDLABEL=%s rootfstype=auto ro rd.live.image quiet rd.luks=0 rd.md=0 rd.dm=0 ostree=%s/current" % (self.data["label"], self.osname))
        f.close()

        # EFI Shell 2.0 for UEFI 2.3+ ( http://sourceforge.net/apps/mediawiki/tianocore/index.php?title=UEFI_Shell )
        uri = "https://edk2.svn.sourceforge.net/svnroot/edk2/trunk/edk2/ShellBinPkg/UefiShell/X64/Shell.efi"
        dst_path = os.path.join(mountpoint, "EFI", "shellx64_v2.efi")
        run_sync(["curl", "-o", dst_path, uri])

        # EFI Shell 1.0 for non UEFI 2.3+ ( http://sourceforge.net/apps/mediawiki/tianocore/index.php?title=Efi-shell )
        uri = "https://edk2.svn.sourceforge.net/svnroot/edk2/trunk/edk2/EdkShellBinPkg/FullShell/X64/Shell_Full.efi"
        dst_path = os.path.join(mountpoint, "EFI", "shellx64_v1.efi")
        run_sync(["curl", "-o", dst_path, uri])

        run_sync(["pkexec", mkefiboot_program, "cleanup", self.work_dir])

    def _make_iso(self, diskpath):
        efiboot_path = os.path.join(self.iso_isolinux_dir, "efiboot.img")

        args = ["xorriso", "-as", "mkisofs", "-iso-level", "3",
                "-full-iso9660-filenames",
                "-volid", self.data["label"],
                "-preparer", "Prepared by mauibuild"]
        if self.data.get("application"):
            args.extend(["-appid", self.data["application"]])
        if self.data.get("publisher"):
            args.extend(["-publisher", self.data["publisher"]])
        args.extend(["-eltorito-boot", "isolinux/isolinux.bin",
                     "-eltorito-catalog", "isolinux/boot.cat",
                     "-no-emul-boot", "-boot-load-size", "4",
                     "-boot-info-table"])
        args.extend(["-isohybrid-mbr", "isolinux/isohdpfx.bin"])
        if os.path.exists(efiboot_path):
            args.extend(["--efi-boot", "EFI/mauibuild/efiboot.img"])
        args.extend(["-output", diskpath, "."])
        run_sync(args, cwd=self.iso_dir)

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
