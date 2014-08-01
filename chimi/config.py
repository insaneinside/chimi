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

"""Configuration-related classes for Chimi."""

from __future__ import print_function

__author__    = 'Collin J. Sutton'
__copyright__ = 'Copyright (C) 2014 Collin J. Sutton'
__license__   = 'GPLv2'

import os
import re
import sys
import socket

import chimi.util

DEFAULT_COMMS_TYPE='net'
"""Default Charm++ communications transport to use"""

def get_architecture(base_arch=DEFAULT_COMMS_TYPE):
    """Get the likely Charm++ platform/architecture for the current host"""
    osname, hostname, discard, discard, machname = os.uname()
    return '-'.join([base_arch, osname.lower(), machname.lower()])

def make_dict_keys_snake_case_recursive(d):
    """
    Recursively convert a dict's keys, **in-place**, from spinal-case to
    snake-case.

    """
    keys = d.keys()
    for k in keys:
        if '-' in k:
            k2 = k.replace('-', '_')
            d[k2] = d[k]
            del d[k]
            if isinstance(d[k2], dict):
                make_dict_keys_snake_case_recursive(d[k2])
    return d

class HostBuildOption(object):
    """
    Default values for a build option loaded from a host configuration file

    """
    def __init__(self, name, enable_by_default=False,
                 prerequisite_components=[], apply_settings={}, apply_extras=[]):
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
            self.prerequisite_components = prerequisite_components
            self.apply_settings = apply_settings
            self.apply_extras = apply_extras
        elif isinstance(name, tuple):
            assert(len(name) == 2 and isinstance(name[0], str) and isinstance(name[1], dict))

            self.name = name[0]
            d = name[1]

            self.enable_by_default = False
            if 'default' in d:
                self.enable_by_default = d['default']
            elif 'enable_by_default' in d:
                self.enable_by_default = d['enable_by_default']
            assert(type(self.enable_by_default) == bool)

            self.prerequisite_components = []
            for po in ['components', 'prerequisites', 'prerequisite_components']:
                if po in d:
                    self.prerequisite_components = d[po]
            assert(type(self.prerequisite_components) == list)

            self.apply_settings = {}
            for _as in ['settings', 'apply_settings']:
                if _as in d:
                    self.apply_settings = d[_as]
            assert(type(self.apply_settings) == dict)

            self.apply_extras = []
            for ae in ['extras', 'apply_extras']:
                if ae in d:
                    self.apply_extras = d[ae]
            assert(type(self.apply_extras) == list)

    def __str__(self):
        return str(self.__dict__)

class HostBuildConfig(object):
    """Build configuration values for a specific host."""
    def __init__(self, arch=None, components=None):
        if isinstance(arch, dict) and components == None:
            d = arch

            if 'default_architecture' in d:
                self.default_architecture = d['default_architecture']
            else:
                self.default_architecture = chimi.config.get_architecture()

            self.components = {}
            if 'components' in d:
                for oname in d['components']:
                    self.components[oname] = HostBuildOption((oname, d['components'][oname]))
        elif isinstance(arch, str) and isinstance(components, dict):
            self.default_architecture = arch
            for oname in components:
                self.components[oname] = HostBuildOption((oname, components[oname]))
        else:
            self.architecture = chimi.config.get_architecture()
            self.components = {}


    def apply(self, build_config, negations):
        """
        Apply the host-specific build configuration to an individual package's
        build configuration

        build_config: the build configuration to modify

        negations: Tuple of (components, features, settings) that should
            not be applied.

        """
        import chimi.build
        assert(isinstance(build_config, chimi.build.BuildConfig))
        negated_components, negated_features, negated_settings = negations
        arch = build_config.architecture
        if isinstance(arch, basestring):
            arch = chimi.core.CharmDefinition.Architectures[arch]
        arch_options = arch.all_options
        for optname in self.components:
            if optname in arch_options and not optname in negated_components:
                opt = self.components[optname]
                # Set the build option if the host data specifies it should be used
                # by default.
                if opt.enable_by_default:
                    build_config.components.append(optname)

                # If this option is set for the build (possibly by us), apply any
                # additional components/settings/extra command-line arguments
                # specified in the host-data file.
                if optname in build_config.components:
                    # Enable all prerequisites for the option.
                    build_config.components.extend(list(set(opt.prerequisite_components).
                                                        difference(set(build_config.components))))

                    # Apply settings defined by the host configuration.
                    if len(opt.apply_settings) > 0:
                        for sname in opt.apply_settings:
                            build_config.settings[sname] = opt.apply_settings[sname]

                    # Apply extra build arguments specified by the host
                    # configuration.
                    if len(opt.apply_extras) > 0:
                        build_config.extras.extend(opt.apply_extras)
        build_config.components.sort()

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
        elif all([chimi.util.which(name) for name in ['srun', 'squeue', 'sbatch']]):
            return 'slurm'
        # FIXME: add detection for other job-management systems
        else:
            # 'shell' is SAGA's shell-based adaptor; it uses no job-management
            # system.
            return 'shell'

    def __init__(self, d=None):
        if isinstance(d, dict):
            make_dict_keys_snake_case_recursive(d)
            if 'job_manager' in d:
                self.manager = d['manager']
            else:
                self.manager = self.determine_job_manager()

            if 'host' in d:
                self.host = d['host']

            if 'launch' in d:
                launch = d['launch']
                make_dict_keys_snake_case_recursive(launch)
                self.launch = HostJobConfig.LaunchConfig(**launch)
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

    module_system: name of the module system in use on the host, if any.

    """

    def __init__(self, d=None, aliases=None, build=None, jobs=None):
        if isinstance(d, dict) and aliases==None and build == None and jobs == None:
            make_dict_keys_snake_case_recursive(d)
            if 'hostname' in d:
                self.hostname = d['hostname']

            if 'aliases' in d:
                self.aliases = d['aliases']
            else:
                self.aliases = []

            if 'build' in d:
                b = d['build']
                self.build = HostBuildConfig(b)
            else:
                self.build = HostBuildConfig({})

            if 'jobs' in d:
                self.jobs = HostJobConfig(d['jobs'])
            else:
                self.jobs = HostJobConfig({})

            if 'module_system' in d:
                self.module_system = d['module_system']
            else:
                self.module_system = None
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
        import yaml
        import pkg_resources

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
        import yaml
        import pkg_resources

        index = yaml.load(pkg_resources.resource_string(__name__, 'data/host-index.yaml'))
        if name in index:
            return index[name]
