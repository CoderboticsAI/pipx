# PYTHON_ARGCOMPLETE_OK

"""The command line interface to pipx"""

import argparse
import logging
import logging.config
import os
import re
import shlex
import sys
import textwrap
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import argcomplete  # type: ignore
import platformdirs
from packaging.utils import canonicalize_name

import pipx.constants
from pipx import commands, constants
from pipx.animate import hide_cursor, show_cursor
from pipx.colors import bold, green
from pipx.constants import MINIMUM_PYTHON_VERSION, WINDOWS, ExitCode
from pipx.emojis import hazard
from pipx.interpreter import DEFAULT_PYTHON, find_py_launcher_python
from pipx.util import PipxError, mkdir, pipx_wrap, rmdir
from pipx.venv import VenvContainer
from pipx.version import __version__

logger = logging.getLogger(__name__)

VenvCompleter = Callable[[str], List[str]]


def print_version() -> None:
    print(__version__)
def prog_name() -> str:
    """
    Returns the program name.

    Returns:
        str: The program name.

    Raises:
        None

    Examples:
        >>> prog_name()
        'pipx'
    """
    prog = os.path.basename(sys.argv[0])
    if prog == "__main__.py":
        return f"{sys.executable} -m pipx"
    return prog


SPEC_HELP = textwrap.dedent(
    """\
    The package name or specific installation source passed to pip.
    Runs `pip install -U SPEC`.
    For example `--spec mypackage==2.0.0` or `--spec  git+https://github.com/user/repo.git@branch`
    """
)

PIPX_DESCRIPTION = textwrap.dedent(
    f"""
    Install and execute apps from Python packages.

    Binaries can either be installed globally into isolated Virtual Environments
    or run directly in a temporary Virtual Environment.

    Virtual Environment location is {str(constants.PIPX_LOCAL_VENVS)}.
    Symlinks to apps are placed in {str(constants.LOCAL_BIN_DIR)}.

    """
)
PIPX_DESCRIPTION += pipx_wrap(
    """
    optional environment variables:
      PIPX_HOME             Overrides default pipx location. Virtual Environments will be installed to $PIPX_HOME/venvs.
      PIPX_BIN_DIR          Overrides location of app installations. Apps are symlinked or copied here.
      PIPX_DEFAULT_PYTHON   Overrides default python used for commands.
      USE_EMOJI             Overrides emoji behavior. Default value varies based on platform.
    """,
    subsequent_indent=" " * 24,  # match the indent of argparse options
    keep_newlines=True,
)

DOC_DEFAULT_PYTHON = os.getenv("PIPX__DOC_DEFAULT_PYTHON", DEFAULT_PYTHON)

INSTALL_DESCRIPTION = textwrap.dedent(
    f"""
    The install command is the preferred way to globally install apps
    from python packages on your system. It creates an isolated virtual
    environment for the package, then ensures the package's apps are
    accessible on your $PATH.

    The result: apps you can run from anywhere, located in packages
    you can cleanly upgrade or uninstall. Guaranteed to not have
    dependency version conflicts or interfere with your OS's python
    packages. 'sudo' is not required to do this.

    pipx install PACKAGE_NAME
    pipx install --python PYTHON PACKAGE_NAME
    pipx install VCS_URL
    pipx install ./LOCAL_PATH
    pipx install ZIP_FILE
    pipx install TAR_GZ_FILE

    The PACKAGE_SPEC argument is passed directly to `pip install`.

    The default virtual environment location is {constants.DEFAULT_PIPX_HOME}
    and can be overridden by setting the environment variable `PIPX_HOME`
    (Virtual Environments will be installed to `$PIPX_HOME/venvs`).

    The default app location is {constants.DEFAULT_PIPX_BIN_DIR} and can be
    overridden by setting the environment variable `PIPX_BIN_DIR`.

    The default python executable used to install a package is
    {DOC_DEFAULT_PYTHON} and can be overridden
    by setting the environment variable `PIPX_DEFAULT_PYTHON`.
    """
)


class LineWrapRawTextHelpFormatter(argparse.RawDescriptionHelpFormatter):
    def _split_lines(self, text: str, width: int) -> List[str]:
        text = self._whitespace_matcher.sub(" ", text).strip()
        return textwrap.wrap(text, width)


