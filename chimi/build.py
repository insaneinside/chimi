# chimi: a companion tool for ChaNGa: build-related classes
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

"""
Build-related classes for Chimi.

"""

__author__    = 'Collin J. Sutton'
__copyright__ = 'Copyright (C) 2014 Collin J. Sutton'
__license__   = 'GPLv2'


import os
import sys
import time
import uuid
import datetime

import chimi
import chimi.settings

__all__ = [ 'InvalidArchitectureError', 'InvalidBuildOptionError',
            'BuildMessage', 'BuildStatus', 'BuildConfig', 'Build' ]

class InvalidArchitectureError(chimi.Error):
    """
    Error type thrown when an attempt is made to create a BuildConfig with an
    invalid architecture name.

    """
    def __init__(self, archname, qualifier=None):
        self.architecture = archname
        self.qualifier = qualifier
    @property
    def message(self):
        return '%s%s`%s\' is not a valid Charm++ build architecture.' % \
            (self.qualifier if self.qualifier else '',
             ' ' if self.qualifier else '',
             self.architecture)

class InvalidBuildOptionError(chimi.Error):
    """
    Error type thrown when a unknown build option is specified when creating a
    BuildConfig.

    """
    def __init__(self, package, option, raw_option=None):
        self.package = package
        self.option = option
        self.raw_option = raw_option if raw_option != option else None

    @property
    def message(self):
        return '`%s\' %sis not a valid %s.' % \
            (self.option,
             ('(specified as `%s\') ' % self.raw_option) \
                 if self.raw_option else '',
             'Charm++ component or configuration option' if \
                 self.package.definition == chimi.core.CharmDefinition \
                 else 'Charm++ component or ChaNGa configuration option')

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
        if chimi.settings.relative_message_timestamps:
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

    def __lt__(self, other):
        return self.time < other.time

class BuildStatus:
    """A recorded build status"""
    value = None
    def __init__(self, value):
        self.value = value

    def __lt__(self, other):
        return isinstance(other, BuildStatus) and self.value < other.value

    def __gt__(self, other):
        return isinstance(other, BuildStatus) and self.value > other.value

    def __eq__(self, other):
        return isinstance(other, BuildStatus) and self.value == other.value

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
del i

