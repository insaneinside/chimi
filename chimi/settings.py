# chimi: a companion tool for ChaNGa: settings and generic constants
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
DEFAULT_REPOSITORIES={
    'charm' : 'http://charm.cs.uiuc.edu/gerrit/charm',
    'changa' : 'http://charm.cs.uiuc.edu/gerrit/changa',
    'utility' : 'http://charm.cs.illinois.edu/gerrit/cosmo/utility.git'
    }
"""Default URIs for remote Git repositories"""



noact = False
"""
Dry-run flag.  When `noact' is set, no files will be changed and no external
processes that change files will be run.  [This is a _contract_: all `chimi'
code must obey it or face excision.]

"""
