# vim: et:ts=4:sw=4
# Copyright (C) 2013-2014 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
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

import sys, argparse

from .. import builtins
from .. import taskset
from ..tasks import build
from ..tasks import resolve

class BuiltinRunTask(builtins.Builtin):
    name = "run-task"
    short_description = "Internal helper to execute a task"

    def __init__(self):
        builtins.Builtin.__init__(self)

    def execute(self, argv):
        self.parser.add_argument("-l", "--list", action="store_true",
                                 help="list all available tasks and exit")
        self.parser.add_argument("-n", "--task-name", metavar="NAME",
                                 help="task name")
        self.parser.add_argument("-v", "--verbose", action="count", default=0,
                                 help="increase output verbosity")
        self.parser.add_argument("--task-help", action="store_true",
                                 help="show help message for the specified task and exit")
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

        task_def = taskset.get_task(args.task_name)
        instance = task_def(self, None, args.task_name, args.parameters)
        instance.verbose = args.verbose
        if args.task_help:
            instance.subparser.print_help()
            self._loop.quit()
            return
        try:
            instance.prepare()
            instance.execute()
        except Exception:
            import traceback
            traceback.print_exc()
            sys.exit(127)

        self._loop.quit()
 
builtins.register(BuiltinRunTask)
