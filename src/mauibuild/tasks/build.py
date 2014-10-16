# vim: et:ts=4:sw=4
# Copyright (C) 2012-2014 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
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

import os, shutil

from .. import taskset
from .. import jsondb
from .. import fileutil
from .. import vcs
from ..task import TaskDef
from ..snapshot import Snapshot
from ..subprocess_helpers import run_sync, run_sync_get_output

class TaskBuild(TaskDef):
    name = "build"
    short_description = "Build target images"
    after = ["resolve",]

    def __init__(self, builtin, taskmaster, name, argv):
        TaskDef.__init__(self, builtin, taskmaster, name, argv)

    def execute(self):
        args = self.subparser.parse_args(self.argv)

        self.subworkdir = os.getcwd()

        snapshot_dir = os.path.join(self.workdir, "snapshots")
        srcdb = jsondb.JsonDB(snapshot_dir)
        snapshot_path = srcdb.get_latest_path()
        if snapshot_path is None:
            self.logger.fatal("No snapshot found, did you run the resolve task?")
        working_snapshot_path = os.path.join(self.subworkdir, os.path.basename(snapshot_path))
        fileutil.file_linkcopy(snapshot_path, working_snapshot_path, overwrite=True)
        data = srcdb.load_from_path(working_snapshot_path)
        self._snapshot = Snapshot(data, working_snapshot_path)

        builddb = self._get_result_db("build")

        target_source_version = builddb.parse_version_str(os.path.basename(self._snapshot.path))

        self.logger.info("Building " + target_source_version)

        # Build targets
        target_names = self._snapshot.data["targets"].keys()
        if len(target_names) == 0:
            self.logger.fatal("No targets to build")
        for target in target_names:
            self._build(self._snapshot.get_target(target))

        build_data = {"snapshot": self._snapshot.data,
                      "snapshot-name": os.path.basename(self._snapshot.path)}

        (path, modified) = builddb.store(build_data)
        self.logger.info("Build complete: " + path)

    def _build(self, targetmeta):
        """Build the target image."""
        kickstartermeta = self._snapshot.data["kickstarter"]
        sdkmeta = self._snapshot.data["sdk"]

        build_workdir = os.path.join(self.subworkdir, targetmeta["name"])
        checkoutdir = os.path.join(self.subworkdir, kickstartermeta["name"])

        if targetmeta.get("cache"):
            cachedir = os.path.join(self.cachedir, targetmeta["cache"])
        else:
            cachedir = os.path.join(self.cachedir, targetmeta["name"])

        fileutil.ensure_parent_dir(checkoutdir)

        (keytype, uri) = vcs.parse_src_key(kickstartermeta["src"])
        if keytype == "local":
            if os.path.exists(checkoutdir):
                shutil.rmtree(checkoutdir)
            os.symlink(uri, checkoutdir)
        else:
            vcs.get_vcs_checkout(self.mirrordir, kickstartermeta, checkoutdir, overwrite=False)

        # Create kickstart files
        cmd = [sdkmeta["chroot"], "cd", "/parentroot/" + checkoutdir, ";",
               "maui-kickstarter", "-e", ".",
               "-c", targetmeta["config"]]
        run_sync(cmd)

        # Run build
        cmd = [sdkmeta["chroot"], "cd", "/parentroot/" + checkoutdir, ";",
               "sudo", "mic", "create", "auto", targetmeta["name"] + ".ks",
               "-k", "/parentroot/" + cachedir]
        run_sync(cmd)

        if keytype == "local":
            os.unlink(checkoutdir)
        else:
            shutil.rmtree(checkoutdir)

        self._publish(build_workdir, targetmeta["name"])

    def _publish(self, build_workdir, target_name):
        version = os.environ["_MAUIBUILD_TASK_VERSION"]
        destdir = os.path.join(self.publishdir, version, target_name)
        if os.path.exists(destdir):
            if not os.path.isdir(destdir):
                self.logger.fatal("Destination directory \"%s\" already exists" % destdir)
        else:
            os.makedirs(destdir)

        for filename in os.listdir(build_workdir):
            srcfilename = os.path.join(build_workdir, filename)
            dstfilename = os.path.join(destdir, filename)

            try:
                # Get name and extention
                name, ext = os.path.splitext(os.path.basename(srcfilename))

                # Move to the publish directory
                if not (ext == ".ks" and name != target_name):
                    shutil.move(srcfilename, destdir)

                # Create checksums for some files
                valid_exts = (".tar", ".gz", ".bz2", ".xz", ".iso", ".raw", ".img")
                if ext in valid_exts:
                    if not os.path.exists(dstfilename + ".md5"):
                        md5sum = run_sync_get_output(["md5sum", filename], cwd=destdir)
                        self._write_file(dstfilename + ".md5", md5sum)
                    if not os.path.exists(dstfilename + ".sha256"):
                        sha256sum = run_sync_get_output(["sha256sum", filename], cwd=destdir)
                        self._write_file(dstfilename + ".sha256", sha256sum)
            except Exception, e:
                self.logger.fatal(unicode(e))

    def _write_file(self, filename, text):
        f = open(filename, "w")
        f.write(text)
        f.close()

taskset.register(TaskBuild)
