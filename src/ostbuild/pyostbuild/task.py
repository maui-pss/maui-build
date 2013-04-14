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

import os, sys, re, argparse, shutil, datetime, json
import __builtin__
from multiprocessing import cpu_count
from gi.repository import GLib, GObject

from . import buildutil
from . import jsondb
from . import jsonutil
from . import timeutil
from . import taskset
from .subprocess_helpers import run_async
from .logger import Logger

class TaskMaster(GObject.GObject):
    __gsignals__ = {
        "task_executing": (GObject.SIGNAL_RUN_FIRST, None,
                           (GObject.GObject,)),
        "task_complete": (GObject.SIGNAL_RUN_FIRST, None,
                          (GObject.GObject, bool, str,))
    }

    def __init__(self, builtin, path, on_empty=None, process_after=True, skip=[]):
        GObject.GObject.__init__(self)

        self.logger = Logger()
        self.builtin = builtin
        self.path = path
        self._process_after = process_after
        self._skip_tasks = {}
        for skip_task in skip:
            self._skip_tasks[skip_task] = True
        self.max_concurrent = cpu_count()
        self._on_empty = on_empty
        self._idle_recalculate_id = 0
        self._executing = []
        self._pending_tasks_list = []
        self._seen_tasks = {}
        self._task_errors = {}
        self._caught_error = False
        self._task_versions = {}

    def push_task(self, name, args):
        taskdef = taskset.get_task(name)
        self._push_task_def(taskdef, args)

    def is_task_queued(self, name):
        return self._is_task_pending(name) or self.is_task_executing(name)

    def is_task_executing(self, name):
        for executing_task in self._executing:
            if executing_task.name == name:
                return True
        return False

    def get_task_state(self):
        ret = []
        for task in self._pending_tasks_list:
            retval.append({"running": False, "task": task})
        for task in self._executing:
            retval.append({"running": True, "task": task})
        return ret

    def _push_task_def(self, taskdef, args):
        name = taskdef.name
        if not self._is_task_pending(name):
            instance = taskdef(self.builtin, self, name, args)
            instance.connect("complete", self._on_complete, instance)
            instance.prepare()
            self._pending_tasks_list.append(instance)
            self._queue_recalculate()

    def _is_task_pending(self, name):
        for pending in self._pending_tasks_list:
            if pending.name == name:
                return True
        return False

    def _queue_recalculate(self):
        if self._idle_recalculate_id > 0:
            return
        self._idle_recalculate_id = GObject.idle_add(self._recalculate)

    def _recalculate(self):
        self._idle_recalculate_id = 0

        if len(self._executing) == 0 and len(self._pending_tasks_list) == 0:
            self._on_empty(True, None)
            return
        elif len(self._pending_tasks_list) == 0:
            return

        not_executing = []
        executing = []
        for pending in self._pending_tasks_list:
            if self.is_task_executing(pending.name):
                executing.append(pending)
            else:
                not_executing.append(pending)

        self._pending_tasks_list = not_executing + executing
        self._reschedule()

    def _reschedule(self):
        while ((len(self._executing) < self.max_concurrent) and
                (len(self._pending_tasks_list) > 0) and
                not self.is_task_executing(self._pending_tasks_list[0].name)):
            task = self._pending_tasks_list.pop(0)
            version = task.query_version()
            if version is not None:
                self._task_versions[task.name] = version
            task._execute_in_subprocess_internal()
            self._executing.append(task)
            self.emit("task_executing", task)

    def _on_complete(self, success, error, *extra):
        task = extra[1]
        idx = -1
        for i in range(len(self._executing)):
            executing_task = self._executing[i]
            if executing_task != task:
                continue
            idx = i
            break
        if idx == -1:
            self.logger.fatal("TaskMaster: Internal error - Failed to find completed task %r" % task.name)
        self._executing.pop(idx)
        self.emit("task_complete", task, success, error)
        if success and self._process_after:
            changed = True
            version = task.query_version()
            if version is not None:
                old_version = self._task_versions[task.name]
                if old_version == version:
                    changed = False
                elif old_version is not None:
                    self.logger.info("task %s new version: %s" % (task.name, version))
            if changed:
                tasks_after = taskset.get_tasks_after(task.name)
                for after in tasks_after:
                    if not self._skip_tasks[after.name]:
                        self._push_task_def(after, {})
        self._queue_recalculate()

