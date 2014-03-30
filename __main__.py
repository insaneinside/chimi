#!/usr/bin/env python

# chimi: a companion tool for ChaNGa: entry-point script file
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
import sys
__dir__ = os.path.dirname(os.path.abspath(__file__))
parentdir = os.path.dirname(__dir__)
if os.path.exists(os.path.join(parentdir, 'Makefile')):
    sys.path.insert(0, parentdir)

import chimi.command
exit(chimi.command.main())
