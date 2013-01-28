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

from . import builtins
from .ostbuildlog import log, error, fatal
from .subprocess_helpers import run_sync, run_sync_get_output
from .subprocess_helpers import run_sync_monitor_log_file
from .guestfish import GuestFish, GuestMount

class OstbuildQaPullDeploy(builtins.Builtin):
    name = "qa-pull-deploy"
    short_description = "Extract data from shadow repository to a disk image repository"

    def __init__(self):
        builtins.Builtin.__init__(self)

    def _find_current_kernel(self, mntdir, osname):
        deploy_bootdir = os.path.join(mntdir, "ostree", "deploy", osname, "current", "boot")
        for item in os.listdir(deploy_bootdir):
            child = os.path.join(deploy_bootdir, item)
            if os.path.basename(child)[:8] == "vmlinuz-":
                return child
        fatal("Couldn't find vmlinuz- in %s" % deploy_bootdir)

    def _parse_kernel_release(self, kernel_path):
        name = os.path.basename(kernel_path)
        try:
            index = name.index("-")
        except ValueError:
            fatal("Invalid kernel name %s" % kernel_path)
        return name[index+1:]

    def _get_initramfs_path(self, mntdir, kernel_release):
        bootdir = os.path.join(mntdir, "boot")
        initramfs_name = "initramfs-%s.img" % kernel_release
        path = os.path.join(bootdir, "ostree", initramfs_name)
        if not os.path.exists(path):
            fatal("Couldn't find initramfs %s" % path)
        return path

    def _do_pull_deploy(self, osname=None, srcrepo=None, target=None):
        if not osname:
            raise ValueError("Invalid OS name '%s'" % (osname, ))
        if not srcrepo:
            raise ValueError("Invalid source repository '%s'" % (srcrepo, ))
        if not target:
            raise ValueError("Invalid target '%s'" % (target, ))

        import copy

        bootdir = os.path.join(self._mntdir, "boot")
        ostreedir = os.path.join(self._mntdir, "ostree")
        ostree_osdir = os.path.join(ostreedir, "deploy", osname)

        admin_args = ["ostree", "admin", "--ostree-dir=" + ostreedir, "--boot-dir=" + bootdir]

        env_copy = os.environ.copy()
        env_copy["LIBGSYSTEM_ENABLE_GUESTFS_FUSE_WORKAROUND"] = "1"

        procdir = os.path.join(self._mntdir, "proc")
        if not os.path.exists(procdir):
            args = copy.copy(admin_args)
            args.extend(["init-fs", self._mntdir])
            run_sync(args, env=env_copy)

        # *** NOTE ***
        # Here we blow away any current deployment.  This is pretty lame, but it
        # avoids us triggering a variety of guestfs/FUSE bugs =(
        # See: https://bugzilla.redhat.com/show_bug.cgi?id=892834
        #
        # But regardless, it's probably useful if every
        # deployment starts clean, and callers can use libguestfs
        # to crack the FS open afterwards and modify config files
        # or the like.
        #shutil.rmtree(ostree_osdir)
        #os.makedirs(ostree_osdir, 0755)

        args = copy.copy(admin_args)
        args.extend(["os-init", osname])
        run_sync(args, env=env_copy)

        run_sync(["ostree", "--repo=" + os.path.join(ostreedir, "repo"), "pull-local",
                  srcrepo, target], env=env_copy)

        args = copy.copy(admin_args)
        args.extend(["deploy", "--no-kernel", osname, target])
        run_sync(args, env=env_copy)

        args = copy.copy(admin_args)
        args.extend(["update-kernel", "--no-bootloader", osname])
        run_sync(args, env=env_copy)

        args = copy.copy(admin_args)
        args.extend(["prune", osname])
        run_sync(args, env=env_copy)

        deploy_kernel_path = self._find_current_kernel(self._mntdir, osname)
        boot_kernel_path = os.path.join(bootdir, "ostree", os.path.basename(deploy_kernel_path))
        if not os.path.exists(boot_kernel_path):
            fatal("%s doesn't exist" % boot_kernel_path)
        kernel_release = self._parse_kernel_release(deploy_kernel_path)
        initramfs_path = self._get_initramfs_path(self._mntdir, kernel_release)

        default_fstab = "LABEL=maui-root / ext4 defaults 1 1\n" \
            "LABEL=maui-boot /boot ext4 defaults 1 2\n" \
            "LABEL=maui-swap swap swap defaults 0 0\n"
        fstab_path = os.path.join(ostreedir, "deploy", osname, "current-etc", "fstab")
        fstab_file = open(fstab_path, "w")
        fstab_file.write(default_fstab)
        fstab_file.close()

        grub_dir = os.path.join(self._mntdir, "boot", "grub")
        if not os.path.exists(grub_dir):
            os.mkdir(grub_dir, 0755)
        boot_relative_kernel_path = os.path.relpath(boot_kernel_path, bootdir)
        boot_relative_initramfs_path = os.path.relpath(initramfs_path, bootdir)
        grub_conf_path = os.path.join(grub_dir, "grub.conf")
        grub_conf = "default=0\n" \
            "timeout=5\n" \
            "title %s\n" \
            "root (hd0,0)\n" \
            "kernel /%s root=LABEL=maui-root ostree=%s/current\n" \
            "initrd /%s\n" % (osname, boot_relative_kernel_path, osname, boot_relative_initramfs_path)
        grub_conf_file = open(grub_conf_path, "w")
        grub_conf_file.write(grub_conf)
        grub_conf_file.close()

    def execute(self, argv):
        parser = argparse.ArgumentParser(description=self.short_description)
        parser.add_argument("diskpath")
        parser.add_argument("srcrepo")
        parser.add_argument("osname")
        parser.add_argument("target")

        args = parser.parse_args(argv)

        diskpath = args.diskpath

        self._workdir = os.getcwd()
        self._mntdir = os.path.join(self._workdir, "mnt")
        if not os.path.exists(self._mntdir):
            os.makedirs(self._mntdir, 0755)

        gfmnt = GuestMount(diskpath, partition_opts=["-m", "/dev/sda3", "-m", "/dev/sda1:/boot"], read_write=True)
        gfmnt.mount(self._mntdir)
        try:
            self._do_pull_deploy(osname=args.osname, srcrepo=args.srcrepo, target=args.target)
        except Exception, e:
            error(e.message)
        finally:
            gfmnt.umount()

        gf = GuestFish(diskpath, partition_opts=["-m", "/dev/sda3", "-m", "/dev/sda1:/boot"], read_write=True)
        gf.run("grub-install / /dev/vda\n")
        log("Complete!")

builtins.register(OstbuildQaPullDeploy)
