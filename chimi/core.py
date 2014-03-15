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
import os
import re
import git
import sys
import yaml
import uuid
import time
import shutil
import datetime
import textwrap
import threading
import subprocess
from collections import Counter

import chimi.util
import chimi.settings

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

def build_configure_flags(config):
    """Construct `configure` flags from the given build config."""
    bool_mapping = { 'yes': True, 'on': True,
                     'no': False, 'off': False }
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

    if len(config.extras) > 0:
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

class BuildMessage(object):
    """A recorded build message"""
    time = None
    status = None
    message = None

    def __init__(self, status, message=None):
        self.time = time.time()
        self.status = status
        if message != None:
            self.message = message

    def __str__(self):
        time_string = None
        use_time = self.time
        if isinstance(self.time, time.struct_time):
            use_time = time.mktime(self.time)
        if chimi.util.relative_message_timestamps:
            dt = datetime.datetime.fromtimestamp(use_time)
            time_string = chimi.util.relative_datetime_string(dt) + ' ago'
        else:
            time_string = time.ctime(use_time)

        message = self.message
        if self.message == None:
            message = BuildStatus.default_message(self.status)

        color = 'yellow'
        if self.status.failure:
            color = 'red'
        elif self.status.completion:
            color = 'green'

        return "%12s \033[1;%dm%s:\033[0m %s" \
            % (time_string, chimi.util.ANSI_COLORS[color],
               self.status.name, message)

class BuildStatus:
    """A recorded build status"""
    value = None
    def __init__(self, value):
        self.value = value

    def __lt__(self, other):
        return self.value < other.value

    def __gt__(self, other):
        return self.value > other.value

    def __eq__(self, other):
        return self.value == other.value

    @property
    def completion(self):
        """Whether the status indicates a completion state"""
        return self.value == BuildStatus.Configured.value or \
            self.value == BuildStatus.Complete.value
    @property
    def failure(self):
        """Whether the status indicates a failure state"""
        return self.value == BuildStatus.ConfigureFailed.value or \
            self.value == BuildStatus.CompileFailed.value or \
            self.value == BuildStatus.InterruptedByUser.value

    @property
    def name(self):
        """Canonical name for this build status"""
        return { BuildStatus.Unconfigured.value: 'Unconfigured',
                 BuildStatus.Configure.value: 'Configure',
                 BuildStatus.ConfigureFailed.value: 'Configuration failed',
                 BuildStatus.Configured.value: 'Configured',
                 BuildStatus.Compile.value: 'Compile',
                 BuildStatus.CompileFailed.value: 'Compile failed',
                 BuildStatus.Complete.value: 'Complete',
                 BuildStatus.PreexistingBuild.value: 'Unknown (preexisting build)',
                 BuildStatus.InterruptedByUser.value: 'Interrupted by user',
                 }[self.value]

    @classmethod
    def default_message(self, status):
        if status.value == self.Unconfigured.value:
            return "build started."
        elif status.value == self.Configure.value:
            return "configuring... "
        elif status.value == self.ConfigureFailed.value:
            return "configuration failed."
        elif status.value == self.Configured.value:
            return "configuration complete."
        elif status.value == self.Compile.value:
            return "compiling... "
        elif status.value == self.CompileFailed.value:
            return "compilation failed."
        elif status.value == self.Complete.value:
            return "build completed."
        elif status.value == self.PreexistingBuild.value:
            return "recorded preexisting build."
        elif status.value == self.InterruptedByUser.value:
            return 'build aborted.'
        else:
            raise RuntimeError("Unknown status: %s (%d)\n" % (status, status.value))


BuildStatus.Unconfigured, BuildStatus.Configure, BuildStatus.ConfigureFailed, \
    BuildStatus.Configured, BuildStatus.Compile, BuildStatus.CompileFailed, \
    BuildStatus.Complete, BuildStatus.PreexistingBuild, BuildStatus.InterruptedByUser \
    = [ BuildStatus(i) for i in range(9) ]

