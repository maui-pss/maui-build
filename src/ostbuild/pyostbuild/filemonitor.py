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
import stat

from . import mainloop

_global_filemon = None

class FileMonitor(object):
    def __init__(self):
        self._paths = {}
        self._path_modtimes = {}
        self._timeout = 1000
        self._timeout_installed = False
        self._loop = mainloop.Mainloop.get(None)
        self._counter = 0

    @classmethod
    def get(cls):
        global _global_filemon
        if _global_filemon is None:
            _global_filemon = cls()
        return _global_filemon

    def _stat(self, path):
        try:
            st = os.stat(path)
            return st[stat.ST_MTIME]
        except OSError, e:
            return None

    def add(self, path, callback):
        if path not in self._paths:
            self._paths[path] = []
            self._path_modtimes[path] = self._stat(path)
        self._counter += 1
        self._paths[path].append((self._counter, callback))
        if not self._timeout_installed:
            self._timeout_installed = True
            self._loop.timeout_add(self._timeout, self._check_files)
        return self._counter

    def remove(self, cb_id):
        found = False
        for path in self._paths:
            cbs = self._paths[path]
            idx = -1
            for i,(iter_cb_id, callback) in enumerate(cbs):
                if iter_cb_id == cb_id:
                    idx = i
                    break
            if idx != -1:
                cbs.pop(idx)
                found = True
                break
        assert found

    def _check_files(self):
        cbs = []
        for (path,callbacks) in self._paths.iteritems():
            mtime = self._stat(path)
            orig_mtime = self._path_modtimes[path]
            if (mtime is not None) and (orig_mtime is None or (mtime > orig_mtime)):
                self._path_modtimes[path] = mtime
                for (counter, cb) in callbacks:
                    cbs.append(cb)
        for cb in cbs:
            cb()
        self._timeout_installed = len(self._paths) > 0
        return self._timeout_installed
