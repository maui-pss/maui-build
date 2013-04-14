# vim: et:ts=4:sw=4
# Copyright (C) 2012-2013 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
# Copyright (C) 2011-2013 Colin Walters <walters@verbum.org>
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

import os, sys, tempfile, shutil

from .. import taskset
from .. import jsondb
from .. import fileutil
from .. import jsonutil
from .. import vcs
from ..task import TaskDef
from ..snapshot import Snapshot
from ..subprocess_helpers import run_sync, run_sync_get_output

OPT_COMMON_CFLAGS = {'i686': '-O2 -pipe -g -m32 -march=i686 -mtune=atom -fasynchronous-unwind-tables',
                     'x86_64': '-O2 -pipe -g -m64 -march=x86-64 -mtune=generic'}

OPT_COMMON_LDFLAGS = {'i686': '-Wl,-O1,--sort-common,--as-needed,-z,relro',
                      'x86_64': '-Wl,-O1,--sort-common,--as-needed,-z,relro'}

class TaskBuild(TaskDef):
    name = "build"
    short_description = "Build multiple components and generate trees"

    def __init__(self, builtin, taskmaster, name, argv):
        TaskDef.__init__(self, builtin, taskmaster, name, argv)
        self.subparser.add_argument('components', nargs='*')

    def execute(self):
        args = self.subparser.parse_args(self.argv)

        self.subworkdir = os.getcwd()

        self.force_build_components = {}
        for name in args.components:
            self.force_build_components[name] = True
        self.cached_patchdir_revision = None

        snapshot_dir = os.path.join(self.workdir, "snapshots")
        srcdb = jsondb.JsonDB(snapshot_dir)
        snapshot_path = srcdb.get_latest_path()
        working_snapshot_path = os.path.join(self.subworkdir, os.path.basename(snapshot_path))
        fileutil.file_linkcopy(snapshot_path, working_snapshot_path, overwrite=True)
        data = srcdb.load_from_path(working_snapshot_path)
        self._snapshot = Snapshot(data, working_snapshot_path)
        osname = self._snapshot.data["osname"]
        self.osname = osname

        self.patchdir = os.path.join(self.workdir, "patches")

        components = self._snapshot.data["components"]

        builddb = self._get_result_db("build")

        target_source_version = builddb.parse_version_str(os.path.basename(self._snapshot.path))

        have_local_component = False
        for component in components:
            if component["src"][:6] == "local:":
                have_local_component = True
                break

        latest_build_path = builddb.get_latest_path()
        if latest_build_path is not None:
            last_build_source_data = builddb.load_from_path(latest_build_path)
            last_build_source_version = builddb.parse_version_str(last_build_source_data["snapshot-name"])
            self.logger.info("Already built source snapshot %s" % last_built_source_version)
            return
        else:
            self.logger.info("Last successful build was " + last_built_source_version)
        self.logger.info("Building " + target_source_version)

        self.repo = os.path.join(self.workdir, "repo")
        if not os.path.isdir(self.repo):
            os.makedirs(self.repo)

        if os.path.exists(os.path.join(self.repo, "objects")):
            run_sync(["ostree", "--repo=" + self.repo, "init", "--archive"])

        self._component_build_cache_path = os.path.join(self.cachedir, "component-builds.json")
        if os.path.exists(self._component_build_cache_path):
            self._component_build_cache = jsonutil.load_json(self._component_build_cache_path)
        else:
            self._component_build_cache = {}

        base_name = self._snapshot.data["base"]["name"]
        architectures = self._snapshot.data["architectures"]
        for architecture in architectures:
            self._build_base(architecture)

        component_to_arches = {}

        runtime_components = []
        devel_components = []

        for component in components:
            name = component["name"]

            is_runtime = (component.get("component") or "runtime") == "runtime"
            if is_runtime:
                runtime_components.append(component)
            devel_components.append(component)

            is_noarch = component.get("noarch") or False
            if is_noarch:
                # Just use the first specified architecture
                component_arches = [architectures[0]]
            else:
                component_arches = component.get("architectures") or architectures
            component_to_arches[name] = component_arches

        components_to_build = []
        component_skipped_count = 0
        component_build_revs = {}

        for component in components:
            for architecture in architectures:
                components_to_build.append((component, architectures))

        previous_build_epoch = self._component_build_cache["build-apoch"]
        current_build_epoch = self._snapshot.data["build-epoch"]
        if ((previous_build_epoch is None) or
            ((current_build_epoch is not None) and
             previous_build_epoch["version"] < current_build_epoch["version"])):
            current_epoch_ver = current_build_epoch["version"]
            rebuild_all = current_build_epoch["all"]
            rebuilds = []
            if rebuild_all:
                for component in components:
                    rebuilds.append(component["name"])
            else:
                rebuilds = current_build_epoch["component-names"]
            for rebuild in rebuilds:
                component = self._snapshot.get_component(rebuild)
                name = component["name"]
                self.logger.info("Component %r build forced via epoch" % name)
                for architecture in architectures:
                    build_ref = self._component_build_ref(component, architecture)
                    del self._component_build_cache[build_ref]

        self._component_build_cache["build-epoch"] = current_build_epoch
        jsonutil.write_json_file_atomic(self._component_build_cache_path, self._component_build_cache)

        for (component, architecture) in components_to_build:
            archname = component["name"] + "/" + architecture
            build_rev = self._build_one_component(component, architecture)
            component_build_revs[archname] = build_rev

        targets_list = []
        target_component_types = ['runtime', 'runtime-debug', 'devel', 'devel-debug']
        for target_component_type in target_component_types:
            for architecture in architectures:
                target = {}
                targets_list.append(target)
                target['name'] = 'buildmaster/%s-%s' % (architecture, target_component_type)

                base_runtime_ref = '%s/%s-runtime' % (base_name, architecture)
                buildroot_ref = '%s/%s-devel' % (base_name, architecture)
                if target_component_type == 'runtime':
                    base_ref = base_runtime_ref
                else:
                    base_ref = buildroot_ref
                target['base'] = {'name': base_ref,
                                  'runtime': base_runtime_ref,
                                  'devel': buildroot_ref}

                if target_component_type[:8] == "runtime-":
                    target_components = runtime_components
                else:
                    target_components = devel_components

                contents = []
                for component in target_components:
                    if component.get('bootstrap'):
                        continue
                    builds_for_component = component_to_arches[component['name']]
                    if architecture not in builds_for_component:
                        continue
                    binary_name = '%s/%s' % (component['name'], architecture)
                    component_ref = {'name': binary_name}
                    if target_component_type == 'runtime':
                        component_ref['trees'] = ['/runtime']
                    elif target_component_type == 'runtime-debug':
                        component_ref['trees'] = ['/runtime', '/debug']
                    elif target_component_type == 'devel':
                        component_ref['trees'] = ['/runtime', '/devel', '/doc']
                    elif target_component_type == 'devel-debug':
                        component_ref['trees'] = ['/runtime', '/devel', '/doc', '/debug']
                    contents.append(component_ref)
                target['contents'] = contents

        target_revisions = {}
        build_data = {"snapshot-name": os.path.basename(self._snapshot.path),
                      "snapshot": self._snapshot.data,
                      "targets": target_revisions}

        (path, modified) = builddb.store(build_data)
        self.logger.info("Build complete: " + path)

    def _resolve_refs(self, refs):
        if len(refs) == 0:
            return []
        args = ['ostree', '--repo=' + self.repo, 'rev-parse']
        args.extend(refs)
        output = run_sync_get_output(args)
        return output.split('\n')

    def _clean_stale_buildroots(self, buildroot_cachedir, keep_root):
        roots = os.listdir(buildroot_cachedir)
        for root in roots:
            if root == keep_root:
                continue
            self.logger.info("Removing old cached buildroot %s" % (root, ))
            path = os.path.join(buildroot_cachedir, root)
            shutil.rmtree(path)

    def _compose_buildroot(self, workdir, component_name, architecture):
        starttime = time.time()

        buildname = '%s/%s/%s' % (self.osname, component_name, architecture)
        buildroot_cachedir = os.path.join(self.workdir, 'roots', buildname)
        fileutil.ensure_dir(buildroot_cachedir)

        components = self._snapshot.data['components']
        build_dependencies = []
        for component in components:
            if component['name'] == component_name:
                break
            build_dependencies.append(component)

        ref_to_rev = {}

        arch_buildroot_name = '%s/bases/%s/%s-devel' % (self.osname,
                                                        self._snapshot.data['base']['name'],
                                                        architecture)

        self.logger.info("Computing buildroot contents")

        arch_buildroot_rev = run_sync_get_output(['ostree', '--repo=' + self.repo, 'rev-parse',
                                                  arch_buildroot_name]).strip()

        ref_to_rev[arch_buildroot_name] = arch_buildroot_rev
        checkout_trees = [(arch_buildroot_name, '/')]
        refs_to_resolve = []
        for dependency in build_dependencies:
            buildname = '%s/components/%s/%s' % (self.osname, dependency['name'], architecture)
            refs_to_resolve.append(buildname)
            checkout_trees.append((buildname, '/runtime'))
            checkout_trees.append((buildname, '/devel'))

        resolved_refs = self._resolve_refs(refs_to_resolve)
        for ref, rev in zip(refs_to_resolve, resolved_refs):
            ref_to_rev[ref] = rev

        sha = hashlib.sha256()

        uid = os.getuid()
        gid = os.getgid()
        etc_passwd = 'root:x:0:0:root:/root:/bin/bash\nbuilduser:x:%u:%u:builduser:/:/bin/bash\n' % (uid, gid)
        etc_group = 'root:x:0:root\nbuilduser:x:%u:builduser\n' % (gid, )

        (fd, tmppath) = tempfile.mkstemp(suffix='.txt', prefix='ostbuild-buildroot-')
        f = os.fdopen(fd, 'w')
        for (branch, subpath) in checkout_trees:
            f.write(ref_to_rev[branch])
            f.write('\0')
            f.write(subpath)
            f.write('\0')
        f.close()

        f = open(tmppath)
        buf = f.read(8192)
        while buf != '':
            sha.update(buf)
            buf = f.read(8192)
        f.close()

        sha.update(etc_passwd)
        sha.update(etc_group)

        new_root_cacheid = sha.hexdigest()

        cached_root = os.path.join(buildroot_cachedir, new_root_cacheid)
        if os.path.isdir(cached_root):
            self.logger.info("Reusing cached buildroot: %s" % cached_root)
            self._clean_stale_buildroots(buildroot_cachedir, cached_root)
            os.unlink(tmppath)
            return cached_root

        if len(checkout_trees) > 0:
            self.logger.info("Composing buildroot from %d parents (last: %r)" % (len(checkout_trees),
                                                                                 checkout_trees[-1][0]))

        cached_root_tmp = cached_root + '.tmp'
        if os.path.isdir(cached_root_tmp):
            shutil.rmtree(cached_root_tmp)
        run_sync(['ostree', '--repo=' + self.repo,
                  'checkout', '--user-mode', '--union',
                  '--from-file=' + tmppath, cached_root_tmp])
        os.unlink(tmppath)

        builddir_tmp = os.path.join(cached_root_tmp, 'ostbuild')
        fileutil.ensure_dir(os.path.join(builddir_tmp, 'source', component_name))
        fileutil.ensure_dir(os.path.join(builddir_tmp, 'results'))
        f = open(os.path.join(cached_root_tmp, 'etc', 'passwd'), 'w')
        f.write(etc_passwd)
        f.close()
        f = open(os.path.join(cached_root_tmp, 'etc', 'group'), 'w')
        f.write(etc_group)
        f.close()
        os.rename(cached_root_tmp, cached_root)

        self._clean_stale_buildroots(buildroot_cachedir, cached_root)

        endtime = time.time()
        self.logger.info("Composed buildroot; %d seconds elapsed" % (int(endtime - starttime),))

        return cached_root

    def _analyze_build_failure(self, t, architecture, component, component_srcdir,
                               current_vcs_version, previous_vcs_version):
        # Dump last bit of log
        print "LOGFILE: " + t.logfile_path
        f = open(t.logfile_path)
        lines = f.readlines()
        lines = lines[-250:]
        for line in lines:
            print "| " + line.strip()
        f.close()
        if (current_vcs_version is not None and previous_vcs_version is not None):
            git_args = ['git', 'log', '--format=short']
            git_args.append(previous_vcs_version + '...' + current_vcs_version)
            subproc_env = dict(os.environ)
            subproc_env['GIT_PAGER'] = 'cat'
            run_sync(git_args, cwd=component_srcdir, stdin=open('/dev/null'),
                     stdout=sys.stdout, env=subproc_env, log_success=False)
        else:
            self.logger.info("No previous build; skipping source diff")

    def _needs_rebuild(self, previous_metadata, new_metadata):
        build_keys = ['config-opts', 'src', 'revision', 'setuid', 'build-system']
        for k in build_keys:
            if (k in previous_metadata) and (k not in new_metadata):
                return 'key %r removed' % (k, )
            elif (k not in previous_metadata) and (k in new_metadata):
                return 'key %r added' % (k, )
            elif (k in previous_metadata) and (k in new_metadata):
                oldval = previous_metadata[k]
                newval = new_metadata[k]
                if oldval != newval:
                    return 'key %r differs (%r -> %r)' % (k, oldval, newval)
 
        if 'patches' in previous_metadata:
            if 'patches' not in new_metadata:
                return 'patches differ'
            old_patches = previous_metadata['patches']
            new_patches = new_metadata['patches']
            old_files = old_patches['files']
            new_files = new_patches['files']
            if len(old_files) != len(new_files):
                return 'patches differ'
            old_sha256sums = old_patches.get('files_sha256sums')
            new_sha256sums = new_patches.get('files_sha256sums')
            if ((old_sha256sums is None or new_sha256sums is None) or
                len(old_sha256sums) != len(new_sha256sums) or
                old_sha256sums != new_sha256sums):
                return 'patch sha256sums differ'

        return None

    def _compute_sha256sums_for_patches(self, patchdir, component):
        patches = buildutil.get_patch_paths_for_component(patchdir, component)
        result = []

        for patch in patches:
            csum = hashlib.sha256()
            f = open(patch)
            patchdata = f.read()
            csum.update(patchdata)
            f.close()
            result.append(csum.hexdigest())
        return result

    def _write_component_cache(self, key, data):
        self._component_build_cache[key] = data
        jsonutil.write_json_file_atomic(self._component_build_cache_path, self._component_build_cache)

    def _save_component_build(self, build_ref, expanded_component):
        cachedata = dict(expanded_component)
        cachedata['ostree'] = run_sync_get_output(['ostree', '--repo=' + self.repo,
                                                   'rev-parse', build_ref])
        self._write_component_cache(build_ref, cachedata)
        return cachedata['ostree']

    def _component_build_ref(self, component, architecture):
        arch_buildname = "%s/%s" % (component["name"], architecture)
        return self.osname + "/components/" + arch_buildname

    def _build_one_component(self, component, architecture):
        basename = component['name']

        arch_buildname = "%s/%s" % (component["name"], architecture)
        unix_buildname = arch_buildname.replace("/", "_")
        build_ref = self._component_build_ref(component, architecture)

        current_vcs_version = component.get('revision')
        expanded_component = self._snapshot.get_expanded(basename)
        previous_metadata = self._component_build_cache.get(build_ref)
        previous_build_version = None
        previous_vcs_version = None
        if previous_metadata is not None:
            previous_build_version = previous_metadata['ostree']
            previous_vcs_version = previous_metadata["revision"]
        else:
            self.logger("No previous build for %s" % arch_buildname)

        if 'patches' in expanded_component:
            patches_revision = expanded_component['patches']['revision']
            if self.cached_patchdir_revision == patches_revision:
                patchdir = self.patchdir
            else:
                patchdir = vcs.checkout_patches(self.mirrordir,
                                                self.patchdir,
                                                expanded_component)
                self.patchdir = patchdir
                self.cached_patchdir_revision = patches_revision
            if ((previous_metadata is not None) and
                'patches' in previous_metadata and
                not previous_metadata['patches']['src'].startswith("local:") and
                'revision' in previous_metadata['patches'] and
                previous_metadata['patches']['revision'] == patches_revision):
                # Copy over the sha256sums
                expanded_component['patches'] = previous_metadata['patches']
            else:
                patches_sha256sums = self._compute_sha256sums_for_patches(patchdir, expanded_component)
                expanded_component['patches']['files_sha256sums'] = patches_sha256sums
        else:
            patchdir = None

        force_rebuild = (basename in self.force_build_components or
                         expanded_component['src'].startswith('local:'))

        if previous_metadata is not None:
            rebuild_reason = self._needs_rebuild(previous_metadata, expanded_component)
            if rebuild_reason is None:
                if force_rebuild:
                    self.logger.info("Build forced regardless")
                else:
                    self.logger.info("Reusing cached build of %s at %s" % (arch_buildname, previous_vcs_version)) 
                    return previous_build_version
            else:
                self.logger.info("Need rebuild of %s: %s" % (arch_buildname, rebuild_reason, ) )

        build_workdir = os.path.join(os.getcwd(), "tmp-" + unix_buildname)
        fileutil.ensure_dir(build_workdir)

        temp_metadata_path = os.path.join(workdir, '_ostbuild-meta.json')
        jsonutil.write_json_file_atomic(temp_metadata_path, expanded_component)

        component_src = os.path.join(build_workdir, basename)
        child_args = ['ostbuild', 'checkout', '--snapshot=' + self._snapshot.get_path(),
                      "--workdir=" + self.workdir,
                      '--checkoutdir=' + component_src,
                      '--metadata-path=' + temp_metadata_path,
                      "--overwrite", basename]
        if patchdir is not None:
            child_args.append('--patches-path=' + patchdir)
        run_sync(child_args)

        os.unlink(temp_metadata_path)

        component_resultdir = os.path.join(build_workdir, 'results')
        fileutil.ensure_dir(component_resultdir)

        rootdir = self._compose_buildroot(build_workdir, basename, architecture)

        tmpdir = os.path.join(build_workdir, 'tmp')
        fileutil.ensure_dir(tmpdir)

        src_compile_one_path = os.path.join(self.libdir, 'ostbuild', 'ostree-build-compile-one')
        src_compile_one_mods_path = os.path.join(self.libdir, 'ostbuild', 'pyostbuild')
        dest_compile_one_path = os.path.join(rootdir, 'ostree-build-compile-one')
        dest_compile_one_mods_path = os.path.join(rootdir, 'ostbuild', 'pyostbuild')
        shutil.copy(src_compile_one_path, dest_compile_one_path)
        if os.path.exists(dest_compile_one_mods_path):
            shutil.rmtree(dest_compile_one_mods_path)
        shutil.copytree(src_compile_one_mods_path, dest_compile_one_mods_path)
        os.chmod(dest_compile_one_path, 0755)
        
        chroot_sourcedir = os.path.join('/ostbuild', 'source', basename)

        child_args = ['setarch', architecture]
        child_args.extend(buildutil.get_base_user_chroot_args())
        child_args.extend([
                '--mount-readonly', '/',
                '--mount-proc', '/proc', 
                '--mount-bind', '/dev', '/dev',
                '--mount-bind', tmpdir, '/tmp',
                '--mount-bind', component_src, chroot_sourcedir,
                '--mount-bind', component_resultdir, '/ostbuild/results',
                '--chdir', chroot_sourcedir,
                rootdir, '/ostree-build-compile-one',
                '--ostbuild-resultdir=/ostbuild/results',
                '--ostbuild-meta=_ostbuild-meta.json'])
        env_copy = dict(buildutil.BUILD_ENV)
        env_copy['PWD'] = chroot_sourcedir
        env_copy['CFLAGS'] = OPT_COMMON_CFLAGS[architecture]
        env_copy['CXXFLAGS'] = OPT_COMMON_CFLAGS[architecture]
        env_copy['LDFLAGS'] = OPT_COMMON_LDFLAGS[architecture]

        run_sync(child_args, env=env_copy)

        final_build_result_dir = os.path.join(build_workdir, "post-results")
        shutil.rmtree(final_build_result_dir)
        fileutil.ensure_dir(final_build_result_dir)

        self._process_build_results(component, component_resultdir, final_build_result_dir)

        recorded_meta_path = os.path.join(final_build_result_dir, '_ostbuild-meta.json')
        jsonutil.write_json_file_atomic(recorded_meta_path, expanded_component)

        args = ['ostree', '--repo=' + self.repo,
                'commit', '-b', build_ref, '-s', 'Build',
                '--owner-uid=0', '--owner-gid=0', '--no-xattrs', 
                '--skip-if-unchanged']

        setuid_files = expanded_component.get('setuid', [])
        statoverride_path = None
        if len(setuid_files) > 0:
            (fd, statoverride_path) = tempfile.mkstemp(suffix='.txt', prefix='ostbuild-statoverride-')
            f = os.fdopen(fd, 'w')
            for path in setuid_files:
                f.write('+2048 ' + path)
                f.write('\n')
            f.close()
            args.append('--statoverride=' + statoverride_path)

        run_sync(args, cwd=final_build_result_dir)
        if statoverride_path is not None:
            os.unlink(statoverride_path)

        shutil.rmtree(build_workdir)

        ostree_revision = self._save_component_build(build_ref, expanded_component)

        return ostree_revision

    def _compose_one_target(self, target, component_build_revs):
        base = target['base']
        base_name = '%s/bases/%s' % (self.osname, base['name'])
        runtime_name = '%s/bases/%s' % (self.osname, base['runtime'])
        devel_name = '%s/bases/%s' % (self.osname, base['devel'])

        compose_rootdir = os.path.join(self.subworkdir, target['name'])
        if os.path.isdir(compose_rootdir):
            shutil.rmtree(compose_rootdir)
        fileutil.ensure_parent_dir(compose_rootdir)

        related_refs = {}

        base_revision = run_sync_get_output(['ostree', '--repo=' + self.repo,
                                             'rev-parse', base_name])

        runtime_revision = run_sync_get_output(['ostree', '--repo=' + self.repo,
                                                'rev-parse', runtime_name])
        related_refs[runtime_name] = runtime_revision
        devel_revision = run_sync_get_output(['ostree', '--repo=' + self.repo,
                                              'rev-parse', devel_name])
        related_refs[devel_name] = devel_revision

        for name, rev in component_build_revs.iteritems():
            build_ref = '%s/components/%s' % (self.osname, name)
            related_refs[build_ref] = rev

        (related_fd, related_tmppath) = tempfile.mkstemp(suffix='.txt', prefix='ostbuild-compose-')
        related_f = os.fdopen(related_fd, 'w')
        for (name, rev) in related_refs.iteritems():
            related_f.write(name) 
            related_f.write(' ') 
            related_f.write(rev) 
            related_f.write('\n') 
        related_f.close()

        compose_contents = [(base_revision, '/')]
        for tree_content in target['contents']:
            name = tree_content['name']
            rev = component_build_revs[name]
            subtrees = tree_content['trees']
            for subpath in subtrees:
                compose_contents.append((rev, subpath))

        (contents_fd, contents_tmppath) = tempfile.mkstemp(suffix='.txt', prefix='ostbuild-compose-')
        contents_f = os.fdopen(contents_fd, 'w')
        for (branch, subpath) in compose_contents:
            contents_f.write(branch)
            contents_f.write('\0')
            contents_f.write(subpath)
            contents_f.write('\0')
        contents_f.close()

        run_sync(['ostree', '--repo=' + self.repo,
                  'checkout', '--user-mode', '--no-triggers', '--union', 
                  '--from-file=' + contents_tmppath, compose_rootdir])
        os.unlink(contents_tmppath)

        contents_path = os.path.join(compose_rootdir, 'contents.json')
        jsonutil.write_json_file_atomic(contents_path, self._snapshot.data)

        treename = 'trees/%s' % (target['name'], )
        
        child_args = ['ostree', '--repo=' + self.repo,
                      'commit', '-b', treename, '-s', 'Compose',
                      '--owner-uid=0', '--owner-gid=0', '--no-xattrs', 
                      '--related-objects-file=' + related_tmppath,
                      ]
        if not self.buildopts.no_skip_if_unchanged:
            child_args.append('--skip-if-unchanged')
        run_sync(child_args, cwd=compose_rootdir)
        os.unlink(related_tmppath)
        shutil.rmtree(compose_rootdir)

    def _build_base(self, architecture):
        """Build the Yocto base system."""
        basemeta = self._snapshot.get_expanded(self._snapshot.data['base']['name'])
        build_workdir = os.path.join(self.subworkdir, 'build-' + basemeta['name'] + '-' + architecture)
        checkoutdir = os.path.join(build_workdir, basemeta["name"])
        builddir_name = "build-%s-%s" % (basemeta["name"], architecture)
        builddir = os.path.join(self.workdir, builddir_name)
        buildname = "bases/%s-%s" % (basemeta["name"], architecture)

        #force_rebuild = (basemeta['name'] in self.force_build_components or
        #                 basemeta['src'][:6] == 'local')
        force_rebuild = False

        previous_build = self._component_build_cahce[buildname]
        if previous_build is not None:
            previous_vcs_version = previous_build["revision"]
        else:
            previous_vcs_version = None
        if force_rebuild:
            self.logger.info("%s forced rebuild" % builddir_name)
        elif previous_vcs_version == basemeta["revision"]:
            self.logger.info("Already built %s at %s" % (builddir_name, previous_vcs_version))
            return
        elif previous_vcs_version is not None:
            self.logger.info("%s was %s, now at revision %s" % (builddir_name, previous_vcs_version, basemeta["revision"]))
        if os.path.islink(checkoutdir):
            os.unlink(checkoutdir)

        fileutil.ensure_parent_dir(checkoutdir)

        (keytype, uri) = vcs.parse_src_key(basemeta["src"])
        if keytype == "local":
            shutil.rmtree(checkoutdir)
            os.symlink(uri, checkoutdir)
        else:
            vcs.get_vcs_checkout(self.mirrordir, basemeta, checkoutdir, overwrite=False)

        # Just keep reusing the old working directory downloads and sstate
        old_builddir = os.path.join(self.workdir, "build-%s" % basemeta["name"])
        sstate_dir = os.path.join(old_builddir, 'sstate-cache')
        downloads = os.path.join(old_builddir, 'downloads')

        cmd = ['linux-user-chroot', '--unshare-pid', '/',
               os.path.join(self.libdir, 'ostbuild', 'ostree-build-yocto'),
               checkoutdir, builddir, architecture, self.repo]
        # We specifically want to kill off any environment variables jhbuild
        # may have set.
        env = dict(buildutil.BUILD_ENV)
        env['DL_DIR'] = downloads
        env['SSTATE_DIR'] = sstate_dir
        run_sync(cmd, env=env)

        component_types = ['runtime', 'devel']
        for component_type in component_types:
            treename = '%s/bases/%s/%s-%s' % (self.osname, basename, architecture, component_type)
            tar_path = os.path.join(builddir, 'maui-contents-%s-%s.tar.gz' % (component_type, architecture))
            cmd = ['ostree', '--repo=' + self.repo, 'commit', '-s', 'Build', '--skip-if-unchanged',
                   '-b', treename, '--tree=tar=' + tar_path]
            run_sync(cmd, env=env)
            os.remove(tar_path)

        shutil.rmtree(checkoutdir)

        self._write_component_cache(buildname, basemeta)

taskset.register(TaskBuild)