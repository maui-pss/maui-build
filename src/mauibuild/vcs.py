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

import os, re, urlparse, shutil, datetime, hashlib

from .subprocess_helpers import run_sync_get_output, run_sync
from . import buildutil
from .logger import Logger

def get_mirrordir(mirrordir, keytype, uri, prefix=''):
    colon = uri.find("://")
    if colon >= 0:
        scheme = uri[0:colon]
        rest = uri[colon+3:]
    else:
        scheme = 'file'
        if os.path.exists(uri):
            rest = uri[1:]
        else:
            rest = uri
    if prefix: prefix += '/'
    return os.path.join(mirrordir, prefix, keytype, scheme, rest)

def _process_submodules(cwd):
    if not os.path.exists(os.path.join(cwd, ".gitmodules")):
        return {}
    submodules = {}
    output = run_sync_get_output(["git", "config", "-f", ".gitmodules", "--list"], cwd=cwd)
    lines = output.split("\n")
    for line in lines:
        m = re.match(r'^submodule\.(.*)\.(path|url)=(.*)$', line)
        if m:
            (name, key, value) = m.groups()
            if not submodules.has_key(name):
                submodules[name] = {}
            submodules[name].update({key: value})
            if key == "path":
                status_line = run_sync_get_output(["git", "submodule", "status", value], cwd=cwd).strip()
                status_line = status_line[1:]
                (checksum, path) = status_line.split(" ", 2)[:2]
                submodules[name]["checksum"] = checksum
    return submodules

def _process_checkout_submodules(mirrordir, parent_uri, cwd):
    logger = Logger()
    submodules = _process_submodules(cwd)
    have_submodules = len(submodules.keys()) > 0
    for name in submodules.keys():
        submodule = submodules[name]
        logger.info("Processing submodule \"%s\" (%s)" % (name, submodule["url"]))
        sub_url = submodule["url"]
        if sub_url.find("../") == 0:
            sub_url = _make_absolute_url(parent_uri, sub_url)
        local_mirror = get_mirrordir(mirrordir, "git", sub_url)
        run_sync(['git', 'config', 'submodule.%s.url' % name, 'file://' + local_mirror], cwd=cwd)
        run_sync(['git', 'submodule', 'update', '--init', name], cwd=cwd)
        _process_checkout_submodules(mirrordir, sub_url, os.path.join(cwd, name))

def get_vcs_checkout(mirrordir, component, dest, overwrite=True, quiet=False):
    logger = Logger()
    (keytype, uri) = parse_src_key(component["src"])
    if keytype in ("git", "local"):
        if not component.get("revision"):
            logger.fatal("Component \"%s\" does not have revision key" % component["name"])
        revision = component["revision"]
        module_mirror = get_mirrordir(mirrordir, keytype, uri)
        add_upstream = True
    elif keytype == "tarball":
        if not component.get("checksum"):
            logger.fatal("Tarball components must have the checksum key, "
                         "please check the \"%s\" component" % component["name"])
        revision = "tarball-import-" + component["checksum"]
        module_mirror = get_mirrordir(mirrordir, "tarball", component["name"])
        add_upstream = False
    else:
        logger.fatal("Unsupported %r SRC uri" % keytype)

    checkoutdir_parent = os.path.dirname(dest)
    if not os.path.isdir(checkoutdir_parent):
        os.makedirs(checkoutdir_parent)
    tmp_dest = dest + ".tmp"
    if os.path.isdir(tmp_dest):
        shutil.rmtree(tmp_dest)
    if os.path.islink(dest):
        os.unlink(dest)
    if os.path.isdir(dest):
        if overwrite and os.path.isdir(dest):
            shutil.rmtree(dest)
        else:
            tmp_dest = dest
    if not os.path.isdir(tmp_dest):
        run_sync(['git', 'clone', '-q', '--origin', 'localmirror',
                  '--no-checkout', module_mirror, tmp_dest],
                 log_initiation=(not quiet),
                 log_success=(not quiet))
        if add_upstream:
            run_sync(['git', 'remote', 'add', 'upstream', uri], cwd=tmp_dest,
                     log_initiation=(not quiet),
                     log_success=(not quiet))
    else:
        run_sync(['git', 'fetch', 'localmirror'], cwd=tmp_dest,
                 log_initiation=(not quiet),
                 log_success=(not quiet))
    run_sync(['git', 'checkout', '-q', revision], cwd=tmp_dest,
             log_initiation=(not quiet),
             log_success=(not quiet))
    _process_checkout_submodules(mirrordir, uri, tmp_dest)
    if tmp_dest != dest:
        os.rename(tmp_dest, dest)
    return dest

