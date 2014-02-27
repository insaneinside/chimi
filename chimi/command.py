# chimi: a companion tool for ChaNGa: interactive commands
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
import sys
import saga
import yaml
import string
import inspect
import subprocess

import chimi
import chimi.lmod
from chimi import *

global DEFAULT_REPOSITORIES
DEFAULT_REPOSITORIES={
    'charm' : 'http://charm.cs.uiuc.edu/gerrit/charm',
    'changa' : 'http://charm.cs.uiuc.edu/gerrit/changa',
    'utility' : 'http://charm.cs.illinois.edu/gerrit/cosmo/utility.git'
    }

basename = os.path.basename(sys.argv[0])

def load_platform_resources():
    if os.environ.has_key('LMOD_CMD'):
        chimi.lmod.load('cuda')
        chimi.lmod.load('git')
    else:
        if os.path.exists('/usr/lib/nvidia-cuda-toolkit'):
            os.environ['CUDA_DIR'] = '/usr/lib/nvidia-cuda-toolkit'
        elif os.path.exists('/usr/local/cuda'):
            os.environ['CUDA_DIR'] = '/usr/local/cuda'

def is_root_dir(_dir):
    return os.path.dirname(_dir) == _dir

def find_current_package_set():
    _dir = os.getcwd()

    check = os.path.join(_dir, PackageSet.SET_FILE)
    if os.path.exists(check):
        return PackageSet.load(_dir);
    else:
        while not os.path.exists(check):
            if os.path.ismount(_dir):
                break
            else:
                _dir = os.path.dirname(_dir)
                check = os.path.join(_dir, PackageSet.SET_FILE)
        if os.path.exists(check):
            return PackageSet.load(_dir)
        else:
            if is_root_dir(os.getcwd()):
                sys.stderr.write("The current directory does not look like " +
                                 "an initialized chimi\ndirectory.  " +
                                 "Do you need to run `%s init .'?\n" % \
                                     basename)
            else:
                sys.stderr.write("Neither the current directory nor any parent " +
                                 "up to mount point %s looks\nlike an " % _dir +
                                 "initialized chimi directory.  " +
                                 "Do you need to run `%s init .'?\n" % basename)
            exit(1)

# def fetch_sources(opts, dest_dir=None):

#     if dest_dir == None:
#         dest_dir = os.getcwd()
#     if not os.path.exists(dest_dir):
#         os.makedirs(dest_dir)

#     for proj in DEFAULT_REPOSITORIES:
#         repo = DEFAULT_REPOSITORIES[proj]
#         os.chdir(dest_dir)
#         if not os.path.exists(proj):
#             subprocess.check_call(['git', 'clone', repo, proj])
#         else:
#             os.chdir(proj)
#             subprocess.check_call(['git', 'pull', 'origin'])

def helpfn(opts, *args):
    args = list(args)
    io = sys.stdout

    if len(args) > 0 and isinstance(args[-1], file):
        io = args[-1]
        del args[-1]

    if len(args) == 0:
        io.write("Valid commands are:\n")
        for cmd in COMMAND_LIST:
            brief = cmd.brief
            if brief == None:
                brief = '<undocumented>'
            io.write("  %-10s  %s\n" % (cmd.name, brief))
        io.write("\nUse `%s help COMMAND' for detailed information on a command.\n" % basename)
        io.write("If no command is given, `%s' does nothing.\n" % basename)

    else:
        io.write(COMMANDS[args[0]].help)

