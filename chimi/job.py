# chimi: a companion tool for ChaNGa: ChaNGa invocation support
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

"""
Job-management utilities for Chimi.  This module allows Chimi to
semi-intelligently launch jobs on a variety of hosts, using host-,
architecture-, and option-specific configuration data to influence the ChaNGa
command-line for a job.

"""


__author__    = 'Collin J. Sutton'
__copyright__ = 'Copyright (C) 2014 Collin J. Sutton'
__license__   = 'GPLv2'

import os
import re
import sys
import stat
import math
import copy

import threading
import chimi.config
import chimi.transient

__all__ = ['ADAPTORS', 'JOB_MANAGERS', 'build_changa_args', 'service_uri',
           'run', 'watch', 'cancel']

ADAPTORS=None
ADAPTORS_DIR=None
ADAPTOR_DIRS=None

def load_saga():
    if not 'saga' in chimi.job.__dict__:
        chimi.transient.import_(__name__, 'saga')
        chimi.transient.import_(__name__, 'saga.job')
        chimi.transient.import_(__name__, 'saga.adaptors')

        # SAGA-Python loads adaptors on-demand, but we want to be able to query their
        # supported URI schemas here; manually load them.
        chimi.job.ADAPTORS_DIR = saga.adaptors.__path__[0]
        chimi.job.ADAPTOR_DIRS = filter(lambda e: os.path.isdir(os.path.join(chimi.job.ADAPTORS_DIR, e)),
                              os.listdir(chimi.job.ADAPTORS_DIR))
        chimi.job.ADAPTORS=[]

        for name in chimi.job.ADAPTOR_DIRS:
            for f in filter(lambda e: e[0] != '_' and re.match(r'^.*job\.py$', e),
                           os.listdir(os.path.join(chimi.job.ADAPTORS_DIR, name))):
                subname = re.sub('\.py$', '', f)
                modname = '.'.join([name, subname])
                try:
                    chimi.transient.import_(__name__, 'saga.adaptors.%s'%modname)
                    mod = getattr(saga.adaptors, name)
                    mod = getattr(mod, subname)
                    if '_ADAPTOR_DOC' in dir(mod):
                        chimi.job.ADAPTORS.append(mod)
                    del mod
                except ImportError:
                    pass
                del subname
                del modname

        chimi.job.ACCESS_TYPE_NAMES=['local', 'ssh', 'gsissh']
        chimi.job.JOB_MANAGERS={}
        for ad in chimi.job.ADAPTORS:
            if re.match('.*job$', ad.__name__):
                schemas = ad._ADAPTOR_DOC['schemas'].keys()
                schemas.sort()

                manager_name = re.sub(r'^.*\.([^.]+)\.[^.]+$', r'\1', ad.__name__)

                dual_modes = filter(lambda x: '+' in x, schemas)

                if len(dual_modes) > 0:
                    chimi.job.JOB_MANAGERS[manager_name] = {'name': manager_name,
                                                            'access-types': map(lambda x: re.sub('^.+\+(.+)$', r'\1', x),
                                                                                dual_modes)}
                else:
                    chimi.job.JOB_MANAGERS[manager_name] = {'name': manager_name,
                                                            'access-types': schemas}
                del schemas
                del manager_name
                del dual_modes
            del ad

def service_uri(job_manager, hostname=None, access_type=None,
                host_config=None):
    """
    Constructs SAGA job-service URI.  If `access_type` is `None`, a local
    connection is used.

    """
    if access_type == None:
        hostname = 'localhost'

    if access_type != None and not access_type in \
            JOB_MANAGERS[job_manager]['access-types']:
        raise ValueError('Invalid access type `%s\' for job manager `%s\'' %
                         (name, job_manager))

    if ((host_config and not host_config.matches_current_host) or not host_config) and \
            hostname != 'localhost' and access_type == None:
        access_type = 'ssh'

    if access_type == None:
        if job_manager == 'shell' and hostname == 'localhost':
            return 'local://localhost'
        else:
            return '%s://%s' % (job_manager, hostname)
    else:
        return '%s+%s://%s' % (job_manager, access_type, hostname)


