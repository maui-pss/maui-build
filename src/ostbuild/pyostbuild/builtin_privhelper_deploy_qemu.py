# Copyright (C) 2012 Colin Walters <walters@verbum.org>
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

import os,sys,subprocess,tempfile,re,shutil
import argparse
import time
import urlparse
import json
from StringIO import StringIO

from . import builtins
from .ostbuildlog import log, fatal
from .subprocess_helpers import run_sync
from . import ostbuildrc
from . import fileutil

class OstbuildPrivhelperDeployQemu(builtins.Builtin):
    name = "privhelper-deploy-qemu"
    short_description = "Helper for deploy-qemu"

    def __init__(self):
        builtins.Builtin.__init__(self)

    def _create_qemu_disk(self):
        log("%s not found, creating" % (self.qemu_path, ))
        success = False
        tmppath = self.qemu_path + '.tmp'
        if os.path.exists(tmppath):
            os.unlink(tmppath)
        subprocess.check_call(['qemu-img', 'create', tmppath, '6G'])
        subprocess.check_call(['mkfs.ext4', '-q', '-F', tmppath])

        subprocess.call(['umount', self.mountpoint], stderr=open('/dev/null', 'w'))
        try:
            subprocess.check_call(['mount', '-o', 'loop', tmppath, self.mountpoint])
            
            for topdir in ['mnt', 'sys', 'root', 'home', 'opt', 'tmp', 'run',
                           'ostree']:
                path = os.path.join(self.mountpoint, topdir)
                fileutil.ensure_dir(path)
            os.chmod(os.path.join(self.mountpoint, 'root'), 0700)
            os.chmod(os.path.join(self.mountpoint, 'tmp'), 01777)

            ostree_dir = os.path.join(self.mountpoint, 'ostree')
            if not os.path.isdir(os.path.join(ostree_dir, 'repo')):
                run_sync(['ostree', 'admin', '--ostree-dir=' + ostree_dir, 'init'])

            success = True
        finally:
            subprocess.call(['umount', self.mountpoint])
        if success:
            os.rename(tmppath, self.qemu_path)

    def execute(self, argv):
        parser = argparse.ArgumentParser(description=self.short_description)
        parser.add_argument('--rootdir',
                            help="Directory containing OSTree data (default: /ostree)")
        parser.add_argument('srcrepo')
        parser.add_argument('target')

        args = parser.parse_args(argv)

        if os.geteuid() != 0:
            fatal("This helper can only be run as root")

        if args.rootdir:
            self.ostree_dir = args.rootdir
        else:
            self.ostree_dir = self.find_ostree_dir()
        self.qemu_path = os.path.join(self.ostree_dir, "ostree-qemu.img")

        self.mountpoint = os.path.join(self.ostree_dir, 'ostree-qemu-mnt')
        fileutil.ensure_dir(self.mountpoint)

        if not os.path.exists(self.qemu_path):
            self._create_qemu_disk()

        subprocess.call(['umount', self.mountpoint], stderr=open('/dev/null', 'w'))
        ostree_dir = os.path.join(self.mountpoint, 'ostree')
        repo_path = os.path.join(ostree_dir, 'repo')
        try:
            subprocess.check_call(['mount', '-o', 'loop', self.qemu_path, self.mountpoint])
            child_args = ['ostree', '--repo=' + repo_path, 'pull-local', args.srcrepo, args.target]
            run_sync(child_args)

            run_sync(['ostree', 'admin', '--ostree-dir=' + ostree_dir, 'deploy', '--no-kernel', args.target],
                     cwd=ostree_dir)
        finally:
            subprocess.call(['umount', self.mountpoint])

        
builtins.register(OstbuildPrivhelperDeployQemu)
