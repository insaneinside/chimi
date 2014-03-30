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
"""
Classes and functions that implement Chimi's commands interface.

"""
from __future__ import print_function

__author__    = 'Collin J. Sutton'
__copyright__ = 'Copyright (C) 2014 Collin J. Sutton'
__license__   = 'GPLv2'

import os
import re
import sys

from chimi.option import Option, OptionParser

import chimi
import chimi.job
import chimi.core
import chimi.settings

basename = os.path.basename(sys.argv[0])

__all__ = ['CommandError', 'CommandUsageError', 'SubcommandError', 'Command',
           'find_current_package_set', 'main']

class CommandError(chimi.Error):
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
        self.name = name
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
            self.subcommand_dict = {}
            for cmd in self.subcommands:
                cmd.parent = self
                self.subcommand_dict[cmd.name] = cmd
        else:
            self.subcommands = []
            self.subcommand_dict = {}

        for arg in self.arguments_usage:
            if arg[0] != '[':
                self.required_arg_count += 1

    def __repr__(self):
        return '<Command:%s>' % ' '.join(self.full_name_list)

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
                       chimi.util.wrap_text(self.help_detail, respect_newlines=False) +
                       "\n\n" if self.help_detail else ''])

    @property
    def num_args(self):
        """Maximum number of arguments accepted"""
        return len(self.arguments_usage)

    def find_subcommand(self, name):
        """Find a subcommand by name."""
        if len(self.subcommands) == 0 or not name in self.subcommand_dict:
            raise SubcommandError(self, name)
        else:
            return self.subcommand_dict[name]

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
        options = []
        if len(self.options) > 0:
            options.extend(OptionParser.flatten(self.options))


        # Make "-h" work for printing the help string for any command.
        # Anything after this option will be ignored -- even subcommands (and
        # "-h" flags that follow them).
        def impromptu_help(self):
            helpfn({}, cmd=self)
            exit(0)
        options.append(Option('h', 'help', 'Show help for the %s command' % self.name)\
                        .handle(lambda *x: impromptu_help(self)))

        # Parse options for this command.
        stop_set = self.subcommand_dict.keys()
        try:
            opts_out.update(OptionParser.handle_options(options, args, stop_set))
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
            else:
                cmd = self.find_subcommand(args[0])
                del args[0]

                if len(args) < cmd.required_arg_count:
                    raise CommandUsageError(cmd)
                elif self.callback != None:
                    # Invoke the parent command's handler to do e.g. common
                    # initialization for subcommands, and then invoke the
                    # subcommand using the results of that call.
                    common_result = self.callback(opts_out, *args)
                    if common_result is None:
                        opts_out, args_out, _kwargs = opts_out, args, {}
                    else:
                        opts_out, args_out, _kwargs = common_result
                        if _kwargs is None:
                            if isinstance(args_out, dict):
                                _kwargs = args_out
                            args_out = args

                    return cmd.call(opts=opts_out, args=args_out, kwargs=_kwargs)
                else:
                    # No handler for parent command, so invoke the subcommand
                    # "normally" (we still provide the additional options from
                    # the parent command).
                    return cmd.call(opts=opts_out, args=args)

def load_platform_resources():
    import chimi.lmod
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
    PackageSet = chimi.core.PackageSet
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

    command_list=kwargs['command_list'] if 'command_list' in kwargs else COMMAND_LIST

    if len(args) == 0 and not 'cmd' in kwargs and 'command_list' in kwargs:
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
            io.write("\nUse `%s help %s COMMAND' for detailed information on a command.\n" %
                     (basename, ' '.join(command_list[0].parent.full_name_list[1:])))

    else:
        cmd = None
        if 'cmd' in kwargs:
            cmd = kwargs['cmd']
        else:
            cmd = chimi_command
            while len(args) > 0:# and len(cmd.subcommands) > 0:
                cmd = cmd.find_subcommand(args.pop(0))
        io.write(cmd.help)
        if isinstance(cmd.subcommands, list) and len(cmd.subcommands) > 0:
            helpfn(opts, io, command_list=cmd.subcommands)


