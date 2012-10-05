# Copyright (C) 2012 Colin Walters <walters@verbum.org>
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

import os,sys,json
import argparse
import json

from . import builtins
from .ostbuildlog import log, fatal
from .subprocess_helpers import run_sync, run_sync_get_output

class OstbuildRepoWebJson(builtins.Builtin):
    name = "repoweb-json"
    short_description = "Dump tree status as JSON"

    def __init__(self):
        builtins.Builtin.__init__(self)

    def _snapshot_from_rev(self, rev):
        self.init_repo()
        text = run_sync_get_output(['ostree', '--repo=' + self.repo,
                                    'cat', rev, '/contents.json'],
                                   log_initiation=False)
        return json.loads(text)

    def execute(self, argv):
        parser = argparse.ArgumentParser(description=self.short_description)
        parser.add_argument('--prefix')
        parser.add_argument('--src-snapshot')
        parser.add_argument('output', help="Output filename")

        args = parser.parse_args(argv)
        self.parse_config()
        self.parse_snapshot(args.prefix, args.src_snapshot)

        output = {'00ostbuild-repoweb-json-version': 0}

        f = open('/proc/loadavg')
        loadavg = f.read().strip()
        f.close()
        output['load'] = loadavg

        targets_list = []
        for target_component_type in ['runtime', 'devel']:
            for architecture in self.snapshot['architectures']:
                name = 'trees/%s-%s-%s' % (self.snapshot['prefix'], architecture, target_component_type)
                targets_list.append(name)

        output['targets'] = {}
        for target in targets_list:
            target_data = {}
            output['targets'][target] = target_data
            target_data['revision'] = run_sync_get_output(['ostree', '--repo=' + self.repo, 'rev-parse', target])
            
        f = open(args.output, 'w')
        json.dump(output, f, indent=4, sort_keys=True)
        f.close()

        print "Wrote %r" % (args.output, )

builtins.register(OstbuildRepoWebJson)