class InstalledVenvsCompleter:
    def __init__(self, venv_container: VenvContainer) -> None:
        self.packages = [str(p.name) for p in sorted(venv_container.iter_venv_dirs())]

    def use(self, prefix: str, **kwargs: Any) -> List[str]:
        return [
            f"{prefix}{x[len(prefix):]}"
            for x in self.packages
            if x.startswith(canonicalize_name(prefix))
        ]
def get_pip_args(parsed_args: Dict[str, str]) -> List[str]:
    """Returns the arguments to be passed to pip based on the parsed command line arguments.

    Args:
        parsed_args: A dictionary containing the parsed command line arguments.

    Returns:
        A list of strings representing the arguments to be passed to pip.

    """

    index_url = parsed_args.get("index_url")
    pip_args = shlex.split(parsed_args.get("pip_args", ""), posix=not WINDOWS)
    editable = parsed_args.get("editable")

    return build_pip_args(index_url, pip_args, editable)


def build_pip_args(
    index_url: Optional[str], pip_args: List[str], editable: Optional[bool]
) -> List[str]:
    """Builds the arguments to be passed to pip.

    Args:
        index_url: The index URL for pip, if provided.
        pip_args: The pip arguments parsed from the command line.
        editable: A flag specifying whether the package should be installed in editable mode.

    Returns:
        A list of strings representing the arguments to be passed to pip.

    """
    result = []

    if index_url:
        result += ["--index-url", index_url]

    result += pip_args

    if editable:
        result += ["--editable"]

    return result
def get_venv_args(parsed_args: Dict[str, Any]) -> List[str]:
    """Return the arguments to pass to the virtual environment creation command.

    Args:
        parsed_args: The parsed command line arguments.

    Returns:
        A list of arguments to pass to the virtual environment creation command.

    """
    system_site_packages = parsed_args.get("system_site_packages")
    venv_args = ["--system-site-packages"] if system_site_packages else []
    return venv_args


def run_command(
    command: str, venv_dir: Optional[str], pip_args: List[str], verbose: bool, **kwargs
) -> ExitCode:
    """
    Execute the specified command with the given arguments.

    Args:
        command: The command to execute.
        venv_dir: The virtual environment directory.
        pip_args: The pip arguments.
        verbose: Whether to output verbose information.
        **kwargs: Additional command-specific arguments.

    Returns:
        ExitCode: The exit code indicating success or failure of the command.
    """
    if command == "run":
        commands.run(
            kwargs["app_with_args"][0],
            kwargs["spec"],
            kwargs["path"],
            kwargs["app_with_args"][1:],
            kwargs["python"],
            pip_args,
            kwargs["venv_args"],
            kwargs["pypackages"],
            verbose,
            not kwargs["no_cache"],
        )
        return ExitCode(1)
    elif command == "install":
        return commands.install(
            None,
            None,
            kwargs["package_spec"],
            constants.LOCAL_BIN_DIR,
            kwargs["python"],
            pip_args,
            kwargs["venv_args"],
            verbose,
            force=kwargs["force"],
            include_dependencies=kwargs["include_deps"],
            suffix=kwargs["suffix"],
        )
    elif command == "inject":
        return commands.inject(
            venv_dir,
            None,
            kwargs["dependencies"],
            pip_args,
            verbose=verbose,
            include_apps=kwargs["include_apps"],
            include_dependencies=kwargs["include_deps"],
            force=kwargs["force"],
        )
    elif command == "uninject":
        return commands.uninject(
            venv_dir,
            kwargs["dependencies"],
            local_bin_dir=constants.LOCAL_BIN_DIR,
            leave_deps=kwargs["leave_deps"],
            verbose=verbose,
        )
    elif command == "upgrade":
        return commands.upgrade(
            venv_dir,
            pip_args,
            verbose,
            include_injected=kwargs["include_injected"],
            force=kwargs["force"],
        )
    elif command == "upgrade-all":
        return commands.upgrade_all(
            kwargs["venv_container"],
            verbose,
            include_injected=kwargs["include_injected"],
            skip=kwargs["skip_list"],
            force=kwargs["force"],
        )
    elif command == "list":
        return commands.list_packages(
            kwargs["venv_container"],
            kwargs["include_injected"],
            kwargs["json"],
            kwargs["short"],
        )
    elif command == "uninstall":
        return commands.uninstall(venv_dir, constants.LOCAL_BIN_DIR, verbose)
    elif command == "uninstall-all":
        return commands.uninstall_all(venv_container, constants.LOCAL_BIN_DIR, verbose)
    elif command == "reinstall":
        return commands.reinstall(
            venv_dir=venv_dir,
            local_bin_dir=constants.LOCAL_BIN_DIR,
            python=kwargs["python"],
            verbose=verbose,
        )
    elif command == "reinstall-all":
        return commands.reinstall_all(
            kwargs["venv_container"],
            constants.LOCAL_BIN_DIR,
            kwargs["python"],
            verbose,
            skip=kwargs["skip_list"],
        )
    elif command == "runpip":
        if not venv_dir:
            raise PipxError("Developer error: venv_dir is not defined.")
        return commands.run_pip(
            kwargs["package"], venv_dir, kwargs["pipargs"], kwargs["verbose"]
        )
    elif command == "ensurepath":
        try:
            return commands.ensure_pipx_paths(force=kwargs["force"])
        except Exception as e:
            logger.debug("Uncaught Exception:", exc_info=True)
            raise PipxError(str(e), wrap_message=False)
    elif command == "completions":
        print(constants.completion_instructions)
        return ExitCode(0)
    elif command == "environment":
        return commands.environment(value=kwargs["value"])
    else:
        raise PipxError(f"Unknown command {command}")