class TaskDef(GObject.GObject):
    __gsignals__ = {
        "complete": (GObject.SIGNAL_RUN_FIRST, None,
                     (bool, str,))
    }

    name = None
    short_description = None

    pattern = None
    after = []

    preserve_stdout = False
    retain_failed = 1
    retain_success = 5

    _VERSION_RE = re.compile(r'^(\d+\d\d\d\d)\.(\d+)$')

    def __init__(self, builtin, taskmaster, name, argv):
        GObject.GObject.__init__(self)

        self.builtin = builtin
        self.taskmaster = taskmaster
        self.name = name
        self.subparsers = builtin.parser.add_subparsers(title=self.name,
                                                        description=self.short_description)
        self.subparser = self.subparsers.add_parser(self.name, add_help=False)
        self.argv = argv
        self.logger = Logger()

    def get_depends(self):
        return []

    def query_versions(self):
        return None

    def prepare(self):
        if self.taskmaster is not None:
            self.workdir = os.path.realpath(os.path.join(self.taskmaster.path, os.pardir))
        else:
            self.workdir = os.environ["_OSTBUILD_WORKDIR"]

        buildutil.check_is_work_directory(self.workdir)

        self.resultdir = os.path.join(self.workdir, "results")
        if not os.path.isdir(self.resultdir):
            os.makedirs(self.resultdir)
        self.mirrordir = os.path.join(self.workdir, "src")
        if not os.path.isdir(self.mirrordir):
            os.makedirs(self.mirrordir)
        self.cachedir = os.path.join(self.workdir, "cache", "raw")
        if not os.path.isdir(self.cachedir):
            os.makedirs(self.cachedir)
        self.libdir = __builtin__.__dict__["LIBDIR"]
        self.repo = os.path.join(self.workdir, "repo")

    def execute(self):
        raise NotImplementedError("Not implemented")

    def _get_result_db(self, taskname):
        path = os.path.join(self.resultdir, taskname)
        return jsondb.JsonDB(path)

    def _load_versions_from(self, dirname):
        results = []
        for subpath, subdirs, files in os.walk(dirname):
            for subdir in subdirs:
                path = os.path.join(subpath, subdir)
                if not self._VERSION_RE.match(subdir):
                    continue
                if subdir not in results:
                    results.append(subdir)
        results.sort(cmp=buildutil.compare_versions)
        return results

    def _clean_old_versions(self, path, retain):
        versions = self._load_versions_from(path)
        while len(versions) > retain:
            subpath = os.path.join(path, versions.pop(0))
            if os.path.isdir(subpath):
                shutil.rmtree(subpath)

    def _load_all_versions(self):
        all_versions = []

        success_versions = self._load_versions_from(self._success_dir)
        for version in success_versions:
            all_versions.append((True, version))

        failed_versions = self._load_versions_from(self._failed_dir)
        for version in failed_versions:
            all_versions.append((False, version))

        def cmp(a, b):
            (success_a, version_a) = a
            (success_b, version_b) = b
            return buildutil.compare_versions(version_a, version_b)
        all_versions.sort(cmp=cmp)
        return all_versions

    def _execute_in_subprocess_internal(self):
        self._start_time_millis = int(timeutil.monotonic_time() * 1000)

        self.dir = os.path.join(self.taskmaster.path, self.name)
        if not os.path.isdir(self.dir):
            os.makedirs(self.dir)

        self._success_dir = os.path.join(self.dir, "successful")
        if not os.path.isdir(self._success_dir):
            os.makedirs(self._success_dir)
        self._failed_dir = os.path.join(self.dir, "failed")
        if not os.path.isdir(self._failed_dir):
            os.makedirs(self._failed_dir)

        all_versions = self._load_all_versions()

        current_time = datetime.datetime.utcnow()
        current_ymd = current_time.strftime("%Y%m%d")

        version = None
        if len(all_versions) > 0:
            (last_success, last_version) = all_versions[-1]
            m = self._VERSION_RE.match(last_version)
            if not m:
                raise Exception("Invalid version")
            last_ymd = m.group(1)
            last_serial = m.group(2)
            if last_ymd == last_serial:
                version = current_ymd + "." + str(int(last_serial) + 1)
        if version is None:
            version = current_ymd + ".0"

        self._version = version
        self._workdir = os.path.join(self.dir, version)
        if os.path.isdir(self._workdir):
            shutil.rmtree(self._workdir)
        if not os.path.isdir(self._workdir):
            os.makedirs(self._workdir)

        base_args = [sys.argv[0], "run-task", "--task-name", self.name]
        base_args.extend(self.argv)
        env_copy = os.environ.copy()
        env_copy["_OSTBUILD_WORKDIR"] = self.workdir
        if self.preserve_stdout:
            out_path = os.path.join(self._workdir, "output.txt")
            stdout = open(out_path, "w")
            stderr = stdout
        else:
            err_path = os.path.join(self._workdir, "errors.txt")
            stdout = open("/dev/null", "w")
            stderr = open(err_path, "w")
        proc = run_async(base_args, cwd=self._workdir, stdout=stdout,
                         stderr=stderr, env=env_copy)
        self.logger.debug("waiting for pid %d" % proc.pid)
        GLib.child_watch_add(proc.pid, self._on_child_exited)

    def _update_index(self):
        all_versions = self._load_all_versions()

        file_list = []
        for (successful, version) in all_versions:
            fname = ("successful/" if successful else "failed/") + version
            file_list.append(fname)

        index = {"files": file_list}
        jsonutil.write_json_file_atomic(os.path.join(self.dir, "index.json"), index)

    def _on_child_exited(self, pid, exitcode):
        success = (exitcode == 0)
        self.logger.debug("child %d exited with code %d" % (pid, exitcode))
        errmsg = None
        if not success:
            errmsg = "Child process exited with code %d" % exitcode

        elapsed_millis = int(timeutil.monotonic_time() * 1000) - self._start_time_millis
        meta = {"task-meta-version": 0, "task-version": self._version,
            "success": success, "errmsg": errmsg, "elapsed-millis": elapsed_millis}
        jsonutil.write_json_file_atomic(os.path.join(self._workdir, "meta.json"), meta)

        if success:
            target = os.path.join(self._success_dir, self._version)
            if os.path.exists(target):
                self.logger.fatal("%s already exists" % target)
            shutil.move(self._workdir, target)
            self._workdir = target
            self._clean_old_versions(self._success_dir, self.retain_success)
            self.emit("complete", success, None)
        else:
            target = os.path.join(self._failed_dir, self._version)
            if os.path.exists(target):
                self.logger.fatal("%s already exists" % target)
            shutil.move(self._workdir, target)
            self._workdir = target
            self._clean_old_versions(self._failed_dir, self.retain_failed)
            self.emit("complete", success, errmsg)

        # Also remove any old interrupted versions
        self._clean_old_versions(self.dir, 0)

        self._update_index()

        buildutil.atomic_symlink_swap(os.path.join(self.dir, "current"), target)
