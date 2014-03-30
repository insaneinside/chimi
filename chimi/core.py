# chimi: a companion tool for ChaNGa: core classes and utilities
# Copyright (C) 2014 Collin J. Sutton
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
# The GNU General Public License version 2 may be found at
# <http://www.gnu.org/licenses/gpl-2.0.html>.


__author__    = 'Collin J. Sutton'
__copyright__ = 'Copyright (C) 2014 Collin J. Sutton'
__license__   = 'GPLv2'


import os
import re
import sys
import uuid
import time
import copy
import shlex
import shutil
import datetime
import textwrap
import threading
import subprocess
from collections import Counter

import chimi
import chimi.util
import chimi.settings
import chimi.transient
from chimi.build import Build
from chimi.build import BuildStatus
from chimi.build import BuildConfig

git = None

git = chimi.transient.OnDemandLoader(__name__, 'git')
yaml = chimi.transient.OnDemandLoader(__name__, 'yaml' )


def check_call(call, cwd=None):
    oldcwd = os.getcwd();

    if cwd != None and cwd != oldcwd:
        # the directory might not even exist if no-act is enabled, so don't
        # actually switch directory if it is [enabled].
        if not chimi.settings.noact:
            os.chdir(cwd)
    else:
        cwd = oldcwd

    if len(call) == 1 and isinstance(call[0], list):
        call = call[0]

    result = 0

    if chimi.settings.noact:
        sys.stderr.write('would execute [in %s]: %s\n' % (os.path.relpath(cwd, oldcwd), ' '.join(call)))
    else:
        result = subprocess.check_call(call)

    if not chimi.settings.noact:
        os.chdir(oldcwd)

    return result

def get_cuda_dir():
    """Attempt to find the location of the CUDA toolkit on the local machine."""
    names = filter(lambda x: 'CUDA_DIR' in x, os.environ.keys())
    if len(names) > 0:
        return os.environ[names[0]]
    else:
        for name in ['/usr/local/cuda', '/usr/lib/nvidia-cuda-toolkit']:
            if os.path.exists(name):
                return name
        return None

def build_configure_flags(definition, config):
    """Construct `configure` flags from the given build config."""
    bool_mapping = { 'yes': True, 'on': True,
                     'no': False, 'off': False,
                     True: True, False: False }
    out = []

    for name in config.settings:
        value = config.settings[name]
        if value in bool_mapping:
            value = bool_mapping[value]
            if value:
                wo = 'with'
            else:
                wo = 'without'
            out.append('--%s-%s' % (wo, name))
        else:
            out.append('--with-%s=%s' % (name, value))
    for name in config.features:
        value = config.features[name]
        assert(value in  bool_mapping)
        value = bool_mapping[value]
        if value:
            ed = 'enable'
        else:
            ed = 'disable'
        out.append('--%s-%s' % (ed, name))

    if definition.name == 'ChaNGa' and len(config.extras) > 0:
        ldflags=[]
        cppflags=[]
        for x in config.extras:
            if re.search(r'^-L', x):
                ldflags.append(x)
            elif re.search(r'^-I', x):
                cppflags.append(x)
        if len(ldflags) > 0:
            out.append('LDFLAGS=%s'%' '.join(ldflags))
        if len(cppflags) > 0:
            out.append('CPPFLAGS=%s'%' '.join(cppflags))

    return out

