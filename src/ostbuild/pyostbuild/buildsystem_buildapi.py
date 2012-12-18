#!/usr/bin/env python
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

# This implements the GNOME build API:
# http://people.gnome.org/~walters/docs/build-api.txt

import os, shutil
from .buildsystem import BuildSystem, PREFIX

class BuildApiBuildSystem(BuildSystem):
    def _has_buildapi_configure_variable(name):
        var = '#buildapi-variable-%s' % (name, )
        for line in open('configure'):
            if line.find(var) >= 0:
                return True
        return False

    def detect(self):
        for name in os.listdir(os.getcwd()):
            if name in ('configure', 'autogen.sh', 'bootstrap'):
                return True
        return False

    def do_build(self, args):
        configargs = ['--build=' + self.build_target,
                      '--prefix=' + PREFIX,
                      '--libdir=' + os.path.join(PREFIX, 'lib'),
                      '--sysconfdir=/etc',
                      '--localstatedir=/var',
                      '--bindir=' + os.path.join(PREFIX, 'bin'),
                      '--sbindir=' + os.path.join(PREFIX, 'sbin'),
                      '--datadir=' + os.path.join(PREFIX, 'share'),
                      '--includedir=' + os.path.join(PREFIX, 'include'),
                      '--libexecdir=' + os.path.join(PREFIX, 'libexec'),
                      '--mandir=' + os.path.join(PREFIX, 'share', 'man'),
                      '--infodir=' + os.path.join(PREFIX, 'share', 'info')]
        configargs.extend(self.metadata.get('config-opts', []))

        configure_path = 'configure'
        if self.metadata.get('rm-configure', False):
            if os.path.exists(configure_path):
                os.unlink(configure_path)

        autogen_script = None
        if not os.path.exists(configure_path):
            self.log("No 'configure' script found, looking for autogen/bootstrap")
            for name in ['autogen', 'autogen.sh', 'bootstrap']:
                if os.path.exists(name):
                    self.log("Using bootstrap script '%s'" % (name, ))
                    autogen_script = name
            if autogen_script is None:
                self.fatal("No configure or autogen script detected; unknown buildsystem")

        if autogen_script is not None:
            env = dict(os.environ)
            env['NOCONFIGURE'] = '1'
            self.run_sync(['./' + autogen_script], env=env)

        use_builddir = True
        doesnot_support_builddir = _has_buildapi_configure_variable('no-builddir')
        if doesnot_support_builddir:
            self.log("Found no-builddir Build API variable; copying source tree to " + self.builddir)
            if os.path.isdir(self.builddir):
                shutil.rmtree(self.builddir)
            shutil.copytree('.', self.builddir, symlinks=True,
                            ignore=shutil.ignore_patterns(self.builddir))
            use_builddir = False

        if use_builddir:
            self.log("Using build directory %r" % (self.builddir, ))
            if not os.path.isdir(self.builddir):
                os.mkdir(self.builddir)

        if use_builddir:
            args = ['../configure']
        else:
            args = ['./configure']
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
 
        if makefile_path and not user_specified_jobs:
            has_notparallel = False

            for line in open(makefile_path):
                if line.startswith('.NOTPARALLEL'):
                    has_notparallel = True
                    self.log("Found .NOTPARALLEL")

            if not has_notparallel:
                self.log("Didn't find NOTPARALLEL, using parallel make by default")
                args.extend(self.default_make_jobs)

        self.run_sync(args, cwd=self.builddir)

        self.tempdir = tempfile.mkdtemp(prefix='ostbuild-destdir-%s' % (self.metadata['name'].replace('/', '_'), ))
        self.tempfiles.append(self.tempdir)
        args = ['make', 'install', 'DESTDIR=' + self.tempdir]
        self.run_sync(args, cwd=self.builddir)
