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

import os,sys,subprocess,tempfile,re,shutil,stat
import argparse
import time
import urlparse
import hashlib
import json

from . import fileutil

VERSION_RE = re.compile(r'(\d+)\.(\d+)')

class TaskDir(object):
    def __init__(self, path):
        self.path = path

    def get(self, name):
        task_path = os.path.join(self.path, name)
        fileutil.ensure_dir(task_path)

        return TaskSet(task_path)
        
class TaskHistoryEntry(object):
    def __init__(self, path, state=None):
        self.path = path
        match = VERSION_RE.match(os.path.basename(path))
        assert match is not None
        self.major = int(match.group(1))
        self.minor = int(match.group(2))
        self.timestamp = None
        self.logfile_path = None
        self.logfile_stream = None
        self.start_timestamp = None
        if state is None:
            statuspath = os.path.join(self.path, 'status')
            if os.path.isfile(statuspath):
                f = open(statuspath)
                self.state = f.read()
                f.close()
                self.timestamp = int(os.stat(statuspath)[stat.ST_MTIME])
            else:
                self.state = 'interrupted'
        else:
            self.state = state
            self.start_timestamp = int(time.time())

    def finish(self, success):
        statuspath = os.path.join(self.path, 'status')
        f = open(statuspath, 'w')
        if success:
            success_str = 'success'
        else:
            success_str = 'failed'
        self.state = success_str
        self.timestamp = int(time.time())
        self.logfile_stream.write('Task %s in %d seconds\n' % (success_str, self.timestamp - self.start_timestamp))
        self.logfile_stream.close()
        f.write(success_str)
        f.close()

    def __cmp__(self, other):
        if not isinstance(other, TaskHistoryEntry):
            return -1
        elif (self.major != other.major):
            return cmp(self.major, other.major)
        else:
            return cmp(self.minor, other.minor)

class TaskSet(object):
    def __init__(self, path):
        self.path = path

        self._history = []
        self._running = False
        self._running_version = None

        self._load()

    def _load(self):
        for item in os.listdir(self.path):
            match = VERSION_RE.match(item)
            if match is None:
                continue
            history_path = os.path.join(self.path, item)
            self._history.append(TaskHistoryEntry(history_path))
        self._history.sort()

    def start(self):
        assert not self._running
        self._running = True
        yearver = time.gmtime().tm_year
        if len(self._history) == 0:
            lastversion = -1 
        else:
            last = self._history[-1]
            if last.major == yearver:
                lastversion = last.minor
            else:
                lastversion = -1 
        history_path = os.path.join(self.path, '%d.%d' % (yearver, lastversion + 1))
        fileutil.ensure_dir(history_path)
        entry = TaskHistoryEntry(history_path, state='running')
        self._history.append(entry)
        entry.logfile_path = os.path.join(history_path, 'log')
        entry.logfile_stream = open(entry.logfile_path, 'w')
        return entry

    def finish(self, success):
        assert self._running
        last = self._history[-1]
        last.finish(success)
        self._running = False

    def get_history(self):
        return self._history
