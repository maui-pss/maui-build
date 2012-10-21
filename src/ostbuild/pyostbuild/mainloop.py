#
# Copyright (C) 2011 Colin Walters <walters@verbum.org>
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

import os
import sys
import select
import time

class Mainloop(object):
    DEFAULT = None
    def __init__(self):
        self._running = True
        self.poll = None
        self._timeouts = []
        self._pid_watches = {}
        self._fd_callbacks = {}
        self._source_counter = 0

    @classmethod
    def get(cls, context):
        if context is None:
            if cls.DEFAULT is None:
                cls.DEFAULT = cls()
            return cls.DEFAULT
        raise NotImplementedError("Unknown context %r" % (context, ))

    def _ensure_poll(self):
        if self.poll is None:
            self.poll = select.poll()

    def watch_fd(self, fd, callback):
        self._ensure_poll()
        self.poll.register(fd)
        self._fd_callbacks[fd] = callback

    def unwatch_fd(self, fd):
        self.poll.unregister(fd)
        del self._fd_callbacks[fd]

    def watch_pid(self, pid, callback):
        self._pid_watches[pid] = callback

    def timeout_add(self, ms, callback):
        self._source_counter += 1
        self._timeouts.append((self._source_counter, ms, callback))
        return self._source_counter

    def quit(self):
        self._running = False

    def run_once(self):
        min_timeout = None
        if len(self._pid_watches) > 0:
            min_timeout = 500
        for (source_id, ms, callback) in self._timeouts:
            if (min_timeout is None) or (ms < min_timeout):
                min_timeout = ms
        origtime = time.time() * 1000
        self._ensure_poll()
        fds = self.poll.poll(min_timeout)
        for fd in fds:
            self._fd_callbacks[fd]()
        hit_pids = []
        for pid in self._pid_watches:
            (opid, status) = os.waitpid(pid, os.WNOHANG)
            if opid == pid:
                hit_pids.append((pid, status))
        for (pid, status) in hit_pids:
            watch = self._pid_watches[pid]
            del self._pid_watches[pid]
            watch(pid, status)
        newtime = time.time() * 1000
        diff = int(newtime - origtime)
        if diff < 0: diff = 0
        new_timeouts = []
        for i,(source_id, ms, callback) in enumerate(self._timeouts):
            remaining_ms = ms - diff
            if remaining_ms <= 0:
                result = callback()
                if result:
                    new_timeouts.append((source_id, ms, callback))
            else:
                new_timeouts.append((source_id, remaining_ms, callback))
        self._timeouts = new_timeouts

    def run(self):
        self._running = True
        while self._running:
            self.run_once()
