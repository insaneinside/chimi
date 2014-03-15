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

import os
import re
import sys

from datetime import datetime
import threading
import chimi.config
import chimi.command
import saga
import saga.job
import saga.adaptors

__all__ = ['ADAPTORS', 'JOB_MANAGERS', 'build_changa_args', 'service_uri',
           'run', 'watch', 'cancel']

# SAGA-Python loads adaptors on-demand, but we want to be able to query their
# supported URI schemas here; manually load them.
ADAPTORS_DIR = saga.adaptors.__path__[0]
ADAPTOR_DIRS = filter(lambda e: os.path.isdir(os.path.join(ADAPTORS_DIR, e)),
                      os.listdir(ADAPTORS_DIR))
ADAPTORS=[]

for name in ADAPTOR_DIRS:
    for f in filter(lambda e: e[0] != '_' and re.match(r'^.*\.py$', e),
                   os.listdir(os.path.join(ADAPTORS_DIR, name))):
        subname = re.sub('\.py$', '', f)
        modname = '.'.join([name, subname])
        try:
            __import__('saga.adaptors.%s'%modname)
            mod = getattr(saga.adaptors, name)
            mod = getattr(mod, subname)
            if '_ADAPTOR_DOC' in dir(mod):
                ADAPTORS.append(mod)
            del mod
        except:
            pass
        del subname
        del modname

ACCESS_TYPE_NAMES=['local', 'ssh', 'gsissh']
JOB_MANAGERS={}
for ad in ADAPTORS:
    if re.match('.*job$', ad.__name__):
        schemas = ad._ADAPTOR_DOC['schemas'].keys()
        schemas.sort()

        manager_name = re.sub(r'^.*\.([^.]+)\.[^.]+$', r'\1', ad.__name__)

        dual_modes = filter(lambda x: '+' in x, schemas)

        if len(dual_modes) > 0:
            JOB_MANAGERS[manager_name] = {'name': manager_name,
                                          'access-types': map(lambda x: re.sub('^.+\+(.+)$', r'\1', x),
                                                              dual_modes)}
        else:
            JOB_MANAGERS[manager_name] = {'name': manager_name,
                                          'access-types': schemas}
        del schemas
        del manager_name
        del dual_modes
    del ad

def service_uri(job_manager, hostname='localhost', access_type=None):
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

    if access_type == None:
        if job_manager == 'shell' and hostname == 'localhost':
            return 'local://localhost'
        else:
            return '%s://%s' % (job_manager, hostname)
    else:
        return '%s+%s://%s' % (job_manager, access_type, hostname)


def build_changa_args(job_description):
    """
    Build ChaNGa/charmrun arguments corresponding to the job description.
    """
    out = []
    import saga
    assert(isinstance(job_description, saga.job.Description))
    if job_description.attribute_exists(saga.job.TOTAL_CPU_COUNT):
        out.append('+p%d'%job_description.total_cpu_count)

    if job_description.attribute_exists(saga.job.PROCESSES_PER_HOST):
        out.extend(['++ppn', str(job_description.processes_per_host)])

    if job_description.attribute_exists(saga.job.WALL_TIME_LIMIT):
        out.extend(['-wall', str(job_description.wall_time_limit)])

    return out
                   

def common(opts, *args):
    host_config = None
    context = None

    host_name = 'localhost'
    user_name = None

    if 'host' in opts:
        host_name = opts['host']
    if '@' in host_name:
        user_name, host_name = host_name.split('@')


    sys.stderr.write("Loading host configuration... ")
    host_config = chimi.config.HostConfig.load(host_name)
    sys.stderr.write("loaded.\n")

    access_type = None
    if not host_config.matches_current_host:
        access_type = 'ssh'

    job_manager = host_config.jobs.manager # job-manager _name_
    if 'manager' in opts:
        job_manager = opts['manager']

    # Load the SAGA security context.
    sys.stderr.write("Setting up SAGA security context... ")
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
        context = saga.Context('ssh')
        ssh_config = chimi.SSHConfig()

        if user_name == None:
            user_name = ssh_config.value('User', host_name)

        if user_name != None:
            context.user_id = user_name

        identity_file = ssh_config.value('IdentityFile', host_name)

        if identity_file != None:
            context.user_cert = identity_file
    sys.stderr.write("done.\n")

    # Create the SAGA session object.
    sys.stderr.write("Creating SAGA session... ")
    session = saga.Session()
    if context != None:
        session.add_context(context)
    sys.stderr.write("okay.\n")

    # Instantiate the job-service adaptor.
    sys.stderr.write("Instantiating job-manager service handle... ")
    uri = chimi.job.service_uri(job_manager, host_name, access_type)
    service = saga.job.Service(uri, session)
    sys.stderr.write("done.\n")

    return (opts, {'service': service})

