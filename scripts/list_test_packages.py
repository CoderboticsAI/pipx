#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from test_packages_support import get_platform_list_path
import argparse
from typing import List


def parse_package_list(package_list_file: Path) -> List[Dict[str, Any]]:
    """
    Parse the primary package list file and return a list of dictionaries.

    Each dictionary represents a package specification and may include the 'spec' key and the 'no-deps' key.

    Args:
        package_list_file (Path): The path to the primary package list file to be parsed.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries representing each package specification.

    Examples:
        >>> package_list_file = Path("package_list.txt")
        >>> parse_package_list(package_list_file)
        [{'spec': 'package1'}, {'spec': 'package2', 'no-deps': False}]
    """
    output_list: List[Dict[str, Any]] = []

    def parse_line(line: str) -> Dict[str, Any]:
        line_parsed = re.sub(r"#.+$", "", line)
        if not re.search(r"\S", line_parsed):
            raise ValueError("No valid content found in line")
        line_list = line_parsed.strip().split()
        if len(line_list) == 1:
            return {"spec": line_list[0]}
        if len(line_list) == 2:
            return {
                "spec": line_list[0],
                "no-deps": line_list[1].lower() == "true",
            }
        raise ValueError("Invalid number of fields in line")

    try:
        with package_list_file.open("r") as package_list_fh:
            for line in package_list_fh:
                try:
                    output_list.append(parse_line(line))
                except ValueError as e:
                    print(f"ERROR: {e}\n    {line.strip()}")
                    return []
    except IOError:
        print("ERROR: File problem reading primary package list.")
        return []

    return output_list


def create_test_packages_list(
    package_list_dir_path: Path, primary_package_list_path: Path, verbose: bool
) -> int:
    """Create a list of test packages.

    Args:
        package_list_dir_path (Path): The path to the directory where the package list will be saved.
        primary_package_list_path (Path): The path to the primary package list file.
        verbose (bool): Whether to print verbose output or not.

    Returns:
        int: The exit code.

    Raises:
        ValueError: If there is a problem reading the primary package list.

    Examples:
        >>> package_list_dir_path = Path("package_list")
        >>> primary_package_list_path = Path("primary_package_list.txt")
        >>> verbose = True
        >>> create_test_packages_list(package_list_dir_path, primary_package_list_path, verbose)
        Examined package1
        Examined package2 (no-deps)
    """
    exit_code = 0

    def get_verbose_string(verbose: bool, verbose_this_iteration: bool) -> str:
        if verbose or verbose_this_iteration:
            return f"\n{pip_download_process.stdout.strip()}\n{pip_download_process.stderr.strip()}"
        return ""

    def parse_test_package(spec: str, no_deps: bool) -> Tuple[List[str], bool]:
        verbose_this_iteration = False
        cmd_list = [
            "pip",
            "download",
            *(["--no-deps"] if no_deps else []),
            spec,
            "-d",
            str(download_dir),
        ]
        if verbose:
            print(f"CMD: {' '.join(cmd_list)}")
        pip_download_process = subprocess.run(
            cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        if pip_download_process.returncode == 0:
            print(f"Examined {spec}{' (no-deps)' if no_deps else ''}")
        else:
            print(
                f"ERROR with {spec}{' (no-deps)' if no_deps else ''}",
                file=sys.stderr,
            )
            verbose_this_iteration = True
            exit_code = 1
        return get_verbose_string(verbose, verbose_this_iteration), exit_code

    package_list_dir_path.mkdir(exist_ok=True)
    platform_package_list_path = get_platform_list_path(package_list_dir_path)

    primary_test_packages = parse_package_list(primary_package_list_path)
    if not primary_test_packages:
        raise ValueError(f"Problem reading {primary_package_list_path}.")

    with tempfile.TemporaryDirectory() as download_dir:
        for test_package in primary_test_packages:
            verbose_string, exit_code = parse_test_package(
                test_package["spec"], test_package.get("no-deps", False)
            )
            print(verbose_string)

    downloaded_list = os.listdir(download_dir)

    all_packages = []
    for downloaded_filename in downloaded_list:
        wheel_re = re.search(
            r"(.+)\-([^-]+)\-([^-]+)\-([^-]+)\-([^-]+)\.whl$", downloaded_filename
        )
        src_re = re.search(r"(.+)\-([^-]+)\.(?:tar.gz|zip)$", downloaded_filename)
        if wheel_re:
            package_name = wheel_re.group(1)
            package_version = wheel_re.group(2)
        elif src_re:
            package_name = src_re.group(1)
            package_version = src_re.group(2)
        else:
            print(f"ERROR: cannot parse: {downloaded_filename}", file=sys.stderr)
            continue

        all_packages.append(f"{package_name}=={package_version}")

    with platform_package_list_path.open("w") as package_list_fh:
        for package in sorted(all_packages):
            print(package, file=package_list_fh)

    return exit_code


def process_command_line(argv: List[str]) -> argparse.Namespace:
    """
    Process command line invocation arguments and switches.

    Args:
        argv (List[str]): list of arguments, or `None` from `sys.argv[1:]`.

    Returns:
        argparse.Namespace: named attributes of arguments and switches
    """
    parser = argparse.ArgumentParser(
        description="Create a list of needed test packages for pipx tests and local pypiserver."
    )
    parser.add_argument(
        "primary_package_list",
        help="Main packages to examine, getting a list of "
        "matching distribution files and dependencies.",
    )
    parser.add_argument(
        "package_list_dir", help="Directory to output package distribution lists."
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Maximize verbosity, especially for pip operations.",
    )
    return parser.parse_args(argv[1:])


def main(argv: List[str]) -> int:
    args = process_command_line(argv)

    return create_test_packages_list(
        Path(args.package_list_dir), Path(args.primary_package_list), args.verbose
    )


if __name__ == "__main__":
    try:
        status = main(sys.argv)
    except KeyboardInterrupt:
        print("Stopped by Keyboard Interrupt", file=sys.stderr)
        status = 130

    sys.exit(status)
