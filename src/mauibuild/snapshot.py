# vim: et:ts=4:sw=4
# Copyright (C) 2012-2014 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
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

def snapshot_diff(a, b):
    a_targets = _target_dict(a)
    b_targets = _target_dict(b)

    added = []
    modified = []
    removed = []

    for name in a_targets:
        c_a = a_targets[name]
        c_b = b_targets.get(name)
        if c_b is None:
            removed.append(name)
        elif c_a["revision"] != c_b["revision"]:
            modified.append(name)
    for name in b_targets:
        if name not in a_targets:
            added.append(name)
    return (added, modified, removed)
 
class Snapshot(object):
    def __init__(self, data, path, prepare_resolve=False):
        self.logger = Logger()
        self.data = data
        self.path = path
        if prepare_resolve:
            kickstarter = self._resolve_kickstarter(data, data["kickstarter"])
            targets = {}
            for target in data.get("targets"):
                if not target.get("disabled", False):
                    targets[target["name"]] = target
            self.data["kickstarter"] = kickstarter
            self.data["targets"] = targets
        self._names = self.data["targets"].keys()

    def _resolve_kickstarter(self, manifest, kickstartermeta):
        result = dict(kickstartermeta)
        orig_src = kickstartermeta["src"]
        name = kickstartermeta.get("name")

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

    def get_kickstarter_meta(self):
        return self.data["kickstarter"]

    def get_all_target_names(self):
        return self._names

    def get_target(self, name, allow_none=False):
        if not self.data["targets"].get(name):
            if allow_none:
                return None
            self.logger.fatal("No target '%s' in snapshot" % (name, ))
        return self.data["targets"][name]
