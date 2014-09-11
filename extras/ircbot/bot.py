#!/usr/bin/twistd -ny
# vim: et:ts=4:sw=4
#
# Copyright (c) 2013-2014 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
# Copyright (c) 2013 Jasper St. Pierre <jstpierre@mecheye.net>
# Copyright (c) 2012 Colin Walters <walters@verbum.org>
# Copyright (c) 2003-2004, Jeremiah Fincher
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
#

import itertools
import os
import json
import ConfigParser

from twisted.internet import protocol, task
from twisted.words.protocols import irc
from twisted.application import internet, service
from twisted.python import log

def mirc_color(code, S):
    return "\x03%d%s\x03" % (code, S)

GREEN = 3
RED = 4

# Default configuration
HOST = "irc.freenode.net"
PORT = 6667
TRACKED_BUILD = "master"
WORKDIR = "/srv/maui/mauibuild"
WORKURL = "http://build.maui-project.org/builds"
FLOOD_CHANNELS = ["#maui-build"]
STATUS_CHANNELS = ["#maui-project"]

# Configuration
config = ConfigParser.ConfigParser()
config_filename = os.path.expanduser("~/.config/mauibuild.cfg")
if os.path.exists(config_filename):
    config.read([config_filename])
    options = ("host", "port", "tracked_build", "workdir", "workurl",
               "flood_channels", "status_channels")
    for option in options:
        if config.has_option("ircbot", option):
            value = config.get("ircbot", option)
            if option in ("flood_channels", "status_channels"):
                value = value.split(" ")
            locals()[option.upper()] = value

# Actual bot
class BuildMauiProjectOrg(irc.IRCClient):
    nickname = "mauibuildbot"
    username = nickname
    realname = nickname

    def __init__(self):
        self._flood_channels = FLOOD_CHANNELS
        self._status_channels = STATUS_CHANNELS
        self._joined_channels = []
        self._last_task_versions = {}
        self._flood_tasks = ["resolve"]
        self._announce_changed_tasks = ["build"]
        self._workdir = os.path.expanduser("%s/%s/" % (WORKDIR, TRACKED_BUILD, ))
        self._workurl = "%s/%s" % (WORKURL, TRACKED_BUILD, )
        self._loop = task.LoopingCall(self._query_new_tasks)

        self._errors = []
        if not os.path.isdir(self._workdir):
            self._errors.append("Work directory \"%s\" is either missing or not a directory at all." % (self._workdir, ))

    def signedOn(self):
        for chan in self._flood_channels:
            self.join(chan)
        for chan in self._status_channels:
            self.join(chan)

        self._loop.start(1)

    def joined(self, channel):
        if channel not in self._joined_channels:
            self._joined_channels.append(channel)

    def _msg_unicode(self, channel, msg):
        self.msg(channel, msg.encode("utf8"))

    def _sendTo(self, channels, msg):
        for channel in channels:
            self._msg_unicode(channel, msg)

    def _query_new_tasks(self):
        if len(self._errors) > 0:
            return
        for taskname in self._flood_tasks:
            self._query_new_task(taskname, announce_always=True)
        for taskname in self._announce_changed_tasks:
            self._query_new_task(taskname, announce_always=False)

    def _get_task_metadata(self, taskname):
        current_task_path = os.path.join(self._workdir, "tasks/%s/current/" % (taskname, ))
        meta_path = os.path.join(current_task_path, "meta.json")
        try:
            f = open(meta_path)
            metadata = json.load(f)
            f.close()

            return metadata
        except Exception as e:
            print("Error occurred in _get_task_metadata(%s): %s" % (taskname, e.message))
            return None

    def _status_line_for_task(self, taskname):
        metadata = self._get_task_metadata(taskname)
        taskver = metadata["task-version"]
        millis = float(metadata["elapsed-millis"])
        success = metadata["success"]
        success_str = success and "successful" or "failed"

        msg = u"%s: %s in %.1f seconds. %s " \
              % (taskname, success_str, millis / 1000.0, metadata["errmsg"] or "")

        if success and taskname == "build":
            msg += "%s/publish/%s" % (self._workurl, taskver)
        elif not success:
            msg += "%s/tasks/%s/%s/%s/output.txt" % (self._workurl, taskname, success_str, taskver)

        if not success:
            msg = mirc_color(RED, msg)
        else:
            msg = mirc_color(GREEN, msg)

        return msg

    def _query_new_task(self, taskname, announce_always=False):
        metadata = self._get_task_metadata(taskname)
        if metadata is None:
            return None

        taskver = metadata["task-version"]

        last_version = self._last_task_versions.get(taskname)
        version_unchanged = taskver == last_version
        if version_unchanged:
            return

        self._last_task_versions[taskname] = taskver
        if not version_unchanged:
            msg = "New " + taskname
        else:
            msg = "Current " + taskname
        msg = self._status_line_for_task(taskname)

        if announce_always or not version_unchanged:
            self._sendTo(self._flood_channels, msg)
        if not version_unchanged:
            self._sendTo(self._status_channels, msg)

    def _buildstatus_for_task(self, taskname):
        metadata = self._get_task_metadata(taskname)
        if metadata is None:
            return "No current %s completed" % (taskname, )
        else:
            return self._status_line_for_task(taskname)

    def _print_help(self, channel):
        self._msg_unicode(channel, "Commands:")
        self._msg_unicode(channel, "  * help        - Prints the list of commands")
        self._msg_unicode(channel, "  * buildstatus - Last build status")

    def privmsg(self, user, channel, message):
        message = message.strip()
        if message == "@help":
            self._print_help(channel)
        elif message == "@buildstatus":
            if len(self._errors) > 0:
                self._msg_unicode(channel, "No information available, something bad has happened:")
                for error in self._errors:
                    self._msg_unicode(channel, "  * %s" % (error, ))
                self._msg_unicode(channel, "Please, fix the errors above!")
                return
            for taskname in itertools.chain(self._flood_tasks, self._announce_changed_tasks):
                status = self._buildstatus_for_task(taskname)
                self._msg_unicode(channel, status)
        elif message[:8] == "@promote":
            args = message[:9].split(" ")
            if len(args) != 2:
                self._msg_unicode(channel, mirc_color(RED, "Usage: @promote <task version> <release>"))
                self._msg_unicode(channel, mirc_color(RED, "Example: @promote 20140909.9 0.5.2"))
                return
            #mauibuild make -n promote --task-version args[0] --release args[1]

class BuildMauiProjectOrgFactory(protocol.ReconnectingClientFactory):
    protocol = BuildMauiProjectOrg

application = service.Application("mauibuild")
ircService = internet.TCPClient(HOST, int(PORT), BuildMauiProjectOrgFactory())
ircService.setServiceParent(application)