def build(config, which):
    which_args = ['all', 'changa', 'charm']

    if type(which) != str:
        which = which[0]

    if not which in which_args:
        raise ValueError('Invalid `build` target')

    ps = find_current_package_set()
    changa = ps.packages['changa']
    charm = ps.packages['charm']

    force = False
    if 'force' in config:
        force = config['force']
        del config['force']

    _continue = False
    if 'continue' in config:
        _continue = config['continue']
        del config['continue']

    replace = False
    if 'replace' in config:
        replace = config['replace']
        del config['replace']

    if not 'arch' in config:
        config['arch'] = chimi.config.HostBuildConfig.get_architecture()
    if not 'settings' in config:
        config['settings'] = {}

    # Process "extra" build arguments
    extras=[]
    if 'I' in config:
        for _dir in config['I']:
            if (not force) and not os.path.exists(_dir):
                raise ValueError("\n\nSpecified include path \"%s\" does "%_dir +
                                 "not exist.  If you\'re sure this is the\n"
                                 "right argument, use the `--force\' option.")
        extras.extend([ '-I%s' % _dir for _dir in config['I']])
        del config['I']

    if 'L' in config:
        for _dir in config['L']:
            if (not force) and not os.path.exists(_dir):
                raise ValueError("\n\nSpecified library path \"%s\" does "%_dir +
                                 "not exist.  If you\'re sure this is the\n"
                                 "right argument, use the `--force\' option.")

        extras.extend(['-L%s' % _dir for _dir in config['L']])
        del config['L']
    config['extras'] = extras

    # The 'options' option to `build` takes a comma-separated list of Charm++
    # "build options" (i.e. optional component names) and value assignments
    # ("settings").
    #
    # Separate them.
    negate_options=[]
    if 'options' in config:
        options_ary = []
        for elt in config['options']:
            options_ary.extend(elt.split(','))
        config['options'] = []
        for opt in options_ary:
            if '=' in opt:
                key, value = opt.split('=', 2)
                config['settings'][key] = value
            else:
                if opt[0] == '-':
                    negate_options.append(opt)
                else:
                    config['options'].append(opt)
    else:
        config['options'] = []

    noact = False
    if 'noact' in config:
        noact = True

    # Make the config into an actual build configuration.
    config = chimi.core.BuildConfig(config['arch'], config['options'], config['settings'], config['extras'])

    # Load additional build settings from the host-data file.
    hi = chimi.HostConfig.load()
    if hi != None:
        hi.build.apply(config)

    if len(negate_options) > 0:
        config.options = list(set(config.options).difference(set(negate_options)))

    if noact:
        print(hi)
        print(config.architecture)
        print(config.options)
        print(config.settings)
        print(config.extras)
        return

    if which == 'all':
        which = ['charm', 'changa']
    elif which == 'changa' or which == 'charm':
        pass
    else:
        raise ValueError('Unknown `build` argument: %s' % which)

    if type(which) != list:
        which = [which]

    for item in which:
        if ps[item].have_build(config) and ps[item].find_build(config).status == BuildStatus.Complete:
            sys.stderr.write("Skipping build of \"%s\": already built\n" % item)
        else:
            try:
                ps[item].build(config, _continue, replace)
            except KeyboardInterrupt:
                ps[item].find_build(config).update(BuildStatus.InterruptedByUser)
                ps.save()
                exit(1)
    ps.save()

def bootstrap(opts, directory):
    directory = os.path.abspath(directory)
    if os.path.exists(os.path.join(directory, PackageSet.SET_FILE)):
        raise RuntimeError('Directory is already initialized')
    else:
        ps = PackageSet(directory)
        ps.save()

def list_items(opts, directory=None):
    if 'reltime' in opts and opts['reltime'] == True:
        chimi.util.relative_message_timestamps = True

    ps = find_current_package_set()

    for pkg_name in ps.packages:
        pkg = ps.packages[pkg_name]
        sys.stdout.write("package \033[1m%s\033[0m:\n" % pkg.definition.name)
        sys.stdout.write("  remotes:\n")
        remotes = pkg.remotes
        max_name_len = max([len(name) for name, url in remotes])
        for name, url in pkg.remotes:
            sys.stdout.write("    %%-%ds   %%s\n" % max_name_len % (name, url))
        for build in pkg.builds:
            sys.stdout.write("  build \033[1m%s\033[0m:\n" % build.name)
            sys.stdout.write("    directory: %s\n" % build.directory)
            sys.stdout.write("    source version: %s\n" % build.version)
            sys.stdout.write("    id: %s\n" % str(build.uuid))
            status_color = 'yellow'
            if build.status.failure:
                status_color = 'brightred'
            elif build.status.completion:
                status_color = 'brightgreen'
            sys.stdout.write("    status: \033[%dm%s\033[0m\n" % (chimi.util.ANSI_COLORS[status_color], build.status.name))
            sys.stdout.write("    architecture: %s\n" % build.config.architecture)

            options_desc = 'none'
            if len(build.config.options) > 0:
                options_desc = ' '.join(build.config.options)
            sys.stdout.write("    options: %s\n" % options_desc)

            if len(build.config.settings) > 0:
                sys.stdout.write("    settings:\n")
                for sname in build.config.settings:
                    sys.stdout.write("      %s=%s\n" % (sname, build.config.settings[sname]))
            else:
                sys.stdout.write("    settings: none\n")
            if len(build.config.extras) > 0:
                sys.stdout.write("    extra arguments:\n")
                for arg in build.config.extras:
                    sys.stdout.write("      %s\n" % arg)
            else:
                sys.stdout.write("    extra arguments: none\n")
            sys.stdout.write("\n    Build log:\n")
            for msg in build.messages:
                sys.stdout.write("      " + str(msg) + "\n")