def add_pip_venv_args(parser: argparse.ArgumentParser) -> None:
    """
    Add arguments related to creating virtual environments using pip to the parser.

    Args:
        parser: An instance of `argparse.ArgumentParser` to add the arguments to.
    """

    def _add_system_site_packages_arg() -> None:
        parser.add_argument(
            "--system-site-packages",
            action="store_true",
            help="Give the virtual environment access to the system site-packages dir.",
        )

    def _add_index_url_arg() -> None:
        parser.add_argument(
            "--index-url",
            "-i",
            help="Specify the base URL of the Python Package Index",
        )

    def _add_editable_arg() -> None:
        parser.add_argument(
            "--editable",
            "-e",
            action="store_true",
            help="Install a project in editable mode",
        )

    def _add_pip_args_arg() -> None:
        parser.add_argument(
            "--pip-args",
            help="Arbitrary pip arguments to pass directly to pip install/upgrade commands",
        )

    _add_system_site_packages_arg()
    _add_index_url_arg()
    _add_editable_arg()
    _add_pip_args_arg()


def run_pipx_command(args: argparse.Namespace) -> ExitCode:
    """
    Execute the appropriate command based on the given command line arguments.

    Args:
        args: The parsed command line arguments.

    Returns:
        ExitCode: The exit code indicating success or failure of the command.
    """
    verbose = args.verbose if "verbose" in args else False
    pip_args = get_pip_args(vars(args))
    venv_args = get_venv_args(vars(args))

    venv_container = VenvContainer(constants.PIPX_LOCAL_VENVS)

    if "package" in args:
        package = args.package
        if urllib.parse.urlparse(package).scheme:
            raise PipxError("Package cannot be a url")

        if "spec" in args and args.spec is not None:
            if urllib.parse.urlparse(args.spec).scheme:
                if "#egg=" not in args.spec:
                    args.spec = args.spec + f"#egg={package}"

        venv_dir = venv_container.get_venv_dir(package)
        logger.info(f"Virtual Environment location is {venv_dir}")

    if "skip" in args:
        skip_list = [canonicalize_name(x) for x in args.skip]

    if "python" in args and not Path(args.python).is_file():
        py_launcher_python = find_py_launcher_python(args.python)
        if py_launcher_python:
            args.python = py_launcher_python

    return run_command(
        args.command,
        venv_dir,
        pip_args,
        verbose,
        venv_container=venv_container,
        skip_list=skip_list,
        **vars(args),
    )
