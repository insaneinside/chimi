# chimi: a companion tool for ChaNGa: SSH configuration parser
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
from __future__ import print_function

import os
import re
import pwd
import sys

class SSHConfig(object):
    """Stores values found in a user's ~/.ssh/config"""
    KEYWORD_REGEXP = '[A-Z][a-zA-Z0-9]+'
    DEFAULTS = { 'User': pwd.getpwuid(os.getuid()).pw_name }

    # Fetch a host host-specific configuration.
    #
    # @param [String] name Hostname to search for.
    #
    # @return [Hash,nil] A Hash if there is a configuration section for the specified host,
    #   otherwise <code>nil</code>.
    def host(self, name):
        if not name in self.host_settings:
            self.host_settings[name] = {}
        return self.host_settings[name]

    ## Search for configuration value NAME (optionally for host HOST), and
    #  return the global value if not found.
    def value(self, name, host=None):
        if host != None and host in self.host_settings:
            return self.host_settings[host][name]
        elif name in self.global_settings:
            return self.global_settings[name]
        elif name in SSHConfig.DEFAULTS:
            return SSHConfig.DEFAULTS[name]

    # Load an SSH config file.
    #
    # @param [String] filename Name of the file to load.  The default value select's the current
    #   user's own SSH configuration file.
    def __init__(self, filename=os.path.join(os.environ['HOME'],  '.ssh', 'config')):
        self.host_settings = {}
        self.global_settings = {}
        self.host_settings['*'] = self.global_settings
        target = self.global_settings

        lines = file(filename, 'r').readlines()
        for l in lines:
            if not re.match(r'^\s*\#.*', l): # skip comments
                l = re.sub(r'^\s+', '', l)
                x = re.search(r'^(%s)(?:(?:\s+)|(?:\s*=\s*)|(?:=\s*))(.+)$'% SSHConfig.KEYWORD_REGEXP, l)
                if x != None:
                    x = x.groups()
                    if x[0] == 'Host':
                      if x[1] == '*':
                        target = self.global_settings
                      else:
                        self.host_settings[x[1]] = {}
                        target = self.host_settings[x[1]]
                    elif len(x) == 2:
                      target[x[0]] = x[1]
