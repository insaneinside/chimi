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

import chimi
import chimi.settings

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
            self.__init__(*args)
            self.host_build_config.apply(self)
        else:
            arch=chimi.config.get_architecture()
            components = []
            features = []
            settings = {}
            extras=[]
            branch=None

            if len(args) > 0:
                arch = args.pop(0)
            if len(args) > 0:
                components = args.pop(0)
            if len(args) > 0:
                components = args.pop(0)

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
                self.options = options if options else []
                self.settings = settings if settings else {}
                self.extras = extras if extras else []
                if 'cuda' in self.options:
                    cuda_dir = chimi.core.get_cuda_dir()
                    if cuda_dir != None:
                        self.settings['cuda'] = cuda_dir
            else:
                self.architecture = chimi.config.get_architecture()
                self.options = []
                self.settings = {}
                self.extras = []

        self.options.sort()
        self.extras.sort()

    def __str__(self):
        brstr = ''
        if self.branch:
            brstr = ' branch=%s'
        return '<%s:%s arch=%s options=%s settings=%s extras=%s>' % \
            (self.__class__.__name__, brstr, self.architecture, self.options, self.settings,
             self.extras)

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
