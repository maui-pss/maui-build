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

# Applied to filenames only
_IGNORE_FILENAME_REGEXPS = map(re.compile,
                               [r'.*\.py[co]$'])

_DOC_DIRS = ['usr/share/doc',
             'usr/share/gtk-doc',
             'usr/share/man',
             'usr/share/info']

_DEVEL_DIRS = ['usr/include',
               'usr/share/aclocal',
               'usr/share/pkgconfig',
               'usr/lib/pkgconfig',
               'usr/share/cmake',
               'usr/lib/cmake',
               'usr/lib/qt5/cmake',
               'usr/lib/qt5/mkspecs']

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
        #
        # Pre-build phase
        #

        self.starttime = time.time()

        # Call the method that subclasses will override
        self.do_build()

        #
        # Post-build phase
        #

        runtime_path = os.path.join(self.ostbuild_resultdir, 'runtime')
        devel_path = os.path.join(self.ostbuild_resultdir, 'devel')
        doc_path = os.path.join(self.ostbuild_resultdir, 'doc')
        debug_path = os.path.join(self.ostbuild_resultdir, 'debug')
        for resultdir in [runtime_path, devel_path, doc_path, debug_path]:
            if os.path.isdir(resultdir):
                shutil.rmtree(resultdir)
            os.makedirs(resultdir)

        # Some components install files that are read-only even for the user,
        # this will make stripping debugging information fail so we need
        # to change file modes before we continue
        for subpath, subdirs, files in os.walk(self.tempdir):
            for filename in files:
                src_path = os.path.join(subpath, filename)
                # Ensure that files are at least rw-rw-r-- and directories
                # are rwxrw-r--
                statsrc = os.lstat(src_path)
                if not stat.S_ISLNK(statsrc.st_mode):
                    minimal_mode = (stat.S_IRUSR | stat.S_IWUSR |
                                    stat.S_IRGRP | stat.S_IWGRP |
                                    stat.S_IROTH)
                    if stat.S_ISDIR(statsrc.st_mode):
                        minimal_mode |= stat.S_IXUSR
                    os.chmod(src_path, statsrc.st_mode | minimal_mode)

        # Remove /var from the install - components are required to
        # auto-create these directories on demand
        varpath = os.path.join(self.tempdir, 'var')
        if os.path.isdir(varpath):
            shutil.rmtree(varpath)

        # Delete all .la and .a files
        libdir = os.path.join(self.tempdir, 'usr/lib')
        for dirpath, subdirs, files in os.walk(libdir):
            for filename in files:
                path = os.path.join(dirpath, filename)
                if filename.endswith('.la') or filename.endswith('.a'):
                    os.unlink(path)

        # Move symbolic links for shared libraries to devel
        if os.path.exists(libdir):
            for filename in os.listdir(libdir):
                path = os.path.join(libdir, filename)
                stbuf = os.lstat(path)
                if not (filename.endswith('.so')
                        and stat.S_ISLNK(stbuf.st_mode)):
                        continue
                dest = os.path.join(devel_path, 'usr/lib', filename)
                self._install_and_unlink(path, dest)

        for subpath, subdirs, files in os.walk(self.tempdir):
            for filename in files:
                src_path = os.path.join(subpath, filename)
                self._process_build_result_split_debuginfo(self.tempdir, debug_path, src_path)

        for dirname in _DEVEL_DIRS:
            dirpath = os.path.join(self.tempdir, dirname)
            if os.path.isdir(dirpath):
                dest = os.path.join(devel_path, dirname)
                self._install_and_unlink(dirpath, dest)

        for dirname in _DOC_DIRS:
            dirpath = os.path.join(self.tempdir, dirname)
            if os.path.isdir(dirpath):
                dest = os.path.join(doc_path, dirname)
                self._install_and_unlink(dirpath, dest)

        for filename in os.listdir(self.tempdir):
            src_path = os.path.join(self.tempdir, filename)
            dest_path = os.path.join(runtime_path, filename)
            self._install_and_unlink(src_path, dest_path)

        for tmpname in self.tempfiles:
            assert os.path.isabs(tmpname)
            if os.path.isdir(tmpname):
                shutil.rmtree(tmpname)
            else:
                try:
                    os.unlink(tmpname)
                except OSError, e:
                    pass
    
        self.endtime = time.time()

        self.logger.info("Compilation succeeded; %d seconds elapsed" % (int(self.endtime - self.starttime),))
        self.logger.info("Results placed in %s" % (self.ostbuild_resultdir, ))

    def _get_env_for_cwd(self, cwd=None, env=None):
        # This dance is necessary because we want to keep the PWD
        # environment variable up to date.  Not doing so is a recipie
        # for triggering edge conditions in pwd lookup.
        if (cwd is not None) and (env is None or ('PWD' in env)):
            if env is None:
                env_copy = os.environ.copy()
            else:
                env_copy = env.copy()
            if ('PWD' in env_copy) and (not cwd.startswith('/')):
                env_copy['PWD'] = os.path.join(env_copy['PWD'], cwd)
            else:
                env_copy['PWD'] = cwd
        else:
            env_copy = env
        return env_copy

    def _install_and_unlink(self, src, dest):
        statsrc = os.lstat(src)
        dirname = os.path.dirname(dest)
        if not os.path.isdir(dirname):
            os.makedirs(dirname)

        # Ensure that all installed files are at least rw-rw-r--;
        # we don't support private/hidden files.
        # Directories also need u+x, i.e. they're rwxrw-r--
        if not stat.S_ISLNK(statsrc.st_mode):
            minimal_mode = (stat.S_IRUSR | stat.S_IWUSR |
                            stat.S_IRGRP | stat.S_IWGRP |
                            stat.S_IROTH)
            if stat.S_ISDIR(statsrc.st_mode):
                minimal_mode |= stat.S_IXUSR
            os.chmod(src, statsrc.st_mode | minimal_mode)

        if stat.S_ISDIR(statsrc.st_mode):
            if not os.path.isdir(dest):
                os.mkdir(dest)
            for filename in os.listdir(src):
                src_child = os.path.join(src, filename)
                dest_child = os.path.join(dest, filename)
    
                self._install_and_unlink(src_child, dest_child)
            os.rmdir(src)
        else:
            basename = os.path.basename(src)
            ignored = False
            for r in _IGNORE_FILENAME_REGEXPS:
                if r.match(basename):
                    ignored = True
                    break
            if ignored:
                self.logger.info("Not installing %s" % (src, ))
                os.unlink(src)
                return
            try:
                os.rename(src, dest)
            except OSError, e:
                if stat.S_ISLNK(statsrc.st_mode):
                    linkto = os.readlink(src)
                    os.symlink(linkto, dest)
                else:
                    shutil.copy2(src, dest)
                os.unlink(src)

    def _process_build_result_split_debuginfo(self, build_result_dir, debug_path, path):
        # Only process shared libraries and executables
        file_mimetype = run_sync_get_output(["file", "-b", "--mime-type", path]).strip()
        is_shared = file_mimetype == "application/x-sharedlib"
        is_exec = file_mimetype == "application/x-executable"
        if not is_shared and not is_exec:
            return
        # Retrieve Build ID
        build_id = run_sync_get_output(["eu-readelf", "-n", path]).strip()
        m = re.search(r'\s+Build ID: ([0-9a-f]+)', build_id)
        if not m:
            self.logger.warning("No build-id for ELF object %s" % path)
            return
        build_id = m.group(1)
        self.logger.info("ELF object %s buildid=%s" % (path, build_id))
        dbg_name = "%s/%s.debug" % (s[:2], s[2:])
        objdebug_path = os.path.abspath(os.path.join(debug_path, "usr/lib/debug/.build-id/" + dbg_name))
        if not os.path.isdir(objdebug_path):
            os.makedirs(objdebug_path)
        run_sync(["objcopy", "--only-keep-debug", path, objdebug_path])

        strip_args = ["strip", "--remove-section=.comment", "--remove-section=.note"]
        if is_shared:
            strip_args.append("--strip-unneeded")
        strip_args.append(path)
        run_sync(strip_args)