class PackageDefinition(object):
    """Information about how to fetch and build a particular package."""

    ConfigureOption = chimi.util.create_struct(__name__, 'ConfigureOption',
                                               kind='enable',
                                               name=None,
                                               default=None)
    name = None
    repository = None

    @classmethod
    def get_configure_path(self, instance):
        """Get the path to the instance's `configure' script, if it has one."""
        pass

    @classmethod
    def get_configure_options(self, instance):
        """
        Get the package and feature options available for a package instance's
        `configure' script.

        return: dict

        """
        chimi.transient.push('(Loading %s configure options ... ' % self.name)

        script = self.get_configure_path(instance)
        script_help = subprocess.check_output([script, '--help'])
        lre = re.compile(r'^\s*--(enable|disable|with|without)-([^\s\[=]+)')
        lines = filter(lambda x: lre.match(x), script_help.split('\n'))

        o = {}

        for l in lines:
            m = lre.match(l)
            kind, name = m.groups()

            opt = None
            if kind == 'enable':
                opt = self.ConfigureOption(kind='enable', name=name, default=False)
            elif kind == 'disable':
                opt = self.ConfigureOption(kind='enable', name=name, default=True)
            elif kind == 'with':
                opt = self.ConfigureOption(kind='with', name=name, default=False)
            elif kind == 'without':
                opt = self.ConfigureOption(kind='with', name=name, default=True)
            else:
                # this should never happen -- the regular expression ensures
                # that one of the above conditions is true.
                os.abort()


            if (opt.kind == 'enable' and opt.name == 'FEATURE') or \
                    (opt.kind == 'with' and opt.name == 'PACKAGE'):
                # Skip the example options.
                continue
            elif name in o:
                raise ValueError('%s: `configure\' option name conflict: %s'%(self.name, name))
            else:
                o[name] = opt
        chimi.transient.pop(')')
        return o

    @classmethod
    def get_build_name(self, build):
        """
        Get a user-friendly name for build `build' of this package.

        """
        pass

    @classmethod
    def find_existing_builds(self, package):
        """
        Find and return a list of existing builds for a package instance.

        """
        return []

    @classmethod
    def get_build_directory(self, build):
        """Get the directory in which a build's files should go"""
        pass

    def __init__(self, name, repo):
        self.name = name
        self.repository = repo

    @classmethod
    def fetch(self, package):
        """Fetch or update sources for the given package instance."""
        srcdir = package.directory

        if not os.path.exists(srcdir):
            parent_dir = os.path.dirname(srcdir)
            if not os.path.exists(parent_dir) and not chimi.settings.noact:
                os.makedirs(parent_dir)
            check_call(['git', 'clone', self.repository, srcdir], cwd=parent_dir)
        else:
            check_call(['git', 'pull', 'origin'], cwd=srcdir)


