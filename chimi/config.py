# chimi, acompanion tool for ChaNGa: host-specific configuration
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

"""Contains configuration-related classes"""

from __future__ import print_function

import os
import re
import sys
import yaml
import socket
import pkg_resources
import chimi.core


DEFAULT_COMMS_TYPE='net'
"""Default Charm++ communications transport to use"""

def get_architecture():
    """Get the likely Charm++ platform/architecture for the current host"""
    osname, hostname, discard, discard, machname = os.uname()
    return '-'.join([DEFAULT_COMMS_TYPE, osname.lower(), machname.lower()])


class HostBuildOption(object):
    """
    Default values for a build option loaded from a host configuration file

    """
    def __init__(self, name, enable_by_default=False,
                 prerequisite_options=[], apply_settings={}, apply_extras=[]):
        """
        name: option name
        enable_by_default: whether this option should be enabled by default on
            the host
        prerequisite_options: other options required by this option
        apply_settings: settings to add to the build configuration when this
            option is enabled
        apply_extras: extra arguments to add to the build configuration when
            this option is enabled
        """
        if isinstance(name, str):
            self.name = name
            self.enable_by_default = enable_by_default
            self.prerequisite_options = prerequisite_options
            self.apply_settings = apply_settings
            self.apply_extras = apply_extras
        elif isinstance(name, tuple):
            assert(len(name) == 2 and isinstance(name[0], str) and isinstance(name[1], dict))

            self.name = name[0]
            d = name[1]

            self.enable_by_default = False
            if 'default' in d:
                self.enable_by_default = d['default']
            elif 'enable-by-default' in d:
                self.enable_by_default = d['enable-by-default']
            assert(type(self.enable_by_default) == bool)

            self.prerequisite_options = []
            for po in ['options', 'prerequisites', 'prerequisite-options']:
                if po in d:
                    self.prerequisite_options = d[po]
            assert(type(self.prerequisite_options) == list)

            self.apply_settings = {}
            for _as in ['settings', 'apply-settings']:
                if _as in d:
                    self.apply_settings = d[_as]
            assert(type(self.apply_settings) == dict)

            self.apply_extras = []
            for ae in ['extras', 'apply-extras']:
                if ae in d:
                    self.apply_extras = d[ae]
            assert(type(self.apply_extras) == list)

    def __str__(self):
        return str(self.__dict__)

class HostBuildConfig(object):
    """Build configuration values for a specific host."""
    def __init__(self, arch=None, options=None):
        if isinstance(arch, dict) and options == None:
            d = arch
            if 'architecture' in d:
                self.architecture = d['architecture']
            else:
                self.architecture = chimi.config.get_architecture()

            self.options = {}
            if 'options' in d:
                for oname in d['options']:
                    self.options[oname] = HostBuildOption((oname, d['options'][oname]))
        elif isinstance(arch, str) and isinstance(options, dict):
            self.architecture = arch
            for oname in options:
                self.options[oname] = HostBuildOption((oname, options[oname]))
        else:
            self.architecture = chimi.config.get_architecture()
            self.options = {}


    def apply(self, build_config, negated_options=[]):
        """
        Apply the host-specific build configuration to an individual package's
        build configuration

        build_config: the build configuration to modify

        negated_options: list of options that should not be applied.

        """
        assert(isinstance(build_config, chimi.core.BuildConfig))
        for optname in self.options:
            if not optname in negated_options:
                opt = self.options[optname]
                # Set the build option if the host data specifies it should be used
                # by default.
                if opt.enable_by_default:
                    build_config.options.append(optname)

                # If this option is set for the build (possibly by us), apply any
                # additional options/settings/extra command-line arguments
                # specified in the host-data file.
                if optname in build_config.options:
                    # Enable all prerequisites for the option.
                    build_config.options.extend(list(set(opt.prerequisite_options).
                                                     difference(set(build_config.options))))

                    # Apply settings defined by the host configuration.
                    if len(opt.apply_settings) > 0:
                        for sname in opt.apply_settings:
                            build_config.settings[sname] = opt.apply_settings[sname]

                    # Apply extra build arguments specified by the host
                    # configuration.
                    if len(opt.apply_extras) > 0:
                        build_config.extras.extend(opt.apply_extras)
        build_config.options.sort()

    def __str__(self):
        return str(self.__dict__)

