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

import os, argparse

from .. import builtins
from .. import libqa
from ..guestfish import GuestMount

class OstbuildQaPullDeploy(builtins.Builtin):
    name = "qa-pull-deploy"
    short_description = "Copy from shadow repository into disk image and deploy it"

    def __init__(self):
        builtins.Builtin.__init__(self)

    def execute(self, argv):
        parser = argparse.ArgumentParser(description=self.short_description)
        parser.add_argument("diskpath")
        parser.add_argument("srcrepo")
        parser.add_argument("osname")
        parser.add_argument("target")
        parser.add_argument("revision")

        args = parser.parse_args(argv)

        diskpath = args.diskpath

        self._workdir = os.getcwd()
        self._mntdir = os.path.join(self._workdir, "mnt")
        if not os.path.exists(self._mntdir):
            os.makedirs(self._mntdir, 0755)

        gfmnt = GuestMount(diskpath, partition_opts=libqa.DEFAULT_GF_PARTITION_OPTS, read_write=True)
        gfmnt.mount(self._mntdir)
        try:
            libqa.pull_deploy(self._mntdir, args.srcrepo, args.osname, args.target, args.revision)
        except Exception, e:
            self.logger.error(e.message)
        finally:
            gfmnt.umount()

        libqa.grub_install(diskpath)
        self.logger.info("Complete!")

builtins.register(OstbuildQaPullDeploy)
