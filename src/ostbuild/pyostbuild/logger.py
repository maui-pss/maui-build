# vim: et:ts=4:sw=4
#
# Copyright (C) 2013 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
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

import os, sys, logging

try:
    from termcolor import colored
except ImportError:
    def colored(message, *args, **kwargs):
        return message

class Logger(object):
    def __init__(self):
        # Setup the logger
        logging.basicConfig(format="%(asctime)s %(name)s: %(prefix)s%(message)s",
                            datefmt="%c")
        self._logger = logging.getLogger(os.path.basename(sys.argv[0]))
        self._logger.setLevel(logging.DEBUG)

        # Add custom level for action
        logging.ACTION = logging.INFO + 1
        logging.addLevelName(logging.ACTION, "ACTION")
        def action(self, message, *args, **kwargs):
            self._log(logging.ACTION, message, args, **kwargs)
        logging.Logger.action = action
 
        # Add custom level for fatal
        logging.FATAL = 100
        logging.addLevelName(logging.FATAL, "FATAL")
        def fatal(self, message, *args, **kwargs):
            self._log(logging.FATAL, message, args, **kwargs)
            sys.exit(1)
        logging.Logger.fatal = fatal

        # Color dictionary
        self._colormap = dict(
            info = dict(color="cyan"),
            action = dict(color="cyan", attrs=["bold"]),
            warn = dict(color="yellow", attrs=["bold"]),
            warning = dict(color="yellow", attrs=["bold"]),
            error = dict(color="red"),
            critical = dict(color="red", attrs=["bold"]),
            fatal = dict(color="red", attrs=["bold"])
        )

    def __getattr__(self, name):
        if name in ("debug", "info", "action", "warn", "warning", "error", "critical", "fatal"):
            extra = {"prefix": ""}
            if name in ("warn", "warning"):
                extra["prefix"] = "WARNING: "
            elif name == "error":
                extra["prefix"] = "ERROR: "
            elif name == "critical":
                extra["prefix"] = "CRITICAL: "
            elif name == "fatal":
                extra["prefix"] = "FATAL: "
            return lambda s, *args: getattr(self._logger, name)(
                colored(s, **self._colormap[name]) if name != "debug" else s, *args, extra=extra)
        return getattr(self._logger, name)
