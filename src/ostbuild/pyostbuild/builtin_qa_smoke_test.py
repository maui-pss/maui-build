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

import os

from . import builtins
from .ostbuildlog import log
from .subprocess_helpers import run_sync
from .fileutil import find_program_in_path

class OstbuildQaSmokeTest(builtins.Builtin):
    name = "qa-smoke-test"
    short_description = "Basic smoke testing via parsing serial console"

    def __init__(self):
        builtins.Builtin.__init__(self)

    def execute(self, argv):
        parser = argparse.ArgumentParser(description=self.short_description)
        parser.add_argument("--diskpath")

        args = parser.parse_args(argv)

        path = args.diskpath
        workdir = "."

        fallback_paths = ["/usr/libexec/qemu-kvm"]
        qemu_path_string = find_program_in_path("qemu-kvm")
        if not qemu_path_string:
            for path in fallback_paths:
                if not os.path.exist(path):
                    continue
                qemu_path_string = path
        if not qemu_path_string:
            raise Exception("Unable to find qemu-kvm")

        log("Starting qemu...")
        run_sync([qemu_path_string, "-vga", "std", "m", "768M", "-usb", "-usbdevice", "tablet",
                  "-drive", "file=" + diskpath + ",if=virtio"])
        log("Complete!")

builtins.register(OstbuildQaSmokeTest)
