import os
import sys
from typing import Union


def strtobool(val: str) -> bool:
    """
    Convert a string representation of a boolean value to a boolean.

    Args:
        val: A string representing a boolean value.

    Returns:
        The corresponding boolean value.

    Examples:
        >>> strtobool('yes')
        True
        >>> strtobool('f')
        False
        >>> strtobool('invalid')
        False
    """
    true_values = ["y", "yes", "t", "true", "on", "1"]
    false_values = ["n", "no", "f", "false", "off", "0"]

    val = val.lower()
    if val in true_values:
        return True
    elif val in false_values:
        return False
    else:
        return False


def use_emojis() -> bool:
    """
    Determine if emojis should be used based on the platform and environment variable.

    Returns:
        A boolean value indicating whether emojis should be used or not.

    Examples:
        >>> os.environ["USE_EMOJI"] = "true"
        >>> use_emojis()
        True
        >>> os.environ["USE_EMOJI"] = "false"
        >>> use_emojis()
        False
        >>> os.environ["USE_EMOJI"] = ""  # no value set
        >>> sys.stderr.encoding = "ascii"
        >>> use_emojis()
        False
    """
    emoji_test_str = "✨🌟⚠️😴⣷⣯⣟⡿⢿⣻⣽⣾"
    platform_emoji_support = check_platform_emoji_support()
    env_emoji_support = strtobool(os.getenv("USE_EMOJI", str(platform_emoji_support)))
    return env_emoji_support


def check_platform_emoji_support() -> bool:
    """
    Check if the platform supports emojis.

    Returns:
        A boolean value indicating if the platform supports emojis.

    Raises:
        UnicodeEncodeError: If the platform does not support emojis.

    Examples:
        >>> sys.stderr.encoding = "utf-8"
        >>> check_platform_emoji_support()
        True
        >>> sys.stderr.encoding = "ascii"
        >>> check_platform_emoji_support()
        Traceback (most recent call last):
            ...
        UnicodeEncodeError: 'ascii' codec can't encode ...
    """
    emoji_test_str = "✨🌟⚠️😴⣷⣯⣟⡿⢿⣻⣽⣾"
    try:
        emoji_test_str.encode(sys.stderr.encoding)
        return True
    except UnicodeEncodeError:
        raise


EMOJI_SUPPORT = use_emojis()

if EMOJI_SUPPORT:
    stars = "✨ 🌟 ✨"
    hazard = "⚠️"
    error = "⛔"
    sleep = "😴"
else:
    stars = ""
    hazard = ""
    error = ""
    sleep = ""
