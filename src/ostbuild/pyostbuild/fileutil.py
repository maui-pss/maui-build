# Copyright (C) 2012-2013 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
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

import os, json

def ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)

def ensure_parent_dir(path):
    ensure_dir(os.path.dirname(path))

def find_program_in_path(program, env=None):
    if env:
        environment = env
    else:
        environment = os.environ
    program_path = None
    for dirname in environment["PATH"].split(":"):
        path = os.path.join(dirname, program)
        if os.access(path, os.X_OK):
            program_path = path
            break
    return program_path

def write_json_file_atomic(path, data):
    path_tmp = path + '.tmp'
    f = open(path_tmp, 'w')
    json.dump(data, f, indent=4, sort_keys=True)
    f.close()
    os.chmod(path_tmp, 0644)
    os.rename(path_tmp, path)
    