class BuildConfig(object):
    """
    Records information about the flags and arguments used during a package
    build.

    """
    @classmethod
    def create(self, package, arch=None, opts=None, extras=None, branch=None,
               ignore_unknown_options=False):
        """
        Create a build configuration for the given package instance.

        package : chimi.core.Package

            The package for which the build configuration is being created.

        arch : None, str

            User-specified architecture name.

        opts : None, str, list<str>

            String or list of strings containing comma-separated build options.

        extras : None, list<str>

            List of extra build/configure arguments.

        branch : None, str

            Name of the repository branch to use for the build.

        ignore_unknown_options : bool

            Whether an error should be thrown for unknown build options.

        """
        package_set = package.package_set
        arch_name = arch
        arch = None
        chose_architecture = False
        completed_architecture = False
        available_arch_options = None
        available_configure_options = None

        # Load architecture definitions if not already loaded.
        if not len(chimi.core.CharmDefinition.Architectures) > 0:
            chimi.core.CharmDefinition.load_architectures(package_set.packages['charm'])

        if not arch_name:
            arch_name = chimi.config.get_architecture()
            chose_architecture = True
        elif arch_name in chimi.core.CharmDefinition.Architectures and\
                chimi.core.CharmDefinition.Architectures[arch_name].is_base:
            # Shorthand (base arch) name given.  Fill it in for the user.
            arch_name = chimi.config.get_architecture(arch_name)
            completed_architecture = True

        if not arch_name in chimi.core.CharmDefinition.Architectures:
            # No such name even exists, either as a base architecture *or* a
            # build architecture.  Complain at the user.
            qualifier = None
            if chose_architecture:
                qualifier = 'Auto-selected'
            elif completed_architecture:
                qualifier = 'Auto-completed'
            raise InvalidArchitectureError(arch_name, qualifier)
        else:
            arch = arch_name

        available_arch_options = chimi.core.CharmDefinition.Architectures[arch_name].all_options
        available_configure_options = package.definition.get_configure_options(package)

        if isinstance(opts, basestring):
            opts = [opts]
        # The 'options' option to `build` takes a comma-separated list of Charm++
        # "build options" (i.e. optional component names), `configure' --enable-*
        # options ("features"), and --with-* options ("settings").
        #
        # Separate them.
        negate_components = []
        negate_features = []
        negate_settings = []
        components = []
        features = {}
        settings = {}

        options_ary = []
        for elt in opts:
            options_ary.extend(filter(lambda x: len(x) > 0, elt.split(',')))
        for opt in options_ary:
            name, value = opt, True

            if '=' in opt:
                name, value = opt.split('=', 1)

            if opt[0] == '-':
                assert(not '=' in opt)
                name = opt[1:]
                value = False

            if name in available_arch_options:
                assert(not name in available_configure_options or
                       available_configure_options[name].kind == 'with')
                if value is False:
                    negate_components.append(name)
                else:
                    components.append(name)
            elif name in available_configure_options:
                co = available_configure_options[name]
                if co.kind == 'enable':
                    if value is False and co.default == False:
                        negate_features.append(name)
                    else:
                        features[name] = value
                else:
                    assert(co.kind == 'with')
                    if value is False and co.default == False:
                        negate_settings.append(name)
                    else:
                        settings[name] = value
            elif not ignore_unknown_options:
                raise InvalidBuildOptionError(package, name, opt)
        kwargs={'package': package,
                'negations': (negate_components, negate_features, negate_settings),
                'source_opts': opts}

        if branch:
            kwargs['branch'] = branch

        # Load the host-data file, and if it exists use it to construct the build
        # configuration.
        hi = chimi.config.HostConfig.load()

        if hi != None:
            return chimi.build.BuildConfig(hi.build,
                                           arch, components, features, settings,
                                           extras, **kwargs)
        else:
            return chimi.build.BuildConfig(arch, components, features, settings,
                                           extras, **kwargs)



    def __init__(self, *args, **kwargs):
        """
        Initialize a new build configuration.

        overload: __init__(config<chimi.core.HostBuildConfig>, ...)

            Initialize using the default settings in the given host-build
            configuration.  If additional arguments are given, they are applied
            as described in the next overload before the given host-build
            configuration is applied.

        overload: __init__(arch<str>, components<list>, features<list>, settings<dict>,
                           extras<list>, branch<str>=None)

           Initialize without any host-default values.

        """
        import chimi.config
        if not isinstance(args, list):
            args = list(args)

        if len(args) > 0 and isinstance(args[0], chimi.config.HostBuildConfig):
            self.host_build_config = args.pop(0)
            self.__init__(*args, **kwargs)
            negations = kwargs['negations'] if 'negations' in kwargs else ([], [], [])
            self.host_build_config.apply(self, negations)
        else:
            arch=chimi.config.get_architecture()
            components = []
            features = {}
            settings = {}
            extras=[]
            branch=None

            if len(args) > 0:
                arch = args.pop(0)
            if len(args) > 0:
                components = args.pop(0)
            if len(args) > 0:
                features = args.pop(0)

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

            if 'source_opts' in kwargs:
                self.source_opts = kwargs['source_opts']

            if 'package' in kwargs:
                self.package = kwargs['package']
                if not self.branch:
                    self.branch = self.package.branch

            if isinstance(arch, str) or isinstance(arch, chimi.core.CharmArchitecture):
                self.architecture = arch
                self.components = components if components else []
                self.features = features if features else {}
                self.settings = settings if settings else {}
                self.extras = extras if extras else []
                if 'cuda' in self.components:
                    cuda_dir = chimi.core.get_cuda_dir()
                    if cuda_dir != None:
                        self.settings['cuda'] = cuda_dir
            else:
                self.architecture = chimi.config.get_architecture()
                self.components = []
                self.features = []
                self.settings = {}
                self.extras = []

        self.components.sort()
        self.extras = list(set(self.extras))
        self.extras.sort()

    def __str__(self):
        brstr = ''
        if self.branch:
            brstr = ' branch=%s'%self.branch
        return '<%s:%s arch=%s components=%s features=%s settings=%s extras=%s%s>' % \
            (self.__class__.__name__, self.package.definition.name, self.architecture,
             self.components, self.features, self.settings,
             self.extras, brstr)

    def __eq__(self, other):
        if id(self) == id(other):
            return True
        elif not isinstance(other, BuildConfig):
            return False
        else:
            return self.architecture == other.architecture and \
                self.components == other.components and \
                self.features == other.features and \
                self.settings == other.settings and \
                self.extras == other.extras and \
                self.branch == other.branch and \
                self.package.definition.name == other.package.definition.name

class Build(object):
    """Information about a build of a particular Package instance"""

    def __init__(self, pkg, config,
                 initial_status=BuildStatus.Unconfigured, initial_message=None,
                 _uuid=None, name=None, messages=None):
        self.uuid = uuid.uuid1()
        self.package = pkg
        self.config = config

        if not 'branch' in self.config.__dict__ or not self.config.branch in self.package.branches:
            self.config.branch = self.package.branch

        if _uuid == None and name == None and messages == None:
            if self.package.definition == chimi.core.ChaNGaDefinition:
                self.name = pkg.definition.get_build_name(build=self,
                                                          charm_name=chimi.core.CharmDefinition.get_build_name(self),
                                                          package=self.package)
            else:
                self.name = pkg.definition.get_build_name(self)

            self.messages = [BuildMessage(initial_status, initial_message)]
        else:
            self.uuid = _uuid
            self.name = name
            self.messages = messages

        self.directory = pkg.definition.get_build_directory(self)
        assert(os.path.basename(self.directory) == self.name)

    @property
    def status(self):
        """
        Build's current status.  This returns the status associated with the
        most recent build message.

        """
        return self.messages[-1].status

    @property
    def configured(self):
        """
        Whether the build has been explicitly configured, successfully.

        """
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

    def __lt__(self, other):
        """Provides comparison based on time of most-recent build message."""
        return self.messages[-1].time < other.messages[-1].time
