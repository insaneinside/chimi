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
import yaml
import string
import inspect
import subprocess

import chimi
import chimi.lmod
from chimi import *

basename = os.path.basename(sys.argv[0])


class CommandError(Exception):
    pass

class CommandUsageError(CommandError,ValueError):
    def __init__(self, cmd):
        self.command = cmd
        super(ValueError, self).__init__('Missing required arguments to "%s".\nUsage: %s' % (cmd.name, cmd.usage))

class SubcommandError(CommandError, NotImplementedError):
    def __init__(self, cmd, subcmd):
        self.command = cmd
        self.subcommand = subcmd
        super(NotImplementedError, self).__init__('Command `%s\' has no such subcommand, `%s\'' % (cmd.name, subcmd))

class Command(object):
    """Describes a program command"""

    def __init__(self, name, args, brief, options, detail,
                 callback=None,
                 subcommands=None):
        self._name = name
        self.arguments_usage = args
        self.options = options
        self.help_brief = brief
        self.help_detail = detail
        self.callback = callback
        self.hidden = name[0] == '*'
        self.required_arg_count = 0
        self.subcommands=subcommands

        self.parent = None
        if subcommands != None:
            for cmd in self.subcommands:
                cmd.parent = self
        else:
            self.subcommands = []

        for arg in self.arguments_usage:
            if arg[0] != '[':
                self.required_arg_count += 1
    @property
    def name(self):
        """Name of this command"""
        return self._name

    @property
    def brief(self):
        """Brief help string for this command"""
        return self.help_brief

    @property
    def detail(self):
        """Detailed help string for this command"""
        return self.help_detail

    @property
    def full_name_list(self):
        """Get the "full name" of the command, including parent command names."""
        parts = []
        part = self
        while part != None:
            parts.insert(0, part.name)
            part = part.parent
        return parts

    @property
    def usage(self):
        """Usage string for this command"""

        parts = self.full_name_list
        parts.insert(0, chimi.command.basename)

        if len(self.options) > 0:
            parts.append('[OPTION]...')
        parts.extend(self.arguments_usage)

        return ' '.join(parts)

    @property
    def short_usage(self):
        """Short usage string containing only command name and arguments"""
        return self.name + ((' ' + ' '.join(self.arguments_usage))
                            if isinstance(self.arguments_usage, list)
                            else '')

    @property
    def help(self):
        """Detailed `help` output string for this command"""
        return \
            "\n".join([chimi.option.OptionParser.format_help(self.options,
                                                             self.usage,
                                                             self.help_brief),
                       self.help_detail + "\n" if self.help_detail else ''])

    @property
    def num_args(self):
        """Maximum number of arguments accepted"""
        return len(self.arguments_usage)

    def call(self, opts={}, args=[], kwargs={}):
        """
        Invoke the command.  If the command has sub-commands, it will be
        invoked and the result used to pass additional options and keyword
        arguments to the subcommand.

        opts: pre-parsed options dict to pass directly to the command's
            handler.

        args: positional arguments.

        kwargs: keyword arguments; these are usually /not/ specified directly.

        """
        opts_out = dict(opts)
        subcommand_dict = {}
        for cmd in self.subcommands:
            subcommand_dict[cmd.name] = cmd

        options = []
        if len(self.options) > 0:
            options.extend(chimi.OptionParser.flatten(self.options))


        # Make "-h" work for printing the help string for any command
        def impromptu_help(self):
            sys.stdout.write(self.help)
            exit(0)
        options.append(chimi.Option('h', 'help', 'Show help for the %s command' % self.name)\
                        .handle(lambda: impromptu_help(self)))

        # Parse options for this command.
        stop_set = subcommand_dict.keys()
        try:
            opts_out.update(chimi.OptionParser.handle_options(options, args, stop_set))
        except Exception as err:
            sys.stderr.write('%s: %s' % (self.name, err.message))
            return 3;

        if len(self.subcommands) == 0:
            # Primary-command invocation.
            if len(args) < self.required_arg_count:
                raise CommandUsageError(self)
            return self.callback(opts_out, *args, **kwargs)
        else:
            # Secondary-command invocation.
            if not len(args) > 0:
                raise CommandUsageError(self)
            elif args[0] in subcommand_dict:
                cmd = subcommand_dict[args[0]]
                del args[0]

                if len(args) < cmd.required_arg_count:
                    raise CommandUsageError(cmd)
                elif self.callback != None:
                    # Invoke the parent command's handler to do e.g. common
                    # initialization for subcommands, and then invoke the
                    # subcommand using the results of that call.
                    opts_out, _kwargs = self.callback(opts_out, *args)
                    return cmd.call(opts=opts_out, args=args, kwargs=_kwargs)
                else:
                    # No handler for parent command, so invoke the subcommand
                    # "normally" (we still provide the additional options from
                    # the parent command).
                    return cmd.call(opts=opts_out, args=args)
            else:
                raise SubcommandError(self, args[0])


