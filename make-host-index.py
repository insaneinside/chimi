# Build a host-data index for Chimi.
import os
import re
import sys
import yaml

host_data_dir = os.path.join(os.path.dirname(__file__),
                             'chimi', 'data', 'host')

host_files = filter(lambda name: re.match(r'.*\.yaml$', name),
                    os.listdir(host_data_dir))

def raise_host_conflict(kind, value, source, entry):
    entry_kind_desc = "a %s" % entry.kind
    if entry.kind == 'alias':
        entry_kind_desc = "an alias"
        
    sys.stderr.write("CONFLICT: tried to add %s \"%s\" from %s to index but"
                     " that name was used as\n %s in %s.\n" %
                     (kind, value, source, entry_kind_desc, entry.host_file))

class IndexEntry(object):
    """Holds information used to report name conflicts"""
    def __init__(self, kind, host_file):
        self.kind = kind
        self.host_file = host_file
        
index = {}

for _file in host_files:
    d = yaml.load(file(os.path.join(host_data_dir, _file), 'r').read())
    if 'hostname' in d:
        hostname = d['hostname']
        if hostname in index and index[hostname].host_file != _file:
            raise_host_conflict('hostname', hostname, _file, index[hostname])
        else:
            index[hostname] = IndexEntry('hostname', _file)
    if 'aliases' in d:
        for alias in d['aliases']:
            if alias in index and index[alias].host_file != _file:
                raise_host_conflict('alias', alias, _file, index[alias])
            else:
                index[alias] = IndexEntry('alias', _file)
    if 'run' in d and 'host' in d['run']:
        run_host = d['run']['host']
        if run_host in index and index[run_host].host_file != _file:
            raise_host_conflict('run host', run_host, _file, index[run_host])
        else:
            index[run_host] = IndexEntry('run host', _file)


# If we've made it to this point, we have no name conflicts and can replace the
# IndexEntry objects with raw file names.
for name in index:
    index[name] = index[name].host_file


sys.stdout.write(yaml.dump(index))