class BuildConfig(object):
    """
    Records information about the flags and arguments used during a package
    build.

    """
    def __init__(self, *args, **kwargs):
        """
        Initialize a new build configuration.

        overload: __init__(config<chimi.core.HostBuildConfig>, ...)

            Initialize using the default settings in the given host-build
            configuration.  If additional arguments are given, they are applied
            as described in the next overload before the given host-build
            configuration is applied.

        overload: __init__(arch<str>, options<list>, settings<dict>, extras<list>,
                           branch<str>=None)

           Initialize without any host-default values.

        """
        import chimi.config
        if not isinstance(args, list):
            args = list(args)

        if len(args) > 0 and isinstance(args[0], chimi.config.HostBuildConfig):
            self.host_build_config = args.pop(0)
            self.__init__(*args)
            self.host_build_config.apply(self)
        else:
            arch=chimi.config.get_architecture()
            options=[]
            settings={}
            extras=[]
            branch=None

            if len(args) > 0:
                arch = args.pop(0)
            if len(args) > 0:
                options = args.pop(0)
            if len(args) > 0:
                settings = args.pop(0)
            if len(args) > 0:
                extras = args.pop(0)

            if len(args) > 0:
                raise ValueError('too many positional arguments passed to __init__')

            if 'branch' in kwargs:
                self.branch = kwargs['branch']
            else:
                self.branch = None

            if isinstance(arch, str):
                self.architecture = arch
                self.options = options
                self.settings = settings
                self.extras = extras
                if 'cuda' in self.options:
                    cuda_dir = get_cuda_dir()
                    if cuda_dir != None:
                        settings['cuda'] = cuda_dir
            else:
                self.architecture = chimi.config.get_architecture()
                self.options = []
                self.settings = {}
                self.extras = []

        self.options.sort()
        self.extras.sort()

    def __str__(self):
        return str((self.architecture, self.branch, self.options, self.settings, self.extras))

    def __eq__(self, other):
        if not isinstance(other, BuildConfig):
            return False
        else:
            return self.architecture == other.architecture and \
                self.options == other.options and \
                self.settings == other.settings and \
                self.extras == other.extras


class Build(object):
    """Information about a build of a particular Package instance"""
    uuid = None
    package = None
    directory = None
    config = None
    status = None
    messages = None

    def __init__(self, pkg, config,
                 initial_status=BuildStatus.Unconfigured, initial_message=None,
                 _uuid=None, name=None, messages=None):
        self.uuid = uuid.uuid1()
        self.package = pkg
        self.config = config

        if not 'branch' in self.config.__dict__:
            self.config.branch = self.package.branch

        if _uuid == None and name == None and status == None and messages == None:
            if self.package.definition == ChaNGaDefinition:
                self.name = pkg.definition.get_build_name(charm_name=CharmDefinition.get_build_name(self),
                                                          package=self.package)
            else:
                self.name = pkg.definition.get_build_name(self)

            self.messages = [BuildMessage(initial_status, initial_message)]
        else:
            self.uuid = _uuid
            self.name = name
            self.messages = messages

        self.directory = pkg.definition.get_build_directory(self)

    @property
    def status(self):
        return self.messages[-1].status

    @property
    def configured(self):
        return len(filter(lambda x: x.status == BuildStatus.Configured, self.messages)) > 0

    @property
    def compiled(self):
        return self.status == BuildStatus.Complete

    @property
    def version(self):
        """Source-package version used for the build"""
        return self.package.definition.get_build_version(self)

    def update(self, status, message=None):
        """Update the build's status."""
        if message == None:
            message = BuildStatus.default_message(status)
        msg = BuildMessage(status, message)
        self.messages.append(msg)

        if not chimi.settings.noact:
            self.package.package_set.save_flag = True

        sys.stderr.write(str(msg) + "\n")