def _add_install(subparsers: argparse._SubParsersAction) -> None:
    """Add the 'install' command to the subparser.

    Parameters:
    - subparsers (argparse._SubParsersAction): The subparsers object to add the command to.
    """

    parser = subparsers.add_parser(
        "install",
        help="Install a package",
        description=INSTALL_DESCRIPTION,
        formatter_class=LineWrapRawTextHelpFormatter,
    )

    parser.add_argument(
        "package_spec",
        help="The package name or specific installation source passed to pip.",
        metavar="PACKAGE_SPEC",
    )
    parser.add_argument(
        "--python",
        "-p",
        default=DOC_DEFAULT_PYTHON,
        help="The Python executable used to run the package's scripts.",
        metavar="PYTHON",
        dest="python",
    )
    parser.add_argument(
        "--include-deps",
        action="store_true",
        help="Also include dependencies",
        dest="include_deps",
    )
    parser.add_argument(
        "--include-deps-verify",
        action="store_true",
        help="Verify each dependency before including",
        dest="include_deps_verify",
    )
    parser.add_argument(
        "--system-site-packages",
        action="store_true",
        help="Give the virtual environment access to the system site-packages",
        dest="system_site",
    )
    parser.add_argument(
        "--suffix",
        default=None,
        help="Add suffix to the app binaries",
        metavar="SUFFIX",
        dest="suffix",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Install the package even if the package already exists",
        dest="force",
    )
    parser.add_argument(
        "--spec",
        default=None,
        help="A specific installation source passed to pip",
        metavar="SPEC",
        dest="specific_install",
    )
    parser.add_argument(
        "--index",
        default=None,
        help="Base URL of Python Package Index",
        metavar="INDEX_URL",
        dest="index_url",
    )
    parser.add_argument(
        "--editable",
        "-e",
        action="store_true",
        help="Install a project in editable mode",
        dest="editable",
    )
    parser.add_argument(
        "--global",
        action="store_true",
        help="Install globally rather than in an isolated Virtual Environment",
        dest="global_install",
    )
    parser.add_argument(
        "--suffix",
        default=None,
        help="Add suffix to the app binaries",
        metavar="SUFFIX",
        dest="suffix",
    )
    parser.add_argument(
        "--suffix",
        default=None,
        help="Add suffix to the app binaries",
        metavar="SUFFIX",
        dest="suffix",
    )
    parser.add_argument(
        "--suffix",
        default=None,
        help="Add suffix to the app binaries",
        metavar="SUFFIX",
        dest="suffix",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run in interactive mode",
        dest="interactive",
    )
    parser.add_argument(
        "--specify",
        action="store_true",
        help="Allow the package to install globally if pipx itself is globally installed",
        dest="allow_global",
    )
    parser.add_argument(
        "--site-packages",
        action="store_true",
        help="Allow the package to use the global site-packages directory",
        dest="site_packages",
    )
    parser.add_argument(
        "--sys-executable",
        "-s",
        action="store_true",
        help="Use system python (default: False)",
        dest="use_sys_executable",
    )
    parser.add_argument(
        "--piptarg",
        default=None,
        help="Specify extra flags to pass to pip",
        metavar="PIP_EXTRA_ARGS",
        dest="pip_args",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Yell verbosely",
        dest="verbose",
    )
    parser.set_defaults(run=_run_install)

    add_pip_venv_args(parser)

    install_venv_group = parser.add_mutually_exclusive_group()
    install_venv_group.add_argument(
        "--venv",
        "-v",
        action="store_true",
        help="Create a virtual environment, with the package installed",
        dest="install_venv",
    )
    install_venv_group.add_argument(
        "--venv-only",
        action="store_true",
        help="Create the virtual environment but don't install the package",
        dest="only_install_venv",
    )


def add_include_dependencies(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--include-deps", help="Include apps of dependent packages", action="store_true"
    )


