# chimi: a companion tool for ChaNGa: miscellaneous utilities
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

"""Various misc. utility functions"""

ANSI_COLORS={
    'default': 0,
    'black': 30, 'red': 31, 'green': 32, 'yellow': 33, 'blue': 34, 'magenta': 35, 'cyan': 36, 'white': 37,
    'brightblack': 90,
    'brightred': 91,
    'brightgreen': 92,
    'brightyellow': 93,
    'brightblue': 94,
    'brightmagenta': 95,
    'brightcyan': 96,
    'brightwhite': 97
    }
ANSI_STYLES={'bold': 1, 'underline': 4, 'blink': 25}

relative_message_timestamps = False
relative_timestamp_default_siguns = 2

def wrap_text(self, _in, start_col=0, max_col=75):
    """
    Wrap text within the given column boundaries, filling the area before
    `start_col` with spaces.

    This method was created because the author was having problems with
    TextWrapper -- not necessarily because he wanted to reinvent the wheel.

    """

    width = max_col - start_col

    if len(_in) <= width:
        return _in

    strs=_in.split('\n')
    out = ''

    for s in strs:
        if out != '':
            out += "\n" + ' ' * start_col
        while len(s) > width:
            front = s[0:width]
            parts = front.rpartition(' ')
            s = parts[2].strip() + s[width:]

            front = parts[0]
            out += "%s\n%s" % (front, ' ' * start_col)
        out += s.strip()
    return out




# This function was copied from a Stack Overflow answer at
# <https://stackoverflow.com/a/377028>
def which(program):
    """
    For a given program name, determine the full path to the executable that
    would be found by shell path-search.

    """

    import os
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None

# This function was copied from a Stack Overflow answer at
# <https://stackoverflow.com/a/1551394>
def relative_datetime_string_ish(time=False):
    """
    Get a datetime object or a int() Epoch timestamp and return a
    pretty string like 'an hour ago', 'yesterday', '3 months ago',
    'just now', etc

    """
    from datetime import datetime
    now = datetime.now()
    diff = None
    if type(time) is int:
        diff = now - datetime.fromtimestamp(time)
    elif isinstance(time,datetime):
        diff = now - time 
    elif not time:
        diff = now - now

    second_diff = diff.seconds
    day_diff = diff.days

    if day_diff < 0:
        return ''

    if day_diff == 0:
        if second_diff < 10:
            return "just now"
        if second_diff < 60:
            return str(second_diff) + " seconds ago"
        if second_diff < 120:
            return  "a minute ago"
        if second_diff < 3600:
            return str( second_diff / 60 ) + " minutes ago"
        if second_diff < 7200:
            return "an hour ago"
        if second_diff < 86400:
            return str( second_diff / 3600 ) + " hours ago"
    if day_diff == 1:
        return "yesterday"
    if day_diff < 7:
        return str(day_diff) + " days ago"
    if day_diff < 31:
        return str(day_diff/7) + " weeks ago"
    if day_diff < 365:
        return str(day_diff/30) + " months ago"
    return str(day_diff/365) + " years ago"

# This one was inspired by the above function, but it's a lot more specific.
def relative_datetime_string(time, significant_units=relative_timestamp_default_siguns):
    """
    Get a shorthand representation of the time elapsed since `time` (ex. "1h52m
    3s").

    `significant_units` specifies how specific the output should be; use
    -1 to include all non-zero elements.


    """
    from datetime import datetime
    now = datetime.now()
    diff = None
    if type(time) is int:
        diff = now - datetime.fromtimestamp(time)
    elif isinstance(time,datetime):
        diff = now - time 
    elif not time:
        diff = now - now

    second_diff = diff.seconds
    day_diff = diff.days

    s = second_diff % 60
    second_diff -= s

    m = (second_diff/60) % 60
    second_diff -= m * 60

    h = (second_diff/3600) % 24
    second_diff -= h * 3600

    d = day_diff % 7
    day_diff -= d

    w = (day_diff/7) % 4.286
    day_diff -= w * 7

    mo = (day_diff/30.416666666) % 12
    day_diff -= mo * 30

    y = day_diff/365.25
    day_diff -= y * 365.25

    out = ''
    if significant_units != 0 and y > 0:
        significant_units -= 1
        out += '%dy ' % y
    if significant_units != 0 and  mo > 0:
        significant_units -= 1
        out += '%dmo ' % mo
    if significant_units != 0 and  w > 0:
        significant_units -= 1
        out += '%dw ' % w
    if significant_units != 0 and  d > 0:
        significant_units -= 1
        out += '%dd ' % d
    if significant_units != 0 and  h > 0:
        significant_units -= 1
        out += '%dh ' % h
    if significant_units != 0 and m > 0:
        significant_units -= 1
        out += '%dm ' % m
    if significant_units != 0 and s > 0:
        significant_units -= 1
        out += '%ds ' % s

    if len(out) == 0:
        out = '0s'

    return out.strip()
