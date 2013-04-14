# vim: et:ts=4:sw=4
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

import os, shutil

from .logger import Logger

BUILD_ENV = {
    'HOME' : '/', 
    'HOSTNAME' : 'ostbuild',
    'LANG': 'C',
    'PATH' : '/usr/bin:/bin:/usr/sbin:/sbin',
    'SHELL' : '/bin/bash',
    'TERM' : 'vt100',
    'TMPDIR' : '/tmp',
    'TZ': 'EST5EDT'
    }

def get_patch_paths_for_component(patchdir, component):
    patches = component.get('patches')
    if not patches:
        return []
    patch_subdir = patches.get('subdir', None)
    if patch_subdir is not None:
        patchdir = os.path.join(patchdir, patch_subdir)
    else:
        patchdir = self.patchdir
    result = []
    for patch in patches['files']:
        result.append(os.path.join(patchdir, patch))
    return result

def find_user_chroot_path():
    # We need to search PATH here manually so we correctly pick up an
    # ostree install in e.g. ~/bin even though we're going to set PATH
    # below for our children inside the chroot.
    ostbuild_user_chroot_path = None
    for dirname in os.environ['PATH'].split(':'):
        path = os.path.join(dirname, 'linux-user-chroot')
        if os.access(path, os.X_OK):
            ostbuild_user_chroot_path = path
            break
    if ostbuild_user_chroot_path is None:
        ostbuild_user_chroot_path = 'linux-user-chroot'
    return ostbuild_user_chroot_path

def get_base_user_chroot_args():
    path = find_user_chroot_path()
    return [path, '--unshare-pid', '--unshare-ipc', '--unshare-net']

def compare_versions(a, b):
    adot = a.find(".")
    while adot != -1:
        bdot = b.find(".")
        if bdot == -1:
            return 1
        a_sub = int(a[:adot])
        b_sub = int(b[:bdot])
        if a_sub > b_sub:
            return 1
        elif a_sub < b_sub:
            return -1
        a = a[adot+1:]
        b = b[bdot+1:]
        adot = a.find(".")
    if b.find(".") != -1:
        return -1
    a_sub = int(a)
    b_sub = int(b)
    if a_sub > b_sub:
        return 1
    elif a_sub < b_sub:
        return -1
    return 0

def atomic_symlink_swap(link_path, new_target):
    parent = os.path.abspath(os.path.join(link_path, os.pardir))
    tmp_link_path = os.path.join(parent, "current-new.tmp")
    if os.path.isdir(tmp_link_path):
        shutil.rmtree(tmp_link_path)
    relpath = os.path.relpath(new_target, parent)
    os.symlink(relpath, tmp_link_path)
    os.rename(tmp_link_path, link_path)

def check_is_work_directory(path):
    logger = Logger()
    manifest_path = os.path.join(path, "manifest.json")
    if not os.path.exists(manifest_path):
        logger.fatal("No manifest.json found in %s" % path)
    dot_git_path = os.path.join(path, ".git")
    if os.path.exists(dot_git_path):
        logger.fatal(".git found in %s; are you in a ostbuild checkout?" % path)
