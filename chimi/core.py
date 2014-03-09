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
import datetime
import textwrap
import threading
import subprocess

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

class CommandError(Exception):
    pass

class CommandUsageError(CommandError,ValueError):
    def __init__(self, cmd):
        self.command = cmd
        super(ValueError, self).__init__('Missing required arguments to "%s".\nUsage: %s' % (cmd.name, cmd.usage))

class SubcommandError(CommandError, NotImplementedError):
    def __init__(self, cmd, subcmd):
        self.command = cmd
        self.subcommand = subcmd
        super(NotImplementedError, self).__init__('Command `%s\' has no such subcommand, `%s\'' % (cmd.name, subcmd))

class Command(object):
    """Describes a program command"""

    def __init__(self, name, args, brief, options, detail,
                 callback=None,
                 subcommands=None):
        self._name = name
        self.arguments_usage = args
        self.options = options
        self.help_brief = brief
        self.help_detail = detail
        self.callback = callback
        self.hidden = name[0] == '*'
        self.required_arg_count = 0
        self.subcommands=subcommands

        self.parent = None
        if subcommands != None:
            for cmd in self.subcommands:
                cmd.parent = self
        else:
            self.subcommands = []

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
    def full_name_list(self):
        """Get the "full name" of the command, including parent command names."""
        parts = []
        part = self
        while part != None:
            parts.insert(0, part.name)
            part = part.parent
        return parts

    @property
    def usage(self):
        """Usage string for this command"""

        parts = self.full_name_list
        parts.insert(0, chimi.command.basename)

        if len(self.options) > 0:
            parts.append('[OPTION]...')
        parts.extend(self.arguments_usage)

        return ' '.join(parts)

    @property
    def short_usage(self):
        """Short usage string containing only command name and arguments"""
        return self.name + ((' ' + ' '.join(self.arguments_usage))
                            if isinstance(self.arguments_usage, list)
                            else '')

    @property
    def help(self):
        """Detailed `help` output string for this command"""
        return \
            "\n".join([chimi.option.OptionParser.format_help(self.options,
                                                             self.usage,
                                                             self.help_brief),
                       self.help_detail + "\n" if self.help_detail else ''])

    @property
    def num_args(self):
        """Maximum number of arguments accepted"""
        return len(self.arguments_usage)

    def call(self, opts={}, args=[], kwargs={}):
        """Invoke the sub-command"""
        opts_out = opts
        subcommand_dict = {}
        for cmd in self.subcommands:
            subcommand_dict[cmd.name] = cmd

        if len(self.options) > 0:
            options = chimi.OptionParser.flatten(self.options)

            def impromptu_help(self):
                sys.stdout.write(self.help)
                exit(0)

            options.append(chimi.Option('h', 'help', 'Show help for the %s command' % self.name)\
                            .handle(lambda: impromptu_help(self)))
            stop_set = subcommand_dict.keys()
            opts_out = chimi.OptionParser.handle_options(options, args, stop_set)


        if len(self.subcommands) == 0:
            if len(args) < self.required_arg_count:
                raise CommandUsageError(self)
            return self.callback(opts_out, *args, **kwargs)
        else:
            if args[0] in subcommand_dict:
                cmd = subcommand_dict[args[0]]
                del args[0]

                if len(args) < cmd.required_arg_count:
                    raise CommandUsageError(cmd)
                elif self.callback != None:
                    opts_out, _kwargs = self.callback(opts_out, *args)
                    cmd.call(opts=opts_out, args=args, kwargs=_kwargs)
                else:
                    cmd.call(opts=opts_out, args=args)
            else:
                raise SubcommandError(self, args[0])

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

    def __init__(self, pkg, config,
                 initial_status=BuildStatus.Unconfigured, initial_message=None,
                 _uuid=None, name=None, status=None, messages=None):
        self.uuid = uuid.uuid1()
        self.package = pkg
        self.config = config
        self.directory = directory

        if not 'branch' in self.config.__dict__:
            self.config.branch = self.package.branch

        if _uuid == None and name == None and status == None and messages == None:
            if self.package.definition == ChaNGaDefinition:
                self.name = pkg.definition.get_build_name(charm_name=CharmDefinition.get_build_name(self),
                                                          package=self.package)
            else:
                self.name = pkg.definition.get_build_name(self)

            if not self.directory:
                self.directory = pkg.definition.get_build_directory(self)

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

        # Ensure that the build directory exists, and cd into it.
        build_name = self.get_build_name(charm_name=charm_build.name, package=package)
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
            _build = Build(package, config)
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
            builds.append(Build(package, BuildConfig(arch, opts, {}, []),
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
            _build = Build(package, config)
            package.add_build(_build, replace=replace) # Register this build of the package

        if _continue:
            os.chdir(os.path.join(_build.directory, 'tmp'))
            build_args = ['gmake', 'basics', 'ChaNGa']
        else:
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
    def branch(self):
        return re.sub(r'^heads/', '', self.repository.git.describe(all=True))

    @property
    def repository(self):
        if self._repository != None:
            return self._repository
        else:
            self._repository = git.Repo(self.directory)
            return self._repository

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
        self.mutex = threading.Lock()
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
