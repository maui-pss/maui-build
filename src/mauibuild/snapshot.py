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

import os, sys
from .logger import Logger

def _component_dict(snapshot):
    r = {}
    for component in snapshot['components']:
        r[component['name']] = component
    patches = snapshot.get('patches')
    if patches is not None:
        r[patches['name']] = patches
    images = snapshot.get('images')
    if images is not None:
        r[images['name']] = images
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
    def __init__(self, data, path, prepare_resolve=False):
        self.logger = Logger()
        self.data = data
        self.path = path
        if prepare_resolve:
            data["base"] = self._resolve_component(data, data["base"])
            if "patches" in data:
                data["patches"] = self._resolve_component(data, data["patches"])
            if "images" in data:
                data["images"] = self._resolve_component(data, data["images"])
            data["components"] = [self._resolve_component(data, component) for component in data["components"]]
            data["components"] = [component for component in data["components"] if not component.get("disabled", False)]
        self._dict = _component_dict(data)
        self._names = []
        for name in self._dict:
            self._names.append(name)

    def _resolve_component(self, manifest, component_meta):
        result = dict(component_meta)
        orig_src = component_meta["src"]
        name = component_meta.get("name")

        if orig_src.startswith("tarball:"):
            if not name:
                self.logger.fatal("Component src %s has no name attribute" % orig_src)
            if not component_meta.get("checksum"):
                self.logger.fatal("Component src %s has no checksum attribute" % orig_src)

        did_expand = False
        vcs_config = manifest["vcsconfig"]
        for vcsprefix in vcs_config.keys():
            expansion = vcs_config[vcsprefix]
            prefix = vcsprefix + ":"
            if orig_src.find(prefix) == 0:
                result["src"] = expansion + orig_src[len(prefix):]
                did_expand = True
                break

        if name is None:
            if did_expand:
                src = orig_src
                idx = src.rindex(":")
            else:
                src = result["src"]
                idx = src.rindex("/")
            name = src[idx+1:]

            i = name.rindex(".git")
            if i != -1 and i == len(name) - 4:
                name = name[:len(name)-4]
            name = name.replace("/", "-")
            result["name"] = name

        branch_or_tag = result.get("branch") or result.get("tag")
        if branch_or_tag is None:
            result["branch"] = "master"

        return result

    def _expand_component(self, component):
        meta = dict(component)
        patch_meta = self.data.get('patches')
        if patch_meta is not None:
            component_patch_files = component.get('patches', [])
            if len(component_patch_files) > 0:
                patches = dict(patch_meta)
                patches['files'] = component_patch_files
                meta['patches'] = patches
        config_opts = list(self.data.get('config-opts', []))
        config_opts.extend(component.get('config-opts', []))
        meta['config-opts'] = config_opts
        return meta

    def get_all_component_names(self):
        return self._names

    def get_component_map(self):
        return self._dict

    def get_component(self, name, allow_none=False):
        if not self._dict.get(name) and not allow_none:
            self.logger.fatal("No component '%s' in snapshot" % (name, ))
        return self._dict[name]

    def get_matching_src(self, src, allow_none=False):
        result = []
        for name in self._names:
            component = self.get_component(name)
            if component['src'] == src:
                result.append(component)
        return result

    def get_expanded(self, name):
        return self._expand_component(self.get_component(name))
