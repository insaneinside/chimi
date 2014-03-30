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
e.g. [git](http://git-scm.org).

Options to each command are specific *to that command*: `chimi -n job run foo`
is **not** the same as `chimi job run -n foo` or even `chimi job -n run foo`.
The sole exception is `-h`/`--help`, which is available for all commands.

### `help`: access Chimi's built-in documentation.

Chimi provides built-in documentation, available via the `help` command, for
all commands.

    chimi help COMMAND

Some commands have subcommands; the built-in documentation for a subcommand can
be accessed via

    chimi help COMMAND SUBCOMMAND

Note that these two forms are functionally identical, and the only difference
is that in the latter case the full "command" is specified as two arguments.

Printing of a command's built-in documentation will also be triggered if the
option `-h` or `--help` is given.


### `build`: compile Charm++ and/or ChaNGa

The `build` command allows the user to initiate the build process for a
package.  The default target is ChaNGa, but this can be changed on the command
line:

    chimi build [OPTION]... [changa|charm|all]

Chimi will automatically attempt to build a compatible version of Charm++ if
one is not available when a ChaNGa build is requested; the ChaNGa build will be
aborted if the Charm++ build fails in such a case.

Configuration-related options are:

  * `--arch`: specify the Charm++ build architecture to use.  For ChaNGa, this
    determines the Charm++ build on which the ChaNGa build is based.
  * `-b` or `--branch`: select a branch in the Git repository to use for the
    build.  If *not* given, the currently checked-out branch is used.  It is an
    error to specify a branch that does not exist.

    If this option is given for a ChaNGa build that triggers a Charm++ build
    and the specified branch exists in the repository for the latter, it is
    used for both; otherwise Chimi behaves as if the option was not specified
    when performing the Charm++ build.
  * `-o` or `--options`: used to specify a comma-separated list of build
    options and settings.  Both Charm++ "options" specifying build components
    and compilers, and settings normally available through `configure` script
    options, can be specified here. See section
    [Options & Settings](#Options%20&amp;amp;%20Settings) for more information.

Although the build command is designed to provide a simple interface, its
behaviour is necessarily somewhat complex and deserves a section of its own;
see the section "Building packages" section in this document for a more
thorough treatment of this command.

### `job`: manage and run ChaNGa batch jobs on grid systems

Jobs can be submitted to batch systems (`run`), watched for status changes
(`watch`), listed (`list`), and canceled (`cancel`).

## Building packages
### Options & Settings
Chimi can inspect a Charm++ source directory to determine the available build
architectures and the "options" (build components and compiler selections)
available for each, and can determine configure-time options and settings from
the "help" output of a configure script for either Charm++ or ChaNGa.

Options and settings are specified with the `-o` or `--options` option to the
build command.  This option takes a comma-separated list of settings and/or
features to enable or disable; prefixing a name with "-" will disable it.

For example, one might use

    chimi build -ocuda,-ibverbs changa

to request a CUDA-enabled build of ChaNGa without InfiniBand support on a host
where Chimi's built-in configuration would otherwise have enabled it.  (Note
that the `changa` argument is superfluous, since that's the default anyway.)
If we need to specify the CUDA install path, we could run

    chimi build -ocuda,-ibverbs,cuda=/path/to/cuda/toolkit

and Chimi would figure out that the two "cuda" options are semantically
distinct: the first maps to the Charm++ "cuda" build component, while the
second maps to the `--with-cuda=...` "configure" option.


## License

Chimi is distributed under the
[GNU General Public License version 2](https://www.gnu.org/licenses/gpl-2.0.html).