def apply_tree(to, tree, root=None):
    """
    Apply terminal values in a `dict` configuration tree on top of a dict-like
    object.

    If `root` is given, it should be a tuple specifying the location within
    `tree` at which to start applying values; it is *not* an error if the tree
    does not contain such a node, but *is* an error if that node does not
    resolve to a dict.

    """
    if root:
        root = list(root)
        while len(root) > 0:
            if not root[0] in tree:
                return
            else:
                tree = tree[root.pop(0)]
    if not isinstance(tree, dict):
        raise ValueError('Invalid value for apply_tree: root node of `tree` is not a dict!')

    for key in tree:
        value = tree[key]
        assign_key = key.replace('-', '_')
        if isinstance(value, dict):
            if not key in to:
                to[assign_key] = {}
            apply_tree(to[assign_key], value)
        else:
            to[assign_key] = value

def make_launch_config(build, host_config, architectures):
    import yaml
    import pkg_resources

    # Copy the host configuration
    lc = copy.copy(host_config.jobs.launch)
    option_db = yaml.load(pkg_resources.resource_string(__name__, 'data/option.yaml'))
    arch_db = yaml.load(pkg_resources.resource_string(__name__, 'data/architecture.yaml'))
    opts = set(build.config.components)
    opts.update(filter(lambda x: build.config.features[x], build.config.features.keys()))

    for option in opts:
        if option in option_db:
            apply_tree(lc, option_db[option],
                       ('jobs', 'launch'))

    arch, base_arch = architectures

    if arch_db:
        if base_arch.name in arch_db:
            apply_tree(lc, arch_db[base_arch.name],
                       ('jobs', 'launch'))
        if arch.name in arch_db:
            apply_tree(lc, arch_db[arch.name],
                       ('jobs', 'launch'))
    return lc

def build_charm_extension(package_set):
    """
    Builds Chimi's built-in Charm extension, if necessary, and sets up the
    Python search path so we can find it.

    """

    charm = package_set.packages['charm']
    charm_build = charm.builds[0]
    extension_dir = os.path.join(package_set.directory, 'chimi-tmp', 'ext')
    extension_path = os.path.join(extension_dir, 'charm.so')
    if not os.path.exists(extension_path):
        if not os.path.isdir(extension_dir):
            os.makedirs(extension_dir)
        import pkg_resources
        charm_source_string = pkg_resources.resource_string(__name__, 'data/ext/charm.cc')
        charm_source_path = os.path.join(extension_dir, 'charm.cc')

        # Fetch and transform the `CmiNumCores` source.
        src = file(os.path.join(charm.directory, 'src', 'conv-core', 'cputopology.C'), 'r').read()
        match = re.search(r'CmiNumCores[\s\n]*\((?:[\s\n]*void[\s\n]*|[\s\n]*)?\)[\s\n]*{', src, re.DOTALL)
        score = 1
        idx = match.end() + 1
        braces = re.compile(r'[{}]')
        while score > 0:
            m = braces.search(src, idx)
            score += 1 if m.group() == '{' else -1
            idx = m.end() + 1
        func_source = src[match.end()-1:idx+1]
        retre = re.compile(r'\breturn[\s\n]+([^\s\n]+)[\s\n]*;')
        py_cmi_num_cores_code = \
            'static PyObject*\n' + \
            'PyCmiNumCores()'+retre.subn(r'return PyInt_FromLong(\1);', func_source)[0]
        file(charm_source_path, 'w').write(charm_source_string.replace('PY_CMI_NUM_CORES_CODE',
                                                                       py_cmi_num_cores_code))

        # Prepare the extension for compilation.
        import distutils.core
        import distutils.dist
        import distutils.command.build_ext
        ext = distutils.core.Extension('charm',
                                       sources=['charm.cc'],
                                       include_dirs=[os.path.join(charm_build.directory, 'include')],
                                       extra_compile_args=['--no-warnings'],
                                       language='c++'
                                       )

        dist = distutils.dist.Distribution({'ext_modules': [ext],
                                            'script_args': ['build_ext', '--inplace']})
        cmd = dist.get_command_obj('build_ext')
        dist._set_command_options(cmd, {'inplace': (None, True)})


        # distutils or python-config (...or something) decides to pass
        # '-Wstrict-prototypes' (a C-language option) to the compiler, which of
        # course complains because we're compiling C++ sources.  (And *of
        # course* the '--no-warnings' compile flag [or any similar flag] has no
        # effect because of the order in which distutils combines compiler
        # flags.  Grrrrr!)
        #
        # I don't like being told that I did something wrong when it's not my
        # fault, so we redirect standard error to /dev/null.  (Compile errors?
        # What compile errors?)
        stderr = os.dup(sys.stderr.fileno())
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, sys.stderr.fileno())

        # Change directory into the extension dir, build the extension, and
        # restore the previous working directory.
        oldcwd = os.getcwd()
        error = None
        try:
            os.chdir(extension_dir)
            dist.run_command('build_ext')
        except distutils.errors.CompileError as err:
            error = err
        finally:
            os.chdir(oldcwd)
            os.dup2(stderr, sys.stderr.fileno())

        if error:
            print(error)

    if not extension_dir in sys.path:
        sys.path.append(extension_dir)

