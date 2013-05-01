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

import sys, os, argparse, shutil

from .. import fileutil
from .. import taskset
from ..tasks import TaskZDisks
from ..subprocess_helpers import run_sync

class TaskZDisks(TaskBuildDisks):
    name = "zdisks"
    short_description = "Compress disk images"
    after = ["builddisks",]
    schedule_min_secs = 60*60

    _image_subdir = os.path.join("images", "z")
    _inherit_previous_disk = False
    _only_tree_suffixes = ["-runtime", "-devel"]

    def __init__(self, builtin, taskmaster, name, argv):
        TaskBuildDisks.__init__(self, builtin, taskmaster, name, argv)

    def _post_disk_creation(self, diskpath):
        parent = os.path.abspath(os.path.join(diskpath, os.pardir))
        out_path = os.path.join(parent, os.path.basename(diskpath) + ".gz")
        in_stream = open(diskpath, "rb")
        out_stream = gzip.open(out_path, "wb")
        out_stream.write(in_stream.read())
        in_stream.close()
        out_stream.close()
        os.unlink(diskpath)

taskset.register(TaskZDisks)
