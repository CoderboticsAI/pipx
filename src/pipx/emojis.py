import os
import sys


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
    # All emojis that pipx might possibly use
    emoji_test_str = "✨🌟⚠️😴⣷⣯⣟⡿⢿⣻⣽⣾"
    try:
        emoji_test_str.encode(sys.stderr.encoding)
        platform_emoji_support = True
    except UnicodeEncodeError:
        platform_emoji_support = False
    return strtobool(str(os.getenv("USE_EMOJI", platform_emoji_support)))


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