def _add_inject(subparsers, venv_completer: VenvCompleter) -> None:
    p = subparsers.add_parser(
        "inject",
        help="Install packages into an existing Virtual Environment",
        description="Installs packages to an existing pipx-managed virtual environment.",
    )
    p.add_argument(
        "package",
        help="Name of the existing pipx-managed Virtual Environment to inject into",
    ).completer = venv_completer
    p.add_argument(
        "dependencies",
        nargs="+",
        help="the packages to inject into the Virtual Environment--either package name or pip package spec",
    )
    p.add_argument(
        "--include-apps",
        action="store_true",
        help="Add apps from the injected packages onto your PATH",
    )
    add_include_dependencies(p)
    add_pip_venv_args(p)
    p.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Modify existing virtual environment and files in PIPX_BIN_DIR",
    )
    p.add_argument("--verbose", action="store_true")


def _add_uninject(subparsers, venv_completer: VenvCompleter):
    p = subparsers.add_parser(
        "uninject",
        help="Uninstall injected packages from an existing Virtual Environment",
        description="Uninstalls injected packages from an existing pipx-managed virtual environment.",
    )
    p.add_argument(
        "package",
        help="Name of the existing pipx-managed Virtual Environment to inject into",
    ).completer = venv_completer
    p.add_argument(
        "dependencies",
        nargs="+",
        help="the package names to uninject from the Virtual Environment",
    )
    p.add_argument(
        "--leave-deps",
        action="store_true",
        help="Only uninstall the main injected package but leave its dependencies installed.",
    )
    p.add_argument("--verbose", action="store_true")


def _add_upgrade(subparsers, venv_completer: VenvCompleter) -> None:
    p = subparsers.add_parser(
        "upgrade",
        help="Upgrade a package",
        description="Upgrade a package in a pipx-managed Virtual Environment by running 'pip install --upgrade PACKAGE'",
    )
    p.add_argument("package").completer = venv_completer
    p.add_argument(
        "--include-injected",
        action="store_true",
        help="Also upgrade packages injected into the main app's environment",
    )
    p.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Modify existing virtual environment and files in PIPX_BIN_DIR",
    )
    add_pip_venv_args(p)
    p.add_argument("--verbose", action="store_true")


def _add_upgrade_all(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "upgrade-all",
        help="Upgrade all packages. Runs `pip install -U <pkgname>` for each package.",
        description="Upgrades all packages within their virtual environments by running 'pip install --upgrade PACKAGE'",
    )
    p.add_argument(
        "--include-injected",
        action="store_true",
        help="Also upgrade packages injected into the main app's environment",
    )
    p.add_argument("--skip", nargs="+", default=[], help="skip these packages")
    p.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Modify existing virtual environment and files in PIPX_BIN_DIR",
    )
    p.add_argument("--verbose", action="store_true")


def _add_uninstall(subparsers, venv_completer: VenvCompleter) -> None:
    p = subparsers.add_parser(
        "uninstall",
        help="Uninstall a package",
        description="Uninstalls a pipx-managed Virtual Environment by deleting it and any files that point to its apps.",
    )
    p.add_argument("package").completer = venv_completer
    p.add_argument("--verbose", action="store_true")


def _add_uninstall_all(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "uninstall-all",
        help="Uninstall all packages",
        description="Uninstall all pipx-managed packages",
    )
    p.add_argument("--verbose", action="store_true")


def _add_reinstall(subparsers, venv_completer: VenvCompleter) -> None:
    p = subparsers.add_parser(
        "reinstall",
        formatter_class=LineWrapRawTextHelpFormatter,
        help="Reinstall a package",
        description=textwrap.dedent(
            """
            Reinstalls a package.

            Package is uninstalled, then installed with pipx install PACKAGE
            with the same options used in the original install of PACKAGE.

            """
        ),
    )
    p.add_argument("package").completer = venv_completer
    p.add_argument(
        "--python",
        default=DEFAULT_PYTHON,
        help=(
            "Python to reinstall with. Possible values can be the executable name (python3.11), "
            "the version to pass to py launcher (3.11), or the full path to the executable."
            f"Requires Python {MINIMUM_PYTHON_VERSION} or above."
        ),
    )
    p.add_argument("--verbose", action="store_true")


