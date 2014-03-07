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
import sys
import yaml
import uuid
import time
import subprocess
import datetime
import textwrap

import chimi.util

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
    return out

class Command(object):
    """Describes a program command"""

    def __init__(self, name, args, brief, options, detail, func):
        self._name = name
        self.arguments_usage = args
        self.options = options
        self.help_brief = brief
        self.help_detail = detail
        self.func = func
        self.hidden = name[0] == '*'
        self.required_arg_count = 0
        
        for arg in self.arguments_usage:
            if arg[0] != '[':
                self.required_arg_count += 1
    @property
    def name(self):
        """Name of this command"""
        return self._name

    @property
    def brief(self):
        """Brief help string for this command"""
        return self.help_brief

    @property
    def detail(self):
        """Detailed help string for this command"""
        return self.help_detail

    @property
    def usage(self):
        """Usage string for this command"""
        parts = [self.name]
        if len(self.options) > 0:
            parts.append('[OPTION]...')
        parts.extend(self.arguments_usage)
        return ' '.join(parts)

    @property
    def help(self):
        """Detailed `help` output string for this command"""
        desc = self.help_brief
        if self.help_detail:
            desc = "%s\n\n%s" % (self.help_brief, self.help_detail)
        return chimi.option.OptionParser.format_help(self.options,
                                                     ' '.join([sys.argv[0], self.usage]),
                                                     desc)

    @property
    def num_args(self):
        """Maximum number of arguments accepted"""
        return len(self.arguments_usage)

    def call(self, aa):
        """Invoke the sub-command"""
        opts_out = {}
        if len(self.options) > 0:
            opts = list(self.options)
            opts.append(chimi.Option('h', 'help', 'Show help for the %s command' % self.name)\
                            .handle(lambda:  sys.stdout.write(self.help)))
            opts_out = chimi.OptionParser.handle_options(self.options, aa)

        if len(aa) < self.required_arg_count:
            sys.stderr.write("%s\n" % self.usage)
            raise ValueError('Missing required arguments to "%s"' % self.name)
        
        return self.func(opts_out, *aa)


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

        return "%12s \033[1;%dm%s:\033[0m %s" % (time_string,
                                                 chimi.util.ANSI_COLORS[color],
                                                 self.status.name,
                                                 message)

class BuildStatus:
    """A recorded build status"""
    value = None
    def __init__(self, value):
        self.value = value

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
    def __init__(self, architecture, options, settings, extras):
        self.architecture = architecture
        self.options = options
        self.settings = settings
        self.extras = extras
        if 'cuda' in self.options:
            settings['cuda'] = get_cuda_dir()

    def __str__(self):
        return str((self.architecture, self.options, self.settings, self.extras))

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

    def __init__(self, pkg, directory, config,
                 initial_status=BuildStatus.Unconfigured, initial_message=None,
                 _uuid=None, name=None, status=None, messages=None):
        self.uuid = uuid.uuid1()
        self.package = pkg
        self.config = config
        self.directory = directory
        if _uuid == None and name == None and status == None and messages == None:
            self.name = pkg.definition.get_build_name(self.config)
            self.status = initial_status
            self.messages = [BuildMessage(initial_status, initial_message)]
        else:
            self.uuid = _uuid
            self.name = name
            self.status = status
            self.messages = messages

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

        self.status = status
        if message == None:
            message = BuildStatus.default_message(status)        
        msg = BuildMessage(status, message)
        self.messages.append(msg)
        self.package.package_set.save_flag = True

        sys.stderr.write(str(msg) + "\n")

class PackageDefinition(object):
    """Information about how to fetch and build a particular package."""

    name = None
    repository = None

    @classmethod
    def get_build_name(self, config):
        """
        Get a user-friendly name for a build of this package with build config
        `config`.


        """
        pass

    def __init__(self, name, repo):
        self.name = name
        self.repository = repo

    @classmethod
    def fetch(self, package):
        """Fetch sources for the defined package and """
        srcdir = package.directory
        if not os.path.exists(srcdir):
            parent_dir = os.path.dirname(srcdir)
            if not os.path.exists(parent_dir):
                os.makedirs(parent_dir)
            os.chdir(parent_dir)
            subprocess.check_call(['git', 'clone', self.repository, srcdir])
        else:
            os.chdir(srcdir)
            subprocess.check_call(['git', 'pull', 'origin'])
        

