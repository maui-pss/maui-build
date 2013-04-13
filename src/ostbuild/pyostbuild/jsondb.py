# vim: et:ts=4:sw=4
# Copyright (C) 2012-2013 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
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

import os, re, datetime, tempfile, hashlib, json

from . import jsonutil
from .logger import Logger

class JsonDB(object):
    def __init__(self, path):
        self.logger = Logger()
        self._path = path
        if not os.path.isdir(self._path):
            os.makedirs(self._path)
        self._re = re.compile(r'^(\d+)\.(\d+)-([0-9a-f]+).json$')
        self._max_versions = 5

    def parse_version_str(self, basename):
        (major, minor) = self._parse_version(basename)
        return "%s.%s" % (major, minor)

    def get_latest_path(self):
        files = self._get_all()
        if len(files) == 0:
            return None
        return os.path.join(self._path, files[0][3])

    def get_latest_version(self):
        path = self.get_latest_path()
        if path is None:
            return None
        return self.parse_version_str(os.path.basename(path))

    def get_previous_path(self, path):
        name = os.path.basename(path)
        (target_major, target_minor) = self._parse_version(name)
        files = self._get_all()
        prev = None
        found = False
        for (major, minor, csum, fname) in reversed(files):
            if target_major == major and target_minor == minor:
                found = True
                break
            prev = fname
        if found and prev:
            return os.path.join(self._path, prev)
        return None

    def load_from_path(self, path):
        return json.load(open(os.path.join(self._path, os.path.basename(path))))

    def _parse_version(self, basename):
        match = self._re.search(basename)
        if match is None:
            self.logger.fatal("No JSONDB version in %s" % basename)
        return [int(match.group(1)), int(match.group(2))]

    def _get_all(self):
        result = []
        for name in os.listdir(self._path):
            match = self._re.search(name)
            if match is None:
                continue
            result.append((int(match.group(1)), int(match.group(2)), match.group(3), name))
        result.sort(self._cmp_match_by_version)
        return result

    def _cmp_match_by_version(self, a, b):
        # Note this is a reversed comparison; bigger is earlier
        a_major = a[0]
        a_minor = a[1]
        b_major = b[0]
        b_minor = b[1]

        if a_major < b_major:
            return 1
        elif a_major > b_major:
            return -1
        elif a_minor < b_minor:
            return 1
        elif a_minor > b_minor:
            return -1
        return 0

    def _update_index(self):
        files = self._get_all()
        fnames = []
        for file in files:
            fnames.append(file[3])
        index = {"files": fnames}
        jsonutil.write_json_file_atomic(os.path.join(self._path, "index.json"), index)

    def store(self, obj):
        files = self._get_all()
        if len(files) == 0:
            latest = None
        else:
            latest = files[0]

        current_time = datetime.datetime.utcnow()

        buf = json.dumps(obj, indent=4, sort_keys=True)
        csum = hashlib.sha256(buf).hexdigest()

        if latest is not None:
            if csum == latest[2]:
                return (os.path.join(self._path, latest[3]), False)
            latest_version = (latest[0], latest[1])
        else:
            latest_version = (current_time.year, 0)

        target_name = "%d.%d-%s.json" % (current_time.year, latest_version[1] + 1, csum)
        target_path = os.path.join(self._path, target_name)
        f = open(target_path, "w")
        f.write(buf)
        f.close()

        if (len(files) + 1) > self._max_versions:
            for f in files[(self._max_versions - 1):]:
                os.unlink(os.path.join(self._path, f[3]))

        self._update_index()

        return (target_path, True)
