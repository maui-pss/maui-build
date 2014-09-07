# vim: et:ts=4:sw=4
# Copyright (C) 2012-2013 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
# Copyright (C) 2011-2012 Colin Walters <walters@verbum.org>
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

import os

from .. import builtins
from .. import vcs
from .. import jsonutil
from ..snapshot import Snapshot

class BuiltinGitMirror(builtins.Builtin):
    name = "git-mirror"
    short_description = "Update internal git mirror for one or more components"

    def __init__(self):
        builtins.Builtin.__init__(self)

    def execute(self, argv):
        self.parser.add_argument('--workdir')
        self.parser.add_argument('--manifest')
        self.parser.add_argument('--snapshot')
        self.parser.add_argument('--timeout-sec', type=int, default=0, metavar="SECONDS",
                                 help="Cache fetch results for provided number of seconds")
        self.parser.add_argument('--fetch', action='store_true',
                                 help="Also do a git fetch for components")
        self.parser.add_argument('-k', '--keep-going', action='store_true',
                                 help="Don't exit on fetch failures")

        args = self.parser.parse_args(argv)

        self._init_workdir(args.workdir)

        if args.manifest is not None:
            manifest_path = os.path.abspath(args.manifest)
            manifest_data = jsonutil.load_json(manifest_path)
            self._snapshot = Snapshot(manifest_data, manifest_path, prepare_resolve=True)
        else:
            self._init_snapshot(None, args.snapshot)

        kickstartermeta = self._snapshot.get_kickstarter_meta()

        if args.fetch:
            self.logger.info("Running git fetch for \"%s\"" % kickstartermeta["name"])
            vcs.fetch(self.mirrordir, kickstartermeta,
                      keep_going=args.keep_going,
                      timeout_sec=args.timeout_sec)
        else:
            vcs.ensure_vcs_mirror(self.mirrordir, kickstartermeta)

        self._loop.quit()

builtins.register(BuiltinGitMirror)
