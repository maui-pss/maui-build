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

import os, json

def write_json_to_stream(stream, data):
    json.dump(data, stream, indent=4, sort_keys=True)

def write_json_file_atomic(path, data):
    path_tmp = path + '.tmp'
    f = open(path_tmp, 'w')
    write_json_to_stream(f, data)
    f.close()
    os.chmod(path_tmp, 0644)
    os.rename(path_tmp, path)

def load_json(path):
    return json.load(open(path, "r"))