class ChaNGaDefinition(PackageDefinition):
    """Package definition for ChaNGa"""
    name = 'ChaNGa'

    @classmethod
    def __init__(self):
        super(ChaNGaDefinition, self).__init__('ChaNGa', globals()['DEFAULT_REPOSITORIES']['changa'])

    @classmethod
    def get_build_name(self, config):
        return CharmDefinition.get_build_name(config)

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
    def build(self, package, config, _continue=False, replace=False):
        srcdir = package.directory
        os.chdir(srcdir)
        if not os.path.exists('builds'):
            os.mkdir('builds')

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

        build_name = charm_build.name
        build_dir = os.path.join(package.directory, 'builds')
        if not os.path.exists(build_dir):
            os.mkdir(build_dir)
        build_dir = os.path.join(build_dir, build_name)
        if not os.path.exists(build_dir):
            os.mkdir(build_dir)
        os.chdir(build_dir)

        _build = None
        if _continue:
            _build = package.find_build(config)
            if not _build:
                raise ValueError('No such build to continue')
            elif _build.compiled:
                raise ValueError('Cannot continue complete build: nothing to do.')
        else:
            _build = Build(package, os.path.join(srcdir, build_dir), config)
            package.add_build(_build, replace=replace) # Register this build of the package

        if (not _continue) or not _build.configured:
            # Build and run a `configure` invocation
            configure_invocation = ['../../configure']
            if not 'CHARMC' in os.environ.keys():
                charmc = os.path.join(charm_build.directory, 'bin/charmc')
                configure_invocation.append('CHARMC=%s' % charmc)

            configure_invocation.extend(build_configure_flags(config))

            _build.update(BuildStatus.Configure, ' '.join(configure_invocation))
            try:
                subprocess.check_call(configure_invocation)
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
                subprocess.check_call(['make'])
            except subprocess.CalledProcessError:
                _build.update(BuildStatus.CompileFailed)
            else:
                _build.update(BuildStatus.Complete)

        return _build

class CharmDefinition(PackageDefinition):
    """Package definition for Charm++"""
    Architectures = []
    name = 'Charm++'

    def __init__(self):
        super('Charm++', DEFAULT_REPOSITORIES['charm'])

    @classmethod
    def get_build_name(self, config):
        if isinstance(config,tuple):
            config = config[0]
        opts = [config.architecture]
        options = list(config.options)
        options.sort()
        opts.extend(options)
        return '-'.join(opts)

    @classmethod
    def get_build_version(self, build):
        version_file = os.path.join(build.directory, 'tmp', 'VERSION')
        if os.path.exists(version_file):
            return file(version_file, 'r').read().strip()

    @classmethod
    def load_architectures(self, directory):
        # We *could* make a native Python version of this shell command, but
        # since we're trying to recreate the same values that Charm++'s "build"
        # script comes up with, it's probably better to just copy the command
        # straight out of that script.
        run = "cd %s ; ls -1 | egrep -v '(^CVS)|(^shmem$)|(^mpi$)|(^sim$)|(^net$)|(^multicore$)|(^util$)|(^common$)|(^uth$)|(^conv-mach-fix.sh$)|(^win32$)|(^win64$)|(^paragon$)|(^lapi$)|(^cell$)|(^gemini_gni$)|(^pami$)|(^template$)|(^cuda$)'" % (os.path.join(directory, 'src/arch'))
        out = subprocess.check_output(run, shell=True)
        CharmDefinition.Architectures = out.split("\n")

    @classmethod
    def find_existing_builds(self, package, build_dir=None):
        if build_dir == None:
            build_dir = package.directory
        if len(CharmDefinition.Architectures) == 0:
            if package.definition == self:
                self.load_architectures(package.directory)
            else:
                raise RuntimeError('Cannot load architectures from non-Charm++ build tree!')
        arches = list(CharmDefinition.Architectures)
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
            builds.append(Build(package, os.path.join(build_dir, dirname),
                                BuildConfig(arch, opts, {}, []),
                                initial_status=BuildStatus.PreexistingBuild))
            
        return builds
        
    @classmethod
    def build(self, package, config, _continue=False, replace=False):
        srcdir = package.directory
        os.chdir(srcdir)

        if len(CharmDefinition.Architectures) == 0:
            self.load_architectures(srcdir)

        opts = []
        _build = None
        if _continue:
            _build = package.find_build(config)
            if not _build:
                raise ValueError('No such build to continue')
        else:
            _build = Build(package, os.path.join(package.directory, self.get_build_name(config)),
                           config)
            package.add_build(_build, replace=replace) # Register this build of the package

        build_args = ['./build', 'ChaNGa', config.architecture]
        build_args.extend(config.options)
        build_args.extend(build_configure_flags(config))
        build_args.extend(config.extras)
            
        _build.update(BuildStatus.Compile, ' '.join(build_args))
        try:
            subprocess.check_call(build_args)
        except subprocess.CalledProcessError:
            _build.update(BuildStatus.CompileFailed)
            return _build
        else:
            _build.update(BuildStatus.Complete)
            return _build
                               

