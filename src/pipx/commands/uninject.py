import logging
import os
from pathlib import Path
from typing import List, Set

from packaging.utils import canonicalize_name

from pipx.colors import bold
from pipx.commands.uninstall import _get_package_bin_dir_app_paths
from pipx.constants import EXIT_CODE_OK, EXIT_CODE_UNINJECT_ERROR, ExitCode
from pipx.emojis import stars
from pipx.util import PipxError, pipx_wrap
from pipx.venv import Venv
from typing import List
from pipx.constants import ExitCode

logger = logging.getLogger(__name__)


def get_include_app_paths(
    package_name: str, venv: Venv, local_bin_dir: Path
) -> Set[Path]:
    """
    Get a set of app path directories to be removed for a package.

    Args:
        package_name: The name of the package.
        venv: The virtual environment instance.
        local_bin_dir: The local bin directory.

    Returns:
        A set of `Path` objects representing app path directories to be removed.

    Examples:
        >>> venv = Venv(path=Path('/path/to/venv'))
        >>> local_bin_dir = Path('/path/to/local/bin')
        >>> get_include_app_paths('package-name', venv, local_bin_dir)
        {Path('/path/to/venv/bin/app1'), Path('/path/to/venv/bin/app2')}
    """
    package_metadata = venv.package_metadata[package_name]
    bin_dir_app_paths = _get_package_bin_dir_app_paths(
        venv, package_metadata, local_bin_dir
    )

    need_to_remove = set()
    for bin_dir_app_path in bin_dir_app_paths:
        if bin_dir_app_path.name in package_metadata.apps:
            need_to_remove.add(bin_dir_app_path)

    return need_to_remove


def uninject_dep(
    venv: Venv, package_name: str, *, local_bin_dir: Path, leave_deps: bool = False
) -> bool:
    """
    Uninjects a package from the virtual environment and removes associated app paths.

    Args:
        venv: The virtual environment instance.
        package_name: The name of the package to uninject.
        local_bin_dir: The local bin directory.
        leave_deps: Whether to leave the dependencies of the uninstalled package.

    Returns:
        True if the package was successfully uninjected, False otherwise.

    Raises:
        None.

    Examples:
        >>> venv = Venv(path=Path('/path/to/venv'))
        >>> local_bin_dir = Path('/path/to/local/bin')
        >>> uninject_dep(venv, 'package-name', local_bin_dir=local_bin_dir)
        True
    """
    package_name = canonicalize_name(package_name)

    if package_name == venv.pipx_metadata.main_package.package:
        logger.warning(
            pipx_wrap(
                f"""
            {package_name} is the main package of {venv.root.name}
            venv. Use `pipx uninstall {venv.root.name}` to uninstall instead of uninject.
            """,
                subsequent_indent=" " * 4,
            )
        )
        return False

    if package_name not in venv.pipx_metadata.injected_packages:
        logger.warning(f"{package_name} is not in the {venv.root.name} venv. Skipping.")
        return False

    need_app_uninstall = venv.package_metadata[package_name].include_apps

    new_app_paths = get_include_app_paths(package_name, venv, local_bin_dir)

    if not leave_deps:
        orig_not_required_packages = venv.list_installed_packages(not_required=True)
        logger.info(f"Original not required packages: {orig_not_required_packages}")

    venv.uninstall_package(package=package_name, was_injected=True)

    if not leave_deps:
        new_not_required_packages = venv.list_installed_packages(not_required=True)
        logger.info(f"New not required packages: {new_not_required_packages}")

        deps_of_uninstalled = new_not_required_packages - orig_not_required_packages
        if len(deps_of_uninstalled) != 0:
            logger.info(f"Dependencies of uninstalled package: {deps_of_uninstalled}")
            for dep_package_name in deps_of_uninstalled:
                venv.uninstall_package(package=dep_package_name, was_injected=False)

        deps_string = " and its dependencies"
    else:
        deps_string = ""

    if need_app_uninstall:
        for app_path in new_app_paths:
            try:
                os.unlink(app_path)
                logger.info(f"removed file {app_path}")
            except FileNotFoundError:
                logger.info(f"tried to remove but couldn't find {app_path}")

    print(
        f"Uninjected package {bold(package_name)}{deps_string} from venv {bold(venv.root.name)} {stars}"
    )
    return True


def find_deps_of_uninstalled(package_name: str, venv: Venv) -> List[str]:
    """Finds the dependencies of an uninstalled package.

    Args:
        package_name: The name of the package.
        venv: The virtual environment instance.

    Returns:
        List[str]: A list of dependency package names.
    """
    orig_not_required_packages = venv.list_installed_packages(not_required=True)
    venv.uninstall_package(package=package_name, was_injected=True)
    new_not_required_packages = venv.list_installed_packages(not_required=True)

    return list(new_not_required_packages - orig_not_required_packages)


def remove_app_paths(app_paths: List[Path]) -> None:
    """Removes the app paths.

    Args:
        app_paths: A list of app paths.
    """
    for app_path in app_paths:
        try:
            os.unlink(app_path)
            logger.info(f"removed file {app_path}")
        except FileNotFoundError:
            logger.info(f"tried to remove but couldn't find {app_path}")


def uninject(
    venv_dir: Path,
    dependencies: List[str],
    local_bin_dir: Path,
    leave_deps: bool,
    verbose: bool,
) -> ExitCode:
    """Uninjects the given packages from the virtual environment.

    Args:
        venv_dir: The directory of the virtual environment.
        dependencies: A list of package names to uninject.
        local_bin_dir: The local bin directory.
        leave_deps: Whether to leave the dependencies of the uninstalled packages.
        verbose: Whether to enable verbose output.

    Returns:
        ExitCode: The exit code.

    Raises:
        PipxError: If the virtual environment does not exist or has missing internal pipx metadata.
    """
    if not venv_dir.exists() or not any(venv_dir.iterdir()):
        raise PipxError(f"Virtual environment {venv_dir.name} does not exist.")

    venv = Venv(venv_dir, verbose=verbose)

    if not venv.package_metadata:
        raise PipxError(
            f"""
            Can't uninject from Virtual Environment {venv_dir.name!r}.
            {venv_dir.name!r} has missing internal pipx metadata.
            It was likely installed using a pipx version before 0.15.0.0.
            Please uninstall and install {venv_dir.name!r} manually to fix.
            """
        )

    all_success = True
    for dep in dependencies:
        all_success &= uninject_dep(
            venv, dep, local_bin_dir=local_bin_dir, leave_deps=leave_deps
        )

    return EXIT_CODE_OK if all_success else EXIT_CODE_UNINJECT_ERROR
