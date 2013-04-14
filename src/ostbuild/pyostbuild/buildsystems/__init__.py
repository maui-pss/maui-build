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

import os, sys, stat, subprocess, re, shutil
from StringIO import StringIO
import json
from multiprocessing import cpu_count
import select, time

from ..logger import Logger
from ..subprocess_helpers import run_sync, run_sync_get_output

PREFIX = '/usr'

class BuildSystem(object):
    name = None
    default_make_jobs = ['-j', '%d' % (cpu_count() + 1), 
                         '-l', '%d' % (cpu_count() * 2)]
    ostbuild_resultdir = '_ostbuild-results'
    ostbuild_meta_path = '_ostbuild-meta.json'
    metadata = None
    builddir = '_build'
    args = []
    makeargs = ['make']
    tempdir = None
    tempfiles = []

    def __init__(self, args):
        self.logger = Logger()
        self.args = args

        uname = os.uname()
        kernel = uname[0].lower()
        machine = uname[4]
        self.build_target = '%s-%s' % (machine, kernel)

        self.chdir = None
        self.opt_install = False

        for arg in self.args:
            if arg.startswith('--ostbuild-resultdir='):
                self.ostbuild_resultdir = arg[len('--ostbuild-resultdir='):]
            elif arg.startswith('--ostbuild-meta='):
                self.ostbuild_meta_path = arg[len('--ostbuild-meta='):]
            elif arg.startswith('--chdir='):
                os.chdir(arg[len('--chdir='):])
            else:
                self.makeargs.append(arg)
        
        f = open(self.ostbuild_meta_path)
        self.metadata = json.load(f)
        f.close()

    def detect(self):
        return False

    def build(self):
        # Call the method that subclasses will override
        self.starttime = time.time()
        self.do_build()
        self.endtime = time.time()

        # Print results
        self.logger.info("Compilation succeeded; %d seconds elapsed" % int(self.endtime - self.starttime))
        self.logger.info("Results placed in %s" % self.ostbuild_resultdir)
