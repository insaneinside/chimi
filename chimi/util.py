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

"""Various misc. utility functions and classes for Chimi."""

__author__    = 'Collin J. Sutton'
__copyright__ = 'Copyright (C) 2014 Collin J. Sutton'
__license__   = 'GPLv2'

import os
import re
import sys
import fcntl
import struct
import termios
import datetime

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

FORMAT_DURATION_DEFAULT_SIGNIFICANT_UNITS = 2
TERMINAL_SIZE_INPUT_DATA = struct.pack('HHHH', 0, 0, 0, 0)

# This function was copied from the StackOverflow answer at
# <https://stackoverflow.com/a/3010495>.
def terminal_size(fd=None):
    """
    Get the width and height of the terminal on FD.  FD defaults to standard
    output if not given.

    """
    if fd is None:
        fd = sys.stdout.fileno()
    h, w, hp, wp = \
        struct.unpack('HHHH', fcntl.ioctl(fd, termios.TIOCGWINSZ,
                                          TERMINAL_SIZE_INPUT_DATA))
    return w, h

def create_struct(__module, __name, *__fields, **__defaults):
    """Create a structure type with default values for each field."""
    def __init__(self, *args, **kwargs):
        setattr(self, '__dict__', self)
        for elt in __defaults:
            setattr(self, elt, __defaults[elt])
        for elt in set(__fields).difference(set(__defaults.keys())):
            setattr(self, elt, None)
        if len(args) > 0:
            args = list(args)
            for elt in __fields[:len(args)]:
                setattr(self, elt, args.pop(0))
        if len(kwargs) > 0:
            for elt in kwargs:
                setattr(self, elt, kwargs[elt])

    __type = type(__name, (dict,), {'__init__': __init__,
                                    '__module__': __module})
    return __type


def wrap_text(_in, start_col=0, max_col=75, respect_newlines=True):
    """
    Wrap text within the given column boundaries, filling the area before
    `start_col` with spaces.

    This method was created because the author was having problems with
    TextWrapper -- not necessarily because he wanted to reinvent the wheel.

    """

    width = max_col - start_col

    if len(_in) <= width:
        return _in

    sep = None
    strs = []

    if respect_newlines:
        sep = '\n'
        strs=_in.split(sep)
    else:
        # Only respect double-newlines and indented text.
        sep = '\n'

        base_strs = _in.split('\n')
        cs = ''
        last_indent = 0
        last_indent_bullet = 0

        def append_current():
            if len(cs) > 0:
                strs.append(((last_indent, last_indent_bullet), cs))

        for s in base_strs:
            if len(s) == 0:
                append_current()
                if len(strs) > 0 and len(strs[-1][1]) > 0:
                    strs.append(((0, 0), s))
                cs = ''
            else:
                m = re.match(r'(\s+([\*-+>]\s*)?)', s)
                indent, indent_bullet = (len(m.group(1)),
                                         len(m.group(2)) if m.group(2) else 0) \
                                         if m else (0, 0)
                if indent > 0:
                    if indent == last_indent and indent_bullet == 0:
                        cs += ' ' + s.strip()
                    else:
                        append_current()
                        cs = s.strip()
                else:
                    cs += ' ' + s.strip() if len(cs) > 0 else s.strip()

                last_indent = indent
                last_indent_bullet = indent_bullet if indent_bullet else last_indent_bullet

        append_current()

    out = ''

    for obj in strs:
        s = None
        indent = (0, 0)
        if isinstance(obj, tuple):
            indent, s = obj
        else:
            s = obj

        if out != '':
            out += sep + ' ' * (start_col + indent[0] - indent[1])

        while len(s) > width:
            front = s[0:width]
            parts = front.rpartition(' ')
            s = parts[2].strip() + s[width:]

            if parts[:-1] == ('', ''):
                m = re.match(r'^(.+)(\s+)?(.+)?$', s)
                parts = m.groups()
                parts = (parts[0],
                         parts[1] if parts[1] else '',
                         parts[2] if parts[2] else '')
                s = ''
            front = parts[0]
            out += "%s\n%s" % (front, ' ' * (start_col+indent[0]) if len(s) > 0 else '')
        out += s.strip()
    return out


def check_call(call, cwd=None, out=None, err=None):
    """
    Run (or pretend to run, depending on the value of `chimi.settings.noact`) a
    command using `subprocess.check_call`.

    """
    import subprocess
    import chimi.settings
    oldcwd = os.getcwd();

    if cwd != None and cwd != oldcwd:
        # the directory might not even exist if no-act is enabled, so don't
        # actually switch directory if it is [enabled].
        if not chimi.settings.noact:
            os.chdir(cwd)
    else:
        cwd = oldcwd

    if len(call) == 1 and isinstance(call[0], list):
        call = call[0]

    result = 0

    if chimi.settings.noact:
        sys.stderr.write('would execute [in %s]: %s\n' % (os.path.relpath(cwd, oldcwd), ' '.join(call)))
    else:
        try:
            subprocess.check_call(call, stdout=out, stderr=err)
        except subprocess.CalledProcessError as error:
            result = error.returncode
        except TypeError:
            print(call)

    if not chimi.settings.noact:
        os.chdir(oldcwd)

    return result


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
    now = datetime.datetime.now()
    diff = None
    if type(time) is int:
        diff = now - datetime.fromtimestamp(time)
    elif isinstance(time,datetime.datetime):
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
def format_duration(duration, significant_units=FORMAT_DURATION_DEFAULT_SIGNIFICANT_UNITS):
    """
    Get a shorthand representation of `duration` (ex. "1h 52m 3s").

    `significant_units` specifies how specific the output should be; use
    -1 to include all non-zero elements.


    """
    seconds = None
    days = None

    dtype = type(duration)
    if dtype is int:
        days = duration / 86400
        seconds = duration - days * 86400
    elif dtype is datetime.timedelta:
        days = duration.days
        seconds = duration.seconds
    else:
        raise ValueError('Invalid type `%s\' for `duration`'%dtype)

    s = seconds % 60
    seconds -= s

    m = (seconds/60) % 60
    seconds -= m * 60

    h = (seconds/3600) % 24
    seconds -= h * 3600

    d = days % 7
    days -= d

    w = (days/7) % 4.286
    days -= w * 7

    mo = (days/30.416666666) % 12
    days -= mo * 30

    y = days/365.25
    days -= y * 365.25

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


