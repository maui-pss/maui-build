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

# This implement a CMake build system

import os, shutil, tempfile
from .buildsystem import BuildSystem, PREFIX

class CMakeBuildSystem(BuildSystem):
    name = "cmake"
    cmakefile_path = None

    def detect(self):
        cmakefile_path = None
        for name in os.listdir(os.getcwd()):
            if name == 'CMakeLists.txt':
                self.cmakefile_path = os.path.join(os.getcwd(), name)
                self.log("Found CMake project " + self.cmakefile_path)
                return True
        return False

    def do_build(self):
        self.log("Using build directory %r" % (self.builddir, ))
        if not os.path.isdir(self.builddir):
            os.mkdir(self.builddir)

        configargs = ['-DCMAKE_INSTALL_PREFIX=' + PREFIX]
        configargs.extend(self.metadata.get('config-opts', []))
        build_type_found = False
        for arg in configargs:
            if arg[:18] == '-DCMAKE_BUILD_TYPE':
                build_type_found = True
                break
        if not build_type_found:
            configargs.extend(['-DCMAKE_BUILD_TYPE=Release'])
        configargs.extend(['..'])
        args = ['cmake']
        args.extend(configargs)
        self.run_sync(args, cwd=self.builddir)

        makefile_path = None
        for name in ['Makefile', 'makefile', 'GNUmakefile']:
            makefile_path = os.path.join(self.builddir, name)
            if os.path.exists(makefile_path):
                break
            else:
                makefile_path = None
        if makefile_path is None:
            self.fatal("No Makefile found")

        args = list(self.makeargs)
        user_specified_jobs = False
        for arg in args:
            if arg == '-j':
                user_specified_jobs = True
        if not user_specified_jobs:
            args.extend(self.default_make_jobs)
        self.run_sync(args, cwd=self.builddir)

        self.tempdir = tempfile.mkdtemp(prefix='ostbuild-destdir-%s' % (self.metadata['name'].replace('/', '_'), ))
        self.tempfiles.append(self.tempdir)
        args = ['make', 'install', 'DESTDIR=' + self.tempdir]
        self.run_sync(args, cwd=self.builddir)