def build_changa_invocation(opts, job_description, build,
                            package_set, host_config, user_args,
                            changa_invocation_as_argument=False):
    """
    Build ChaNGa/charmrun command line corresponding to the job description.

    """
    assert(isinstance(job_description, saga.job.Description))
    import chimi.core

    # Find the architectures -- actual and base -- of the build.
    if not len(chimi.core.CharmDefinition.Architectures) > 0:
        chimi.core.CharmDefinition.load_architectures(package_set.packages['charm'])
    arch = chimi.core.CharmDefinition.Architectures[build.config.architecture]
    base_arch = arch
    while base_arch.parent and base_arch.parent.name != 'common':
        base_arch = base_arch.parent

    # Ensure the Charm-related utilities extension is built and available
    build_charm_extension(package_set)
    import charm

    # Construct the launch configuration based on build and architecture settings.
    lc = make_launch_config(build, host_config, (arch, base_arch))
    out = []

    # Find the shortest path to the ChaNGa and charmrun executables.
    charmrun_path = os.path.join(build.directory, 'charmrun')
    changa_path = os.path.join(build.directory, 'ChaNGa')

    charmrun_relpath = os.path.relpath(charmrun_path, job_description.working_directory)
    changa_relpath = os.path.relpath(changa_path, job_description.working_directory)

    if len(charmrun_relpath) < len(charmrun_path):
        charmrun_path = charmrun_relpath

    if len(changa_relpath) < len(changa_path):
        changa_path = changa_relpath

    # Determine run parameters.
    cpus_per_host = charm.cmi.num_cores()

    total_cpu_count = job_description.total_cpu_count \
        if job_description.attribute_exists(saga.job.TOTAL_CPU_COUNT) \
        else 1
    processes_per_host = job_description.processes_per_host \
        if job_description.attribute_exists(saga.job.PROCESSES_PER_HOST) \
        else cpus_per_host

    if 'spmd_variation' in lc.__dict__:
        job_description.spmd_variation = lc.spmd_variation

    # Ensure we've specified a total CPU count that the job manager likes.  If
    # we haven't, round up to the next multiple-of value.
    if 'total_cpu_count_multiple_of' in lc.__dict__ and\
            total_cpu_count % lc.total_cpu_count_multiple_of != 0:
        job_description.total_cpu_count = total_cpu_count \
            - (total_cpu_count % lc.total_cpu_count_multiple_of) \
            + lc.total_cpu_count_multiple_of

    node_count = int(math.ceil(float(total_cpu_count) / processes_per_host))

    local_run = node_count <= 1

    # We can pass "++local" to non-ibverbs net builds to make them ignore
    # network functionality.
    local_net = \
        local_run and \
        base_arch.name == 'net' and \
        not 'ibverbs' in build.config.components

    # Don't need ++mpiexec or a remote shell for non-ibverbs local runs.
    if local_run and not 'ibverbs' in build.config.components:
        lc.mpiexec = False
        lc.remote_shell = None

    # Are we using a remote shell?  For certain remote-shell names we need to
    # actually create a script.
    remote_shell = lc.remote_shell
    if remote_shell:
        scripts_dir = os.path.join(package_set.directory, 'chimi-tmp', 'scripts')
        if not os.path.isdir(scripts_dir):
            os.makedirs(scripts_dir)
        if remote_shell == 'ibrun-adaptor':
            script_path = os.path.join(scripts_dir, 'ibrun-adaptor.sh')
            if not os.path.isfile(script_path):
                file(script_path, 'w').write("#!/bin/sh\necho ibrun-adaptor args: \"$@\" > /dev/stderr\nshift; shift; exec ibrun \"$@\"\n")
                st = os.stat(script_path)
                os.chmod(script_path, st.st_mode | stat.S_IXUSR)
            remote_shell_relpath = os.path.relpath(script_path, job_description.working_directory)
            if len(remote_shell_relpath) < len(script_path):
                remote_shell = remote_shell_relpath
            else:
                remote_shell = script_path

    # If we're using more than one CPU -- or running locally on a `net' build
    # -- we need to launch with charmrun.
    using_charmrun = False
    if node_count > 1 or total_cpu_count > 1 or \
            (local_net and not changa_invocation_as_argument) or \
            (local_net and changa_invocation_as_argument and '{}' in user_args):
        out = [charmrun_path]
        using_charmrun = True

        if job_description.attribute_exists(saga.job.TOTAL_CPU_COUNT):
            out.append('+p%d'% total_cpu_count)

        if base_arch.name == 'net':
            # `net'-specific options.
            if node_count > 1 and processes_per_host > 1 and job_description.attribute_exists(saga.job.PROCESSES_PER_HOST):
                assert(processes_per_host < cpus_per_host)
                out.extend(['++ppn', str(job_description.processes_per_host)])

            if lc.mpiexec and not local_run:
                out.append('++mpiexec')

            if remote_shell:
                out.extend(['++remote-shell', remote_shell])
    elif remote_shell:
        # When we're *not* using charmrun, this should be the first element.
        assert(len(out) == 0)
        out.append(remote_shell)

    # Now write the ChaNGa command line.
    if not changa_invocation_as_argument:
        out.append(changa_path)
        if local_net and using_charmrun:
            out.append('++local')
        if job_description.attribute_exists(saga.job.WALL_TIME_LIMIT):
            out.extend(['-wall', str(job_description.wall_time_limit)])
        out.extend(user_args)
    else:
        out.extend(user_args)

        insert_index = len(out)

        if '{}' in out:
            insert_index = out.index('{}') + 1
            out[insert_index - 1] = changa_path

            if local_net and using_charmrun:
                out.insert(insert_index, '++local')
                insert_index += 1

            if job_description.attribute_exists(saga.job.WALL_TIME_LIMIT):
                out.insert(insert_index, '-wall')
                out.insert(insert_index + 1, str(job_description.wall_time_limit))

    return out


