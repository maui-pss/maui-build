# vim: et:ts=4:sw=4
# Copyright (C) 2012-2013 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
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
 
class Snapshot(object):
    def __init__(self, data, path):
        self.data = data
        self.path = path
        self._dict = _component_dict(data)
        self._names = []
        for name in self._dict:
            self._names.append(name)

    def expand_component(self, component):
        meta = dict(component)
        global_patchmeta = self._dict.get('patches')
        if global_patchmeta is not None:
            component_patch_files = component.get('patches', [])
            if len(component_patch_files) > 0:
                patches = dict(global_patchmeta)
                patches['files'] = component_patch_files
                meta['patches'] = patches
        config_opts = list(self._dict.get('config-opts', []))
        config_opts.extend(component.get('config-opts', []))
        meta['config-opts'] = config_opts
        return meta

    def get_component(self, name, allow_none=False):
        if not self._dict.get(name) and not allow_none:
            fatal("No component '%s' in snapshot" % (name, ))
        return self._dict[name]

    def get_all_component_names(self):
        return self._names

    def get_expanded(self, name):
        return self.expand_component(self.get_component(name))
