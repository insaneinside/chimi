Chimi: a Companion Tool for ChaNGa
====

Chimi is a command-line tool meant to ease the process of compiling and running
[ChaNGa](http://www-hpcc.astro.washington.edu/tools/changa.html) with a matching
build of Charm++.  It provides

  * host-specific build and job-management configuration support via a built-in
    database,
  * `git` integration for fetching the programs' sources and selecting branches
    for each build,
  * a simplified interface for building matching versions of Charm++ and ChaNGa
    and for tracking the status of those builds, and
  * a single, consistent interface for enqueuing and running jobs across a
    variety of hosts and batch-job systems based on
    [SAGA-Python](http://saga-project.github.io/saga-python/).

Configuration files use the [YAML](http://yaml.org/) format, and should be easy
to write for new hosts.

Chimi is under moderate development and is still growing somewhat organically;
it's not yet ready for general use (and is poorly documented); feel free to try
it out, but nothing is promised. ;)


## Installing
### Dependencies

Chimi is written in Python, and _probably_ requires version 2.7 (2.5 may be
sufficient).  On TACC Lonestar4, the command `module load python` will make
Python 2.7 available.  (The author has no experience with other HPC clusters, so
YMMV there.)

Python packages used are:

  * `yaml` for configuration data,
  * `saga` (PyPI name "saga-python") for job management,
  * `pkg_resources` for extracting configuration data from the self-contained
    executable file, and
  * `GitPython` for git integration.

If these packages are not available, they can be installed to your account
directory via

    easy_install --user PACKAGE

or

    pip install --user PACKAGE

where `PACKAGE` is the Python Package-Index name of the packageto be installed.

Additional software needed to build Chimi are:

  * GNU `make`, version $(WHATEVER_WORKS).  *Any* non-buggy version of the
    program should work just fine.  The only GNU-flavored feature we use is the
    `$(wildcard ...)` function, which was referenced in the changelog as early
    as version 3.49 (and apparently existed before that).

  * `zip` zip-file creation/extraction utility from Info-ZIP.  Chimi's author
    has version 3.0.

### Building

Chimi is designed for maximum portability and ease-of-use; to meet this goal, a
makefile with rules to create an executable archive containing all Chimi
scripts, sources, and data-files is provided.  To build the self-contained
executable, run

    make

from the directory in which you found this file.  The built executable can be
found at `build/chimi`.

Once you've placed the executable in your path (or not), try running it like

    chimi --help

or

    chimi help
    
for usage and sub-command information.


## Use

Chimi is a "commandlet"-based program with a usage style similar to that of
e.g. [git](http://git-scm.org).  It provides built-in documentation, available
via the `help` command for all commands.

To-do: provide detailed info on each of Chimi's commands...


## License

Chimi is distributed under the
[GNU General Public License version 2](https://www.gnu.org/licenses/gpl-2.0.html).