def load_platform_resources():
    if chimi.lmod.available:
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

def fetch_sources(opts, dest_dir=None):
    ps = find_current_package_set()
    if dest_dir == None:
        dest_dir = ps.directory
    if not os.path.exists(dest_dir) and not chimi.settings.noact:
        os.makedirs(dest_dir)

    for proj in ps.packages:
        ps.packages[proj].fetch()


def helpfn(opts, *args, **kwargs):
    args = list(args)
    io = sys.stdout

    if len(args) > 0 and isinstance(args[-1], file):
        io = args[-1]
        del args[-1]

    command_list=kwargs['command_list']
    assert(isinstance(command_list, list))

    if len(args) == 0:
        io.write("Valid %scommands are:\n"%('sub' if command_list != COMMAND_LIST else ''))
        cmds_usage = {}

        # Build a dict of the short-style usage strings for each command, and
        # keep track of the maximum length we get.
        max_usage_len = 0
        for cmd in command_list:
            cmds_usage[cmd.name] = cmd.short_usage
            l = len(cmds_usage[cmd.name])
            if l > max_usage_len:
                max_usage_len = l

        # Use that maximum-length to create a format string with nice alignment
        # for the brief-documentation blurb for each command.
        fmt_str = '  %%-%ds  %%s\n' % max_usage_len

        for cmd in command_list:
            brief = cmd.brief
            if brief == None:
                brief = '<undocumented>'
            io.write(fmt_str % (cmds_usage[cmd.name], chimi.util.wrap_text(brief, max_usage_len + 4)))

        if command_list == COMMAND_LIST:
            io.write("\nUse `%s help COMMAND' for detailed information on a command.\n" % basename)
            io.write("If no command is given, `%s' does nothing.\n" % basename)
        else:
            io.write("\nUse `%s help %s COMMAND' for detailed information on a command.\n" % (basename, ' '.join(command_list[0].parent.full_name_list)))

    else:
        command_list=kwargs['command_list']
        commands = {}
        for cmd in command_list:
            commands[cmd.name] = cmd
        cmd = commands[args.pop(0)]
        while len(args) > 0 and len(cmd.subcommands) > 0:
            command_list = cmd.subcommands
            commands = {}
            commands = {}
            for cmd in command_list:
                commands[cmd.name] = cmd
            cmd = commands[args.pop(0)]

        io.write(cmd.help)
        if isinstance(cmd.subcommands, list) and len(cmd.subcommands) > 0:
            helpfn(opts, io, command_list=cmd.subcommands)


class InvalidArchitectureError(ValueError):
    def __init__(self, archname, qualifier=None):
        self.architecture = archname
        self.qualifier = qualifier
    @property
    def message(self):
        return '%s%s`%s\' is not a valid Charm++ build architecture.' % \
            (self.qualifier if self.qualifier else '',
             ' ' if self.qualifier else '',
             self.architecture)

