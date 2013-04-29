# vim: et:ts=4:sw=4
# Copyright (C) 2012-2013 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
# Copyright (C) 2011-2013 Colin Walters <walters@verbum.org>
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

from .. import taskset
from .. import jsondb
from .. import jsonutil
from .. import vcs
from ..task import TaskDef
from ..snapshot import Snapshot
from ..subprocess_helpers import run_sync

class TaskResolve(TaskDef):
    name = "resolve"
    short_description = "Expand git revisions in source to exact targets"

    def __init__(self, builtin, taskmaster, name, argv):
        TaskDef.__init__(self, builtin, taskmaster, name, argv)

        self.subparser.add_argument('--fetch-base', action='store_true',
                                    help="git fetch base system")
        self.subparser.add_argument('--fetch-patches', action='store_true',
                                    help="git fetch patches")
        self.subparser.add_argument('--fetch-support', action='store_true',
                                    help="git fetch support stuff")
        self.subparser.add_argument('--fetch-all', action='store_true',
                                    help="git fetch patches, base system and all components")
        self.subparser.add_argument('--timeout-sec', default=10, metavar="SECONS",
                                    help="timeout")
        self.subparser.add_argument('components', nargs='*',
                                    help="list of component names to git fetch")

        self._db = None

    def execute(self):
        args = self.subparser.parse_args(self.argv)

        manifest_path = os.path.join(self.workdir, "manifest.json")
        data = jsonutil.load_json(manifest_path)
        self._snapshot = Snapshot(data, manifest_path, prepare_resolve=True)

        # Fetch everything if asked
        if args.fetch_all:
            args.fetch_base = True
            args.fetch_patches = True
            args.fetch_support = True

        # Can't fetch patches and support if not defined in manifest
        args.fetch_patches = args.fetch_patches and self._snapshot.data.has_key("patches")
        args.fetch_support = args.fetch_patches and self._snapshot.data.has_key("support")

        # Fetch base system
        if args.fetch_base:
            component = self._snapshot.data["base"]
            args.components.append(component["name"])

        # Fetch patches
        if args.fetch_patches:
            component = self._snapshot.data["patches"]
            args.components.append(component["name"])

        # Fetch support
        if args.fetch_support:
            component = self._snapshot.data["support"]
            args.components.append(component["name"])

        # Fetch components
        git_mirror_args = [sys.argv[0], "git-mirror", "--timeout-sec=" + str(args.timeout_sec),
                           "--workdir=" + self.workdir, "--manifest=" + manifest_path]
        if args.fetch_all or len(args.components) > 0:
            git_mirror_args.extend(["--fetch", "-k"])
            git_mirror_args.extend(args.components)
        run_sync(git_mirror_args)

        component_names = self._snapshot.get_all_component_names()
        for name in component_names:
            component = self._snapshot.get_component(name)
            branch_or_tag = component.get("branch") or component.get("tag")
            mirrordir = vcs.ensure_vcs_mirror(self.mirrordir, component)
            revision = vcs.describe_version(mirrordir, branch_or_tag)
            component["revision"] = revision

            if args.fetch_patches and self._snapshot.data["patches"]["name"] == name:
                vcs.checkout_patches(self.mirrordir, os.path.join(self.workdir, "patches"),
                                     component)

            if args.fetch_support and self._snapshot.data["support"]["name"] == name:
                vcs.checkout_support(self.mirrordir, os.path.join(self.workdir, "support"),
                                     component)

        (path, modified) = self._get_db().store(self._snapshot.data)
        if modified:
            self.logger.info("New source snapshot: %s" % path)
        else:
            self.logger.info("Source snapshot unchanged: %s" % path)

    def query_version(self):
        return self._get_db().get_latest_version()

    def _get_db(self):
        if self._db is None:
            snapshotdir = os.path.join(self.workdir, "snapshots")
            self._db = jsondb.JsonDB(snapshotdir)
        return self._db
        
taskset.register(TaskResolve)