class ChaNGaDefinition(PackageDefinition):
    """Package definition for ChaNGa"""
    name = 'ChaNGa'
    repository = chimi.settings.DEFAULT_REPOSITORIES['changa']

    @classmethod
    def get_configure_path(self, instance):
        return os.path.join(instance.directory, 'configure')

    @classmethod
    def get_build_name(self, build=None, charm_name=None, package=None):
        if build and not charm_name:
            charm_name = CharmDefinition.get_build_name(build)
        base = re.sub(r'/.*$', '', charm_name)
        branch = build.config.branch
        return base + '+' + branch

    @classmethod
    def get_build_directory(self, build):
        return os.path.join(build.package.directory, 'builds', build.name)

    @classmethod
    def get_build_version(self, build):
        version_file = os.path.join(build.directory, 'VERSION')
        if os.path.exists(version_file):
            return file(version_file, 'r').read().strip()

    @classmethod
    def find_existing_builds(self, package):
        directory = package.directory
        builds_dir = os.path.join(directory, 'builds')
        if os.path.exists(builds_dir):
            return CharmDefinition.find_existing_builds(package, builds_dir)
        else:
            return []

    @classmethod
    def build(self, package, config, _continue=False, replace=False, force=False):
        srcdir = package.directory
        builds_dir = os.path.join(srcdir, 'builds')
        if not os.path.exists(builds_dir) and not chimi.settings.noact:
            os.mkdir(builds_dir)

        # Find a matching Charm++ build.
        charm = package.package_set['charm']
        charm_config = chimi.build.BuildConfig.create(charm, opts=config.source_opts,
                                                      extras=config.extras,
                                                      branch=config.branch if config.branch in charm.branches else charm.branch,
                                                      ignore_unknown_options=True)
        charm_build = charm.find_build(charm_config)

        if charm_build == None:
            sys.stderr.write("No matching Charm++ build found -- building now.\n")
            assert(charm_config.branch in charm.branches)
            charm_build = charm.build(charm_config)

            if charm_build.status.failure:
                sys.stderr.write("\033[1;31mCharm build failed:\033[0m ChaNGa build aborted.\n")
                return None
            else:
                if not charm.have_build(charm_build):
                    charm.add_build(charm_build, replace=replace)
                package.package_set.save_flag = True

        assert(config.branch != None)
        _build = None
        if _continue:
            _build = package.find_build(config, require_matching_branch=True)
            if not _build:
                raise ValueError('No such build to continue')
            elif _build.compiled and not force:
                raise ValueError('Cannot continue complete build: nothing to do.')
        else:
            _build = Build(package, config)
            package.add_build(_build, replace=replace) # Register this build of the package

        # Ensure that the build directory exists, and cd into it.
        if not os.path.isdir(_build.directory) and not chimi.settings.noact:
            os.makedirs(_build.directory)
        build_dir = _build.directory

        if (not _continue) or not _build.configured:
            # Build and run a `configure` invocation
            configure_invocation = ['../../configure']
            if not 'CHARMC' in os.environ.keys():
                charmc = os.path.join(charm_build.directory, 'bin/charmc')
                configure_invocation.append('CHARMC=%s' % charmc)

            configure_invocation.extend(build_configure_flags(self, config))

            _build.update(BuildStatus.Configure, ' '.join(configure_invocation))
            try:
                check_call(configure_invocation, cwd=build_dir)
            except subprocess.CalledProcessError:
                _build.update(BuildStatus.ConfigureFailed)
            except KeyboardInterrupt:
                _build.update(BuildStatus.InterruptedByUser)
                pass
            else:
                _build.update(BuildStatus.Configured)
                assert(_build.status == BuildStatus.Configured)
                assert(_build.configured == True)

        # Compile
        if _build.configured:
            _build.update(BuildStatus.Compile)
            try:
                check_call(['make'], cwd=_build.directory)
            except subprocess.CalledProcessError:
                _build.update(BuildStatus.CompileFailed)
            else:
                _build.update(BuildStatus.Complete, 'ChaNGa build complete.')

        return _build

class CharmArchitecture(object):
    """Stores metadata for a Charm++ build architecture"""
    def __init__(self, parent, name,
                 options=None, compilers=None, fortran_compilers=None,
                 is_base=False):
        self.parent = parent
        self.children = []
        self.name = name

        self._options = None
        self._compilers = None
        self._fortran_compilers = None

        if isinstance(options, list) and len(options) > 0:
            self._options = sorted(options)

        if isinstance(compilers, list) and len(compilers) > 0:
            self._compilers = sorted(compilers)

        if isinstance(fortran_compilers, list) and len(fortran_compilers) > 0:
            self._fortran_compilers = sorted(fortran_compilers)

        self.is_base = is_base

    def merge_property_with_inherited(self, propnames):
        """
        Get all values for a property as specified in both the current object
        and all ancestors.  If a sequence is passed for `propnames`, a list of
        the results for each specified property name will be returned instead.
        Using a this method with a sequence of property names should be more
        efficient than calling the method once for each property name.

        """
        if isinstance(propnames, str):
            propname = propnames
            out = []
            ref = self
            while ref:
                if hasattr(ref, propname):
                    rprop = getattr(ref, propname)
                    if isinstance(rprop, list):
                        out.extend(rprop)
                ref = ref.parent
            return out
        else:
            _range = range(len(propnames))
            out = [[] for i in _range]

            ref = self
            while ref:
                for i in _range:
                    if hasattr(ref, propnames[i]):
                        rprop = getattr(ref, propnames[i])
                        if isinstance(rprop, list):
                            out[i].extend(rprop)
                ref = ref.parent
            return out

    @property
    def all_options(self):
        """
        Convenience method for fetching all options, compilers, and fortran
        compilers that may be specified for this architecture.

        """
        allprops = self.merge_property_with_inherited(('_options', '_compilers', '_fortran_compilers'))
        out = allprops[0]
        out.extend(allprops[1])
        out.extend(allprops[2])
        return out

    @property
    def options(self):
        o = self.merge_property_with_inherited('_options')
        o.sort()
        return o

    @property
    def compilers(self):
        o = self.merge_property_with_inherited('_compilers')
        o.sort()
        return o

    @property
    def fortran_compilers(self):
        o = self.merge_property_with_inherited('_fortran_compilers')
        o.sort()
        return o

    def has_option(self, optname):
        if optname in self.options:
            return True
        elif self.parent:
            return self.parent.has_option(optname)
        else:
            return False

    def __str__(self):
        return self.name

    def __repr__(self):
        opts_string=''
        if hasattr(self, '_options') and self._options and \
                len(self._options) > 0:
            opts_string = 'options=(%s)' % ' '.join(self._options)

        compilers_string = ''
        if hasattr(self, '_compilers') and self._compilers and \
                len(self._compilers) > 0:
            compilers_string = 'compilers=(%s)' % ' '.join(self._compilers)

        fcompilers_string=''
        if hasattr(self, '_fortran_compilers') and self._fortran_compilers and \
                len(self._fortran_compilers) > 0:
            fcompilers_string = 'fortran_compilers=(%s)' % ' '.join(self._fortran_compilers)

        body_string = ' '.join([opts_string, compilers_string, fcompilers_string]).strip()

        name_string = ''
        if self.parent:
            name_string = '%s(%s)' % (self.name, self.parent.name)
        else:
            name_string = self.name

        return '<%s: %s%s>' \
            % (self.__class__.__name__,
               name_string,
               (' ' + body_string) if len(body_string) > 0 else '')

