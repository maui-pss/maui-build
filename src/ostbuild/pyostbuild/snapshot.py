#
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

import os,sys

def _component_dict(snapshot):
    r = {}
    for component in snapshot['components']:
        r[component['name']] = component
    patches = snapshot['patches']
    r[patches['name']] = patches
    base = snapshot['base']
    r[base['name']] = base
    return r

def snapshot_diff(a, b):
    a_components = _component_dict(a)
    b_components = _component_dict(b)

    added = []
    modified = []
    removed = []

    for name in a_components:
        c_a = a_components[name]
        c_b = b_components.get(name)
        if c_b is None:
            removed.append(name)
        elif c_a['revision'] != c_b['revision']:
            modified.append(name)
    for name in b_components:
        if name not in a_components:
            added.append(name)
    return (added, modified, removed)
        
