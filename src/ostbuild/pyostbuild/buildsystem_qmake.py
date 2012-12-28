# Copyright (C) 2012 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
# Copyright (C) 2011, 2012 Colin Walters <walters@verbum.org>
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
from .buildsystem import BuildSystem, PREFIX

class QMakeBuildSystem(BuildSystem):
    name = "qmake"
    qmakefile_path = None
    has_configure = False

    def detect(self):
        qmakefile_path = None
        for name in os.listdir(os.getcwd()):
            if os.path.splitext(name)[1] == '.pro':
                self.qmakefile_path = os.path.join(os.getcwd(), name)
                self.log("Found qmake project " + self.qmakefile_path)

                # Some components like qtbase also have a configure script
                for name in os.listdir(os.getcwd()):
                    if name == 'configure':
                        self.has_configure = True
                        break

                return True
        return False

    def do_build(self, args):
        use_builddir = self.metadata.get('shadow-build', False)
        if use_builddir:
            self.log("Using build directory %r" % (self.builddir, ))
            if not os.path.isdir(self.builddir):
                os.mkdir(self.builddir)
        else:
            self.log("Shadow build disable, copying source tree to %s..." % self.builddir)
            if os.path.isdir(self.builddir):
                shutil.rmtree(self.builddir)
            shutil.copytree('.', self.builddir, symlinks=True,
                            ignore=shutil.ignore_patterns('_build'))

        makefile_path = None

        if self.has_configure:
            configargs = ['--prefix=' + PREFIX]
            configargs.extend(self.metadata.get('config-opts', []))
            if use_builddir:
                args = ['../configure']
            else:
                args = ['./configure']
            args.extend(configargs)
            self.run_sync(args, cwd=self.builddir)
        else:
            #self.run_sync(['qmake', '-o', 'Makefile', qmakefile_path], cwd=self.builddir)
            self.run_sync(['qmake',], cwd=self.builddir)
            makefile_path = os.path.join(self.builddir, 'Makefile')
            if not os.path.exists(makefile_path):
                self.fatal("No Makefile was generated")

        if not makefile_path:
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
        args = ['make', 'install', 'INSTALL_ROOT=' + self.tempdir]
        self.run_sync(args, cwd=self.builddir)
