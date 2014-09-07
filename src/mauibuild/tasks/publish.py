# vim: et:ts=4:sw=4
# Copyright (C) 2012-2014 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
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

import os, shutil

from .. import taskset
from .. import jsondb
from .. import jsonutil
from ..task import TaskDef
from ..snapshot import Snapshot
from ..subprocess_helpers import run_sync_get_output

class TaskBuild(TaskDef):
    name = "publish"
    short_description = "Publish target images"
    after = ["build",]

    def __init__(self, builtin, taskmaster, name, argv):
        TaskDef.__init__(self, builtin, taskmaster, name, argv)

    def execute(self):
        args = self.subparser.parse_args(self.argv)

        self.subworkdir = os.getcwd()

        build_tasks_dir = os.path.join(self.workdir, "tasks", "build")
        indexmeta = jsonutil.load_json(os.path.join(build_tasks_dir, "index.json"))

        # Go through all the tasks and process only the successful
        # and unpublished ones
        for taskdir in indexmeta["files"]:
            curtaskdir = os.path.join(build_tasks_dir, taskdir)
            taskmeta = jsonutil.load_json(os.path.join(curtaskdir, "meta.json"))
            if not taskmeta["success"] or taskmeta["published"]:
                continue

            srcdb = jsondb.JsonDB(curtaskdir)
            snapshot_path = srcdb.get_latest_path()
            if snapshot_path is None:
                self.logger.fatal("No snapshot found, did you run the resolve task?")
            data = srcdb.load_from_path(snapshot_path)
            self._snapshot = Snapshot(data, snapshot_path)

            # Copy all files built for this target
            for name in self._snapshot.get_all_target_names():
                builddir = os.path.join(curtaskdir, "build-%s" % name)
                if not os.path.isdir(builddir):
                    continue
                for filename in os.listdir(builddir):
                    srcfilename = os.path.join(builddir, filename)
                    destdir = os.path.join(self.publishdir, taskmeta["task-version"])
                    if os.path.exists(destdir):
                        if not os.path.isdir(destdir):
                            self.logger.fatal("Destination directory \"%s\" already exists" % destdir)
                    else:
                        os.makedirs(destdir)
                    shutil.move(srcfilename, destdir)

                    # Create checksums for some files
                    valid_exts = (".tar", ".gz", ".bz2", ".xz", ".iso", ".raw", ".img")
                    name, ext = os.path.splitext(os.path.basename(srcfilename))
                    md5sum = run_sync_get_output(["md5sum", filename], cwd=destdir)
                    sha256sum = run_sync_get_output(["sha256sum", filename], cwd=destdir)
                    self._write_file(os.path.join(destdir, filename) + ".md5", md5sum)
                    self._write_file(os.path.join(destdir, filename) + ".sha256", sha256sum)

            # Set this task as published
            taskmeta["published"] = True
            jsonutil.write_json_file_atomic(os.path.join(curtaskdir, "meta.json"), taskmeta)

    def _write_file(self, filename, text):
        f = open(filename, "w")
        f.write(text)
        f.close()

taskset.register(TaskBuild)