class CharmDefinition(PackageDefinition):
    """Package definition for Charm++"""
    name = 'Charm++'
    repository = chimi.settings.DEFAULT_REPOSITORIES['charm']

    Architectures = {}

    COMPILERS_REGEXP = re.compile(r'^cc-([^.]+).h$')
    OPTIONS_REGEXP = re.compile(r'^conv-mach-([^.]+).h$')

    ExistingBuild = chimi.util.create_struct(__name__, 'ExistingBuild',
                                             directory=None,
                                             architecture=None,
                                             components=None,
                                             features=None,
                                             settings=None,
                                             extras=None,
                                             branch=None)


    @classmethod
    def get_configure_path(self, instance):
        return os.path.join(instance.directory, 'src', 'scripts', 'configure')


    @classmethod
    def get_build_name(self, build):
        config = build.config
        if isinstance(config,tuple):
            config = config[0]
        opts = [config.architecture.name \
                    if isinstance(config.architecture, CharmArchitecture) \
                    else config.architecture]
        components = list(config.components)
        components.sort()
        opts.extend(components)
        return '-'.join(opts)

    @classmethod
    def get_build_directory(self, build):
        return os.path.join(build.package.directory, build.name)

    @classmethod
    def get_build_version(self, build):
        version_file = os.path.join(build.directory, 'tmp', 'VERSION')
        if os.path.exists(version_file):
            tagged = file(version_file, 'r').read().strip()
            tags = [re.escape(tag.name) for tag in build.package.repository.tags]
            _re = re.compile(r'^(%s)(?:-[0-9]+)?(?:-g([0-9a-fA-F]+))?'%'|'.join(tags))

            commit = None
            try_two = False
            while not commit and not try_two:
                m = _re.match(tagged)
                tag, commit = m.groups()
                if not commit:
                    tagged = build.package.repository.git.describe(tag, long=True)
                    try_two = True
            return commit


    @classmethod
    def get_arch_options_and_compilers(self, package_directory, arch):
        """
        Fetch available options and compilers for a specific architecture from
        a Charm++ package tree.

        """
        _dir = os.path.join(package_directory, 'src', 'arch', arch)
        entries = os.listdir(_dir)
        compilers = [CharmDefinition.COMPILERS_REGEXP.sub(r'\1', ce) \
                         for ce in filter(lambda x: CharmDefinition.COMPILERS_REGEXP.match(x),
                                          entries)]
        options = [CharmDefinition.OPTIONS_REGEXP.sub(r'\1', ce) \
                       for ce in filter(lambda x: CharmDefinition.OPTIONS_REGEXP.match(x),
                                        entries)]
        fortran_compilers_list = ['g95', 'gfortran', 'absoft', 'pgf90', 'ifc', 'ifort']

        fortran_compilers = filter(lambda x: x in fortran_compilers_list, options)

        # Remove fortran compilers from options
        options = filter(lambda x: not x in fortran_compilers, options)

        return (options, compilers, fortran_compilers)

    @classmethod
    def load_architectures(self, package):
        """
        Initialize CharmDefinition.Architectures.

        This method loads Charm++ architecture data -- including available
        build-options and compilers for each architecture -- from a Charm++
        package tree.

        """
        directory = package.directory
        # We *could* make a native Python version of this shell command, but
        # since we're trying to recreate the same values that Charm++'s "build"
        # script comes up with, it's probably better to just copy the command
        # straight out of that script.
        run = "cd %s ; ls -1 | egrep -v '(^CVS)|(^shmem$)|(^mpi$)|(^sim$)|(^net$)|(^multicore$)|(^util$)|(^common$)|(^uth$)|(^conv-mach-fix.sh$)|(^win32$)|(^win64$)|(^paragon$)|(^lapi$)|(^cell$)|(^gemini_gni$)|(^pami$)|(^template$)|(^cuda$)'" % (os.path.join(directory, 'src', 'arch'))
        out = subprocess.check_output(run, shell=True)
        architecture_names = filter(lambda x: len(x) > 0, out.split("\n"))

        # Now fetch the available compilers and options for each Charm++
        # architecture.
        common = CharmArchitecture(None, 'common', *self.get_arch_options_and_compilers(directory, 'common'),
                                   is_base=True)
        CharmDefinition.Architectures['common'] = common

        for name in architecture_names:
            parent = common

            base_name=re.sub(r'^([^-]+)-.*$', r'\1', name)
            if base_name != name \
                    and os.path.isdir(os.path.join(directory, 'src', 'arch', base_name)):
                if not base_name in CharmDefinition.Architectures:
                    # Load the "base" compiler/option sets for the architecture.
                    CharmDefinition.Architectures[base_name] = \
                        CharmArchitecture(common, base_name,
                                          *self.get_arch_options_and_compilers(directory, base_name),
                                          is_base=True)
                else:
                    base = CharmDefinition.Architectures[base_name]
                    base.is_base = True

                parent = CharmDefinition.Architectures[base_name]

            arch = CharmArchitecture(parent, name,
                                     *self.get_arch_options_and_compilers(directory, name))
            CharmDefinition.Architectures[name] = arch
            if parent:
                parent.children.append(arch)

    @classmethod
    def find_existing_build_data(self, package, build_dir=None):
        if build_dir == None:
            build_dir = package.directory
        if len(CharmDefinition.Architectures) == 0:
            if package.definition == self:
                self.load_architectures(package)
            else:
                raise RuntimeError('Cannot load architectures from non-Charm++ build tree!')
        arches = list(CharmDefinition.Architectures.keys())
        arches.sort(key=lambda x: len(x), reverse=True)

        # Find all entries under `build_dir` that match available architectures.
        name_re = re.compile('^(' + ('|'.join(arches)) + r')(?:-([a-z][-a-z]*))?(?:\+([a-z][-a-z0-9_/]*))?')
        build_dirs = filter(lambda x: name_re.match(x) and os.path.isdir(os.path.join(build_dir, x)),
                            os.listdir(build_dir))
        out = []
        # Extract build architecture and options from build directory names
        config_opts_re = re.compile(r'^  with options \\"(.+)\\"$')
        feature_re = re.compile(r'^--(en|dis)able-(.+)$')
        setting_re = re.compile(r'^--with(out)?-([^=]+)(?:=(.+))?$')
        for dirname in build_dirs:
            m = name_re.match(dirname)
            arch = m.group(1)
            opts = []
            components = []
            features = {}
            settings = {}
            extras = []
            branch = None

            try:
                components = m.group(2).split('-')
            except:
                pass
            try:
                branch = m.group(3)
            except:
                pass

            # Load the autoconf `config_opts.sh' file and reconstruct
            # build-config settings from its contents.
            config_opts_file = os.path.join(build_dir, dirname, 'tmp', 'config.status')
            if not os.path.isfile(config_opts_file):
                config_opts_file = os.path.join(build_dir, dirname, 'config.status')

            if os.path.isfile(config_opts_file):
                config_opts_contents = file(config_opts_file).read().strip()
                lines = config_opts_contents.split('\n')
                matches = filter(lambda x: x, [config_opts_re2.match(l) for l in lines])
                try:
                    m = matches[0]
                except IndexError:
                    m = None

                if m:
                    config_opts = shlex.split(m.group(1))
                    for opt in config_opts:
                        if opt.startswith('CHARMC='):
                            continue
                        m = feature_re.match(opt)
                        if m:
                            how, name = m.groups()
                            if how == 'en':
                                features[name] = True
                            else:
                                features[name] = False
                            continue

                        m = setting_re.match(opt)
                        if m:
                            without, name, value = m.groups()
                            if without == 'out' or value == 'no':
                                settings[name] = False
                            else:
                                settings[name] = value if value else True
                            continue
                        extras.append(opt)
            out.append(CharmDefinition.ExistingBuild(directory=dirname,
                                                     architecture=arch,
                                                     components=components,
                                                     features=features,
                                                     settings=settings,
                                                     extras=extras,
                                                     branch=branch))
        return out

    @classmethod
    def find_existing_builds(self, package, build_dir=None):
        data = self.find_existing_build_data(package, build_dir)
        builds = []
        for eb in data:
            builds.append(Build(package, BuildConfig(eb.architecture, eb.components, eb.features,
                                                     eb.settings, eb.extras, branch=eb.branch,
                                                     package=package),
                                initial_status=BuildStatus.PreexistingBuild))
        return builds

    @classmethod
    def build(self, package, config, _continue=False, replace=False, force=False):
        srcdir = package.directory

        assert(config.branch != None)
        if len(CharmDefinition.Architectures) == 0:
            self.load_architectures(package)

        opts = []
        _build = None
        if _continue:
            _build = package.find_build(config, require_matching_branch=True)
            if not _build:
                raise ValueError('No such build to continue')
        else:
            _build = Build(package, config)
            package.add_build(_build, replace=replace) # Register this build of the package

        build_cwd = None
        build_args = None
        if _continue:
            build_cwd = os.path.join(_build.directory, 'tmp')
            build_args = ['gmake', 'basics', 'ChaNGa']
        else:
            build_cwd = srcdir
            build_args = ['./build', 'ChaNGa', config.architecture.name]
            build_args.extend(config.components)
            build_args.extend(build_configure_flags(self, config))
            build_args.extend(config.extras)

        _build.update(BuildStatus.Compile, ' '.join(build_args))

        try:
            check_call(build_args, cwd=build_cwd)
        except subprocess.CalledProcessError:
            _build.update(BuildStatus.CompileFailed)
            return _build
        else:
            _build.update(BuildStatus.Complete, 'Charm++ build complete.')
            return _build