def _add_reinstall_all(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "reinstall-all",
        formatter_class=LineWrapRawTextHelpFormatter,
        help="Reinstall all packages",
        description=textwrap.dedent(
            """
            Reinstalls all packages.

            Packages are uninstalled, then installed with pipx install PACKAGE
            with the same options used in the original install of PACKAGE.
            This is useful if you upgraded to a new version of Python and want
            all your packages to use the latest as well.

            """
        ),
    )
    p.add_argument(
        "--python",
        default=DEFAULT_PYTHON,
        help=(
            "Python to reinstall with. Possible values can be the executable name (python3.11), "
            "the version to pass to py launcher (3.11), or the full path to the executable."
            f"Requires Python {MINIMUM_PYTHON_VERSION} or above."
        ),
    )
    p.add_argument("--skip", nargs="+", default=[], help="skip these packages")
    p.add_argument("--verbose", action="store_true")


def _add_list(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "list",
        help="List installed packages",
        description="List packages and apps installed with pipx",
    )
    p.add_argument(
        "--include-injected",
        action="store_true",
        help="Show packages injected into the main app's environment",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--json", action="store_true", help="Output rich data in json format."
    )
    g.add_argument("--short", action="store_true", help="List packages only.")
    p.add_argument("--verbose", action="store_true")


def _add_run(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "run",
        formatter_class=LineWrapRawTextHelpFormatter,
        help=(
            "Download the latest version of a package to a temporary virtual environment, "
            "then run an app from it. Also compatible with local `__pypackages__` "
            "directory (experimental)."
        ),
        description=textwrap.dedent(
            f"""
            Download the latest version of a package to a temporary virtual environment,
            then run an app from it. The environment will be cached
            and re-used for up to {constants.TEMP_VENV_EXPIRATION_THRESHOLD_DAYS} days. This
            means subsequent calls to 'run' for the same package will be faster
            since they can re-use the cached Virtual Environment.

            In support of PEP 582 'run' will use apps found in a local __pypackages__
            directory, if present. Please note that this behavior is experimental,
            and acts as a companion tool to pythonloc. It may be modified or
            removed in the future. See https://github.com/cs01/pythonloc.
            """
        ),
    )
    p.add_argument(
        "--no-cache",
        action="store_true",
        help="Do not re-use cached virtual environment if it exists",
    )
    p.add_argument(
        "app_with_args",
        metavar="app ...",
        nargs=argparse.REMAINDER,
        help="app/package name and any arguments to be passed to it",
        default=[],
    )
    p.add_argument(
        "--path", action="store_true", help="Interpret app name as a local path"
    )
    p.add_argument(
        "--pypackages",
        action="store_true",
        help="Require app to be run from local __pypackages__ directory",
    )
    p.add_argument("--spec", help=SPEC_HELP)
    p.add_argument("--verbose", action="store_true")
    p.add_argument(
        "--python",
        default=DEFAULT_PYTHON,
        help=(
            "Python to run with. Possible values can be the executable name (python3.11), "
            "the version to pass to py launcher (3.11), or the full path to the executable. "
            f"Requires Python {MINIMUM_PYTHON_VERSION} or above."
        ),
    )
    add_pip_venv_args(p)
    p.set_defaults(subparser=p)

    # modify usage text to show required app argument
    p.usage = re.sub(r"^usage: ", "", p.format_usage())
    # add a double-dash to usage text to show requirement before app
    p.usage = re.sub(r"\.\.\.", "app ...", p.usage)


def _add_runpip(subparsers, venv_completer: VenvCompleter) -> None:
    p = subparsers.add_parser(
        "runpip",
        help="Run pip in an existing pipx-managed Virtual Environment",
        description="Run pip in an existing pipx-managed Virtual Environment",
    )
    p.add_argument(
        "package",
        help="Name of the existing pipx-managed Virtual Environment to run pip in",
    ).completer = venv_completer
    p.add_argument(
        "pipargs",
        nargs=argparse.REMAINDER,
        default=[],
        help="Arguments to forward to pip command",
    )
    p.add_argument("--verbose", action="store_true")


def _add_ensurepath(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "ensurepath",
        help=(
            "Ensure directories necessary for pipx operation are in your "
            "PATH environment variable."
        ),
        description=(
            "Ensure directory where pipx stores apps is in your "
            "PATH environment variable. Also if pipx was installed via "
            "`pip install --user`, ensure pipx itself is in your PATH. "
            "Note that running this may modify "
            "your shell's configuration file(s) such as '~/.bashrc'."
        ),
    )
    p.add_argument(
        "--force",
        "-f",
        action="store_true",
        help=(
            "Add text to your shell's config file even if it looks like your "
            "PATH already contains paths to pipx and pipx-install apps."
        ),
    )