def runfn(opts, *args):
    hi = chimi.HostConfig.load()
    

from chimi import Command
COMMAND_LIST = [
    Command('init', ['DIR'], 'Bootstrap Chimi configuration from existing files.',
            [], None, bootstrap),
    # Command('fetch', ['[DESTDIR]'],
    #         [],
    #         'Fetch or update program sources.',
    #         None, fetch_sources),
    Command('help', ['[COMMAND]'], 'Show help on available commands.',
            [],
            "If COMMAND is given, show help for that command.  Otherwise, "+
            "show a\nlist of available commands.",
            helpfn),
    Command('build', ['[all|changa|charm]'], 'Build a package.',
            [ Option(None, 'arch', 'Specify Charm++ build architecture.', 'ARCH').store(),
              Option(None, 'continue', 'Attempt to continue an aborted or failed build').store(),
              Option(None, 'replace', 'Replace any existing build with this configuration').store(),
              Option('n', 'noact', 'Don\'t actually run the build; print configuration and exit.').store(),
              Option('o', 'options', 'Specify additional Charm++ build "options"',
                     'OPT[,OPT]...').store(multiple=True),
              Option('I', None, 'specify additional include directories for Charm builds',
                     'DIR').store(multiple=True),
              Option('L', None, 'specify additional library directories for Charm builds',
                     'DIR').store(multiple=True),
              Option(None, 'force', 'Force build even if arguments to -I or -L don\'t exist.').store(),
              ],
            None, build),
    Command('run', ['[ARG]...'], 'Run ChaNGa in a manner appropriate to the current or selected host.',
            [ Option('H', 'host', 'Run the job remotely on host HOST (default: local run)',
                     '[USER@]HOST').store(),
              Option('E', None, 'Set an environment variable for the job',
                     'VAR=VALUE').store(multiple=True),
              Option('o', None, 'Set SAGA build options', 'NAME=VALUE[,NAME=VALUE]...')\
                  .store(multiple=True),
              ],
            None, runfn),
    Command('status', [], 'List recorded build/package information.',
            [ Option('r', 'reltime', 'Use relative time stamps').store() ],
            None, list_items)
    ]

COMMAND_NAMES = [ cmd.name for cmd in COMMAND_LIST ]
COMMANDS = {}

PROGRAM_USAGE='%s [OPTION]... COMMAND [ARGUMENT]...' % basename
PROGRAM_DESCRIPTION='Perform boring ChaNGa-related tasks.'

for cmd in COMMAND_LIST:
    COMMANDS[cmd.name] = cmd

def show_help(io=sys.stderr, _exit=False, _exit_status=None):
    OptionParser.show_help(OPTIONS, PROGRAM_USAGE, PROGRAM_DESCRIPTION, io)
    io.write("\n")
    helpfn(None, io)
    if _exit:
        exit(_exit_status)

OPTIONS = [ Option('h', 'help', 'Show this help.').handle(lambda *x: show_help(sys.stdout, True, 0)) ]


def main():
    chimi.run_cwd = os.getcwd()
    load_platform_resources()
    args = sys.argv[1:]
    OptionParser.handle_options(OPTIONS, args, COMMAND_NAMES)

    if len(args) == 0:
        OptionParser.show_usage(PROGRAM_USAGE, sys.stderr)
        exit(1)
    elif not args[0] in COMMAND_NAMES:
        raise NotImplementedError('No such command "%s"' % args[0])
    elif len(args) > 1 and args[1] == '-h':
        COMMANDS['help'].call([args[0]])
    else:
        COMMANDS[args[0]].call(args[1:])

if __name__ == "__main__":
    main()