def run(opts, *args, **kwargs):
    """Run ChaNGa"""
    args = list(args)

    service = kwargs['service']

    if args[0] == '--':
        del args[0]
    
    # Create the build-config
    sys.stderr.write("Selecting build... ")
    bc = {}
    if 'o' in opts:
        bc['options'] = opts['o']

    if 'L' in opts:
        bc['L'] = opts['L']
    if 'I' in opts:
        bc['I'] = opts['I']

    build_config = chimi.command.make_build_config(bc)

    ps = chimi.command.find_current_package_set() # FIXME: make this work for remote hosts?

    build = ps.packages['changa'].find_build(build_config)
    if not build:
        raise RuntimeError('Failed to find a ChaNGa build matching supplied configuration options.')
    else:
        sys.stderr.write("chose %s.\n"%build.name)

    # Create the job description
    sys.stderr.write("Constructing job description... ")
    import saga.job
    job_desc = saga.job.Description()
    changa_path = os.path.join(build.directory, 'ChaNGa')

    if 'e' in opts:
        if '{}' in args:
            args = list(args)
            args[args.index('{}')] = changa_path

        job_desc.executable = args[0]
        job_desc.arguments = list(args[1:])
    else:
        job_desc.executable = changa_path
        job_desc.arguments = list(args)

    job_desc.working_directory = opts['cwd'] if 'cwd' in opts else os.getcwd()
    os.chdir(job_desc.working_directory)

    job_desc.output = 'job.stdout'
    job_desc.error = 'job.stderr'

    if 'O' in opts:
        jobopts = {}
        for jo_list_string in opts['O']:
            for jo in jo_list_string.split(','):
                name, val = jo.split('=', 2)
                jobopts[name] = val
        for name in jobopts:
            val = jobopts[name]

            # Allow use of hyphen instead of underscore in attribute names.
            if '-' in name:
                name = name.replace('-', '_')
            if name == 'wall_time_limit' or name == 'total_cpu_count':
                val = int(val)
            setattr(job_desc, name, val)
    job_desc.arguments.extend(chimi.job.build_changa_args(job_desc))
    sys.stderr.write("okay.\n")

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
        thr = threading.Thread(target=chimi.job.watch, kwargs={'job':job})
        thr.daemon = False
        thr.start()
    job.run()
    if 'watch' in opts:    
        thr.join()

def find_job(*args, **kwargs):
    service = kwargs['service']
    return service.get_job(service.list()[0])

def _list(*args, **kwargs):
    service = kwargs['service']
    sys.stdout.write('\n'.join(service.list())+"\n")

def watch(opts=None, *args, **kwargs):
    """Watch an enqueued job as it changes state."""
    job = None
    if 'job' in kwargs:
        job = kwargs['job']
    else:
        job = find_job(*args, **kwargs)
        
    global chimi_job_state, chimi_job_mutex, chimi_job_time
    chimi_job_state = saga.job.UNKNOWN
    chimi_job_mutex = threading.Lock()
    chimi_job_time = datetime.now()

    def state_cb(source, metric, value):
        global chimi_job_state, chimi_job_mutex, chimi_job_time
        chimi_job_mutex.acquire()
        print("%s state change: %s \033[32m->\033[0m %s after %s" \
                  % (source, chimi_job_state, value,
                     chimi.util.relative_datetime_string(chimi_job_time)))
        chimi_job_time = datetime.now()
        chimi_job_state = value
        chimi_job_mutex.release()

    # Wait for it to finish, printing state changes along the way.  The
    # (commented-out) line immediately below this comment adds a state-change
    # callback to the job, but SAGA job callbacks are unimplemented for some
    # adaptors so instead we do our own thing...

    # job.add_callback(saga.job.STATE, state_cb)

    def check_state():
        global chimi_job_state

        if job.state != chimi_job_state:
            state_cb(job, saga.job.STATE, job.state)

    check_state()

    while job.state != saga.job.DONE and \
            job.state != saga.job.CANCELED and \
            job.state != saga.job.FAILED and \
            job.state != saga.job.SUSPENDED and \
            job.state != saga.job.UNKNOWN:
        timer = threading.Timer(0.1, check_state)
        timer.start()
        timer.join()
    job.wait()

    check_state()
    exit_code = None
    try:
        # SLURM adapter in SAGA-Python 0.13 fails with a type error when
        # fetching the exit code in some cases.
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
        job = find_job(*args, **kwargs)
        
    try:
        job.cancel()
    except err:
        sys.stderr.write(err.message + "\n")
        exit(1)
