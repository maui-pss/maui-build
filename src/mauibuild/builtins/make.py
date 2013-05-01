# vim: et:ts=4:sw=4
# Copyright (C) 2013 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
# Copyright (C) 2012-2013 Colin Walters <walters@verbum.org>
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

import os, sys, argparse

from .. import builtins
from .. import taskset
from ..task import TaskMaster
from ..tasks import bdiff
from ..tasks import builddisks
from ..tasks import buildlive
from ..tasks import build
from ..tasks import resolve
from ..tasks import zdisks
from ..logger import Logger
from ..subprocess_helpers import run_sync

class BuiltinMake(builtins.Builtin):
    name = "make"
    short_description = "Execute tasks"

    def __init__(self):
        builtins.Builtin.__init__(self)

    def execute(self, argv):
        self.parser.add_argument("-l", "--list", action="store_true",
                                 help="list all available tasks and exit")
        self.parser.add_argument("-n", "--task-name", metavar="NAME",
                                 help="task name")
        self.parser.add_argument("--task-help", action="store_true",
                                 help="show help message for the specified task and exit")
        self.parser.add_argument("-u", "--only", action="store_true",
                                 help="don't process tasks after this")
        self.parser.add_argument("-x", "--skip", action="append", metavar="NAME", default=[],
                                 help="skip this task")
        self.parser.add_argument("-", dest="__dummy", action="store_true",
                                 help=argparse.SUPPRESS),
        self.parser.add_argument("parameters", nargs=argparse.REMAINDER,
                                 help="parameters that will be passed to the task")

        args = self.parser.parse_args(argv)

        if args.list:
            print "Tasks:"
            for task in taskset.get_all_tasks():
                print "    %s - %s" % (task.name, task.short_description)
            self._loop.quit()
            return

        if len(args.parameters) > 1:
            sep = args.parameters.pop(0)
            if sep != "--":
                self.logger.fatal("Wrong arguments separator %r" % sep)

        if args.task_help:
            task_def = taskset.get_task(args.task_name)
            instance = task_def(self, None, args.task_name, args.parameters)
            instance.subparser.print_help()
            self._loop.quit()
            return

        self._init_workdir(None)
        self._failed = False
        self._one_only = args.only

        self._task_master = TaskMaster(self,
                                       os.path.join(self.workdir, "tasks"),
                                       process_after=(not args.only),
                                       on_empty=self._on_tasks_complete,
                                       skip=args.skip)
        self._task_master.connect("task_executing", self._on_task_executing)
        self._task_master.connect("task_complete", self._on_task_completed)

        self._task_master.push_task(args.task_name, args.parameters)

    def _on_task_executing(self, taskmaster, task):
        self.logger.info("Task %s executing in %s" % (task.name, task._workdir))
        self._output_path = os.path.join(task._workdir, "output.txt")

    def _on_task_completed(self, taskmaster, task, success, error):
        self._output_path = os.path.join(task._workdir, "output.txt")
        if self._one_only:
            run_sync(["tail", self._output_path])
        if success:
            self.logger.info("Task %s complete: %s" % (task.name, task._workdir))
        else:
            self._failed = True
            self.logger.info("Task %s failed: %s" % (task.name, task._workdir))

    def _on_tasks_complete(self, success, err):
        if not success:
            self._err = err
        self._loop.quit()

builtins.register(BuiltinMake)