def common(opts, *args):
    load_saga()
    host_config = None

    host_name = 'localhost'
    user_name = None

    if 'host' in opts:
        host_name = opts['host']
    if '@' in host_name:
        user_name, host_name = host_name.split('@')

    sys.stderr.write("Loading host configuration... ")
    host_config = chimi.config.HostConfig.load(host_name)
    if 'host' in host_config.jobs.__dict__ and host_config.jobs.host:
        host_name = host_config.jobs.host
    sys.stderr.write("loaded.\n")

    opts['host'] = host_name
    opts['user'] = user_name

    return (opts, {'host_config': host_config})

def create_job_service(opts, host_config):
    host_name = opts['host']
    user_name = opts['user']
    context = None

    access_type = None
    if not host_config.matches_current_host:
        access_type = 'ssh'

    job_manager = host_config.jobs.manager # job-manager _name_
    if 'manager' in opts:
        job_manager = opts['manager']

    if host_config.jobs.host and not 'host' in opts:
        host_name = re.sub(r'^([^\.]+).*$', r'\1', host_config.jobs.host)

    # Instantiate the job-service adaptor.
    uri = chimi.job.service_uri(job_manager, host_name, access_type, host_config)

    if chimi.settings.noact:
        return chimi.util.create_struct(None, 'FakeService', url=uri, list=lambda: [])()
    else:
        # Load the SAGA security context.
        sys.stderr.write("Loading SAGA security context... ")
        if 'context' in opts:
            cxt = opts['context']
            cxt_settings = {}
            cxtname = cxt
            if ':' in cxt:
                cxtname, cxtopts = cxt.split(':', 2)
                cxtopts = cxtopts.split(',')
                for opt in cxtopts:
                    if not '=' in opt:
                        raise ValueError('Invalid context setting in "%s"' % opt)
                    else:
                        name, val = opt.split('=', 2)
                        cxt_settings[oname] = oval

            context = saga.Context(cxtname)
            for name in cxt_settings:
                setattr(context, name, cxt_settings[name])
        elif not host_config.matches_current_host:
            chimi.transient.import_(__name__, 'chimi.sshconfig')
            context = saga.Context('ssh')
            ssh_config = chimi.sshconfig.SSHConfig()

            if user_name == None:
                user_name = ssh_config.value('User', host_name)

            if user_name != None:
                context.user_id = user_name

            identity_file = ssh_config.value('IdentityFile', host_name)

            if identity_file != None:
                context.user_cert = identity_file
        sys.stderr.write("done.\n")

        # Create the SAGA session object.
        sys.stderr.write("Loading SAGA session... ")
        session = saga.Session()
        if context != None:
            session.add_context(context)
        sys.stderr.write("okay.\n")

        sys.stderr.write("Loading job-manager for \"%s\"... " % uri)
        service = saga.job.Service(uri, session)
        sys.stderr.write("done.\n")
        return service