class PackageDefinition(object):
    """Information about how to fetch and build a particular package."""

    name = None
    repository = None

    @classmethod
    def get_build_name(self, build):
        """
        Get a user-friendly name for build `build' of this package.

        """
        pass

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
    def get_build_name(self, build=None, charm_name=None, package=None):
        if build and not charm_name:
            charm_name = CharmDefinition.get_build_name(build)
        base = re.sub(r'/.*$', '', charm_name)

        branch = None
        if build and not 'branch' in build.config.__dict__:
            build.config.branch = package.repository.git.describe(all=True)
            branch = build.config.branch
        elif package:
            branch = package.repository.git.describe(all=True)
        else:
            raise RuntimeError('couldn\'t get current branch')

        return base + '+' + package.branch

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
        charm_build = charm.find_build(config)

        if charm_build == None:
            sys.stderr.write("No matching Charm++ build found -- building now.\n")
            charm_build = charm.build(config)
            if charm_build.status.failure:
                sys.stderr.write("\033[1;31mCharm build failed:\033[0m ChaNGa build aborted.\n")
                return None
            else:
                if not charm.have_build(charm_build):
                    charm.add_build(charm_build, replace=replace)
                package.package_set.save_flag = True

        # Ensure that the build directory exists, and cd into it.
        build_name = self.get_build_name(charm_name=charm_build.name, package=package)
        build_dir = os.path.join(builds_dir, build_name)
        if not os.path.exists(build_dir) and not chimi.settings.noact:
            os.mkdir(build_dir)

        _build = None
        if _continue:
            _build = package.find_build(config)
            if not _build:
                raise ValueError('No such build to continue')
            elif _build.compiled and not force:
                raise ValueError('Cannot continue complete build: nothing to do.')
        else:
            _build = Build(package, config)
            package.add_build(_build, replace=replace) # Register this build of the package

        if package.branch != config.branch:
            check_call(['git', 'checkout', config.branch], cwd=package.directory)

        if (not _continue) or not _build.configured:
            # Build and run a `configure` invocation
            configure_invocation = ['../../configure']
            if not 'CHARMC' in os.environ.keys():
                charmc = os.path.join(charm_build.directory, 'bin/charmc')
                configure_invocation.append('CHARMC=%s' % charmc)

            configure_invocation.extend(build_configure_flags(config))

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
                _build.update(BuildStatus.Complete)

        return _build

