import logging
import site
import sys
from pathlib import Path
from typing import Optional, Tuple

import userpath  # type: ignore

from pipx import constants
from pipx.constants import EXIT_CODE_OK, ExitCode
from pipx.emojis import hazard, stars
from pipx.util import pipx_wrap

import userpath
from typing import Tuple

logger = logging.getLogger(__name__)


def is_pip_user_installed(script_path: Path, userbase_path: Path) -> bool:
    """Check if pipx is installed using `pip --user`."""
    try:
        relative_path = script_path.relative_to(userbase_path)
        return True
    except ValueError:
        return False


def ensure_path(location: Path, *, force: bool) -> Tuple[bool, bool]:
    """
    Ensure that the provided location is in the user's PATH or add it to PATH.

    Args:
        location (Path): The location to be added to the PATH.
        force (bool): If True, the location will be added to PATH even if it is already present.

    Returns:
        Tuple[bool, bool]: A tuple indicating whether the location was added to the PATH and whether a shell restart is required.
    """
    location_str = str(location)
    path_added = False
    need_shell_restart = userpath.need_shell_restart(location_str)
    in_current_path = userpath.in_current_path(location_str)

    if force or (not in_current_path and not need_shell_restart):
        path_added, need_shell_restart = _add_location_to_path(location_str)
    elif not in_current_path and need_shell_restart:
        _print_shell_restart_message(location_str)
    else:
        _print_already_in_path_message(location_str)

    return path_added, need_shell_restart


def _add_location_to_path(location_str: str) -> Tuple[bool, bool]:
    userpath.append(location_str, "pipx")
    print(
        pipx_wrap(
            f"Success! Added {location_str} to the PATH environment variable.",
            subsequent_indent=" " * 4,
        )
    )
    path_added = True
    need_shell_restart = userpath.need_shell_restart(location_str)
    return path_added, need_shell_restart


def _print_shell_restart_message(location_str: str) -> None:
    print(
        pipx_wrap(
            f"""
            {location_str} has been been added to PATH, but you need to
            open a new terminal or re-login for this PATH change to take
            effect.
            """,
            subsequent_indent=" " * 4,
        )
    )


def _print_already_in_path_message(location_str: str) -> None:
    print(pipx_wrap(f"{location_str} is already in PATH.", subsequent_indent=" " * 4))


def get_pipx_user_bin_path() -> Optional[Path]:
    """
    Returns the parent directory of the pipx binary if pipx is installed using `pip --user`.

    Returns:
        Optional[Path]: The parent directory path of the pipx binary, or None if pipx is not installed using `pip --user`.

    Raises:
        None

    Examples:
        >>> get_pipx_user_bin_path()
        Path('/path/to/pipx')

        >>> get_pipx_user_bin_path()
        None
    """
    user_bin_path = None

    script_path = Path(__file__).resolve()
    userbase_path = Path(site.getuserbase()).resolve()

    if is_pip_user_installed(script_path, userbase_path):
        test_paths = (
            userbase_path / "bin" / "pipx",
            Path(site.getusersitepackages()).resolve().parent / "Scripts" / "pipx.exe",
        )
        for test_path in test_paths:
            if test_path.exists():
                user_bin_path = test_path.parent
                break

    return user_bin_path


def ensure_pipx_paths(force: bool) -> ExitCode:
    """Returns pipx exit code."""
    bin_paths = {constants.LOCAL_BIN_DIR}

    pipx_user_bin_path = get_pipx_user_bin_path()
    if pipx_user_bin_path is not None:
        bin_paths.add(pipx_user_bin_path)

    path_added = False
    need_shell_restart = False
    for bin_path in bin_paths:
        (path_added_current, need_shell_restart_current) = ensure_path(
            bin_path, force=force
        )
        path_added |= path_added_current
        need_shell_restart |= need_shell_restart_current

    print()

    if path_added:
        print(
            pipx_wrap(
                """
                Consider adding shell completions for pipx. Run 'pipx
                completions' for instructions.
                """
            )
            + "\n"
        )
    elif not need_shell_restart:
        sys.stdout.flush()
        logger.warning(
            pipx_wrap(
                f"""
                {hazard}  All pipx binary directories have been added to PATH. If you
                are sure you want to proceed, try again with the '--force'
                flag.
                """
            )
            + "\n"
        )

    if need_shell_restart:
        print(
            pipx_wrap(
                """
                You will need to open a new terminal or re-login for the PATH
                changes to take effect.
                """
            )
            + "\n"
        )

    print(f"Otherwise pipx is ready to go! {stars}")

    return EXIT_CODE_OK