def make_build_config(config, force=False,
                      package_set=None):
    chose_architecture = False
    if not 'arch' in config:
        config['arch'] = chimi.config.get_architecture()
        chose_architecture = True

    completed_architecture = False
    if package_set:
        # Load architecture definitions if not already loaded.
        if not len(CharmDefinition.Architectures) > 0:
            CharmDefinition.load_architectures(package_set.packages['charm'].directory)

        if config['arch'] in chimi.core.CharmDefinition.Architectures and\
                chimi.core.CharmDefinition.Architectures[config['arch']].is_base:
                # Shorthand (base arch) name given.  Fill it in for the user.
                config['arch'] = chimi.config.get_architecture(config['arch'])
                completed_architecture = True

        if not config['arch'] in chimi.core.CharmDefinition.Architectures:
            # No such name even exists, either as a base architecture *or* a
            # build architecture.  Complain at the user.
            qualifier = None
            if chose_architecture:
                qualifier = 'Auto-selected'
            elif completed_architecture:
                qualifier = 'Auto-completed'
            raise InvalidArchitectureError(config['arch'], qualifier)

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
                    negate_options.append(opt[1:])
                else:
                    config['options'].append(opt)
    else:
        config['options'] = []

    kwargs={}
    if 'branch' in config:
        kwargs['branch'] = config['branch']

    # Make the config into an actual build configuration.
    config = chimi.core.BuildConfig(config['arch'], config['options'], config['settings'], config['extras'],
                                    **kwargs)

    # Load additional build settings from the host-data file.
    hi = chimi.HostConfig.load()
    if hi != None:
        hi.build.apply(config, negated_options=negate_options)
    else:
        sys.stderr.write("WARNING: no host configuration found; using default settings.\n")

    # Remove invalid options
    if package_set:
        arch = CharmDefinition.Architectures[config.architecture]
        invalid_options = list(set(config.options).difference(set(arch.all_options)))

        if len(invalid_options) > 0:
            for opt in invalid_options:
                sys.stderr.write('\033[1;31mERROR:\033[0m Option `%s\' is invalid for architecture `%s\'\n' % \
                                     (opt, config.architecture))
            config.options = list(set(config.options).intersection(set(arch.options)))
            config.options.sort()

    return(config)


def build(config, which=None, *args):
    which_args = ['all', 'changa', 'charm']

    args = list(args)
    if '--' in args:
        del args[args.index('--')]

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

    purge = False
    if 'purge' in config:
        purge = config['purge']
        del config['purge']

    config = make_build_config(config, force=force, package_set=ps)
    config.options.sort()
    config.extras.extend(args)

    if isinstance(which, type(None)):
        if purge:
            which = 'all'
        else:
            which = 'changa'

    if not which in which_args:
        raise ValueError('Invalid `build` target')

    if which == 'all':
        which = ['charm', 'changa']
    elif which == 'changa' or which == 'charm':
        which = [which]
    else:
        raise ValueError('Unknown `build` argument: %s' % which)

    for item in which:
        package = ps.packages[item]
        if purge == 'all':
            package.purge_builds()
        elif isinstance(purge,bool) and purge:
            package.purge_builds(config=config)
        elif isinstance(purge,str):
            purge_builds = purge.split(',')
            hd = r'[a-fA-F0-9]'
            uuid_re=re.compile(r'^%s{8}-%s{4}-%s{4}-%s{4}-%s{12}$'%(hd,hd,hd,hd,hd))
            names = []
            uuids = []
            for s in purge_builds:
                if uuid_re.match(s):
                    uuids.append(s)
                else:
                    names.append(s)
            sys.stderr.write('Purging from %s:\n'%package.definition.name)
            n = package.purge_builds(names=names, uuids=uuids,
                                     callback=lambda x: \
                                         sys.stderr.write("  %s build \"%s\"\n"%('purging' \
                                                                                     if not chimi.settings.noact \
                                                                                     else 'would purge',
                                                                                 x.name)))
            if not n:
                sys.stderr.write('  hmmm, no builds matched.\n')
        else:               # We're actually building something.
            _build = package.find_build(config)

            if _build and _build.config.branch == config.branch and _build.compiled and not force:
                sys.stderr.write("Skipping build of \"%s\": already built: %s\n" % (item, _build.name))
            else:
                try:
                    ps[item].build(config, _continue=_continue, replace=replace, force=force)
                except KeyboardInterrupt:
                    ps[item].find_build(config).update(BuildStatus.InterruptedByUser)
                    if not chimi.settings.noact:
                        ps.save_flag = True
                        ps.save()
                    exit(1)
    if not chimi.settings.noact:
        ps.save()