class CharmArchitecture(object):
    """Stores metadata for a Charm++ build architecture"""
    def __init__(self, parent, name,
                 options=None, compilers=None, fortran_compilers=None,
                 is_base=False):
        self.parent = parent
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

        """
        if isinstance(propnames, str):
            propname = propnames
            out = []
            ref = self
            while ref:
                sys.stderr.write(repr(ref)+"\n")
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
                sys.stderr.write(repr(ref)+"\n")
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


    @classmethod
    def get_build_name(self, build):
        config = build.config
        if isinstance(config,tuple):
            config = config[0]
        opts = [config.architecture]
        options = list(config.options)
        options.sort()
        opts.extend(options)
        return '-'.join(opts)

    @classmethod
    def get_build_directory(self, build):
        return os.path.join(build.package.directory, build.name)

    @classmethod
    def get_build_version(self, build):
        version_file = os.path.join(build.directory, 'tmp', 'VERSION')
        if os.path.exists(version_file):
            return file(version_file, 'r').read().strip()


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
    def load_architectures(self, directory):
        """
        Initialize CharmDefinition.Architectures.

        This method loads Charm++ architecture data -- including available
        build-options and compilers for each architecture -- from a Charm++
        package tree.

        """

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

                parent = CharmDefinition.Architectures[base_name]

            CharmDefinition.Architectures[name] = \
                CharmArchitecture(parent, name,
                                  *self.get_arch_options_and_compilers(directory, name))

    @classmethod
    def find_existing_builds(self, package, build_dir=None):
        if build_dir == None:
            build_dir = package.directory
        if len(CharmDefinition.Architectures) == 0:
            if package.definition == self:
                self.load_architectures(package.directory)
            else:
                raise RuntimeError('Cannot load architectures from non-Charm++ build tree!')
        arches = list(CharmDefinition.Architectures.keys())
        arches.sort(key=lambda x: len(x), reverse=True)

        # Find all entries under `build_dir` that match available architectures.
        arches_regex = re.compile('^(' + ('|'.join(arches)) + ')(?:-([a-z][-a-z]*))?$')
        build_dirs = filter(lambda x: arches_regex.match(x) and os.path.isdir(os.path.join(build_dir, x)),
                            os.listdir(build_dir))
        builds = []
        # Extract build architecture and options from build directory names
        for dirname in build_dirs:
            arch = arches_regex.sub(r'\1', dirname)
            opts = []
            try:
                opts = arches_regex.sub(r'\2', dirname).split('-')
            except:
                pass
            builds.append(Build(package, BuildConfig(arch, opts, {}, []),
                                initial_status=BuildStatus.PreexistingBuild))

        return builds

    @classmethod
    def build(self, package, config, _continue=False, replace=False, force=False):
        srcdir = package.directory

        if len(CharmDefinition.Architectures) == 0:
            self.load_architectures(srcdir)

        opts = []
        _build = None
        if _continue:
            _build = package.find_build(config)
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
            build_args = ['./build', 'ChaNGa', config.architecture]
            build_args.extend(config.options)
            build_args.extend(build_configure_flags(config))

        build_args.extend(config.extras)

        _build.update(BuildStatus.Compile, ' '.join(build_args))

        try:
            check_call(build_args, cwd=build_cwd)
        except subprocess.CalledProcessError:
            _build.update(BuildStatus.CompileFailed)
            return _build
        else:
            _build.update(BuildStatus.Complete)
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
        if builds == None:
            self.builds = []
            if os.path.exists(directory):
                self.add_existing_builds()
        else:
            self.builds = builds

    def __setstate__(self, state):
        self.__dict__ = state
        self._repository = None

        # Check for build directories that no longer exist, and builds with the
        # same path.
        builds_to_delete = set()
        for build in self.builds:
            if not os.path.exists(build.directory):
                builds_to_delete.add(build)

        counts = Counter([b.directory for b in self.builds])
        for _dir in counts:
            if counts[_dir] > 1:
                # Discard all but the most-recently-updated build.
                _builds = sorted(filter(lambda x: x.directory == _dir, self.builds))
                builds_to_delete.update(set(_builds[0:-1]))

        if len(builds_to_delete) > 0:
            self.builds = list(set(self.builds).difference(builds_to_delete))
            # Set a flag on the parent package-set to indicate that internal
            # state has changed.  It will save when it's ready -- if we
            # directly called its `save` method here, when it's (possibly) not
            # yet done loading, data would be lost.
            self.package_set.save_flag = True

    @property
    def branch(self):
        return re.sub(r'^heads/', '', self.repository.git.describe(all=True))

    @property
    def repository(self):
        if self._repository != None:
            return self._repository
        else:
            self._repository = git.Repo(self.directory)
            return self._repository

    def fetch(self):
        self.definition.fetch(self)

    @property
    def remotes(self):
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

        return self.definition.build(self, config, **kwargs)

    def purge_builds(self, config=None, names=None):
        """
        Purge any builds matching the supplied configuration or names/UUIDs.
        If no configuration or names are given, purge all builds.

        """
        _builds = None
        if config:
            _builds = self.find_builds(config)
        elif names:
            _builds = filter(lambda _build: _build.name in names or str(_build.uuid) in names,
                             self.builds)
        else:
            _builds = list(self.builds)

        for _build in _builds:
            sys.stderr.write("%s build \"%s\"\n" % ('purging' if not chimi.settings.noact else 'would purge', _build.name))
            if not chimi.settings.noact:
                shutil.rmtree(_build.directory)
                self.builds.remove(_build)

    def find_builds(self, config):
        """Find all builds matching `config` for this package instance."""
        if not isinstance(config,BuildConfig):
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
                for pkg in self.packages:
                    if '_repository' in self.packages[pkg].__dict__:
                        repos[pkg] = self.packages[pkg]._repository
                        del self.packages[pkg]._repository

                file(os.path.join(self.directory, PackageSet.SET_FILE),
                     'w').write(yaml.dump(self))

                for pkg in repos:
                    self.packages[pkg]._repository = repos[pkg]

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
            out.save()

        return out
