# chimi: a companion tool for ChaNGa: transient status messages
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
Provides a utility for supplying the user with feedback during long module
loads.

"""

import sys
import chimi

depth = 0
msg = []
msglen = []

def clear():
    """
    Clear the currently-displayed transient message.  If standard error is a
    terminal, the cursor will be reset to its prior position; otherwise a
    newline will be printed to standard error.

    This method does not normally need to be called directly; use `push' and
    `pop' instead.

    """
    tty = sys.stderr.isatty()
    if tty:
        sys.stderr.write('\033[u%s\033[u'%(' ' * chimi.transient.msglen[-1]))
    else:
        sys.stderr.write('\n')

def show():
    """
    Display the topmost transient message.

    This method does not normally need to be called directly; use `push' and
    `pop' instead.

    """
    if sys.stderr.isatty(): sys.stderr.write('\033[s')
    sys.stderr.write(chimi.transient.msg[-1])


def push(message):
    """
    Push a transient message onto the display stack.

    """
    if chimi.transient.depth > 0:
        chimi.transient.clear()

    chimi.transient.depth += 1

    msglen = len(message)
    chimi.transient.msg.append(message)
    chimi.transient.msglen.append(msglen)

    chimi.transient.show()
    
def pop(close_msg=None):
    """
    Clear the topmost transient message from the terminal and pop it off the
    stack.  If `close_msg` is given, it will be appended to the output before
    the message is cleared.

    """
    if close_msg:
        sys.stderr.write(close_msg)
        chimi.transient.msglen[-1] += len(close_msg)

    chimi.transient.clear()

    chimi.transient.msglen.pop()
    chimi.transient.msg.pop()
    chimi.transient.depth -= 1

    if chimi.transient.depth > 0:
        chimi.transient.show()

def import_(parent_name, name, use_perftable=False):
    """
    Import `name` into the module named `parent_name`.  If `use_perftable`, the
    global Chimi TimeTable will be used to track load time; otherwise transient
    messages will be used to inform the user of the load.

    import_ will usually be called as

        chimi.transient.import_(__name__, 'mymodule')

    parent_name : basestring
        Name of the calling module.

    name : basestring
        Name of the module to load.



    """
    import chimi.dependency

    def go():
        parent = sys.modules[parent_name]
        mod = __import__(name)
        parent.__dict__[name] = mod
        return mod

    popped = False
    try:
        if not use_perftable:
            chimi.transient.push('(Loading `%s\' ... ' % name)
            return go()
        else:
            with chimi.perftable.time('Loading module `%s\''%name):
                return go()
    except ImportError:
        if not use_perftable:
            chimi.transient.pop()
            popped = True
        if chimi.settings.disable_dependency_install:
            raise
        elif name in chimi.dependency.PACKAGES:
            try:
                o = chimi.dependency.install(name)
            except chimi.dependency.InstallError as err:
                sys.stderr.write(err.message+'\n')
                exit(1)
            return go()
        else:
            if not popped and not use_perftable:
                chimi.transient.pop()
            raise
    finally:
        if not popped and not use_perftable:
            chimi.transient.pop(')')


class OnDemandLoader(object):
    """
    Load a module when it is first accessed.  OnDemandLoader acts as a stand-in
    for the module to be loaded:

        submodule = chimi.transient.OnDemandLoader(__name__, 'submodule')
        submodule.some_function() # invokes OnDemandLoader.__getattribute__,
                                  # which loads & replaces itself with the real
                                  # 'submodule' and returns
                                  # `submodule.some_function`

    """
    def __init__(self, parent, name):
        self.__on_demand_name__ = name
        self.__on_demand_parent__ = parent

    def __getattribute__(self, attr):
        if attr == '__on_demand_name__' or attr == '__on_demand_parent__':
            return object.__getattribute__(self, attr)
        else:
            mod = chimi.transient.import_(self.__on_demand_parent__, self.__on_demand_name__)
            setattr(sys.modules[self.__on_demand_parent__], self.__on_demand_name__, mod)
            return getattr(mod, attr)


