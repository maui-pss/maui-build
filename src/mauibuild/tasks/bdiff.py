# vim: et:ts=4:sw=4
# Copyright (C) 2013 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
# Copyright (C) 2013 Colin Walters <walters@verbum.org>
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

import os, re

from .. import taskset
from .. import snapshot
from .. import vcs
from ..task import TaskDef
from ..subprocess_helpers import run_sync, run_sync_get_output

class TaskBdiff(TaskDef):
    name = "bdiff"
    short_description = "Report differences between builds"
    after = ["build",]

    def __init__(self, builtin, taskmaster, name, argv):
        TaskDef.__init__(self, builtin, taskmaster, name, argv)

    def execute(self):
        self.subworkdir = os.getcwd()

        builddb = self._get_result_db("build")
        latest_path = builddb.get_latest_path()
        if not latest_path:
            self.logger.error("No builds!")
            return True
        latest_build_version = builddb.parse_version_str(os.path.basename(latest_path))

        previous_path = builddb.get_previous_path(latest_path)
        if not previous_path:
            self.logger.error("No build previous to %s" % latest_build_version)
            return True

        latest_build_data = builddb.load_from_path(latest_path)
        latest_build_snapshot = snapshot.Snapshot(latest_build_data["snapshot"], None)
        previous_build_data = builddb.load_from_path(previous_path)
        previous_build_snapshot = snapshot.Snapshot(previous_build_data["snapshot"], None)

        added = []
        modified = []
        removed = []

        result = {"from-build-version": builddb.parse_version_str(os.path.basename(previous_path)),
                  "to-build-version": builddb.parse_version_str(os.path.basename(latest_path)),
                  "from-src-version": builddb.parse_version_str(previous_build_data["snapshot-name"]),
                  "to-src-version": builddb.parse_version_str(latest_build_data["snapshot-name"]),
                  "added": added, "modified": modified, "removed": removed}

        modified_names = []

        latest_component_map = latest_build_snapshot.get_component_map()
        previous_component_map = previous_build_snapshot.get_component_map()
        for component_name in latest_component_map:
            component_a = latest_build_snapshot.get_component(component_name)
            component_b = previous_build_snapshot.get_component(component_name, True)

            if component_b is None:
                added.append(component_name)
            elif component_b.get("revision") != component_a.get("revision"):
                modified_names.append(component_name)
        for component_name in previous_component_map:
            component_a = latest_build_snapshot.get_component(component_name, True)

            if component_a is None:
                removed.append(component_name)

        for component_name in modified_names:
            latest_component = latest_build_snapshot.get_component(component_name)
            previous_component = previous_build_snapshot.get_component(component_name)
            latest_revision = latest_component.get("revision")
            previous_revision = previous_component.get("revision")
            mirrordir = vcs.ensure_vcs_mirror(self.mirrordir, previous_component)

            gitlog = self._git_log_to_json(mirrordir, previous_revision + "..." + latest_revision)
            diffstat = self._diffstat(mirrordir, previous_revision + "..." + latest_revision)
            modified.append({"previous": previous_component, "latest": latest_component,
                             "gitlog": gitlog, "diffstat": diffstat})

        bdiffdb = self._get_result_db("bdiff")
        bdiffdb.store(result)

    def _git_log_to_json(self, repo_dir, specification):
        log = run_sync_get_output(["git", "log", "--format=email", specification], cwd=repo_dir)
        if log is None or len(log) == 0:
            return []

        log_lines = log.split("\n")
        r = []
        current_item = None
        parsing_headers = False
        from_regex = re.compile(r'^From ([0-9a-f]{40}) ')
        for line in log_lines:
            match = from_regex.match(line)
            if match:
                if current_item is not None:
                    r.append(current_item)
                current_item = {"Checksum": match.group(1)}
                parsing_headers = True
            elif parsing_headers:
                if len(line) == 0:
                    parsing_headers = False
                else:
                    idx = line.find(":")
                    (k, v) = (line[:idx], line[idx+1:])
                    current_item[k] = v
        if current_item is not None:
            r.append(current_item)
        return r

    def _diffstat(self, repo_dir, specification):
        return run_sync_get_output(["git", "diff", "--stat", specification], cwd=repo_dir)

taskset.register(TaskBdiff)
