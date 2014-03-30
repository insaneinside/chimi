# chimi: a companion tool for ChaNGa: script performance utilities
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

"""Utilities for tracking Chimi's responsiveness"""

import sys
import time

class TimedAction(object):
    """An action timed with `TimeTable`."""
    def __init__(self, description=None, verbose=False):
        self.description = description
        self.verbose = verbose

    def __enter__(self):
        self.start_time = time.clock()
        if self.verbose:
            sys.stderr.write('[+%.03fs] '%(self.start_time)
                             + self.description + '... ')
        return self

    def __exit__(self, *args):
        self.end_time = time.clock()
        if self.verbose:
            sys.stderr.write('%.03fs\n' % (self.time))

    @property
    def time(self):
        return self.end_time - self.start_time

    def __str__(self):
        return '%s %.05fs' % ((self.description|'').lower(), self.time)

class TimeTable(object):
    """Provides an easy way to time different parts of a process."""

    def __init__(self, verbose=False):
        self.verbose = verbose
        self.actions = []

    def total(self):
        return sum([a.time for a in self.actions])

    def time(self, description):
      self.actions.append(TimedAction(description, self.verbose))
      return self.actions[-1]