def run(opts, *args, **kwargs):
    """Run ChaNGa"""
    args = list(args)

    if args[0] == '--':
        del args[0]

    import chimi.command
    ps = chimi.command.find_current_package_set() # FIXME: make this work for remote hosts?

    # Select the build to use for the job.
    sys.stderr.write("Selecting build... ")
    build = None
    build_config = None
    if 'build' in opts:
        # A build was specified by the user; see if we have one with that name
        # or UUID.
        matches = filter(lambda x: x.name == opts['build'], ps.packages['changa'].builds)
        if len(matches) == 0:
            matches = filter(lambda x: str(x.uuid) == opts['build'], ps.packages['changa'].builds)

        if len(matches) == 0:
            sys.stderr.write('no builds with that name or UUID: ')
        elif len(matches) > 1:
            sys.stderr.write("multiple matching builds; this shouldn't happen: ")
        else:
            build = matches[0]
    else:
        # No build-configuration options specified; use the latest build.
        sys.stderr.write('none specified, using latest build: ')
        build = sorted(ps.packages['changa'].builds)[-1]
        build_config = build.config

    if not build:
        sys.stderr.write("failed.\n")
        raise RuntimeError('Failed to find a ChaNGa build for job.')
    else:
        sys.stderr.write("chose %s.\n"%build.name)

    # Create the job description
    sys.stderr.write("Constructing job description... ")
    import saga.job
    job_desc = saga.job.Description()

    job_desc.working_directory = opts['cwd'] if 'cwd' in opts else os.getcwd()

    job_desc.output = 'job.stdout'
    job_desc.error = 'job.stderr'

    if 'O' in opts:
        jobopts = {}
        for jo_list_string in opts['O']:
            for jo in jo_list_string.split(','):
                jo = jo.strip()
                if '=' in jo:
                    name, val = jo.split('=', 2)
                    jobopts[name] = val
                elif jo != '':
                    raise ValueError('Invalid job attribute, `%s\''%jo)
                else:
                    continue
        for name in jobopts:
            val = jobopts[name]

            # Allow use of hyphen instead of underscore in attribute names.
            if '-' in name:
                name = name.replace('-', '_')
            if name == 'wall_time_limit' or name == 'total_cpu_count':
                val = int(val)
            setattr(job_desc, name, val)

    assert('host_config' in kwargs)
    host_config = kwargs['host_config']
    invocation = chimi.job.build_changa_invocation(opts, job_desc, build,
                                                   ps, host_config, args,
                                                   'e' in opts)
    job_desc.executable = invocation[0]
    job_desc.arguments = invocation[1:]

    sys.stderr.write("okay.\n")

    service = create_job_service(opts, host_config)

    # Pretty-print some information for the user.
    jdexec = [job_desc.executable]
    jdexec.extend(job_desc.arguments)
    print('\033[1m          Service:\033[0m %s' % service.url)
    print('\033[1mWorking directory:\033[0m %s' % job_desc.working_directory)
    print('\033[1m          Command:\033[0m %s' % ' '.join(jdexec))

    if 'noact' in opts or chimi.settings.noact:
        return

    # Create the job.
    job = service.create_job(job_desc)
    print("Job ID    : %s" % (job.id))
    print("Job State : %s" % (job.state))
    print("\n...starting job...\n")

    thr = None
    if 'watch' in opts:
        thr = threading.Thread(target=chimi.job.watch,
                               kwargs={'job':job, 'job_description': job_desc})
        thr.daemon = False
        thr.start()
    job.run()
    if 'watch' in opts:
        thr.join()