def bootstrap(opts, directory):
    directory = os.path.abspath(directory)
    if os.path.exists(os.path.join(directory, PackageSet.SET_FILE)):
        raise RuntimeError('Directory is already initialized')
    else:
        ps = PackageSet(directory)
        ps.save_flag = True
        ps.save()

def make_colored_build_status_string(status):
    """Create a color-coded build-status name string."""
    status_color = 'yellow'
    if status.failure:
        status_color = 'brightred'
    elif status.completion:
        status_color = 'brightgreen'
    return '\033[%dm%s\033[0m' % (chimi.util.ANSI_COLORS[status_color], status.name)

def list_items(opts, directory=None):
    if 'reltime' in opts and opts['reltime'] == True:
        chimi.util.relative_message_timestamps = True

    ps = find_current_package_set()

    for pkg_name in ps.packages:
        pkg = ps.packages[pkg_name]
        sys.stdout.write("package \033[1m%s\033[0m:\n" % pkg.definition.name)
        if not os.path.exists(pkg.directory):
            sys.stdout.write("  uninitialized\n")
            continue
        sys.stdout.write("  current branch: %s\n" % pkg.branch)
        sys.stdout.write("  remotes:\n")
        remotes = pkg.remotes
        max_name_len = max([len(name) for name, url in remotes])
        for name, url in pkg.remotes:
            sys.stdout.write("    %%-%ds   %%s\n" % max_name_len % (name, url))
        for build in pkg.builds:
            sys.stdout.write("  build \033[1m%s\033[0m:\n" % build.name)
            sys.stdout.write("    branch: %s\n" % build.config.branch)
            sys.stdout.write("    directory: %s\n" % build.directory)
            sys.stdout.write("    source version: %s\n" % build.version)
            sys.stdout.write("    id: %s\n" % str(build.uuid))

            sys.stdout.write("    status: %s\n"%make_colored_build_status_string(build.status))
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

def show_architectures(opts, *args):
    ps = chimi.command.find_current_package_set()

    if not len(CharmDefinition.Architectures) > 0:
        CharmDefinition.load_architectures(ps.packages['charm'].directory)

    sym_pfx = ''
    if 'unique' in opts:
        sym_pfx = '_'
    if len(args) == 0:
        args = sorted(CharmDefinition.Architectures.keys());

    list_only = False
    if 'list' in opts:
        list_only = True
    show_all = False
    if 'all' in opts:
        show_all = opts['all']

    for aname in args:
        arch = CharmDefinition.Architectures[aname]
        if arch.is_base and not show_all:
            continue

        inh_str = ''
        if arch.parent:
            inh_str = ' (%s)' % arch.parent.name
        sys.stdout.write('\033[1;97m%s\033[0m%s' % (arch.name, inh_str))

        opts = []
        cc = []
        fcc = []
        if not list_only:
            opts = getattr(arch, sym_pfx + 'options')
            cc = getattr(arch, sym_pfx + 'compilers')
            fcc = getattr(arch, sym_pfx + 'fortran_compilers')

        if not list_only and sum(map(lambda x: 0 if not x else len(x), [opts, cc, fcc])) > 0:
            sys.stdout.write(":\n")
            if opts and len(opts) > 0:
                sys.stdout.write('  options: %s\n'% ' '.join(opts))

            if cc and len(cc) > 0:
                sys.stdout.write('  compilers: %s\n'% ' '.join(cc))

            if fcc and len(fcc) > 0:
                sys.stdout.write('  fortran compilers: %s\n'% ' '.join(fcc))
        else:
            sys.stdout.write("\n")

