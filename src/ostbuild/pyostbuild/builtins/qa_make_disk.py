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
from ..ostbuildlog import log, fatal
from ..subprocess_helpers import run_sync, run_sync_get_output
from ..subprocess_helpers import run_sync_monitor_log_file
from ..guestfish import GuestFish

class OstbuildQaMakeDisk(builtins.Builtin):
    name = "qa-make-disk"
    short_description = "Generate a disk image"

    def __init__(self):
        builtins.Builtin.__init__(self)

    def execute(self, argv):
        parser = argparse.ArgumentParser(description=self.short_description)
        parser.add_argument("diskpath")

        args = parser.parse_args(argv)

        path = os.path.realpath(args.diskpath)
        if os.path.exists(path):
            raise Exception("Path %s already exist" % path)

        tmppath = os.path.join(os.path.dirname(path), os.path.basename(path) + ".tmp")
        if os.path.exists(tmppath):
            if not os.path.isfile(tmppath):
                raise Exception("%s already exist and is not a file, cannot delete it" % tmppath)
            os.unlink(tmppath)

        size_mb = 8 * 1024
        bootsize_mb = 200
        swapsize_mb = 64

        run_sync(["qemu-img", "create", tmppath, "%sM" % size_mb])

        make_disk_cmd = "launch\n" \
            "part-init /dev/vda mbr\n" \
            "blockdev-getsize64 /dev/vda\n" \
            "blockdev-getss /dev/vda\n"
        gf = GuestFish(tmppath, partition_opts=[], read_write=True)
        lines = gf.run(make_disk_cmd).split("\n")
        if len(lines) != 2:
            raise Exception("guestfish returned unexpected output lines (%d), expected 2" % len(lines))

        disk_bytesize = int(lines[0])
        disk_sectorsize = int(lines[1])
        log("bytesize: %d, sectorsize: %d" % (disk_bytesize, disk_sectorsize))

        bootsize_sectors = bootsize_mb * 1024 / disk_sectorsize * 1024
        swapsize_sectors = swapsize_mb * 1024 / disk_sectorsize * 1024
        rootsize_sectors = disk_bytesize / disk_sectorsize - bootsize_sectors - swapsize_sectors - 64
        boot_offset = 64
        swap_offset = boot_offset + bootsize_sectors
        root_offset = swap_offset + swapsize_sectors
        end_offset = root_offset + rootsize_sectors

        partconfig = "launch\n" \
            "part-add /dev/vda p %s %s\n" \
            "part-add /dev/vda p %s %s\n" \
            "part-add /dev/vda p %s %s\n" \
            "mkfs ext4 /dev/vda1\n" \
            "set-e2label /dev/vda1 maui-boot\n" \
            "mkswap-L maui-swap /dev/vda2\n" \
            "mkfs ext4 /dev/vda3\n" \
            "set-e2label /dev/vda3 maui-root\n" \
            "mount /dev/vda3 /\n" \
            "mkdir /boot\n" % (boot_offset, swap_offset - 1, swap_offset,
                               root_offset - 1, root_offset, end_offset - 1)
        log("partition configuration: %s" % partconfig)
        lines = gf.run(partconfig).rstrip().split('\n')
        os.rename(tmppath, path)
        log("Created: %s" % path)

builtins.register(OstbuildQaMakeDisk)