def find_job(opts, *args, **kwargs):
    service = create_job_service(opts, kwargs['host_config'])
    jobs = service.list()
    try:
        if not len(jobs):
            raise RuntimeError('no jobs exist.')
        else:
            return service.get_job(jobs[0])
    except Exception as err:
        sys.stderr.write('Failed to get job: %s\n'%err.message)

def _list(opts, *args, **kwargs):
    sys.stdout.write('\n'.join(create_job_service(opts, kwargs['host_config']).list())+"\n")

def watch(opts=None, *args, **kwargs):
    """Watch an enqueued job as it changes state."""
    job = None
    job_description = None
    if 'job' in kwargs:
        job = kwargs['job']
    else:
        job = find_job(opts, *args, **kwargs)

    if not job:
        return

    if 'job_description' in kwargs:
        job_description = kwargs['job_description']
    elif 'description' in job.__dict__:
        job_description = job.description
    else:
        sys.stderr.write('WARNING: failed to get job description; real-time output will not be available.\n')

    chimi_job_mutex = threading.Lock()

    JobAttributeInfo = chimi.util.create_struct(None, 'JobAttributeInfo',
                                                last_value=None,
                                                last_update=None)
    import datetime
    def job_attr_update(self, value):
        self.last_value = value
        self.last_update = datetime.datetime.now()
    JobAttributeInfo.update = job_attr_update

    job_attrs = {
        saga.job.STATE: JobAttributeInfo(last_value=saga.job.UNKNOWN, last_update=datetime.datetime.now()),
        # saga.job.STATE_DETAIL: JobAttributeInfo(last_value=None, last_update=datetime.datetime.now())
        }

    def state_cb(source, metric, value):
        chimi_job_mutex.acquire()
        attr = job_attrs[metric]

        old_value = attr.last_value
        old_time = attr.last_update

        print("%s %s change: %s \033[32m->\033[0m %s after %s" \
                  % (source, metric, old_value, value,
                     chimi.util.relative_datetime_string(old_time)))
        attr.update(value)
        chimi_job_mutex.release()

    # Wait for it to finish, printing state changes along the way.  The
    # (commented-out) line immediately below this comment adds a state-change
    # callback to the job, but SAGA job callbacks are unimplemented for some
    # adaptors so instead we do our own thing...

    # job.add_callback(saga.job.STATE, state_cb)

    def check_state():
        state = job.state
        if state != job_attrs[saga.job.STATE].last_value:
            state_cb(job, saga.job.STATE, state)

        # detail = job.state_detail
        # if detail != job_attrs[saga.job.STATE_DETAIL].last_value:
        #     state_cb(job, saga.job.STATE_DETAIL, detail)

    check_state()               # initialize job state values

    # cpid = -1
    # if job_description and job_description.output:
    #     cpid = os.fork()

    # if not cpid:
    #     chimi.util.watch_files((job_description.output,
    #                             job_description.error),
    #                            prefixes=('output| ', 'error| '),
    #                            outputs=(sys.stdout, sys.stderr))
    # else:
    if True:
        # Parent.  Monitor job state.
        while job.state != saga.job.DONE and \
                job.state != saga.job.CANCELED and \
                job.state != saga.job.FAILED and \
                job.state != saga.job.SUSPENDED and \
                job.state != saga.job.UNKNOWN:
            timer = threading.Timer(0.1, check_state)
            timer.start()

            timer.join()
        job.wait()
        # if not isinstance(cpid, type(None)):
        #     os.kill(cpid, signal.SIGQUIT)

        check_state()
        exit_code = None
        try:
            # SLURM adapter in SAGA-Python 0.13 (and probably other versions as
            # well) fails with a type error when fetching the exit code in some
            # cases.
            exit_code = job.exit_code
        except:
            pass

        print("      state: %s\n"
              "  exit code: %s\n"
              " exec hosts: %s\n"
              "create time: %s\n"
              " start time: %s\n"
              "   end time: %s" % (job.state, exit_code, job.execution_hosts, job.created, job.started, job.finished))


def cancel(opts, *args, **kwargs):
    """Cancel an enqueued job."""
    job = None
    if 'job' in kwargs:
        job = kwargs['job']
    else:
        job = find_job(opts, *args, **kwargs)

    try:
        job.cancel()
    except Exception as err:
        sys.stderr.write(err.message + "\n")
        exit(1)
