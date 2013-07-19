#!/usr/bin/python
# vim: et:ts=4:sw=4
#
# Copyright (C) 2012-2013 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
# Copyright (C) 2011 Colin Walters <walters@verbum.org>
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
from gi.repository import GLib, GObject

from . import builtins
from builtins import checkout
from builtins import git_mirror
from builtins import make
from builtins import qa_make_disk
from builtins import run_task

def usage(ecode):
    print "Builtins:"
    for builtin in builtins.get_all():
        print "    %s - %s" % (builtin.name, builtin.short_description)
    return ecode

def main(args):
    if len(args) < 1:
        return usage(1)
    elif args[0] in ('-h', '--help'):
        return usage(0)
    else:
        builtin = builtins.get(args[0])
        if builtin is None:
            print "error: Unknown builtin '%s'" % (args[0], )
            return usage(1)

        GObject.threads_init()

        loop = GObject.MainLoop()
        builtin._loop = loop

        status = 0

        try:
            def run_builtin():
                builtin.execute(args[1:])
            GLib.idle_add(run_builtin)

            loop.run()
        except KeyboardInterrupt:
            status = 1
            loop.quit()
        except Exception:
            import traceback
            status = 127
            traceback.print_exc()
            loop.quit()

        return status
