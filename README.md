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

Chimi is in an alpha state: the overall design is relatively stable, but some
features may be buggy or incomplete and the documentation is lacking.  Feel
free to try it out, but nothing is promised. ;)


## Installing
### Dependencies

Chimi is written in Python, and requires version 2.7 of the same.  By default
it will automatically fetch and install most external packages on which it
depends if they are not available; since this may be a security concern, a
mechanism is provided to disable the feature.

Non-standard-library Python modules used are:

  * `yaml` (PyPI name "PyYAML") for configuration data,
  * `saga` (PyPI name "saga-python") for batch-job management,
  * `pkg_resources` for extracting configuration data from the self-contained
    executable file, and
  * `git` (PyPI name `GitPython`) for git integration.

`pkg_resources` (from `setuptools`) is the sole module that cannot be
automatically installed.  Because
[setuptools](https://pypi.python.org/pypi/setuptools) normally *provides*
`easy_install` and is a much larger package than any other Chimi dependency,
its installation is left to the user.

#### Manual Python package installation

One may disable automatic installation of external dependencies by changing the line

    disable_dependency_install = False

to

    disable_dependency_install = True

in "settings.py" prior to building Chimi.

In such a case, packages not available can be installed manually using either
the more-common `easy_install` from setuptools or the newer,
[officially-sanctioned](https://python-packaging-user-guide.readthedocs.org/en/latest/current.html#installation-tool-recommendations)
`pip`
([install instructions](http://www.pip-installer.org/en/latest/installing.html)).

With `easy_install` the command is

    easy_install --user PACKAGE

and for `pip`

    pip install --user PACKAGE

where `PACKAGE` is the Python Package-Index name of the package to be
installed.


### Building Chimi

To create a single-file executable out of Chimi, you'll need

  * GNU `make`, version 3.50 or above, and
  * `zip` zip-file creation/extraction utility from Info-ZIP.  Chimi's author
    has version 3.0.

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

If you're ever unsure about what a command does (or how it will interpret its
arguments), passing the `-n` flag immediately after `chimi` will prevent Chimi
from performing any (potentially hazardous) operations.

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

For a listing of the available top-level commands, just use

    chimi help

Printing of a command's built-in documentation will also be triggered if the
option `-h` or `--help` is given; the following two commands are equivalent

    chimi COMMAND [SUBCOMMAND]... -h
    chimi help COMMAND [SUBCOMMAND]...

so long as the same subcommands are given.  Note that, because Chimi's option
parser associates options with the preceding command word, any commands
*following* `-h` will be ignored:

    chimi COMMAND [SUBCOMMAND]... -h SUBSUBCOMMAND... [ARG]...

ignores all `SUBSUBCOMMAND`s and any arguments that follow.


### `init` and `fetch`: initialize Chimi database and fetch package sources

Many of Chimi's commands use information that *could* be collected from a
directory tree at each run, but are not because well that's just stupid; others
(such as `build`) need to store information for later retrieval (such as build
failure/success messages).  To create the bookkeeping database, we run

    chimi init DIR

to initialize a Chimi data file called "chimi.yaml" in DIR, recording therein
the current state of defined Chimi packages.  Those packages are ChaNGa (in
`changa`), Charm++ (in `charm`), and the cosmology-related utility library that
seems to lack a proper name (in `utility`).

If `changa` and `charm` already exist, Chimi will attempt to index the existing
builds in each; otherwise the git repositories need to be cloned.  Once a
working directory has been initialized, running

    chimi fetch

from that directory will clone missing repositories and update existing ones if
possible.  When updating a repository, Chimi executes `git pull --ff-only
origin` directly and so will not clobber any uncommitted/unmerged changes --
unless, of course, you've somehow configured git to do so anyway (in which case
you have only yourself to blame).

**NOTE:** Chimi requires that both Charm++ and ChaNGa support out-of-source
builds, which the official version of ChaNGa does not as of this writing.  The
changes required to support out-of-source builds can be found in the
"build-system-fixes" branch of <https://github.com/insaneinside/changa.git>.

To use a non-default repository or branch for a package, either manually clone
the repository or change Chimi's default.  To select a different default
repository, edit the appropriate data in "chimi/settings.py" and (re)build
Chimi.


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
    determines (along with Charm++ "option" names passed to `-o`) the Charm++
    build on which the ChaNGa build is based.
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
    [Applying options](#applying-options) for more information.

Although the build command is designed to provide a simple interface, its
behaviour is necessarily somewhat complex and deserves a section of its own;
see the section
[Building Packages and Managing Builds](#building-packages-and-managing-builds)
for a more thorough treatment of this command.

### `job`: manage and run ChaNGa batch jobs on grid systems

Jobs can be submitted to batch systems (`run`), watched for status changes
(`watch`), listed (`list`), and canceled (`cancel`).

## Building Packages and Managing Builds
### Options, and their Practical Use

Central to the task of building ChaNGa is the question, "What kind of topping
would you like on that?"  Chimi fully supports all options available as part of
the pre-compile software configuration process, and does so using a common
interface for all option types.

There are two primary sources of the build options supported by Chimi; let's
take a look.

#### Charm++-specific options

ChaNGa is closely tied to Charm++, and as such a desired feature set in ChaNGa
will often depend on a distinct build of Charm++.  For our purposes, each build
of Charm++ is identified by three values:

  * interprocess communication method (we call this the *base architecture*),
  * host system type (OS and hardware architecture), and
  * build options (compiler selection and support for various hardware
    features).

Taken together, the first two determine the *build architecture*.  Which
options are available for a given build architecture are a function of that
architecture's inheritance: most Charm++ *base* architectures define options
specific to that IPC type, and within each base architecture most available
host system types define further build options specific to that build
architecture.

There is a special architecture, "common", from which all base architectures
inherit build options.

Chimi can inspect the working directory of a Charm++ repository to determine
available architectures and the options defined by each.  To do this, use
the `show arch` command:

    chimi show arch

Appending the `-u` flag will cause Chimi to show only non-inherited options,
while `-l` will dispense with the display of options altogether.  To display
only certain architectures, pass their names as arguments to the "show arch"
command, e.g.

    chimi show arch net

Within Chimi, Charm++ build options are generally referred to as "components"
to avoid confusion with e.g. `configure` script options and Chimi command
options.

#### `configure` script options

Both Charm++ and ChaNGa use GNU Autoconf for build configuration, and provide
additional build features and settings through a script called `configure`.

Running

    chimi show options

will produce a table of the available (`configure` script) build options for
each of ChaNGa and Charm++.


#### Applying options

Options and settings are specified as arguments to the `-o` or `--options`
option to `chimi build`.  This option takes a comma-separated list of option
declarations, where each declaration is one of

  * "option", "option=true", or "option=on" to enable the named option,
  * "-option", "option=false", or "option=off" to disable the named option, or
  * "option=value" to set an option to a non-boolean argument.

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

### Build Management

To be written...

## License

Chimi is distributed under the
[GNU General Public License version 2](https://www.gnu.org/licenses/gpl-2.0.html).
