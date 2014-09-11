# vim: et:ts=4:sw=4
# Copyright (C) 2014 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
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
from ..task import TaskDef

class TaskPromote(TaskDef):
    name = "promote"
    short_description = "Promote a build to release"

    def __init__(self, builtin, taskmaster, name, argv):
        TaskDef.__init__(self, builtin, taskmaster, name, argv)

        self.subparser.add_argument("--task-version", metavar="VERSION",
                                    help="which task version is to promote")
        self.subparser.add_argument("--release", metavar="RELEASE",
                                    help="release number to promote to")

    def execute(self):
        args = self.subparser.parse_args(self.argv)

        self.subworkdir = os.getcwd()

        self.logger.info("Promoting from %s to %s" % (task_version, release)

        srcdir = os.path.join(self.publishdir, task_version)
        if not os.path.isdir(srcdir):
            self.logger.fatal("Path \"%s\" is not a directory or it doesn't exist" % srcdir)

        destdir = os.path.join(self.releasedir, release)
        if os.path.exists(destdir):
            self.logger.fatal("Destination directory \"%s\" already exists" % destdir)

        shutil.copytree(srcdir, destdir)

taskset.register(TaskPromote)