def clean(keytype, checkoutdir):
    run_sync(['git', 'clean', '-d', '-f', '-x'], cwd=checkoutdir)

def parse_src_key(srckey):
    idx = srckey.find(':')
    if idx < 0:
        raise ValueError("Invalid SRC uri=%s" % (srckey, ))
    keytype = srckey[:idx]
    if keytype not in ("git", "local", "tarball"):
        raise ValueError("Unsupported SRC uri=%s" % (srckey, ))
    uri = srckey[idx+1:]
    return (keytype, uri)
 
def checkout_patches(mirrordir, patchdir, patches):
    (patches_keytype, patches_uri) = parse_src_key(patches['src'])
    if patches_keytype == 'local':
        return patches_uri
    elif patches_keytype != 'git':
        raise Exception("Unhandled keytype %s" % patches_keytype)

    patches_mirror = get_mirrordir(mirrordir, patches_keytype, patches_uri)
    get_vcs_checkout(mirrordir, patches, patchdir, overwrite=True, quiet=True)

    return patchdir

def checkout_support(mirrordir, supportdir, support):
    (support_keytype, support_uri) = parse_src_key(support['src'])
    if support_keytype == 'local':
        return support_uri
    elif support_keytype != 'git':
        raise Exception("Unhandled keytype %s" % support_keytype)

    support_mirror = get_mirrordir(mirrordir, support_keytype, support_uri)
    get_vcs_checkout(mirrordir, support, supportdir, overwrite=True, quiet=True)

    support_subdir = support.get("subdir", None)
    if support_subdir is not None:
        supportdir = os.path.join(supportdir, support_subdir)

    return supportdir

def get_lastfetch_path(mirrordir, keytype, uri, branch):
    mirror = get_mirrordir(mirrordir, keytype, uri)
    branch_safename = branch.replace('/','_').replace('.', '_')
    return mirror + '.lastfetch-%s' % (branch_safename, )

def _list_submodules(mirrordir, mirror, keytype, uri, branch):
    current_vcs_version = run_sync_get_output(['git', 'rev-parse', branch], cwd=mirror)
    tmp_checkout = get_mirrordir(mirrordir, keytype, uri, prefix='_tmp-checkouts')
    if os.path.isdir(tmp_checkout):
        shutil.rmtree(tmp_checkout)
    parent = os.path.dirname(tmp_checkout)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    run_sync(['git', 'clone', '-q', '--no-checkout', mirror, tmp_checkout])
    run_sync(['git', 'checkout', '-q', '-f', current_vcs_version], cwd=tmp_checkout)
    ret = []
    submodules = _process_submodules(tmp_checkout)
    for name in submodules.keys():
        submodule = submodules[name]
        ret.append((submodule["checksum"], name, submodule["url"]))
    shutil.rmtree(tmp_checkout)
    return ret

def _make_absolute_url(parent, relpath):
    logger = Logger()
    orig_parent = parent
    orig_relpath = relpath
    if parent[-1:] == '/':
        parent = parent[:-1]
    method_index = parent.find('://')
    if method_index == -1:
        logger.fatal("Invalid method")
    first_slash = parent.find('/', method_index + 3)
    if first_slash == -1:
        logger.fatal("Invalid URL")
    parent_path = parent[first_slash:]
    while relpath.find('../') == 0:
        i = parent_path.rfind('/')
        if i < 0:
            logger.fatal("Relative path %s is too long for parent %s" % (orig_relpath, orig_parent))
        relpath = relpath[3:]
        parent_path = parent_path[:i]
    parent = parent[:first_slash] + parent_path
    if len(relpath) == 0:
        return parent
    return parent + '/' + relpath

