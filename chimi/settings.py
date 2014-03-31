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
"""
Various global settings and flags for Chimi.  These values are not necessarily
associated with any one Chimi module.

"""

import chimi.util
DefaultRepository = chimi.util.create_struct(__name__, 'DefaultRepository',
                                             'url', 'branch')

DEFAULT_REPOSITORIES={
    'charm'   : DefaultRepository('http://charm.cs.illinois.edu/gerrit/charm.git',     'master'),
    'changa'  : DefaultRepository('http://charm.cs.illinois.edu/gerrit/cosmo/changa',  'master'),
    'utility' : DefaultRepository('http://charm.cs.illinois.edu/gerrit/cosmo/utility', 'master')
    }
"""Default URLs and branches for remote Git repositories."""



noact = False
"""
Dry-run flag.  When `noact' is set, no files will be changed and no external
processes that change files will be run.  [This is a _contract_: all `chimi'
code must obey it or face excision.]

"""


relative_message_timestamps = False
"""
When converting build messages to strings, should we use a relative time for
the timestamp?  Default False.

"""
