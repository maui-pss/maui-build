# vim: et:ts=4:sw=4
# Copyright (C) 2012-2013 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
# Copyright (C) 2011-2012 Colin Walters <walters@verbum.org>
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

# This implement a qmake build system

import os, shutil, tempfile

from . import BuildSystem, PREFIX
from ..subprocess_helpers import run_sync

class MakeBuildSystem(BuildSystem):
    name = "make"

    def detect(self):
        qmakefile_path = None
        for name in os.listdir(os.getcwd()):
            if name in ("Makefile", "makefile", "GNUmakefile"):
                return True
        return False

    def do_build(self):
        if os.path.isdir(self.builddir):
            shutil.rmtree(self.builddir)
        shutil.copytree(".", self.builddir, symlinks=True,
                        ignore=shutil.ignore_patterns(self.builddir))

        args = list(self.makeargs)
        args.extend(self.config_opts)
        user_specified_jobs = False
        for arg in args:
            if arg == "-j":
                user_specified_jobs = True
        if not user_specified_jobs:
            args.extend(self.default_make_jobs)
        run_sync(args, cwd=self.builddir)

        args = ["make", "install", "DESTDIR=" + self.mauibuild_resultdir]
        run_sync(args, cwd=self.builddir)
