# chimi: a companion tool for ChaNGa: chimi dependency handling
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
Contains utilities for installing specific Chimi dependencies as needed.

"""

__author__    = 'Collin J. Sutton'
__copyright__ = 'Copyright (C) 2014 Collin J. Sutton'
__license__   = 'GPLv2'

import os
import re
import shutil

import chimi
import chimi.util
import chimi.command
import chimi.transient

__all__ = ['source', 'Package', 'PACKAGES', 'InstallError', 'install']

Source = chimi.util.create_enum(__name__, 'Source', 'GIT', 'PYPI', 'FATAL',
                                doc='Source-type enumeration for dependency packages.')
Package = chimi.util.create_struct(__name__, 'Package', 'name', 'source',
                                   pypi_name=None, repo=None, branch=None, fatal_reason=None)

PACKAGES = {'_inotify': Package('_inotify', Source.GIT, repo='https://github.com/insaneinside/python-inotify.git'),
            # GitPython from PyPI seems to be missing some dependencies, so we'll just fetch it from GitHub instead.
            # 'git':	Package('git',      Source.PYPI, pypi_name='GitPython'),
            'git':	Package('git',      Source.GIT, repo='https://github.com/gitpython-developers/GitPython.git'),
            'saga':	Package('saga',     Source.PYPI, pypi_name='saga-python'),
            'yaml':	Package('yaml',     Source.PYPI, pypi_name='PyYAML'),
            'pkg_resources': Package('setuptools', Source.FATAL,
                                     fatal_reason='provides utilities necessary to install other packages.')}


class InstallError(chimi.Error,RuntimeError):
    Reason = chimi.util.create_enum(__name__, 'Reason', 'COMMAND_FAILED', 'CANNOT_AUTO_INSTALL',
                                    doc='Possible causes of dependency-install errors.')


    def __init__(self, pkg, reason=None, logfile=None):
        self.package = pkg
        if reason == Reason.COMMAND_FAILED:
            if logfile:
                self.logfile = logfile
                logfile_relpath = os.path.relpath(self.logfile, os.getcwd())
                path_for_message = logfile_relpath if len(logfile_relpath) < len(self.logfile) else self.logfile

                super(RuntimeError, self).__init__('Installation of program dependency "%s" failed.\n' % self.package.name
                                                   + '    source: %s\n' % self.source_str(self.package)
                                                   + 'Log: %s' % path_for_message)
            else:
                super(RuntimeError, self).__init__('Installation of program dependency "%s" failed.\n' % self.package.name
                                                   + '    source: %s\n' % self.source_str(self.package))
        elif reason == Reason.CANNOT_AUTO_INSTALL:
            super(RuntimeError, self).__init__('Installation of program dependency "%s" failed.\n' % self.package.name +
                                               '    This package cannot be installed automatically because it\n' +
                                               '    %s.' % self.package.fatal_reason)


    @classmethod
    def source_str(self, pkg):
        if pkg.source == Source.GIT:
            return ('git repository %s (branch "%s")' % (pkg.repo, pkg.branch)
                    if pkg.branch
                    else 'git repository %s' % pkg.repo)
        elif pkg.source == Source.PYPI:
            return 'Python Package Index package "%s"' % pkg.pypi_name

def install(name):
    if name in PACKAGES:
        pkg = PACKAGES[name]
        r = None

        psdir = chimi.command.find_current_package_dir()
        tmp_dir = os.path.join(psdir, 'chimi-tmp', 'dependency')

        # Set up a log file
        if not os.path.isdir(tmp_dir):
            os.makedirs(tmp_dir)
        clean_name = re.sub(r'[._-]', '', name)
        logfile_path = os.path.join(tmp_dir, 'install-%s.log' % clean_name)
        logfile = file(logfile_path, 'w')

        if pkg.source == Source.GIT:
            r = install_from_git(pkg, tmp_dir, clean_name, logfile)
        elif pkg.source == Source.PYPI:
            r = install_from_pypi(pkg, logfile)
        elif pkg.source == Source.FATAL:
            raise InstallError(pkg, reason=InstallError.Reason.CANNOT_AUTO_INSTALL)
        else:
            raise NotImplementedError('%s: unknown dependency source type' % pkg.source)

        logfile.close()

        if r:
            raise InstallError(pkg, reason=InstallError.Reason.COMMAND_FAILED, logfile=logfile)
        else:
            os.unlink(logfile_path)
            if len(os.listdir(tmp_dir)) == 0:
                os.rmdir(tmp_dir)

            return r
    else:
        raise KeyError('Invalid dependency name "%s" given for installation' % name)


def install_from_git(pkg, tmp_dir, clean_name, logfile):
    """Attempt to build and install a package from Git repository source."""
    # Figure out where everything is 
    repo_dir = os.path.join(tmp_dir, clean_name)

    # Build the clone command
    clone_cmd = ['git', 'clone']
    if pkg.branch:
        clone_cmd.extend(['-b', pkg.branch])
    clone_cmd.extend([pkg.repo, repo_dir])

    chimi.transient.push('(Installing dependency "%s": fetching ... ' % pkg.name)
    r = chimi.util.check_call(clone_cmd, out=logfile, err=logfile)
    chimi.transient.pop(')')

    if r:
        return r

    if not chimi.settings.noact:
        assert(os.path.isfile(os.path.join(repo_dir, 'setup.py')))

    chimi.transient.push('(Installing dependency "%s": installing ... ' % pkg.name)
    r = chimi.util.check_call(['python', 'setup.py', 'install', '--user'], repo_dir,
                              out=logfile, err=logfile)
    chimi.transient.pop(')')

    if not r and not chimi.settings.noact:
        shutil.rmtree(repo_dir)

    return r


def install_from_pypi(pkg, logfile):
    """Attempt to install a named package from the Python Package Index"""
    pip = chimi.util.which('pip')
    easy_install = chimi.util.which('easy_install')
    name = pkg.pypi_name if pkg.pypi_name else pkg.name

    cmd = None
    if pip:
        assert(os.path.isfile(pip))
        cmd = [pip, 'install']
    elif easy_install:
        assert(os.path.isfile(easy_install))
        cmd =[easy_install]
    else:
        raise NotImplementedError('no PyPI install program found')

    cmd.extend(['--user', name])

    chimi.transient.push('(Installing dependency "%s" ... ' % pkg.name)
    r = chimi.util.check_call(cmd, out=logfile, err=logfile)
    chimi.transient.pop(')')
    return r