def build(config, which=None, *args):
    which_args = ['all', 'changa', 'charm']

    args = list(args)
    if '--' in args:
        del args[args.index('--')]

    extras = args
    if len(extras) > 0:
        incdirs = [s[2:] for s in filter(lambda x: x.startswith('-I'), extras)]
        linkdirs = [s[2:] for s in filter(lambda x: x.startswith('-L'), extras)]

        for _dir in incdirs:
            if (not force) and not os.path.exists(_dir):
                raise ValueError("\n\nSpecified include path \"%s\" does "%_dir +
                                 "not exist.  If you\'re sure this is the\n"
                                 "right argument, use the `--force\' option.")
        for _dir in linkdirs:
            if (not force) and not os.path.exists(_dir):
                raise ValueError("\n\nSpecified library path \"%s\" does "%_dir +
                                 "not exist.  If you\'re sure this is the\n"
                                 "right argument, use the `--force\' option.")


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

    arch = config['arch'] if 'arch' in config else None
    opts = config['options'] if 'options' in config else []
    branch = config['branch'] if 'branch' in config else None

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

    purge_callback = lambda x: sys.stderr.write("  %s build \"%s\"\n" % \
                                                    ('purging'
                                                     if not chimi.settings.noact
                                                     else 'would purge',
                                                     x.name))

    for item in which:
        package = ps.packages[item]
        config = chimi.build.BuildConfig.create(package, arch=arch, opts=opts,
                                                extras=extras, branch=branch)
        if purge == 'all':
            package.purge_builds()
        elif isinstance(purge,bool) and purge:
            sys.stderr.write('Purging from %s:\n'%package.definition.name)
            n = package.purge_builds(config=config, callback=purge_callback)
            if not n:
                sys.stderr.write('  hmmm, no builds matched.\n')
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
                                     callback=purge_callback)
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
    if os.path.exists(os.path.join(directory, chimi.core.PackageSet.SET_FILE)):
        raise RuntimeError('Directory is already initialized')
    else:
        ps = chimi.core.PackageSet(directory)
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
        chimi.settings.relative_message_timestamps = True

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
            if len(build.config.components) > 0:
                components_desc = ' '.join(build.config.components)
            sys.stdout.write("    components: %s\n" % components_desc)

            if len(build.config.features) > 0:
                sys.stdout.write("    features:\n")
                for sname in build.config.features:
                    sys.stdout.write("      %s=%s\n" % (sname, build.config.features[sname]))

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

    if not len(chimi.core.CharmDefinition.Architectures) > 0:
        chimi.core.CharmDefinition.load_architectures(ps.packages['charm'])

    use_color = sys.stdout.isatty()
    sym_pfx = ''
    unique = False
    if 'unique' in opts:
        unique = True

    _type='build'
    if 'type' in opts:
        _type = opts['type']
    assert(_type in ['build', 'base', 'both', 'all'])

    list_only = False
    if 'list' in opts:
        list_only = True

    if len(args) == 0:
        args = sorted(chimi.core.CharmDefinition.Architectures.keys());
    else:
        # Show _all_ architectures that the user explicitly asked to see.
        _type = 'all'

    name_fmt = '\033[1;97m%s\033[0m%s' if use_color else '%s%s'
    for aname in args:
        arch = chimi.core.CharmDefinition.Architectures[aname]
        if (arch.is_base and _type == 'build') or \
                (_type == 'base' and not arch.is_base) or \
                (arch.name == 'common' and _type != 'all'):
            continue


        inh_str = ''
        if arch.parent and not list_only:
            inh_str = ' (%s)' % arch.parent.name
        sys.stdout.write(name_fmt % (arch.name, inh_str))

        opts = []
        cc = []
        fcc = []
        if not list_only:
            if unique:
                opts = arch._options
                cc = arch._compilers
                fcc = arch._fortran_compilers
            else:
                opts, cc, fcc = arch.merge_property_with_inherited(('_options', '_compilers', '_fortran_compilers'))

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
    t = chimi.util.Table(cols=('Name', 'UUID', 'Branch', 'Version', 'Options', 'Status'))
    use_color = sys.stdout.isatty()
    ps = chimi.command.find_current_package_set()

    package = 'changa'
    branch = None

    if 'package' in opts:
        package = opts['package']

    _builds = ps.packages[package].builds

    if 'branch' in opts:
        _builds = filter(lambda x: x.config.branch == opts['branch'], _builds)

    if 'arch' in opts:
        archname = opts['arch']
        if not len(chimi.core.CharmDefinition.Architectures) > 0:
            chimi.core.CharmDefinition.load_architectures(ps.packages['charm'])
        if not archname in chimi.core.CharmDefinition.Architectures:
            raise InvalidArchitectureError(archname)
        else:
            def gather_names(arch):
                out = [arch.name]
                if len(arch.children) > 0:
                    out.extend([name
                                for ch in arch.children
                                for name in gather_names(ch)
                                ])
                return out
            arch_names = gather_names(chimi.core.CharmDefinition.Architectures[archname])
            _builds = filter(lambda x: x.config.architecture in arch_names, _builds)

    if len(_builds) > 0:
        _builds.sort(cmp=lambda x, y: cmp(x.name,y.name))
        for _build in _builds:
            status = make_colored_build_status_string(_build.status)\
                if use_color \
                else _build.status.name
            t.append((_build.name, _build.uuid, _build.config.branch,
                      _build.version, ' '.join(_build.config.components), status))

        print(t.render(use_color=use_color))
    else:
        sys.stderr.write('No matching builds.\n')
    return 0

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
            lambda x, *y, **kwargs: helpfn(x, *y, **kwargs)),
    # Build.
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
            """
The target, if not given, defaults to "changa".  The ChaNGa package definition
will initiate a matching Charm++ build if a suitable one is not found.

For a list of valid architecture names, run `%s show arch -l'.  As a special
case, the `--arch' option accepts base architectures as well
(`%s show arch -lt base\'); when a base architecture name is given, an attempt
is made to automatically determine the appropriate build architecture.

""" % (basename, basename), build),
    # Job
    Command('job', ['CMD', '[ARG]...'], 'Manage job(s) on local or remote nodes.',
            [Option('H', 'host', 'Manipulate jobs on remote HOST via SSH [default: local]',
                    '[USER@]HOST').store(),
             Option('m', 'manager', 'Specify/override job manager (job-service'
                    ' adaptor) to use.', 'MANAGER').store()],
            'See help for the `run\' subcommand for where to find a list of '
            'available job-service adaptors.',
            callback=chimi.job.common,
            subcommands=[
            # Run
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
for accessing HPC resources.  A list of the available job-service adaptors, and
the job-description attributes available for each, is available in the adaptor
documentation (link below).

Note that even though the SAGA-Python documentation uses CamelCase in listing
job-description attributes, both the API itself and this tool require that they
be given in "snake_case" (all lower-case, words separated by underscores) or
"spinal-case" (like snake case, but with hyphens instead of underscores).

The API documentation for SAGA-Python's adaptors can be found at:

http://saga-project.github.io/saga-python/doc/adaptors/saga.adaptor.index.html

"""
                    , callback=chimi.job.run),
            # Watch
            Command('watch', ['JOB'], 'Watch a job for state changes.',
                    [], None, chimi.job.watch),
            # Cancel
            Command('cancel', ['JOB'], 'Cancel a job.',
                    [], None, chimi.job.cancel),
            # List
            Command('list', [], 'List jobs.',
                    [], None, chimi.job._list),
            ]),
    # Status
    Command('status', [], 'List recorded build/package information.',
            [Option('r', 'reltime', 'Use relative time stamps').store() ],
            None, list_items),
    # Show
    Command('show', ['COMMAND'], 'Show useful information about various items.',
            [], None,
            subcommands=[
            # Architectures list.
            Command('arch', ['[ARCH]...'],
                    'List available options and compilers for a Charm++ '
                    'architecture.  If no architecture is given, do this for '
                    'all available Charm++ architectures.',
                    [Option('t', 'type', 'Show TYPE architectures, where TYPE '
                            'is "build", "base", "both", or "all". (default: build).',
                            'TYPE').store(),
                     Option('l', 'list', 'List only the names of available architectures').store(),
                     Option('u', 'unique', 'Show only non-inherited options and '
                            'compilers for each architecture.').store()],
                    """
This command requires an initialized Chimi directory.

Charm++ builds are generally identified first by their architecture name, then
by optional features included at build time (some of which may be unique to
that architecture).  This command parses the content of a Charm++ source tree
to extract information about available architectures and the options &
compilers available for each.

The `--type' option accepts several values, which are explained here.
  * "build" shows architectures that are available for use in a Charm++ build.
  * "base" shows non-build architectures from which one or more build
    architectures inherit code and/or options.
  * "both" shows both build and base architectures.
  * "all" is equivalent to "both", but also shows the `common' architecture,
    which is inherited by all base architectures.

`--type'/`-t' is ignored when architectures names are passed as arguments.
"""
                    , callback=show_architectures),
            Command('builds', [], 'List package builds.',
                    [Option('p', 'package', 'Show builds for PACKAGE. (default: changa)',
                            'PACKAGE').store(),
                     Option('b', 'branch', 'Filter by branch BRANCH.', 'BRANCH').store(),
                     Option('a', 'arch', 'Filter by architecture ARCH and descendents.',
                            'ARCH').store(),
                     ], None, callback=show_builds),
            ]),
    ]


def common(opts, *args):
    chimi.settings.noact = opts['noact'] if 'noact' in opts else False

chimi_command = Command(basename, ['COMMAND', '[ARGUMENT]...'],
                        'Perform boring ChaNGa-related tasks.',
                        [Option('h', 'help', 'Show this help.').handle(lambda *x: show_help(sys.stdout, True, 0)),
                         Option('n', 'noact', 'Don\'t actually change anything or run any commands.').store(),
                         ],
                        None,
                        callback=common,
                        subcommands=COMMAND_LIST)

def main():
    """
    Chimi's primary entry point.

    """

    load_platform_resources()
    chimi.run_cwd = os.getcwd()

    args = sys.argv[1:]
    try:
        return chimi_command.call({}, args=args)
    except CommandError as err:
        sys.stderr.write(err.message+"\n")
        sys.stderr.write('Try `%s help%s\' for more information.\n'%\
                             (chimi_command.name,
                              ' ' + ' '.join(err.command.full_name_list[1:]) \
                                  if len(args) > 0 \
                                  else ''))
    except chimi.build.InvalidArchitectureError as err:
        sys.stderr.write(err.message+"\n")
        sys.stderr.write('Run `%s show arch -l\' for a list of valid architecture names.\n'%\
                             chimi_command.name)
    except chimi.Error as err:
        sys.stderr.write(err.message+"\n")
    return 1
