# vim: et:ts=4:sw=4
# Copyright (C) 2012-2013 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
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

from .logger import Logger

_all_tasks = {}

def register(taskdef):
    _all_tasks[taskdef.name] = taskdef

def get_task(name, allow_none=False):
    logger = Logger()
    if name is None:
        logger.fatal("No task name given")
    taskdef = _all_tasks.get(name)
    if taskdef is not None:
        return taskdef
    if not allow_none:
        logger.fatal("No task definition matches %r" % (name, ))
    return None

def get_task_after(name):
    ret = []
    for task_name in _all_tasks:
        taskdef = _all_tasks[task_name]
        for after_name in taskdef.after:
            if after_name == name:
                ret.append(taskdef)
                break
    return ret

def get_all_tasks():
    return sorted(_all_tasks.itervalues(), lambda a, b: cmp(a.name, b.name))