class Package(object):
    """A single package instance."""

    def __init__(self, package_set, definition, directory, builds=None):
        self.package_set = package_set
        self.definition = definition
        self.directory = directory
        if builds == None:
            self.builds = []
            if os.path.exists(directory):
                self.add_existing_builds()
        else:
            self.builds = builds

    def __setstate__(self, state):
        self.__dict__ = state

        # Check for build directories that no longer exist.
        builds_to_delete = set()
        for build in self.builds:
            if not os.path.exists(build.directory):
                builds_to_delete.add(build)
        if len(builds_to_delete) > 0:
            self.builds = list(set(self.builds).difference(builds_to_delete))
            # Set a flag on the parent package-set to indicate that internal
            # state has changed.  It will save when it's ready -- if we
            # directly called its `save` method here, when it's (possibly) not
            # yet done loading, data would be lost.
            self.package_set.save_flag = True

    @property
    def remotes(self):
        cwd = os.getcwd()
        out = []
        if os.path.exists(self.directory):
            os.chdir(self.directory)
            url_regexp = re.compile(r'^\s*Fetch URL: ')
            git_remote_names = subprocess.check_output(['git', 'remote']).split("\n")
            for name in git_remote_names:
                if name == '':
                    continue
                gitremote = subprocess.check_output(['git', 'remote', 'show', '-n', name])
                url_line = filter(lambda x: url_regexp.match(x), gitremote.split("\n"))[0]
                out.append((name, url_regexp.sub('', url_line).strip()))
            os.chdir(cwd)
        return out


    def build(self, *args):
        return self.definition.build(self, *args)

    def find_build(self, config):
        if not isinstance(config,BuildConfig):
            raise ValueError('Invalid argument type `%s\' to `find_build`'%type(config))
        matches = filter(lambda x: x.config == config, self.builds)
        if len(matches) > 0:
            return matches[0]
        else:
            return None

    def have_build(self, obj):
        if isinstance(obj, Build):
            return self.find_build(obj.config) != None
        else:
            return self.find_build(obj) != None

    def add_build(self, _build, replace=False):
        owned = self.find_build(_build.config)
        if owned == None or owned.directory != _build.directory:
            self.builds.append(_build)
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
        changa_path = os.path.join(directory, 'changa')
        charm_path = os.path.join(directory, 'charm')

        changa = None
        charm = None

        if os.path.exists(os.path.join(directory, charm_path)):
            charm =  Package(self, CharmDefinition, charm_path)
        if os.path.exists(changa_path):
            changa = Package(self, ChaNGaDefinition, changa_path)

        self.packages = { 'charm': charm, 'changa': changa }

    def __del__(self):
        if 'save_flag' in self.__dict__:
            if self.save_flag:
                self.save()

    def save(self):
        del self.__dict__['save_flag']
        file(os.path.join(self.directory, PackageSet.SET_FILE),
             'w').write(yaml.dump(self))
        self.save_flag = False

    def __getitem__(self, name):
        return self.packages[name]

    @classmethod
    def load(self, directory):
        out = yaml.load(file(os.path.join(directory, PackageSet.SET_FILE),
                             'r').read())
        if 'save_flag' in out.__dict__:
            out.save()

        return out