def show_builds(opts, *args):
    t = chimi.util.Table(cols=('Name', 'UUID', 'Branch', 'Options', 'Status'),
                         types=(basestring, uuid.UUID, basestring, basestring,
                                basestring))
    use_color = sys.stdout.isatty()
    ps = chimi.command.find_current_package_set()
    _builds = ps.packages['changa'].builds
    _builds.sort(cmp=lambda x, y: x.name < y.name)
    for _build in _builds:
        status = make_colored_build_status_string(_build.status)\
            if use_color \
            else _build.status.name
        t.append((_build.name, _build.uuid, _build.config.branch,
                  ' '.join(_build.config.options), status))

    print(t.render(color=use_color))
    return 0

import chimi.job
COMMAND_LIST = [
    Command('init', ['DIR'], 'Bootstrap Chimi configuration from existing files.',
            [], None, bootstrap),
    Command('fetch', ['[DESTDIR]'], 'Fetch or update program sources.',
            [],
            None, fetch_sources),
    Command('help', ['[COMMAND]'], 'Show help on available commands.',
            [],
            "If COMMAND is given, show help for that command.  Otherwise, "+
            "show a\nlist of available commands.",
            lambda x, *y: helpfn(x, *y, command_list=COMMAND_LIST)),
    Command('build', ['[all|changa|charm]'], 'Build a package.',
            [('Configuration options',
              Option(None, 'arch', 'Specify Charm++ build architecture.', 'ARCH').store(),
              Option('b', 'branch', 'Check out BRANCH in the package repository before building.',
                     'BRANCH').store(),
              Option('o', 'options', 'Specify additional Charm++ build "options"',
                     'OPT[,OPT]...').store(multiple=True),
              Option('I', None, 'specify additional include directories for Charm builds',
                     'DIR').store(multiple=True),
              Option('L', None, 'specify additional library directories for Charm builds',
                     'DIR').store(multiple=True),
              ),
             ('Builds management options',
              Option(None, 'continue', 'Attempt to continue an aborted or failed build').store(),
              Option(None, 'replace', 'Replace any existing build with this configuration').store(),
              Option(None, 'purge',
                     'Remove one or all builds for the selected package(s):\n'
                     '`--purge=all` will purge all builds of the selected '
                     'package.\n'
                     '`--purge=BUILD[,BUILD]...` will purge all builds with name '
                     'or ID matching specified BUILD(s).\n'
                     '`--purge` (without arguments) will purge only the build '
                     'matching specified configuration options.',
                     '[all|BUILD[,BUILD]...]').store(),
              ),
             ('Misc. options',
              Option(None, 'force', 'Force build even if arguments to -I or -L don\'t exist.').store(),
              ),
             ],
            'The target, if not given, defaults to "changa".  The ChaNGa '
            'package definition will initiate a matching Charm++ build if a '
            'suitable one is not found.', build),
    Command('job', ['CMD', '[ARG]...'], 'Manage job(s) on local or remote nodes.',
            [Option('H', 'host', 'Manipulate jobs on remote HOST via SSH [default: local]',
                    '[USER@]HOST').store(),
             Option('m', 'manager', 'Specify/override job manager to use.', 'MANAGER').store(),
             ], None,
            callback=chimi.job.common,
            subcommands=[
            Command('run', ['ARG...'], 'Run ChaNGa in a manner appropriate to the current or selected host.',
                    [('Run-time options',
                      [Option(None, 'build', 'Use the build given by name or id.', 'NAME|UUID').store(),
                       Option('w', 'watch', 'Watch the job after starting it.').store(),
                       Option('e', None,
                              'Run a command with the ChaNGa executable as an argument.'
                              '  When this option is specified, the first argument that'
                              ' matches the string \'{}\' will be replaced with the '
                              'path to the ChaNGa executable.').store(),
                       Option('C', 'cwd', 'Run in DIR (use as CWD)', 'DIR').store(),
                       Option('O', None, 'Set SAGA job-description attributes.',
                              'ATTR=VAL[,ATTR=VAL]...').store(multiple=True),
                       Option('E', None, 'Set an environment variable for the job.',
                              'VAR=VALUE').store(multiple=True),
                       ]),
                    ],
                    """
Chimi's `run' command uses the SAGA interface for Python (see
http://saga-project.github.io/saga-python/), which provides a heterogenous API
for accessing HPC resources.  Each job-management service supports a different
set of job-description attributes; see the adaptor documentation (link below)
for details.

Note that even though the SAGA-Python documentation uses CamelCase in listing
job-description attributes, both the API itself and this tool require that they
be given in "snake_case" (all lower-case, words separated by underscores) or
"spinal-case" (like snake case, but with hyphens instead of underscores).

The API documentation for SAGA-Python's adaptors can be found at:

http://saga-project.github.io/saga-python/doc/adaptors/saga.adaptor.index.html

"""
                    , callback=chimi.job.run),
            Command('watch', ['JOB'], 'Watch a job for state changes.',
                    [], None, chimi.job.watch),
            Command('cancel', ['JOB'], 'Cancel a job.',
                    [], None, chimi.job.cancel),
            Command('list', [], 'List jobs.',
                    [], None, chimi.job._list),
            ]),
    Command('status', [], 'List recorded build/package information.',
            [Option('r', 'reltime', 'Use relative time stamps').store() ],
            None, list_items),
    Command('show', ['COMMAND'], 'Show useful information about various items.',
            [], None,
            subcommands=[
            Command('arch', ['[ARCH]'],
                    'List available options and compilers for a Charm++\n'
                    'architecture.  If no architecture is given, do this for\n'
                    'all available Charm++ architectures.',
                    [Option('a', 'all', 'Show all architectures (default: '
                            'build-only/non-base architectures)').store(),
                     Option('l', 'list', 'List only the names of available architectures').store(),
                     Option('u', 'unique', 'Show only non-inherited options and compilers').store()],
                    'NOTE: this command requires an initialized Chimi directory.',
                    callback=show_architectures),
            Command('builds', [], 'List ChaNGa builds.', [], None, callback=show_builds),
            ]),
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
    helpfn(None, io, command_list=COMMAND_LIST)
    if _exit:
        exit(_exit_status)

OPTIONS = [ Option('h', 'help', 'Show this help.').handle(lambda *x: show_help(sys.stdout, True, 0)),
            Option('n', 'noact', 'Don\'t actually change anything or run any commands.').store(),
            ]


def main():
    chimi.run_cwd = os.getcwd()
    load_platform_resources()
    args = sys.argv[1:]
    opts_out = OptionParser.handle_options(OPTIONS, args, COMMAND_NAMES)

    if 'noact' in opts_out:
        chimi.settings.noact = opts_out['noact']

    if len(args) == 0:
        OptionParser.show_usage(PROGRAM_USAGE, sys.stderr)
        return 1
    elif not args[0] in COMMAND_NAMES:
        raise NotImplementedError('No such command "%s"' % args[0])
    elif len(args) > 1 and args[-1] == '-h':
        return COMMANDS['help'].call(args=args[0:-1])
    else:
        try:
            return COMMANDS[args[0]].call(args=args[1:])
        except CommandError as err:
            sys.stderr.write(err.message+"\n")
            sys.stderr.write('Try `%s help %s\' for more information.\n'%\
                                 (chimi.command.basename, ' '.join(err.command.full_name_list)))
        except InvalidArchitectureError as err:
            sys.stderr.write(err.message+"\n")
            sys.stderr.write('Run `%s show arch -l\' for a list of valid architecture names.\n'%\
                                 chimi.command.basename)
        return 1

if __name__ == "__main__":
    exit(main())
