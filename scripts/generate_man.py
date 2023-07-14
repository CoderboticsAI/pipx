#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os.path
import textwrap

from build_manpages.manpage import Manpage  # type: ignore

from pipx.main import get_command_parser
from typing import NoReturn
import os

from build_manpages.manpage import Manpage


def get_manpage_body(parser) -> str:
    """
    Generate the body of the man page for the pipx command line tool.

    Args:
        parser: The command parser.

    Returns:
        The body of the man page as a string.
    """
    parser.man_short_description = parser.description.splitlines()[1]
    manpage = Manpage(parser)
    body = str(manpage)

    # Avoid hardcoding build paths in manpages (and improve readability)
    body = body.replace(os.path.expanduser("~").replace("-", "\\-"), "~")

    return body


def add_credit_section(body: str) -> str:
    """
    Add a credit section to the body of the man page.

    Args:
        body: The body of the man page.

    Returns:
        The body of the man page with the credit section added.
    """
    credit_section = textwrap.dedent(
        """
        .SH AUTHORS
        .IR pipx (1)
        was written by Chad Smith and contributors.
        The project can be found online at
        .UR https://pypa.github.io/pipx/
        .UE
        .SH SEE ALSO
        .IR pip (1),
        .IR virtualenv (1)
        """
    )

    return body + credit_section


def write_manpage(body: str) -> NoReturn:
    """
    Write the man page to a file named `pipx.1`.

    Args:
        body: The body of the man page.
    """
    with open("pipx.1", "w") as f:
        f.write(body)


def main() -> NoReturn:
    """Generate and write the man page for pipx command line tool.

    This function generates the man page for the pipx command line tool using the `Manpage` class from `build_manpages` module.
    It adds a credit section and writes the generated man page to a file named `pipx.1`.

    Raises:
        FileNotFoundError: If the file `pipx.1` cannot be found.

    Examples:
        >>> main()
    """
    parser = get_command_parser()
    body = get_manpage_body(parser)
    body_with_credit = add_credit_section(body)
    write_manpage(body_with_credit)


if __name__ == "__main__":
    main()