class HostJobConfig(object):
    """
    Information on how to run jobs on a specific host.  An instance of
    HostJobConfig currently has the following properties:

    job_manager: batch-job management system employed on the host.

    host: hostname that should be used for remote job execution via SSH.

    """
    LaunchConfig = chimi.util.create_struct(__name__, 'LaunchConfig',
                                            mpiexec=False,
                                            remote_shell=None,
                                            runscript=None)


    @classmethod
    def determine_job_manager(self):
        if all([chimi.util.which(name) for name in ['qacct', 'qconf', 'qdel', 'qstat', 'qsub']]):
            return 'sge'
        # FIXME: add detection for other job-management systems
        else:
            # 'fork' is SAGA's shell-based adaptor; it uses no job-management
            # system.
            return 'shell'

    def __init__(self, d=None):
        if isinstance(d, dict):
            if 'job-manager' in d:
                self.manager = d['manager']
            else:
                self.manager = self.determine_job_manager()

            if 'host' in d:
                self.host = d['host']

            if 'launch' in d:
                self.launch = HostJobConfig.LaunchConfig(**d['launch'])
            else:
                self.launch = HostJobConfig.LaunchConfig()
        else:
            self.manager = self.determine_job_manager()
            self.host = 'localhost'
            self.launch = HostJobConfig.LaunchConfig()


class HostConfig(object):
    """
    Stores host-specific configuration values.

    hostname: FQDN of the current host.

    aliases: list of names that, when specified by the user, should also
        identify this host.

    build: a HostBuildConfig instance.

    jobs: a HostJobConfig instance.

    """


    def __init__(self, d=None, aliases=None, build=None, jobs=None):
        if isinstance(d, dict) and aliases==None and build == None and jobs == None:
            if 'hostname' in d:
                self.hostname = d['hostname']

            if 'aliases' in d:
                self.aliases = d['aliases']
            else:
                self.aliases = []

            if 'build' in d:
                self.build = HostBuildConfig(d['build'])
            else:
                self.build = HostBuildConfig({})

            if 'jobs' in d:
                self.jobs = HostJobConfig(d['jobs'])
            else:
                self.jobs = HostJobConfig({})
        else:
            hostname = d
            if hostname:
                self.hostname = hostname
            else:
                self.hostname = socket.gethostname()

            if aliases:
                self.aliases = aliases
            else:
                self.aliases = socket.gethostbyname_ex(self.hostname)[1]

            if build:
                self.build = build
            else:
                self.build = HostBuildConfig()

            if jobs:
                self.jobs = jobs
            else:
                self.jobs = HostJobConfig()
        
    @property
    def matches_current_host(self):
        """Check if this HostConfig instance refers to the local host."""
        return re.search(r'.*%s$' % self.hostname, socket.gethostname()) != None or \
            self.hostname == 'localhost'


    @classmethod
    def load(self, name=None):
        """
        Attempt to find and load a host-specific configuration file.  Returns
        a HostConfig instance if one was found, and None otherwise.

        name: name or alias of the host to load a configuration for.  Default:
            load a configuration for the current host.

        """

        matching_files = []
        available_files = pkg_resources.resource_listdir(__name__, 'data/host')
        available_files = [re.sub(r'\.yaml$', '', fname) for fname in available_files]

        if name == None or name == 'localhost':
            name = socket.gethostname()
        match = self.find_host_file_by_name(name)

        if match == None:
            name = name.replace('.', '-')
            matching_files = filter(lambda avf: re.match(r'.*%s$' % avf, name), available_files)
        else:
            matching_files = [match]

        if len(matching_files) > 0 and matching_files[0] != None:
            host_data_file = 'data/host/%s' % matching_files[0]
            if pkg_resources.resource_exists(__name__, host_data_file):
                return HostConfig(yaml.load(pkg_resources.resource_string(__name__, host_data_file)))
        else:
            return HostConfig()

    @classmethod
    def find_host_file_by_name(self, name):
        index = yaml.load(pkg_resources.resource_string(__name__, 'data/host-index.yaml'))
        if name in index:
            return index[name]