class UtilityDefinition(PackageDefinition):
    name = 'utility'
    repository = chimi.settings.DEFAULT_REPOSITORIES['utility']

class Package(object):
    """A single package instance."""

    def __init__(self, package_set, definition, directory, builds=None):
        self.package_set = package_set
        self.definition = definition
        self.directory = directory
        self._repository = None
        self._branches = None

        if builds == None:
            self.builds = []
            if os.path.exists(directory):
                self.add_existing_builds()
        else:
            self.builds = builds

    def __setstate__(self, state):
        self.__dict__ = state
        self._repository = None
        self._branches = None

        # Check for build directories that no longer exist, builds with
        # identical paths, and builds with incorrect branch names.
        do_save = False
        builds_to_delete = set()
        for build in self.builds:
            build.config = copy.copy(build.config)
            if not os.path.exists(build.directory):
                do_save = True
                builds_to_delete.add(build)
            if not build.config.branch in self.branches:
                do_save = True
                build.config.branch = \
                    re.sub(r'^(?:heads/|remotes/([^/]+)/)', '',
                           self.repository.git.describe(build.version, all=True))

        counts = Counter([b.directory for b in self.builds])
        for _dir in counts:
            if counts[_dir] > 1:
                # Discard all but the most-recently-updated build.
                _builds = sorted(filter(lambda x: x.directory == _dir, self.builds))
                builds_to_delete.update(set(_builds[0:-1]))

        if len(builds_to_delete) > 0:
            self.builds = list(set(self.builds).difference(builds_to_delete))

        if do_save:
            # Set a flag on the parent package-set to indicate that internal
            # state has changed.  It will save when it's ready -- if we
            # directly called its `save` method here, when it's (possibly) not
            # yet done loading, data would be lost.
            self.package_set.save_flag = True

    @property
    def branches(self):
        """Fetch the names of all local repository branches"""
        # We fetch the branch list only once per instantiation of the class,
        # because we don't expect it to change during a single Chimi run.
        if not self._branches:
            self._branches = [re.sub(r'^heads/', '', br.name) for br in self.repository.branches]
        return self._branches

    @property
    def branch(self):
        """Name of the currently checked-out branch"""
        return re.sub(r'^heads/', '', self.repository.git.describe(all=True))

    @property
    def repository(self):
        """Git repository object for the package."""
        load_git()
        if self._repository != None:
            return self._repository
        else:
            self._repository = git.Repo(self.directory)
            return self._repository

    def fetch(self):
        self.definition.fetch(self)

    @property
    def remotes(self):
        """
        Fetch the names of all Git remote repositories.

        """
        cwd = os.getcwd()
        out = []
        if os.path.exists(self.directory):
            os.chdir(self.directory)
            url_regexp = re.compile(r'^\s*Fetch URL: ')
            git_remote_names = self.repository.git.remote().split("\n")
            for name in git_remote_names:
                if name == '':
                    continue
                gitremote = self.repository.git.remote('show', '-n', name)
                url_line = filter(lambda x: url_regexp.match(x), gitremote.split("\n"))[0]
                out.append((name, url_regexp.sub('', url_line).strip()))
            os.chdir(cwd)
        return out


    def build(self, config, **kwargs):
        """Build the package."""
        if not isinstance(config.branch, str):
            config.branch = self.branch

        old_branch = self.branch
        if self.branch != config.branch:
            check_call(['git', 'checkout', config.branch], cwd=package.directory)

        try:
            return self.definition.build(self, config, **kwargs)
        finally:
            if self.branch != old_branch:
                check_call(['git', 'checkout', old_branch], cwd=package.directory)


    def purge_builds(self, config=None, names=None, uuids=None,
                     callback=None):
        """
        Purge any builds matching the supplied configuration or names/UUIDs.
        If no configuration or names are given, purge all builds.

        """
        _builds = None
        if config:
            _builds = self.find_builds(config)
        elif names or uuids:
            _builds = filter(lambda _build: \
                                 (names and _build.name in names) or \
                                 (uuids and str(_build.uuid) in uuids),
                             self.builds)
        else:
            _builds = list(self.builds)

        for _build in _builds:
            if callback:
                callback(_build)
            if not chimi.settings.noact:
                shutil.rmtree(_build.directory)
                self.builds.remove(_build)

        return len(_builds)

    def find_builds(self, config):
        """Find all builds matching `config` for this package instance."""
        if not isinstance(config,chimi.build.BuildConfig):
            raise ValueError('Invalid argument type `%s\' to `find_build`'%type(config))
        return filter(lambda x: x.config == config, self.builds)

    def find_build(self, config):
        """Find a build matching `config` for this package instance."""
        matches = self.find_builds(config)

        if len(matches) > 0:
            return matches[0]
        else:
            return None

    def have_build(self, obj):
        """
        Check if a build matching `obj` is present for this package instance.

        """

        if isinstance(obj, Build):
            return self.find_build(obj.config) != None
        elif isinstance(obj, BuildConfig):
            return self.find_build(obj) != None
        else:
            raise ValueError('Parameter to `have_build` must be a Build or BuildConfig')

    def add_build(self, _build, replace=False):
        owned = self.find_build(_build.config)
        if owned == None or owned.directory != _build.directory:
            self.builds.append(_build)
            if not chimi.settings.noact:
                self.package_set.save_flag = True
        elif replace:
            sys.stderr.write("\033[31mWARNING:\033[0m replacing build \"%s\" at %s\n" %
                             (owned.name, os.path.relpath(owned.directory, self.package_set.directory)))
            idx = self.builds.index(owned)
            del self.builds[idx]
            self.builds.append(_build)
        else:
            wrapper = textwrap.TextWrapper(break_long_words=False, break_on_hyphens=False, subsequent_indent=' ' * 4)
            sys.stderr.write(wrapper.fill("\033[91mERROR:\033[0m cannot overwrite build unless --replace is given: %s" %
                                          os.path.relpath(owned.directory, chimi.run_cwd)) + "\n")
            raise RuntimeError('Cowardly refusing to overwrite previous build')

    def add_existing_builds(self):
        for _build in self.definition.find_existing_builds(self):
            self.add_build(_build)