def ensure_vcs_mirror(mirrordir, component, fetch=False,
                      fetch_keep_going=False, timeout_sec=0):
    logger = Logger()
    (keytype, uri) = parse_src_key(component["src"])
    if keytype in ("git", "local"):
        branch = component.get("branch") or component.get("tag")
        return _ensure_vcs_mirror_git(mirrordir, uri, branch,
                                      fetch=fetch, fetch_keep_going=fetch_keep_going,
                                      timeout_sec=timeout_sec)
    elif keytype == "tarball":
        name = component["name"]
        checksum = component.get("checksum")
        if not checksum:
            logger.fatal("Component %r missing checksum attribute" % name)
        return _ensure_vcs_mirror_tarball(mirrordir, name, uri, checksum,
                                          fetch=fetch, fetch_keep_going=fetch_keep_going,
                                          timeout_sec=timeout_sec)
    else:
        logger.fatal("Unhandled %r keytype" % keytype)

def _ensure_vcs_mirror_git(mirrordir, uri, branch, fetch=False,
                           fetch_keep_going=False, timeout_sec=0):
    logger = Logger()
    keytype = "git"
    mirror = get_mirrordir(mirrordir, keytype, uri)
    tmp_mirror = os.path.abspath(os.path.join(mirror, os.pardir, os.path.basename(mirror) + ".tmp"))
    did_update = False
    current_time = datetime.datetime.now()
    last_fetch_path = get_lastfetch_path(mirrordir, keytype, uri, branch)
    if os.path.exists(last_fetch_path):
        f = open(last_fetch_path)
        last_fetch_contents = f.read()
        f.close()
        last_fetch_contents = last_fetch_contents.strip()

        if timeout_sec > 0:
            t = os.path.getmtime(last_fetch_path)
            last_fetch_time = datetime.datetime.fromtimestamp(t)
            diff = current_time - last_fetch_time
            if diff.total_seconds() < timeout_sec:
                fetch = False
    else:
        last_fetch_contents = None
    if os.path.isdir(tmp_mirror):
        shutil.rmtree(tmp_mirror)
    if not os.path.exists(mirror):
        run_sync(['git', 'clone', '--mirror', uri, tmp_mirror])
        run_sync(['git', 'config', 'gc.auto', '0'], cwd=tmp_mirror)
        os.rename(tmp_mirror, mirror)
    elif fetch:
        run_sync(['git', 'fetch'], cwd=mirror, fatal_on_error=(not fetch_keep_going)) 

    current_vcs_version = run_sync_get_output(['git', 'rev-parse', branch], cwd=mirror).strip()

    changed = current_vcs_version != last_fetch_contents
    if changed:
        logger.info("Last fetch %r differs from branch %r" % (last_fetch_contents, current_vcs_version))
        for (sub_checksum, sub_name, sub_url) in _list_submodules(mirrordir, mirror, keytype, uri, branch):
            logger.info("Processing submodule %s at %s from %s" % (sub_name, sub_checksum, sub_url))
            if sub_url.find('../') == 0:
                sub_url = _make_absolute_url(uri, sub_url)
                logger.info("Absolute URL: %s" % (sub_url, ))
            _ensure_vcs_mirror_git(mirrordir, sub_url, sub_checksum, fetch=fetch,
                                   fetch_keep_going=fetch_keep_going, timeout_sec=timeout_sec)
    
    if changed or (fetch and timeout_sec > 0):
        f = open(last_fetch_path, 'w')
        f.write(current_vcs_version + '\n')
        f.close()

    return mirror

