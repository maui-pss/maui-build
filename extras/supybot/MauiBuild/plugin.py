###
# Copyright (c) 2003-2004, Jeremiah Fincher
# Copyright (c) 2012 Colin Walters <walters@verbum.org>
# Copyright (c) 2013 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###

import time
import os
import re
import shutil
import tempfile
import json

import supybot.ircdb as ircdb
import supybot.ircmsgs as ircmsgs
import supybot.ircutils as ircutils
import supybot.conf as conf
import supybot.utils as utils
from supybot.commands import *
import supybot.schedule as schedule
import supybot.callbacks as callbacks
import supybot.world as world

class MauiBuild(callbacks.Plugin):
    def __init__(self, irc):
        self.__parent = super(MauiBuild, self)
        self.__parent.__init__(irc)
        schedule.addPeriodicEvent(self._query_new_tasks, 1, now=False)
        self._irc = irc
        self._last_task_versions = {}
        self._jsondb_re = re.compile(r'^(\d+\.\d+)-([0-9a-f]+)\.json$')
        tracked_build = "buildmaster"
        self._workdir = os.path.expanduser("/srv/mauibuild/%s/" % tracked_build)
        self._workurl = "http://build.maui-project.org/%s/" % tracked_build

    def _broadcast(self, msg):
        for channel in self._irc.state.channels:
            self._irc.queueMsg(ircmsgs.privmsg(channel, msg))

    def _query_new_tasks(self, status=False):
        for taskname in ["build", "smoketest", "integrationtest"]:
            self._query_new_task(taskname, status=status)

    def _query_new_task(self, taskname, status=False):
        current_task_path = os.path.join(self._workdir, "tasks/" + taskname + "/current")
        meta_path = os.path.join(current_task_path, "meta.json")
        if not os.path.exists(meta_path):
            if status:
                self._broadcast("No current %s completed" % taskname)
            return

        f = open(meta_path)
        metadata = json.load(f)
        f.close()
 
        taskver = metadata["task-version"]

        last_version = self._last_task_versions.get(taskname)
        version_unchanged = taskver == last_version
        if (not status and version_unchanged):
            return

        self._last_task_versions[taskname] = taskver
        if (not status and not version_unchanged):
            msg = "New " + taskname
        else:
            msg = "Current " + taskname
        success = metadata["success"]
        success_str = success and "successful" or "failed"
        millis = int(metadata['elapsed-millis'])
        msg += " %s: %s in %.1f seconds. " % (taskver, success_str, millis / 1000)
        msg += self._workurl + "tasks/" + taskname + "/%s/%s/output.txt" % (success_str, taskver)

        if not success:
            msg = ircutils.mircColor(msg, fg="red")
        else:
            msg = ircutils.mircColor(msg, fg="green")

        self._broadcast(msg)

    def buildstatus(self, irc, msg, args):
        self._query_new_tasks(status=True)

Class = MauiBuild
