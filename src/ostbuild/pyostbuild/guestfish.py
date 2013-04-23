# vim: et:ts=4:sw=4
# Copyright (C) 2013 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
# Copyright (C) 2012-2013 Colin Walters <walters@verbum.org>
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

import os, time

from .logger import Logger
from .subprocess_helpers import run_sync
from .subprocess_helpers import run_sync_with_input_get_output

class LibGuestfs(object):
    def __init__(self, diskpath, use_lock_file=True, partition_opts=["-i"], read_write=False):
        self.logger = Logger()

        self._diskpath = diskpath
        self._read_write = read_write
        self._partition_opts = partition_opts
        if use_lock_file:
            self._lockfile_path = diskpath + ".guestfish-lock"
        else:
            self._lockfile_path = None

    def _lock(self):
        if self._lockfile_path:
            stream = open(self._lockfile_path, "w")
            stream.close()

    def _unlock(self):
        if self._lockfile_path is not None:
            os.unlink(self._lockfile_path)

    def _append_opts(self, argv):
        argv.extend(["-a", self._diskpath])
        if self._read_write:
            argv.append("--rw")
        else:
            argv.append("--ro")
        argv.extend(self._partition_opts)

class GuestFish(LibGuestfs):
    def run(self, input):
        self._lock()
        args = ["guestfish",]
        self._append_opts(args)
        result = run_sync_with_input_get_output(args, input,
                                                log_initiation=True,
                                                log_success=True)
        self._unlock()
        return result.split("\n")

class GuestMount(LibGuestfs):
    def mount(self, mntdir):
        self._lock()

        self._mntdir = mntdir
        self._mount_pid_file = mntdir + ".guestmount-pid"

        if os.path.exists(self._mount_pid_file):
            self.logger.fatal("guestfish pid file exists: %s" % self._mount_pid_file)

        args = ["guestmount", "-o", "allow_root", "--pid-file", self._mount_pid_file]
        self._append_opts(args)
        args.append(mntdir)

        self.logger.info("Mounting %s: %s" % (mntdir, " ".join(args)))

        self._mounted = False
        if run_sync(args, log_initiation=False):
            self._mounted = True
        else:
            self._unlock()
        return self._mounted

    def umount(self):
        if not self._mounted:
            return

        pid_file = open(self._mount_pid_file, "r")
        pid_str = pid_file.read().rstrip()
        pid_file.close()
        if len(pid_str) == 0:
            self._mounted = False
            return

        for i in range(0, 30):
            # See "man guestmount" for why retry loops here might be needed if this
            # script is running on a client machine with programs that watch for new mounts
            if run_sync(["fusermount", "-u", self._mntdir], fatal_on_error=False):
                break
            else:
                run_sync(["fuser", "-m", self._mntdir])
                run_sync(["ls", "-al", "/proc/" + str(os.getpid()) + "/fd"])
                time.sleep(1)

        for i in range(0, 30):
            if run_sync(["kill", "-0", pid_str], stderr=None):
                self.log.info("Awaiting termination of guestfish, pid=%s timeout=%ss" % (pid_str, str(30 - i)))
                time.sleep(1)
            else:
                guestfish_exited = True
                break

        if not guestfish_exited:
            self.logger.fatal("guestfish failed to exit")
        self._mounted = false

        self._unlock()