def _ensure_vcs_mirror_tarball(mirrordir, name, uri, checksum, fetch=False):
    logger = Logger()
    mirror = get_mirrordir(mirrordir, "tarball", name)
    tmp_mirror = os.path.abspath(os.path.join(mirror, os.pardir, os.path.basename(mirror) + ".tmp"))
    if not os.path.exists(mirror):
        shutil.rmtree(tmp_mirror)
        if not os.path.isdir(tmp_mirror):
            os.makedirs(tmp_mirror)
        run_sync(["git", "init", "--bare"], cwd=tmp_mirror)
        run_sync(["git", "config", "gc.auto", "0"], cwd=tmp_mirror)
        os.rename(tmp_mirror, mirror)

    import_tag = "tarball-import-" + checksum
    git_revision = run_sync_get_output(["git", "rev-parse", import_tag], cwd=mirror).strip()
    if not git_revision:
        return mirror

    # First, we get a clone of the tarball git repo
    tmp_checkout_path = os.path.join(mirrordir, "tarball-cwd-" + name)
    shutil.rmtree(tmp_checkout_path)
    run_sync(["git", "clone", mirror, tmp_checkout_path])
    # Now, clean the contents out
    run_sync(["git", "rm", "-r", "--ignore-unmatch", "."], cwd=tmp_checkout_path)

    # Download the tarball
    tmp_path = os.path.join(mirrordir, "tarball-" + name)
    shutil.rmtree(tmp_path)
    tmp_path_parent = os.path.abspath(os.path.join(tmp_path, os.pardir))
    if not os.path.isdir(tmp_path_parent):
        os.makedirs(tmp_path_parent)
    run_sync(["curl", "-o", tmp_path, uri])

    # And verify the checksum
    actual_checksum = hashlib.sha256(open(tmp_path, "rb").read()).hexdigest()
    if checksum != actual_checksum:
        logger.fatal("Wrong checksum for %r, %r was expected but "
                     "it's actually %r" % (uri, checksu, actual_checksum))

    ext = os.path.splitext(uri)[1]
    decomp_opt = None
    if ext == ".xz":
        decomp_opt = "--xz"
    elif ext == ".bz2":
        decomp_opt = "--bzip2"
    elif ext == ".gz":
        decomp_opt = "--gzip"

    # Extract the tarball to our checkout
    args = ["tar", "-C", tmp_checkout_path, "-x"]
    if decomp_opt:
        args.append(decomp_opt)
    args.extend(["-f", tmp_path])
    run_sync(args)
    os.unlink(tmp_path)

    # Automatically strip the first element if there's exactly one directory
    n_files = 0
    last_file = None
    for name in os.listdir(tmp_checkout_path):
        if name == ".git":
            continue
        n_files += 1
        last_file = os.path.join(tmp_checkout_path, name)
    if n_files == 1 and os.path.isdir(last_file):
        for name in os.listdir(last_file):
            child = os.path.join(last_file, name)
            if child != last_file:
                os.rename(child, os.path.join(tmp_checkout_path, name))
        os.unlink(last_file)

    msg = "Automatic import of " + uri
    author = "Automatic Tarball Importer <maui-development@googlegroups.com>"
    run_sync(["git", "add", "."], cwd=tmp_checkout_path)
    run_sync(["git", "commit", "-a", "--author=" + author, "-m", msg], cwd=tmp_checkout_path)
    run_sync(["git", "push", "--tags", "origin", "master:master"], cwd=tmp_checkout_path)
    shutil.rmtree(tmp_checkout_path)

    return mirror

def uncache_repository(mirrordir, keytype, uri, branc):
    last_fetch_path = get_lastfetch_path(mirrordir, keytype, uri, branch)
    shutil.rmtree(last_fetch_path)

def fetch(mirrordir, component, keep_going=False, timeout_sec=0):
    ensure_vcs_mirror(mirrordir, component, fetch=True,
                      fetch_keep_going=keep_going,
                      timeout_sec=timeout_sec)

def describe_version(dirpath, branch):
    args = ["git", "describe", "--long", "--abbrev=42", "--always"]
    if branch:
        args.append(branch)
    return run_sync_get_output(args, cwd=dirpath).strip()