def _add_environment(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "environment",
        formatter_class=LineWrapRawTextHelpFormatter,
        help=("Print a list of variables used in pipx.constants."),
        description=textwrap.dedent(
            """
            Available variables:
            PIPX_HOME, PIPX_BIN_DIR, PIPX_SHARED_LIBS, PIPX_LOCAL_VENVS, PIPX_LOG_DIR,
            PIPX_TRASH_DIR, PIPX_VENV_CACHEDIR

            Only PIPX_HOME and PIPX_BIN_DIR can be set by users in the above list.

            """
        ),
    )
    p.add_argument(
        "--value", "-v", metavar="VARIABLE", help="Print the value of the variable."
    )


def get_command_parser() -> argparse.ArgumentParser:
    venv_container = VenvContainer(constants.PIPX_LOCAL_VENVS)

    completer_venvs = InstalledVenvsCompleter(venv_container)

    parser = argparse.ArgumentParser(
        prog=prog_name(),
        formatter_class=LineWrapRawTextHelpFormatter,
        description=PIPX_DESCRIPTION,
    )
    parser.man_short_description = PIPX_DESCRIPTION.splitlines()[1]  # type: ignore

    subparsers = parser.add_subparsers(
        dest="command", description="Get help for commands with pipx COMMAND --help"
    )

    _add_install(subparsers)
    _add_uninject(subparsers, completer_venvs.use)
    _add_inject(subparsers, completer_venvs.use)
    _add_upgrade(subparsers, completer_venvs.use)
    _add_upgrade_all(subparsers)
    _add_uninstall(subparsers, completer_venvs.use)
    _add_uninstall_all(subparsers)
    _add_reinstall(subparsers, completer_venvs.use)
    _add_reinstall_all(subparsers)
    _add_list(subparsers)
    _add_run(subparsers)
    _add_runpip(subparsers, completer_venvs.use)
    _add_ensurepath(subparsers)
    _add_environment(subparsers)

    parser.add_argument("--version", action="store_true", help="Print version and exit")
    subparsers.add_parser(
        "completions",
        help="Print instructions on enabling shell completions for pipx",
        description="Print instructions on enabling shell completions for pipx",
    )
    return parser


def delete_oldest_logs(file_list: List[Path], keep_number: int) -> None:
    file_list = sorted(file_list)
    if len(file_list) > keep_number:
        for existing_file in file_list[:-keep_number]:
            try:
                existing_file.unlink()
            except FileNotFoundError:
                pass


def _setup_log_file(pipx_log_dir: Optional[Path] = None) -> Path:
    max_logs = 10
    pipx_log_dir = pipx_log_dir or constants.PIPX_LOG_DIR
    # don't use utils.mkdir, to prevent emission of log message
    pipx_log_dir.mkdir(parents=True, exist_ok=True)

    delete_oldest_logs(list(pipx_log_dir.glob("cmd_*[0-9].log")), max_logs)
    delete_oldest_logs(list(pipx_log_dir.glob("cmd_*_pip_errors.log")), max_logs)

    datetime_str = time.strftime("%Y-%m-%d_%H.%M.%S")
    log_file = pipx_log_dir / f"cmd_{datetime_str}.log"
    counter = 1
    while log_file.exists() and counter < 10:
        log_file = pipx_log_dir / f"cmd_{datetime_str}_{counter}.log"
        counter += 1

    log_file.touch()

    return log_file


def setup_log_file() -> Path:
    try:
        return _setup_log_file()
    except PermissionError:
        return _setup_log_file(platformdirs.user_log_path("pipx"))


