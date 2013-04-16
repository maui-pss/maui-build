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

import os, shutil, argparse

from .. import builtins
from .. import buildutil
from .. import fileutil
from .. import jsonutil
from .. import vcs
from ..subprocess_helpers import run_sync

class BuiltinCheckout(builtins.Builtin):
    name = "checkout"
    short_description = "Check out git repository"

    def __init__(self):
        builtins.Builtin.__init__(self)

    def execute(self, argv):
        self.parser.add_argument('--overwrite', action='store_true')
        self.parser.add_argument('--patches-path')
        self.parser.add_argument('--metadata-path')
        self.parser.add_argument('--workdir')
        self.parser.add_argument('--snapshot')
        self.parser.add_argument('--checkoutdir')
        self.parser.add_argument('--clean', action='store_true')
        self.parser.add_argument('component') 

        args = self.parser.parse_args(argv)

        component_name = args.component

        self._init_snapshot(args.workdir, args.snapshot)

        if component_name == '*':
            for name in self._snapshot.get_all_component_names():
                component = self.snapshot.get_expanded(name)
                self._checkout_one_component(component,
                                             checkoutdir=args.checkoutdir,
                                             clean=args.clean,
                                             patches_path=args.patches_path,
                                             overwrite=args.overwrite)
        else:
            if args.metadata_path is not None:
                component = jsonutil.load_json(args.metadata_path)
            else:
                component = self._snapshot.get_expanded(component_name)

            self._checkout_one_component(component,
                                         checkoutdir=args.checkoutdir,
                                         clean=args.clean,
                                         patches_path=args.patches_path,
                                         overwrite=args.overwrite)

        self._loop.quit()

    def _checkout_one_component(self, component, checkoutdir=None, clean=False, patches_path=None, overwrite=False):
        (keytype, uri) = vcs.parse_src_key(component['src'])

        is_local = (keytype == 'local')

        if is_local:
            if checkoutdir is not None:
                # Kind of a hack, but...
                if os.path.islink(checkoutdir):
                    os.unlink(checkoutdir)
                if overwrite and os.path.isdir(checkoutdir):
                    shutil.rmtree(checkoutdir)
                os.symlink(uri, checkoutdir)
            else:
                checkoutdir = uri
        else:
            if not checkoutdir:
                checkoutdir = os.path.join(os.getcwd(), component['name'])
                fileutil.ensure_parent_dir(checkoutdir)
            vcs.get_vcs_checkout(self.mirrordir, component, checkoutdir, overwrite=overwrite)

        if clean:
            if is_local:
                self.logger.info("note: ignoring --clean argument due to \"local:\" specification")
            else:
                vcs.clean(keytype, checkoutdir)

        if 'patches' in component:
            if patches_path is None:
                use_patchdir = vcs.checkout_patches(self.mirrordir,
                                                    self.patchdir,
                                                    component)
            else:
                use_patchdir = patches_path
            patches = buildutil.get_patch_paths_for_component(use_patchdir, component)
            for patch in patches:
                run_sync(['git', 'am', '--ignore-date', '-3', patch], cwd=checkoutdir)

        metadata_path = os.path.join(checkoutdir, '_ostbuild-meta.json')
        jsonutil.write_json_file_atomic(metadata_path, component)
 
        self.logger.info("Checked out %r at %s in %r" % (component["name"], component["revision"], checkoutdir))

builtins.register(BuiltinCheckout)
