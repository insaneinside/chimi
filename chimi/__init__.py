# chimi, a companion tool for ChaNGa: package __init__ file
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
Chimi root namespace.

Chimi is a companion tool for ChaNGa, the highly-parallel Charm++-based
cosmological gravitational simulation.

"""

__author__    = 'Collin J. Sutton'
__copyright__ = 'Copyright (C) 2014 Collin J. Sutton'
__license__   = 'GPLv2'


class Error(Exception):
    """
    Base for all Chimi-defined exception types.

    """
    pass

from chimi.option import Option
from chimi.option import OptionParser
from chimi.core import *
from chimi.config import *
from chimi.util import *
from chimi.sshconfig import SSHConfig

# import chimi.perfutil
# perftable = chimi.perfutil.TimeTable(True)

import chimi.transient
dependency = chimi.transient.OnDemandLoader(__name__, 'chimi.dependency')
chimi.transient.import_(__name__, 'chimi.job')
