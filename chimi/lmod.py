# chimi: a companion tool for ChaNGa: `lmod` integration
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
import sys
import types
import subprocess

class LModModule(types.ModuleType):
    @property
    @classmethod
    def available(self):
        return 'LMOD_CMD' in os.environ

    @classmethod
    def load(self, x, version=None):
        if version != None:
            x = "%s/%s" % (x, version)
            out = subprocess.check_output([os.environ['LMOD_CMD'], 'python', 'load', x])
            exec out

# Override the `chimi.lmod` reference (which normally refers to the scope of
# this file) with LModModule.
sys.modules['chimi.lmod'] = LModModule
