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

import os, sys, stat, subprocess, re, shutil
from StringIO import StringIO
import json
from multiprocessing import cpu_count
import select, time

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
               'usr/lib/qt5/mkspecs']

class BuildSystem(object):
    default_make_jobs = ['-j', '%d' % (cpu_count() * 2, )]
    ostbuild_resultdir = '_ostbuild-results'
    ostbuild_meta_path = '_ostbuild-meta.json'
    metadata = None
    builddir = '_build'
    makeargs = ['make']
    tempdir = None
    tempfiles = []

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
                self.log("Not installing %s" % (src, ))
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

    def detect(self):
        return False

    def log(self, x):
        sys.stdout.write('ob: ' + x)
        sys.stdout.write('\n')
        sys.stdout.flush()

    def fatal(self, x):
        self.log(x)
        sys.exit(1)

    def run_sync(self, args, cwd=None, env=None):
        self.log("running: %s" % (subprocess.list2cmdline(args),))

        env_copy = self._get_env_for_cwd(cwd, env)

        stdin_target = open('/dev/null', 'r')
        stdout_target = sys.stdout
        stderr_target = sys.stderr

        proc = subprocess.Popen(args, stdin=stdin_target, stdout=stdout_target, stderr=stderr_target,
                                close_fds=True, cwd=cwd, env=env_copy)
        stdin_target.close()
        returncode = proc.wait()
        if returncode != 0:
            logfn = self.fatal
        else:
            logfn = None
        if logfn is not None:
            logfn("pid %d exited with code %d" % (proc.pid, returncode))
        return returncode

    def build(self, args):
        #
        # Pre-build phase
        #

        uname = os.uname()
        kernel = uname[0].lower()
        machine = uname[4]
        self.build_target = '%s-%s' % (machine, kernel)

        self.chdir = None
        self.opt_install = False

        for arg in args:
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

        self.starttime = time.time()

        # Call the method that subclasses will override
        self.do_build(args)

        #
        # Post-build phase
        #

        runtime_path = os.path.join(self.ostbuild_resultdir, 'runtime')
        devel_path = os.path.join(self.ostbuild_resultdir, 'devel')
        doc_path = os.path.join(self.ostbuild_resultdir, 'doc')
        for artifact_type in ['runtime', 'devel', 'doc']:
            resultdir = os.path.join(self.ostbuild_resultdir, artifact_type)
            if os.path.isdir(resultdir):
                shutil.rmtree(resultdir)
            os.makedirs(resultdir)

        # Remove /var from the install - components are required to
        # auto-create these directories on demand.
        varpath = os.path.join(self.tempdir, 'var')
        if os.path.isdir(varpath):
            shutil.rmtree(varpath)

        # Move symbolic links for shared libraries as well
        # as static libraries.  And delete all .la files.
        for libdirname in ['lib', 'usr/lib']:
            path = os.path.join(self.tempdir, libdirname)
            if not os.path.isdir(path):
                continue
            for filename in os.listdir(path):
                subpath = os.path.join(path, filename)
                if filename.endswith('.la'):
                    os.unlink(subpath)
                    continue
                if not ((filename.endswith('.so')
                         and os.path.islink(filename))
                        or filename.endswith('.a')):
                        continue
                dest = os.path.join(devel_path, libdirname, filename)
                self._install_and_unlink(subpath, dest)

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

        for tmpname in tempfiles:
            assert os.path.isabs(tmpname)
            if os.path.isdir(tmpname):
                shutil.rmtree(tmpname)
            else:
                try:
                    os.unlink(tmpname)
                except OSError, e:
                    pass
    
        self.endtime = time.time()

        self.log("Compilation succeeded; %d seconds elapsed" % (int(self.endtime - self.starttime),))
        self.log("Results placed in %s" % (self.ostbuild_resultdir, ))