class PackageSet(object):
    """A set of package instances required to build (and including) ChaNGa"""
    SET_FILE = 'chimi.yaml'
    def __init__(self, directory):
        self.directory = directory
        self.save_flag = False
        self.mutex = threading.Lock()

        self.packages = { 'charm': Package(self, CharmDefinition,
                                           os.path.join(directory, 'charm')),
                          'changa': Package(self, ChaNGaDefinition,
                                            os.path.join(directory, 'changa')),
                          'utility': Package(self, UtilityDefinition,
                                             os.path.join(directory, 'utility'))}

    def __del__(self):
        if 'save_flag' in self.__dict__ and not chimi.settings.noact:
            if self.save_flag:
                self.save()

    def save(self):
        assert(chimi.settings.noact == False)
        self.mutex.acquire()
        mtx = self.mutex
        try:
            if not 'save_flag' in self.__dict__ or self.save_flag:
                # Remove some values from stuff to avoid writing those values
                # to the YAML package-set file.
                del self.__dict__['mutex']
                if 'save_flag' in self.__dict__:
                    del self.__dict__['save_flag']
                repos = {}
                branches = {}
                for pkg in self.packages:
                    if '_repository' in self.packages[pkg].__dict__:
                        repos[pkg] = self.packages[pkg]._repository
                        del self.packages[pkg]._repository
                    if '_branches' in self.packages[pkg].__dict__:
                        branches[pkg] = self.packages[pkg]._branches
                        del self.packages[pkg]._branches

                file(os.path.join(self.directory, PackageSet.SET_FILE),
                     'w').write(yaml.dump(self))

                for pkg in repos:
                    self.packages[pkg]._repository = repos[pkg]
                for pkg in branches:
                    self.packages[pkg]._branches = branches[pkg]
                self.save_flag = False
                self.mutex = mtx
                # sys.stderr.write("done.\n")
        finally:
            self.mutex = mtx
            self.mutex.release()

    def __getitem__(self, name):
        return self.packages[name]

    @classmethod
    def load(self, directory):
        out = yaml.load(file(os.path.join(directory, PackageSet.SET_FILE),
                             'r').read())
        if not 'mutex' in out.__dict__:
            out.mutex = threading.Lock()


        if 'save_flag' in out.__dict__:
            # Allow saving immediately after loading even if the global `noact`
            # flag is set; `save_flag` set in such a case indicates that there
            # were e.g. inconsistencies to remove.
            noact = chimi.settings.noact
            chimi.settings.noact = False

            out.save()

            chimi.settings.noact = noact

        return out
