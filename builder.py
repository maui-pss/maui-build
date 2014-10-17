#!/usr/bin/python2
# vim: et:ts=4:sw=4
#
# Maui Build
# Copyright (C) 2014 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#

import os
import sys
import json
import shutil
import datetime

from builderlib.subprocess_helpers import *
from builderlib.fileutil import ensure_parent_dir

def chown(path):
    s = "%d:%d" % (os.getuid(), os.getgid())
    run_sync(["sudo", "chown", "-R", s, path])

def readconf():
    script_dir = os.path.realpath(os.path.dirname(sys.argv[0]))
    manifest_filename = os.path.join(script_dir, "maui-build.json")
    if not os.path.exists(manifest_filename):
        print >> sys.stderr, "Please provide \"maui-build.json\" manifest!"
        sys.exit(1)

    data = None
    with open(manifest_filename, "r") as f:
        data = json.loads(f.read())
        f.close()

    return data

def resolve(sources_dir):
    # Update git sources
    if os.path.isdir(sources_dir):
        run_sync(["git", "pull"], cwd=sources_dir)

def copy_sources(sources_dir, build_dir):
    # Copy sources to a location where we can build in peace
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    new_sources_dir = os.path.join(build_dir, "builds", timestamp)
    shutil.copytree(sources_dir, new_sources_dir)
    return new_sources_dir

def build(targets, sdk_cmd, sources_dir, build_dir):
    # Save build information
    info = []

    # Build targets
    for target in targets:
        # Skip disabled targets
        if target.get("disabled", False):
            continue

        # Create kickstart files
        config_filename = os.path.join(sources_dir, target["config"])
        cmd = [sdk_cmd, "cd", "/parentroot" + sources_dir, ";",
               "maui-kickstarter", "-e", ".", "-c", target["config"]]
        run_sync(cmd)

        # Create packages empty cache
        cache_dir = os.path.join(build_dir, "cache", target["cache"])
        if not os.path.isdir(cache_dir):
            ensure_parent_dir(cache_dir)

        # Run build
        cmd = [sdk_cmd, "cd", "/parentroot" + sources_dir, ";",
               "sudo", "mic", "create", "auto", target["name"] + ".ks",
               "-k", "/parentroot" + cache_dir]
        run_sync(cmd)

        # Rectify owner after using sudo
        chown(sources_dir)

        # Append build information
        path = os.path.join(sources_dir, target["name"])
        info.append({"name": target["name"], "path": path})

    return info

def main():
    # Read configuration and take a dictionary
    data = readconf()
    if not data:
        print >> sys.stderr, "No valid configuration found"
        sys.exit(1)

    # Paths
    sources_dir = os.path.expanduser(data["paths"]["sources"])
    build_dir = os.path.expanduser(data["paths"]["buildroot"])
    publish_dir = os.path.expanduser(data["paths"]["publish"])

    # Update sources and make a working copy
    resolve(sources_dir)
    new_sources_dir = copy_sources(sources_dir, build_dir)

    # Build targets
    builds = build(data["targets"], data["sdk"]["chroot"], new_sources_dir, build_dir)

    # Publish targets
    for b in builds:
        timestamp = datetime.datetime.now().strftime("%Y%m%d")
        dest_dir = os.path.join(publish_dir, timestamp, b["name"])
        ensure_parent_dir(dest_dir)
        shutil.move(b["path"], dest_dir)

    # Remove sources directory (it's a copy, don't worry)
    shutil.rmtree(new_sources_dir)

if __name__ == "__main__":
    main()