def relative_datetime_string(time, significant_units=FORMAT_DURATION_DEFAULT_SIGNIFICANT_UNITS):
    diff = None
    from datetime import datetime
    now = datetime.now()
    if isinstance(time, int):
        diff = now - datetime.fromtimestamp(time)
    elif isinstance(time, datetime):
        diff = now - time
    elif not time:
        diff = now - now

    return format_duration(diff, significant_units)


def list_excluding_index(lst, idx):
    """Get a copy of `lst` without the value at `idx`."""
    if idx == 0:
        return lst[1:]
    elif idx == len(lst) - 1:
        return lst[0:-1]
    else:
        out = lst[0:idx]
        out.extend(lst[idx+1:])
        return out

def isnumeric(x):
    """Check if the given value supports basic numeric operations"""
    try:
        x + 1
        return True
    except:
        return False


class Table(object):
    """
    Utility for pretty-printing a text-based table.  Unlike the "texttable"
    package, Table doesn't include superfluous and distracting borders, and
    includes support for text wrapping.

    """
    DEFAULT_MAX_WIDTH=132

    def __init__(self, cols=None, types=None, max_width=None, col_sep=2):
        if types:
            assert(len(types) == len(cols))

        self.columns = cols
        self.types = types
        self.rows = []

        self.max_width = max_width \
            if max_width \
            else (terminal_size(sys.stdout.fileno())[0] \
                      if sys.stdout.isatty() \
                      else Table.DEFAULT_MAX_WIDTH)
        self.col_sep = col_sep
        self.range = range(len(self.columns))
        self.column_data_widths = [len(self.columns[i]) for i in self.range]
        self.color_re = re.compile(r'^(\033\[[^a-zA-Z]*[a-zA-Z])([^\033]+)(\033\[[^a-zA-Z]*[a-zA-Z])$')


    def append(self, data):
        if len(data) != len(self.columns):
            raise ValueError('Invalid row length; expected %d, got %d'%
                             (len(self.columns),len(data)))
        else:
            if self.types:
                for i in range(len(self.types)):
                    if not isinstance(data[i], self.types[i]):
                        raise ValueError('Entry %d has invalid type: expected `%s\', got `%s\''%
                                         (i, self.types[i], type(data[i])))
            for i in self.range:
                value = str(data[i])
                match = self.color_re.match(value)
                if match:
                    value = match.group(2)
                _len = len(value)
                self.column_data_widths[i] = max(self.column_data_widths[i], _len)
            self.rows.append(data)


    def render(self, use_color=False):
        """
        Render the table to a string.

        """

        column_widths = self.column_data_widths
        slop = self.max_width - (sum(column_widths) + self.col_sep * (len(self.columns) - 1))

        align_flags = ['-' for i in self.range]
        if self.types:
            align_flags = []
            for i in self.range:
                if not isnumeric(self.rows[0][i]):
                    align_flags.append('-')
                else:
                    align_flags.append('')

        if slop < 0:
            mw = max(column_widths)
            mwi = column_widths.index(mw)
            other_widths = list_excluding_index(column_widths, mwi)
            mow = max(other_widths)
            if mow > column_widths[mwi] + slop:
                # Split the difference
                moi = column_widths.index(mow)
                column_widths[moi] += slop/2
                column_widths[mwi] += slop/2
            else:
                column_widths[mwi] += slop

        # Build the format string that we'll use to format each row of the
        # output.  If the final column is left-aligned, we skip specifying
        # field-width for it.
        col_fmts = [('%%s%%%s%ds%%s' % (align_flags[i], column_widths[i])) \
                        for i in self.range[0:-1]]
        if align_flags[-1] == '-':
            col_fmts.append('%%s%%%ss%%s'%(align_flags[-1]))
        else:
            col_fmts.append('%%s%%%s%ds%%s' % (align_flags[-1], column_widths[-1]))
        row_format = (' '*self.col_sep).join(col_fmts) + "\n"


        o = ''
        rows = list(self.rows)

        # Insert the header row
        if use_color:
            fmt = "\033[1m%s\033[m"
            rows.insert(0, [fmt%col for col in self.columns])

        else:
            rows.insert(0, self.columns)

        for row in rows:
            rv = []
            for entry in row:
                pre_str = ''
                value = str(entry)
                post_str = ''
                if '\033' in value:
                    match = self.color_re.match(value)
                    if match:
                        if use_color:
                            pre_str, value, post_str = match.groups()
                        else:
                            pre_str, value, post_str = ('', match.group(2), '')
                rv.extend([pre_str, value, post_str])
            o += row_format % tuple(rv)

        return o