def setup_logging(verbose: bool) -> None:
    pipx_str = bold(green("pipx >")) if sys.stdout.isatty() else "pipx >"
    pipx.constants.pipx_log_file = setup_log_file()

    # "incremental" is False so previous pytest tests don't accumulate handlers
    logging_config = {
        "version": 1,
        "formatters": {
            "stream_nonverbose": {
                "class": "logging.Formatter",
                "format": "{message}",
                "style": "{",
            },
            "stream_verbose": {
                "class": "logging.Formatter",
                "format": pipx_str + "({funcName}:{lineno}): {message}",
                "style": "{",
            },
            "file": {
                "class": "logging.Formatter",
                "format": "{relativeCreated: >8.1f}ms ({funcName}:{lineno}): {message}",
                "style": "{",
            },
        },
        "handlers": {
            "stream": {
                "class": "logging.StreamHandler",
                "formatter": "stream_verbose" if verbose else "stream_nonverbose",
                "level": "INFO" if verbose else "WARNING",
            },
            "file": {
                "class": "logging.FileHandler",
                "formatter": "file",
                "filename": str(pipx.constants.pipx_log_file),
                "encoding": "utf-8",
                "level": "DEBUG",
            },
        },
        "loggers": {"pipx": {"handlers": ["stream", "file"], "level": "DEBUG"}},
        "incremental": False,
    }
    logging.config.dictConfig(logging_config)


def setup(args: argparse.Namespace) -> None:
    if "version" in args and args.version:
        print_version()
        sys.exit(0)

    setup_logging("verbose" in args and args.verbose)

    logger.debug(f"{time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.debug(f"{' '.join(sys.argv)}")
    logger.info(f"pipx version is {__version__}")
    logger.info(f"Default python interpreter is '{DEFAULT_PYTHON}'")

    mkdir(constants.PIPX_LOCAL_VENVS)
    mkdir(constants.LOCAL_BIN_DIR)
    mkdir(constants.PIPX_VENV_CACHEDIR)

    cachedir_tag = constants.PIPX_VENV_CACHEDIR / "CACHEDIR.TAG"
    if not cachedir_tag.exists():
        logger.debug("Adding CACHEDIR.TAG to cache directory")
        signature = (
            "Signature: 8a477f597d28d172789f06886806bc55\n"
            "# This file is a cache directory tag created by pipx.\n"
            "# For information about cache directory tags, see:\n"
            "#       https://bford.info/cachedir/\n"
        )
        with open(cachedir_tag, "w") as file:
            file.write(signature)

    rmdir(constants.PIPX_TRASH_DIR, False)

    old_pipx_venv_location = constants.PIPX_LOCAL_VENVS / "pipx-app"
    if old_pipx_venv_location.exists():
        logger.warning(
            pipx_wrap(
                f"""
                {hazard}  A virtual environment for pipx was detected at
                {str(old_pipx_venv_location)}. The 'pipx-app' package has been
                renamed back to 'pipx'
                (https://github.com/pypa/pipx/issues/82).
                """,
                subsequent_indent=" " * 4,
            )
        )


def check_args(parsed_pipx_args: argparse.Namespace) -> None:
    if parsed_pipx_args.command == "run":
        # we manually discard a first -- because using nargs=argparse.REMAINDER
        #   will not do it automatically
        if parsed_pipx_args.app_with_args and parsed_pipx_args.app_with_args[0] == "--":
            parsed_pipx_args.app_with_args.pop(0)
        # since we would like app to be required but not in a separate argparse
        #   add_argument, we implement our own missing required arg error
        if not parsed_pipx_args.app_with_args:
            parsed_pipx_args.subparser.error(
                "the following arguments are required: app"
            )


def cli() -> ExitCode:
    """Entry point from command line"""
    try:
        hide_cursor()
        parser = get_command_parser()
        argcomplete.autocomplete(parser)
        parsed_pipx_args = parser.parse_args()
        setup(parsed_pipx_args)
        check_args(parsed_pipx_args)
        if not parsed_pipx_args.command:
            parser.print_help()
            return ExitCode(1)
        return run_pipx_command(parsed_pipx_args)
    except PipxError as e:
        print(str(e), file=sys.stderr)
        logger.debug(f"PipxError: {e}", exc_info=True)
        return ExitCode(1)
    except KeyboardInterrupt:
        return ExitCode(1)
    except Exception:
        logger.debug("Uncaught Exception:", exc_info=True)
        raise
    finally:
        logger.debug("pipx finished.")
        show_cursor()


if __name__ == "__main__":
    sys.exit(cli())
