# This file is part of beets.
# Copyright 2016, Adrian Sampson.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

"""This module contains all of the core logic for beets' command-line
interface. To invoke the CLI, just call beets.ui.main(). The actual
CLI commands are implemented in the ui.commands module.
"""

import errno
import optparse
import os.path
import re
import sqlite3
import struct
import sys
import textwrap
import traceback
from difflib import SequenceMatcher
from typing import Any, Callable

import confuse

from beets import config, library, logging, plugins, util
from beets.autotag import mb
from beets.dbcore import db
from beets.dbcore import query as db_query
from beets.util import as_string
from beets.util.functemplate import template

# On Windows platforms, use colorama to support "ANSI" terminal colors.
if sys.platform == "win32":
    try:
        import colorama
    except ImportError:
        pass
    else:
        colorama.init()


log = logging.getLogger("beets")
if not log.handlers:
    log.addHandler(logging.StreamHandler())
log.propagate = False  # Don't propagate to root handler.


PF_KEY_QUERIES = {
    "comp": "comp:true",
    "singleton": "singleton:true",
}


class UserError(Exception):
    """UI exception. Commands should throw this in order to display
    nonrecoverable errors to the user.
    """


# Encoding utilities.


def _in_encoding():
    """Get the encoding to use for *inputting* strings from the console."""
    return _stream_encoding(sys.stdin)


def _out_encoding():
    """Get the encoding to use for *outputting* strings to the console."""
    return _stream_encoding(sys.stdout)


def _stream_encoding(stream, default="utf-8"):
    """A helper for `_in_encoding` and `_out_encoding`: get the stream's
    preferred encoding, using a configured override or a default
    fallback if neither is not specified.
    """
    # Configured override?
    encoding = config["terminal_encoding"].get()
    if encoding:
        return encoding

    # For testing: When sys.stdout or sys.stdin is a StringIO under the
    # test harness, it doesn't have an `encoding` attribute. Just use
    # UTF-8.
    if not hasattr(stream, "encoding"):
        return default

    # Python's guessed output stream encoding, or UTF-8 as a fallback
    # (e.g., when piped to a file).
    return stream.encoding or default


def decargs(arglist):
    """Given a list of command-line argument bytestrings, attempts to
    decode them to Unicode strings when running under Python 2.
    """
    return arglist


def print_(*strings, **kwargs):
    """Like print, but rather than raising an error when a character
    is not in the terminal's encoding's character set, just silently
    replaces it.

    The arguments must be Unicode strings: `unicode` on Python 2; `str` on
    Python 3.

    The `end` keyword argument behaves similarly to the built-in `print`
    (it defaults to a newline).
    """
    if not strings:
        strings = [""]
    assert isinstance(strings[0], str)

    txt = " ".join(strings)
    txt += kwargs.get("end", "\n")

    # Encode the string and write it to stdout.
    # On Python 3, sys.stdout expects text strings and uses the
    # exception-throwing encoding error policy. To avoid throwing
    # errors and use our configurable encoding override, we use the
    # underlying bytes buffer instead.
    if hasattr(sys.stdout, "buffer"):
        out = txt.encode(_out_encoding(), "replace")
        sys.stdout.buffer.write(out)
        sys.stdout.buffer.flush()
    else:
        # In our test harnesses (e.g., DummyOut), sys.stdout.buffer
        # does not exist. We instead just record the text string.
        sys.stdout.write(txt)


# Configuration wrappers.


def _bool_fallback(a, b):
    """Given a boolean or None, return the original value or a fallback."""
    if a is None:
        assert isinstance(b, bool)
        return b
    else:
        assert isinstance(a, bool)
        return a


def should_write(write_opt=None):
    """Decide whether a command that updates metadata should also write
    tags, using the importer configuration as the default.
    """
    return _bool_fallback(write_opt, config["import"]["write"].get(bool))


def should_move(move_opt=None):
    """Decide whether a command that updates metadata should also move
    files when they're inside the library, using the importer
    configuration as the default.

    Specifically, commands should move files after metadata updates only
    when the importer is configured *either* to move *or* to copy files.
    They should avoid moving files when the importer is configured not
    to touch any filenames.
    """
    return _bool_fallback(
        move_opt,
        config["import"]["move"].get(bool)
        or config["import"]["copy"].get(bool),
    )


# Input prompts.


def indent(count):
    """Returns a string with `count` many spaces."""
    return " " * count


def input_(prompt=None):
    """Like `input`, but decodes the result to a Unicode string.
    Raises a UserError if stdin is not available. The prompt is sent to
    stdout rather than stderr. A printed between the prompt and the
    input cursor.
    """
    # raw_input incorrectly sends prompts to stderr, not stdout, so we
    # use print_() explicitly to display prompts.
    # https://bugs.python.org/issue1927
    if prompt:
        print_(prompt, end=" ")

    try:
        resp = input()
    except EOFError:
        raise UserError("stdin stream ended while input required")

    return resp


def input_options(
    options,
    require=False,
    prompt=None,
    fallback_prompt=None,
    numrange=None,
    default=None,
    max_width=72,
):
    """Prompts a user for input. The sequence of `options` defines the
    choices the user has. A single-letter shortcut is inferred for each
    option; the user's choice is returned as that single, lower-case
    letter. The options should be provided as lower-case strings unless
    a particular shortcut is desired; in that case, only that letter
    should be capitalized.

    By default, the first option is the default. `default` can be provided to
    override this. If `require` is provided, then there is no default. The
    prompt and fallback prompt are also inferred but can be overridden.

    If numrange is provided, it is a pair of `(high, low)` (both ints)
    indicating that, in addition to `options`, the user may enter an
    integer in that inclusive range.

    `max_width` specifies the maximum number of columns in the
    automatically generated prompt string.
    """
    # Assign single letters to each option. Also capitalize the options
    # to indicate the letter.
    letters = {}
    display_letters = []
    capitalized = []
    first = True
    for option in options:
        # Is a letter already capitalized?
        for letter in option:
            if letter.isalpha() and letter.upper() == letter:
                found_letter = letter
                break
        else:
            # Infer a letter.
            for letter in option:
                if not letter.isalpha():
                    continue  # Don't use punctuation.
                if letter not in letters:
                    found_letter = letter
                    break
            else:
                raise ValueError("no unambiguous lettering found")

        letters[found_letter.lower()] = option
        index = option.index(found_letter)

        # Mark the option's shortcut letter for display.
        if not require and (
            (default is None and not numrange and first)
            or (
                isinstance(default, str)
                and found_letter.lower() == default.lower()
            )
        ):
            # The first option is the default; mark it.
            show_letter = "[%s]" % found_letter.upper()
            is_default = True
        else:
            show_letter = found_letter.upper()
            is_default = False

        # Colorize the letter shortcut.
        show_letter = colorize(
            "action_default" if is_default else "action", show_letter
        )

        # Insert the highlighted letter back into the word.
        descr_color = "action_default" if is_default else "action_description"
        capitalized.append(
            colorize(descr_color, option[:index])
            + show_letter
            + colorize(descr_color, option[index + 1 :])
        )
        display_letters.append(found_letter.upper())

        first = False

    # The default is just the first option if unspecified.
    if require:
        default = None
    elif default is None:
        if numrange:
            default = numrange[0]
        else:
            default = display_letters[0].lower()

    # Make a prompt if one is not provided.
    if not prompt:
        prompt_parts = []
        prompt_part_lengths = []
        if numrange:
            if isinstance(default, int):
                default_name = str(default)
                default_name = colorize("action_default", default_name)
                tmpl = "# selection (default %s)"
                prompt_parts.append(tmpl % default_name)
                prompt_part_lengths.append(len(tmpl % str(default)))
            else:
                prompt_parts.append("# selection")
                prompt_part_lengths.append(len(prompt_parts[-1]))
        prompt_parts += capitalized
        prompt_part_lengths += [len(s) for s in options]

        # Wrap the query text.
        # Start prompt with U+279C: Heavy Round-Tipped Rightwards Arrow
        prompt = colorize("action", "\u279c ")
        line_length = 0
        for i, (part, length) in enumerate(
            zip(prompt_parts, prompt_part_lengths)
        ):
            # Add punctuation.
            if i == len(prompt_parts) - 1:
                part += colorize("action_description", "?")
            else:
                part += colorize("action_description", ",")
            length += 1

            # Choose either the current line or the beginning of the next.
            if line_length + length + 1 > max_width:
                prompt += "\n"
                line_length = 0

            if line_length != 0:
                # Not the beginning of the line; need a space.
                part = " " + part
                length += 1

            prompt += part
            line_length += length

    # Make a fallback prompt too. This is displayed if the user enters
    # something that is not recognized.
    if not fallback_prompt:
        fallback_prompt = "Enter one of "
        if numrange:
            fallback_prompt += "%i-%i, " % numrange
        fallback_prompt += ", ".join(display_letters) + ":"

    resp = input_(prompt)
    while True:
        resp = resp.strip().lower()

        # Try default option.
        if default is not None and not resp:
            resp = default

        # Try an integer input if available.
        if numrange:
            try:
                resp = int(resp)
            except ValueError:
                pass
            else:
                low, high = numrange
                if low <= resp <= high:
                    return resp
                else:
                    resp = None

        # Try a normal letter input.
        if resp:
            resp = resp[0]
            if resp in letters:
                return resp

        # Prompt for new input.
        resp = input_(fallback_prompt)


def input_yn(prompt, require=False):
    """Prompts the user for a "yes" or "no" response. The default is
    "yes" unless `require` is `True`, in which case there is no default.
    """
    # Start prompt with U+279C: Heavy Round-Tipped Rightwards Arrow
    yesno = colorize("action", "\u279c ") + colorize(
        "action_description", "Enter Y or N:"
    )
    sel = input_options(("y", "n"), require, prompt, yesno)
    return sel == "y"


def input_select_objects(prompt, objs, rep, prompt_all=None):
    """Prompt to user to choose all, none, or some of the given objects.
    Return the list of selected objects.

    `prompt` is the prompt string to use for each question (it should be
    phrased as an imperative verb). If `prompt_all` is given, it is used
    instead of `prompt` for the first (yes(/no/select) question.
    `rep` is a function to call on each object to print it out when confirming
    objects individually.
    """
    choice = input_options(
        ("y", "n", "s"), False, "%s? (Yes/no/select)" % (prompt_all or prompt)
    )
    print()  # Blank line.

    if choice == "y":  # Yes.
        return objs

    elif choice == "s":  # Select.
        out = []
        for obj in objs:
            rep(obj)
            answer = input_options(
                ("y", "n", "q"),
                True,
                "%s? (yes/no/quit)" % prompt,
                "Enter Y or N:",
            )
            if answer == "y":
                out.append(obj)
            elif answer == "q":
                return out
        return out

    else:  # No.
        return []


# Human output formatting.


def human_bytes(size):
    """Formats size, a number of bytes, in a human-readable way."""
    powers = ["", "K", "M", "G", "T", "P", "E", "Z", "Y", "H"]
    unit = "B"
    for power in powers:
        if size < 1024:
            return f"{size:3.1f} {power}{unit}"
        size /= 1024.0
        unit = "iB"
    return "big"


def human_seconds(interval):
    """Formats interval, a number of seconds, as a human-readable time
    interval using English words.
    """
    units = [
        (1, "second"),
        (60, "minute"),
        (60, "hour"),
        (24, "day"),
        (7, "week"),
        (52, "year"),
        (10, "decade"),
    ]
    for i in range(len(units) - 1):
        increment, suffix = units[i]
        next_increment, _ = units[i + 1]
        interval /= float(increment)
        if interval < next_increment:
            break
    else:
        # Last unit.
        increment, suffix = units[-1]
        interval /= float(increment)

    return f"{interval:3.1f} {suffix}s"


def human_seconds_short(interval):
    """Formats a number of seconds as a short human-readable M:SS
    string.
    """
    interval = int(interval)
    return "%i:%02i" % (interval // 60, interval % 60)


# Colorization.

# ANSI terminal colorization code heavily inspired by pygments:
# https://bitbucket.org/birkenfeld/pygments-main/src/default/pygments/console.py
# (pygments is by Tim Hatch, Armin Ronacher, et al.)
COLOR_ESCAPE = "\x1b["
LEGACY_COLORS = {
    "black": ["black"],
    "darkred": ["red"],
    "darkgreen": ["green"],
    "brown": ["yellow"],
    "darkyellow": ["yellow"],
    "darkblue": ["blue"],
    "purple": ["magenta"],
    "darkmagenta": ["magenta"],
    "teal": ["cyan"],
    "darkcyan": ["cyan"],
    "lightgray": ["white"],
    "darkgray": ["bold", "black"],
    "red": ["bold", "red"],
    "green": ["bold", "green"],
    "yellow": ["bold", "yellow"],
    "blue": ["bold", "blue"],
    "fuchsia": ["bold", "magenta"],
    "magenta": ["bold", "magenta"],
    "turquoise": ["bold", "cyan"],
    "cyan": ["bold", "cyan"],
    "white": ["bold", "white"],
}
# All ANSI Colors.
ANSI_CODES = {
    # Styles.
    "normal": 0,
    "bold": 1,
    "faint": 2,
    # "italic":       3,
    "underline": 4,
    # "blink_slow":   5,
    # "blink_rapid":  6,
    "inverse": 7,
    # "conceal":      8,
    # "crossed_out":  9
    # Text colors.
    "black": 30,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    "white": 37,
    # Background colors.
    "bg_black": 40,
    "bg_red": 41,
    "bg_green": 42,
    "bg_yellow": 43,
    "bg_blue": 44,
    "bg_magenta": 45,
    "bg_cyan": 46,
    "bg_white": 47,
}
RESET_COLOR = COLOR_ESCAPE + "39;49;00m"

# These abstract COLOR_NAMES are lazily mapped on to the actual color in COLORS
# as they are defined in the configuration files, see function: colorize
COLOR_NAMES = [
    "text_success",
    "text_warning",
    "text_error",
    "text_highlight",
    "text_highlight_minor",
    "action_default",
    "action",
    # New Colors
    "text",
    "text_faint",
    "import_path",
    "import_path_items",
    "action_description",
    "added",
    "removed",
    "changed",
    "added_highlight",
    "removed_highlight",
    "changed_highlight",
    "text_diff_added",
    "text_diff_removed",
    "text_diff_changed",
]
COLORS = None


def _colorize(color, text):
    """Returns a string that prints the given text in the given color
    in a terminal that is ANSI color-aware. The color must be a list of strings
    from ANSI_CODES.
    """
    # Construct escape sequence to be put before the text by iterating
    # over all "ANSI codes" in `color`.
    escape = ""
    for code in color:
        escape = escape + COLOR_ESCAPE + "%im" % ANSI_CODES[code]
    return escape + text + RESET_COLOR


def colorize(color_name, text):
    """Colorize text if colored output is enabled. (Like _colorize but
    conditional.)
    """
    if config["ui"]["color"] and "NO_COLOR" not in os.environ:
        global COLORS
        if not COLORS:
            # Read all color configurations and set global variable COLORS.
            COLORS = dict()
            for name in COLOR_NAMES:
                # Convert legacy color definitions (strings) into the new
                # list-based color definitions. Do this by trying to read the
                # color definition from the configuration as unicode - if this
                # is successful, the color definition is a legacy definition
                # and has to be converted.
                try:
                    color_def = config["ui"]["colors"][name].get(str)
                except (confuse.ConfigTypeError, NameError):
                    # Normal color definition (type: list of unicode).
                    color_def = config["ui"]["colors"][name].get(list)
                else:
                    # Legacy color definition (type: unicode). Convert.
                    if color_def in LEGACY_COLORS:
                        color_def = LEGACY_COLORS[color_def]
                    else:
                        raise UserError("no such color %s", color_def)
                for code in color_def:
                    if code not in ANSI_CODES.keys():
                        raise ValueError("no such ANSI code %s", code)
                COLORS[name] = color_def
        # In case a 3rd party plugin is still passing the actual color ('red')
        # instead of the abstract color name ('text_error')
        color = COLORS.get(color_name)
        if not color:
            log.debug("Invalid color_name: {0}", color_name)
            color = color_name
        return _colorize(color, text)
    else:
        return text


def uncolorize(colored_text):
    """Remove colors from a string."""
    # Define a regular expression to match ANSI codes.
    # See: http://stackoverflow.com/a/2187024/1382707
    # Explanation of regular expression:
    #     \x1b     - matches ESC character
    #     \[       - matches opening square bracket
    #     [;\d]*   - matches a sequence consisting of one or more digits or
    #                semicola
    #     [A-Za-z] - matches a letter
    ansi_code_regex = re.compile(r"\x1b\[[;\d]*[A-Za-z]", re.VERBOSE)
    # Strip ANSI codes from `colored_text` using the regular expression.
    text = ansi_code_regex.sub("", colored_text)
    return text


def color_split(colored_text, index):
    ansi_code_regex = re.compile(r"(\x1b\[[;\d]*[A-Za-z])", re.VERBOSE)
    length = 0
    pre_split = ""
    post_split = ""
    found_color_code = None
    found_split = False
    for part in ansi_code_regex.split(colored_text):
        # Count how many real letters we have passed
        length += color_len(part)
        if found_split:
            post_split += part
        else:
            if ansi_code_regex.match(part):
                # This is a color code
                if part == RESET_COLOR:
                    found_color_code = None
                else:
                    found_color_code = part
                pre_split += part
            else:
                if index < length:
                    # Found part with our split in.
                    split_index = index - (length - color_len(part))
                    found_split = True
                    if found_color_code:
                        pre_split += part[:split_index] + RESET_COLOR
                        post_split += found_color_code + part[split_index:]
                    else:
                        pre_split += part[:split_index]
                        post_split += part[split_index:]
                else:
                    # Not found, add this part to the pre split
                    pre_split += part
    return pre_split, post_split


def color_len(colored_text):
    """Measure the length of a string while excluding ANSI codes from the
    measurement. The standard `len(my_string)` method also counts ANSI codes
    to the string length, which is counterproductive when layouting a
    Terminal interface.
    """
    # Return the length of the uncolored string.
    return len(uncolorize(colored_text))


def _colordiff(a, b):
    """Given two values, return the same pair of strings except with
    their differences highlighted in the specified color. Strings are
    highlighted intelligently to show differences; other values are
    stringified and highlighted in their entirety.
    """
    # First, convert paths to readable format
    if isinstance(a, bytes) or isinstance(b, bytes):
        # A path field.
        a = util.displayable_path(a)
        b = util.displayable_path(b)

    if not isinstance(a, str) or not isinstance(b, str):
        # Non-strings: use ordinary equality.
        if a == b:
            return str(a), str(b)
        else:
            return (
                colorize("text_diff_removed", str(a)),
                colorize("text_diff_added", str(b)),
            )

    a_out = []
    b_out = []

    matcher = SequenceMatcher(lambda x: False, a, b)
    for op, a_start, a_end, b_start, b_end in matcher.get_opcodes():
        if op == "equal":
            # In both strings.
            a_out.append(a[a_start:a_end])
            b_out.append(b[b_start:b_end])
        elif op == "insert":
            # Right only.
            b_out.append(colorize("text_diff_added", b[b_start:b_end]))
        elif op == "delete":
            # Left only.
            a_out.append(colorize("text_diff_removed", a[a_start:a_end]))
        elif op == "replace":
            # Right and left differ. Colorise with second highlight if
            # it's just a case change.
            if a[a_start:a_end].lower() != b[b_start:b_end].lower():
                a_color = "text_diff_removed"
                b_color = "text_diff_added"
            else:
                a_color = b_color = "text_highlight_minor"
            a_out.append(colorize(a_color, a[a_start:a_end]))
            b_out.append(colorize(b_color, b[b_start:b_end]))
        else:
            assert False

    return "".join(a_out), "".join(b_out)


def colordiff(a, b):
    """Colorize differences between two values if color is enabled.
    (Like _colordiff but conditional.)
    """
    if config["ui"]["color"]:
        return _colordiff(a, b)
    else:
        return str(a), str(b)


def get_path_formats(subview=None):
    """Get the configuration's path formats as a list of query/template
    pairs.
    """
    path_formats = []
    subview = subview or config["paths"]
    for query, view in subview.items():
        query = PF_KEY_QUERIES.get(query, query)  # Expand common queries.
        path_formats.append((query, template(view.as_str())))
    return path_formats


def get_replacements():
    """Confuse validation function that reads regex/string pairs."""
    replacements = []
    for pattern, repl in config["replace"].get(dict).items():
        repl = repl or ""
        try:
            replacements.append((re.compile(pattern), repl))
        except re.error:
            raise UserError(
                "malformed regular expression in replace: {}".format(pattern)
            )
    return replacements


def term_width():
    """Get the width (columns) of the terminal."""
    fallback = config["ui"]["terminal_width"].get(int)

    # The fcntl and termios modules are not available on non-Unix
    # platforms, so we fall back to a constant.
    try:
        import fcntl
        import termios
    except ImportError:
        return fallback

    try:
        buf = fcntl.ioctl(0, termios.TIOCGWINSZ, " " * 4)
    except OSError:
        return fallback
    try:
        height, width = struct.unpack("hh", buf)
    except struct.error:
        return fallback
    return width


def split_into_lines(string, width_tuple):
    """Splits string into a list of substrings at whitespace.

    `width_tuple` is a 3-tuple of `(first_width, last_width, middle_width)`.
    The first substring has a length not longer than `first_width`, the last
    substring has a length not longer than `last_width`, and all other
    substrings have a length not longer than `middle_width`.
    `string` may contain ANSI codes at word borders.
    """
    first_width, middle_width, last_width = width_tuple
    words = []
    esc_text = re.compile(
        r"""(?P<pretext>[^\x1b]*)
                            (?P<esc>(?:\x1b\[[;\d]*[A-Za-z])+)
                            (?P<text>[^\x1b]+)(?P<reset>\x1b\[39;49;00m)
                            (?P<posttext>[^\x1b]*)""",
        re.VERBOSE,
    )
    if uncolorize(string) == string:
        # No colors in string
        words = string.split()
    else:
        # Use a regex to find escapes and the text within them.
        for m in esc_text.finditer(string):
            # m contains four groups:
            # pretext - any text before escape sequence
            # esc - intitial escape sequence
            # text - text, no escape sequence, may contain spaces
            # reset - ASCII colour reset
            space_before_text = False
            if m.group("pretext") != "":
                # Some pretext found, let's handle it
                # Add any words in the pretext
                words += m.group("pretext").split()
                if m.group("pretext")[-1] == " ":
                    # Pretext ended on a space
                    space_before_text = True
                else:
                    # Pretext ended mid-word, ensure next word
                    pass
            else:
                # pretext empty, treat as if there is a space before
                space_before_text = True
            if m.group("text")[0] == " ":
                # First character of the text is a space
                space_before_text = True
            # Now, handle the words in the main text:
            raw_words = m.group("text").split()
            if space_before_text:
                # Colorize each word with pre/post escapes
                # Reconstruct colored words
                words += [
                    m.group("esc") + raw_word + RESET_COLOR
                    for raw_word in raw_words
                ]
            elif raw_words:
                # Pretext stops mid-word
                if m.group("esc") != RESET_COLOR:
                    # Add the rest of the current word, with a reset after it
                    words[-1] += m.group("esc") + raw_words[0] + RESET_COLOR
                    # Add the subsequent colored words:
                    words += [
                        m.group("esc") + raw_word + RESET_COLOR
                        for raw_word in raw_words[1:]
                    ]
                else:
                    # Caught a mid-word escape sequence
                    words[-1] += raw_words[0]
                    words += raw_words[1:]
            if (
                m.group("text")[-1] != " "
                and m.group("posttext") != ""
                and m.group("posttext")[0] != " "
            ):
                # reset falls mid-word
                post_text = m.group("posttext").split()
                words[-1] += post_text[0]
                words += post_text[1:]
            else:
                # Add any words after escape sequence
                words += m.group("posttext").split()
    result = []
    next_substr = ""
    # Iterate over all words.
    previous_fit = False
    for i in range(len(words)):
        if i == 0:
            pot_substr = words[i]
        else:
            # (optimistically) add the next word to check the fit
            pot_substr = " ".join([next_substr, words[i]])
        # Find out if the pot(ential)_substr fits into the next substring.
        fits_first = len(result) == 0 and color_len(pot_substr) <= first_width
        fits_middle = len(result) != 0 and color_len(pot_substr) <= middle_width
        if fits_first or fits_middle:
            # Fitted(!) let's try and add another word before appending
            next_substr = pot_substr
            previous_fit = True
        elif not fits_first and not fits_middle and previous_fit:
            # Extra word didn't fit, append what we have
            result.append(next_substr)
            next_substr = words[i]
            previous_fit = color_len(next_substr) <= middle_width
        else:
            # Didn't fit anywhere
            if uncolorize(pot_substr) == pot_substr:
                # Simple uncolored string, append a cropped word
                if len(result) == 0:
                    # Crop word by the first_width for the first line
                    result.append(pot_substr[:first_width])
                    # add rest of word to next line
                    next_substr = pot_substr[first_width:]
                else:
                    result.append(pot_substr[:middle_width])
                    next_substr = pot_substr[middle_width:]
            else:
                # Colored strings
                if len(result) == 0:
                    this_line, next_line = color_split(pot_substr, first_width)
                    result.append(this_line)
                    next_substr = next_line
                else:
                    this_line, next_line = color_split(pot_substr, middle_width)
                    result.append(this_line)
                    next_substr = next_line
            previous_fit = color_len(next_substr) <= middle_width

    # We finished constructing the substrings, but the last substring
    # has not yet been added to the result.
    result.append(next_substr)
    # Also, the length of the last substring was only checked against
    # `middle_width`. Append an empty substring as the new last substring if
    # the last substring is too long.
    if not color_len(next_substr) <= last_width:
        result.append("")
    return result


def print_column_layout(
    indent_str, left, right, separator=" -> ", max_width=term_width()
):
    """Print left & right data, with separator inbetween
    'left' and 'right' have a structure of:
    {'prefix':u'','contents':u'','suffix':u'','width':0}
    In a column layout the printing will be:
    {indent_str}{lhs0}{separator}{rhs0}
            {lhs1 / padding }{rhs1}
            ...
    The first line of each column (i.e. {lhs0} or {rhs0}) is:
    {prefix}{part of contents}{suffix}
    With subsequent lines (i.e. {lhs1}, {rhs1} onwards) being the
    rest of contents, wrapped if the width would be otherwise exceeded.
    """
    if right["prefix"] + right["contents"] + right["suffix"] == "":
        # No right hand information, so we don't need a separator.
        separator = ""
    first_line_no_wrap = (
        indent_str
        + left["prefix"]
        + left["contents"]
        + left["suffix"]
        + separator
        + right["prefix"]
        + right["contents"]
        + right["suffix"]
    )
    if color_len(first_line_no_wrap) < max_width:
        # Everything fits, print out line.
        print_(first_line_no_wrap)
    else:
        # Wrap into columns
        if "width" not in left or "width" not in right:
            # If widths have not been defined, set to share space.
            left["width"] = (
                max_width - len(indent_str) - color_len(separator)
            ) // 2
            right["width"] = (
                max_width - len(indent_str) - color_len(separator)
            ) // 2
        # On the first line, account for suffix as well as prefix
        left_width_tuple = (
            left["width"]
            - color_len(left["prefix"])
            - color_len(left["suffix"]),
            left["width"] - color_len(left["prefix"]),
            left["width"] - color_len(left["prefix"]),
        )

        left_split = split_into_lines(left["contents"], left_width_tuple)
        right_width_tuple = (
            right["width"]
            - color_len(right["prefix"])
            - color_len(right["suffix"]),
            right["width"] - color_len(right["prefix"]),
            right["width"] - color_len(right["prefix"]),
        )

        right_split = split_into_lines(right["contents"], right_width_tuple)
        max_line_count = max(len(left_split), len(right_split))

        out = ""
        for i in range(max_line_count):
            # indentation
            out += indent_str

            # Prefix or indent_str for line
            if i == 0:
                out += left["prefix"]
            else:
                out += indent(color_len(left["prefix"]))

            # Line i of left hand side contents.
            if i < len(left_split):
                out += left_split[i]
                left_part_len = color_len(left_split[i])
            else:
                left_part_len = 0

            # Padding until end of column.
            # Note: differs from original
            # column calcs in not -1 afterwards for space
            # in track number as that is included in 'prefix'
            padding = left["width"] - color_len(left["prefix"]) - left_part_len

            # Remove some padding on the first line to display
            # length
            if i == 0:
                padding -= color_len(left["suffix"])

            out += indent(padding)

            if i == 0:
                out += left["suffix"]

            # Separator between columns.
            if i == 0:
                out += separator
            else:
                out += indent(color_len(separator))

            # Right prefix, contents, padding, suffix
            if i == 0:
                out += right["prefix"]
            else:
                out += indent(color_len(right["prefix"]))

            # Line i of right hand side.
            if i < len(right_split):
                out += right_split[i]
                right_part_len = color_len(right_split[i])
            else:
                right_part_len = 0

            # Padding until end of column
            padding = (
                right["width"] - color_len(right["prefix"]) - right_part_len
            )
            # Remove some padding on the first line to display
            # length
            if i == 0:
                padding -= color_len(right["suffix"])
            out += indent(padding)
            # Length in first line
            if i == 0:
                out += right["suffix"]

            # Linebreak, except in the last line.
            if i < max_line_count - 1:
                out += "\n"

        # Constructed all of the columns, now print
        print_(out)


def print_newline_layout(
    indent_str, left, right, separator=" -> ", max_width=term_width()
):
    """Prints using a newline separator between left & right if
    they go over their allocated widths. The datastructures are
    shared with the column layout. In contrast to the column layout,
    the prefix and suffix are printed at the beginning and end of
    the contents. If no wrapping is required (i.e. everything fits) the
    first line will look exactly the same as the column layout:
    {indent}{lhs0}{separator}{rhs0}
    However if this would go over the width given, the layout now becomes:
    {indent}{lhs0}
    {indent}{separator}{rhs0}
    If {lhs0} would go over the maximum width, the subsequent lines are
    indented a second time for ease of reading.
    """
    if right["prefix"] + right["contents"] + right["suffix"] == "":
        # No right hand information, so we don't need a separator.
        separator = ""
    first_line_no_wrap = (
        indent_str
        + left["prefix"]
        + left["contents"]
        + left["suffix"]
        + separator
        + right["prefix"]
        + right["contents"]
        + right["suffix"]
    )
    if color_len(first_line_no_wrap) < max_width:
        # Everything fits, print out line.
        print_(first_line_no_wrap)
    else:
        # Newline separation, with wrapping
        empty_space = max_width - len(indent_str)
        # On lower lines we will double the indent for clarity
        left_width_tuple = (
            empty_space,
            empty_space - len(indent_str),
            empty_space - len(indent_str),
        )
        left_str = left["prefix"] + left["contents"] + left["suffix"]
        left_split = split_into_lines(left_str, left_width_tuple)
        # Repeat calculations for rhs, including separator on first line
        right_width_tuple = (
            empty_space - color_len(separator),
            empty_space - len(indent_str),
            empty_space - len(indent_str),
        )
        right_str = right["prefix"] + right["contents"] + right["suffix"]
        right_split = split_into_lines(right_str, right_width_tuple)
        for i, line in enumerate(left_split):
            if i == 0:
                print_(indent_str + line)
            elif line != "":
                # Ignore empty lines
                print_(indent_str * 2 + line)
        for i, line in enumerate(right_split):
            if i == 0:
                print_(indent_str + separator + line)
            elif line != "":
                print_(indent_str * 2 + line)


FLOAT_EPSILON = 0.01


def _field_diff(field, old, old_fmt, new, new_fmt):
    """Given two Model objects and their formatted views, format their values
    for `field` and highlight changes among them. Return a human-readable
    string. If the value has not changed, return None instead.
    """
    oldval = old.get(field)
    newval = new.get(field)

    # If no change, abort.
    if (
        isinstance(oldval, float)
        and isinstance(newval, float)
        and abs(oldval - newval) < FLOAT_EPSILON
    ):
        return None
    elif oldval == newval:
        return None

    # Get formatted values for output.
    oldstr = old_fmt.get(field, "")
    newstr = new_fmt.get(field, "")

    # For strings, highlight changes. For others, colorize the whole
    # thing.
    if isinstance(oldval, str):
        oldstr, newstr = colordiff(oldval, newstr)
    else:
        oldstr = colorize("text_error", oldstr)
        newstr = colorize("text_error", newstr)

    return f"{oldstr} -> {newstr}"


def show_model_changes(new, old=None, fields=None, always=False):
    """Given a Model object, print a list of changes from its pristine
    version stored in the database. Return a boolean indicating whether
    any changes were found.

    `old` may be the "original" object to avoid using the pristine
    version from the database. `fields` may be a list of fields to
    restrict the detection to. `always` indicates whether the object is
    always identified, regardless of whether any changes are present.
    """
    old = old or new._db._get(type(new), new.id)

    # Keep the formatted views around instead of re-creating them in each
    # iteration step
    old_fmt = old.formatted()
    new_fmt = new.formatted()

    # Build up lines showing changed fields.
    changes = []
    for field in old:
        # Subset of the fields. Never show mtime.
        if field == "mtime" or (fields and field not in fields):
            continue

        # Detect and show difference for this field.
        line = _field_diff(field, old, old_fmt, new, new_fmt)
        if line:
            changes.append(f"  {field}: {line}")

    # New fields.
    for field in set(new) - set(old):
        if fields and field not in fields:
            continue

        changes.append(
            "  {}: {}".format(field, colorize("text_highlight", new_fmt[field]))
        )

    # Print changes.
    if changes or always:
        print_(format(old))
    if changes:
        print_("\n".join(changes))

    return bool(changes)


def show_path_changes(path_changes):
    """Given a list of tuples (source, destination) that indicate the
    path changes, log the changes as INFO-level output to the beets log.
    The output is guaranteed to be unicode.

    Every pair is shown on a single line if the terminal width permits it,
    else it is split over two lines. E.g.,

    Source -> Destination

    vs.

    Source
      -> Destination
    """
    sources, destinations = zip(*path_changes)

    # Ensure unicode output
    sources = list(map(util.displayable_path, sources))
    destinations = list(map(util.displayable_path, destinations))

    # Calculate widths for terminal split
    col_width = (term_width() - len(" -> ")) // 2
    max_width = len(max(sources + destinations, key=len))

    if max_width > col_width:
        # Print every change over two lines
        for source, dest in zip(sources, destinations):
            color_source, color_dest = colordiff(source, dest)
            print_("{0} \n  -> {1}".format(color_source, color_dest))
    else:
        # Print every change on a single line, and add a header
        title_pad = max_width - len("Source ") + len(" -> ")

        print_("Source {0} Destination".format(" " * title_pad))
        for source, dest in zip(sources, destinations):
            pad = max_width - len(source)
            color_source, color_dest = colordiff(source, dest)
            print_(
                "{0} {1} -> {2}".format(
                    color_source,
                    " " * pad,
                    color_dest,
                )
            )


# Helper functions for option parsing.


def _store_dict(option, opt_str, value, parser):
    """Custom action callback to parse options which have ``key=value``
    pairs as values. All such pairs passed for this option are
    aggregated into a dictionary.
    """
    dest = option.dest
    option_values = getattr(parser.values, dest, None)

    if option_values is None:
        # This is the first supplied ``key=value`` pair of option.
        # Initialize empty dictionary and get a reference to it.
        setattr(parser.values, dest, {})
        option_values = getattr(parser.values, dest)

    try:
        key, value = value.split("=", 1)
        if not (key and value):
            raise ValueError
    except ValueError:
        raise UserError(
            "supplied argument `{}' is not of the form `key=value'".format(
                value
            )
        )

    option_values[key] = value


class CommonOptionsParser(optparse.OptionParser):
    """Offers a simple way to add common formatting options.

    Options available include:
        - matching albums instead of tracks: add_album_option()
        - showing paths instead of items/albums: add_path_option()
        - changing the format of displayed items/albums: add_format_option()

    The last one can have several behaviors:
        - against a special target
        - with a certain format
        - autodetected target with the album option

    Each method is fully documented in the related method.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._album_flags = False
        # this serves both as an indicator that we offer the feature AND allows
        # us to check whether it has been specified on the CLI - bypassing the
        # fact that arguments may be in any order

    def add_album_option(self, flags=("-a", "--album")):
        """Add a -a/--album option to match albums instead of tracks.

        If used then the format option can auto-detect whether we're setting
        the format for items or albums.
        Sets the album property on the options extracted from the CLI.
        """
        album = optparse.Option(
            *flags, action="store_true", help="match albums instead of tracks"
        )
        self.add_option(album)
        self._album_flags = set(flags)

    def _set_format(
        self,
        option,
        opt_str,
        value,
        parser,
        target=None,
        fmt=None,
        store_true=False,
    ):
        """Internal callback that sets the correct format while parsing CLI
        arguments.
        """
        if store_true:
            setattr(parser.values, option.dest, True)

        # Use the explicitly specified format, or the string from the option.
        if fmt:
            value = fmt
        elif value:
            (value,) = decargs([value])
        else:
            value = ""

        parser.values.format = value
        if target:
            config[target._format_config_key].set(value)
        else:
            if self._album_flags:
                if parser.values.album:
                    target = library.Album
                else:
                    # the option is either missing either not parsed yet
                    if self._album_flags & set(parser.rargs):
                        target = library.Album
                    else:
                        target = library.Item
                config[target._format_config_key].set(value)
            else:
                config[library.Item._format_config_key].set(value)
                config[library.Album._format_config_key].set(value)

    def add_path_option(self, flags=("-p", "--path")):
        """Add a -p/--path option to display the path instead of the default
        format.

        By default this affects both items and albums. If add_album_option()
        is used then the target will be autodetected.

        Sets the format property to '$path' on the options extracted from the
        CLI.
        """
        path = optparse.Option(
            *flags,
            nargs=0,
            action="callback",
            callback=self._set_format,
            callback_kwargs={"fmt": "$path", "store_true": True},
            help="print paths for matched items or albums",
        )
        self.add_option(path)

    def add_format_option(self, flags=("-f", "--format"), target=None):
        """Add -f/--format option to print some LibModel instances with a
        custom format.

        `target` is optional and can be one of ``library.Item``, 'item',
        ``library.Album`` and 'album'.

        Several behaviors are available:
            - if `target` is given then the format is only applied to that
            LibModel
            - if the album option is used then the target will be autodetected
            - otherwise the format is applied to both items and albums.

        Sets the format property on the options extracted from the CLI.
        """
        kwargs = {}
        if target:
            if isinstance(target, str):
                target = {"item": library.Item, "album": library.Album}[target]
            kwargs["target"] = target

        opt = optparse.Option(
            *flags,
            action="callback",
            callback=self._set_format,
            callback_kwargs=kwargs,
            help="print with custom format",
        )
        self.add_option(opt)

    def add_all_common_options(self):
        """Add album, path and format options."""
        self.add_album_option()
        self.add_path_option()
        self.add_format_option()


# Subcommand parsing infrastructure.
#
# This is a fairly generic subcommand parser for optparse. It is
# maintained externally here:
# https://gist.github.com/462717
# There you will also find a better description of the code and a more
# succinct example program.


class Subcommand:
    """A subcommand of a root command-line application that may be
    invoked by a SubcommandOptionParser.
    """

    func: Callable[[library.Library, optparse.Values, list[str]], Any]

    def __init__(self, name, parser=None, help="", aliases=(), hide=False):
        """Creates a new subcommand. name is the primary way to invoke
        the subcommand; aliases are alternate names. parser is an
        OptionParser responsible for parsing the subcommand's options.
        help is a short description of the command. If no parser is
        given, it defaults to a new, empty CommonOptionsParser.
        """
        self.name = name
        self.parser = parser or CommonOptionsParser()
        self.aliases = aliases
        self.help = help
        self.hide = hide
        self._root_parser = None

    def print_help(self):
        self.parser.print_help()

    def parse_args(self, args):
        return self.parser.parse_args(args)

    @property
    def root_parser(self):
        return self._root_parser

    @root_parser.setter
    def root_parser(self, root_parser):
        self._root_parser = root_parser
        self.parser.prog = "{} {}".format(
            as_string(root_parser.get_prog_name()), self.name
        )


class SubcommandsOptionParser(CommonOptionsParser):
    """A variant of OptionParser that parses subcommands and their
    arguments.
    """

    def __init__(self, *args, **kwargs):
        """Create a new subcommand-aware option parser. All of the
        options to OptionParser.__init__ are supported in addition
        to subcommands, a sequence of Subcommand objects.
        """
        # A more helpful default usage.
        if "usage" not in kwargs:
            kwargs["usage"] = """
  %prog COMMAND [ARGS...]
  %prog help COMMAND"""
        kwargs["add_help_option"] = False

        # Super constructor.
        super().__init__(*args, **kwargs)

        # Our root parser needs to stop on the first unrecognized argument.
        self.disable_interspersed_args()

        self.subcommands = []

    def add_subcommand(self, *cmds):
        """Adds a Subcommand object to the parser's list of commands."""
        for cmd in cmds:
            cmd.root_parser = self
            self.subcommands.append(cmd)

    # Add the list of subcommands to the help message.
    def format_help(self, formatter=None):
        # Get the original help message, to which we will append.
        out = super().format_help(formatter)
        if formatter is None:
            formatter = self.formatter

        # Subcommands header.
        result = ["\n"]
        result.append(formatter.format_heading("Commands"))
        formatter.indent()

        # Generate the display names (including aliases).
        # Also determine the help position.
        disp_names = []
        help_position = 0
        subcommands = [c for c in self.subcommands if not c.hide]
        subcommands.sort(key=lambda c: c.name)
        for subcommand in subcommands:
            name = subcommand.name
            if subcommand.aliases:
                name += " (%s)" % ", ".join(subcommand.aliases)
            disp_names.append(name)

            # Set the help position based on the max width.
            proposed_help_position = len(name) + formatter.current_indent + 2
            if proposed_help_position <= formatter.max_help_position:
                help_position = max(help_position, proposed_help_position)

        # Add each subcommand to the output.
        for subcommand, name in zip(subcommands, disp_names):
            # Lifted directly from optparse.py.
            name_width = help_position - formatter.current_indent - 2
            if len(name) > name_width:
                name = "%*s%s\n" % (formatter.current_indent, "", name)
                indent_first = help_position
            else:
                name = "%*s%-*s  " % (
                    formatter.current_indent,
                    "",
                    name_width,
                    name,
                )
                indent_first = 0
            result.append(name)
            help_width = formatter.width - help_position
            help_lines = textwrap.wrap(subcommand.help, help_width)
            help_line = help_lines[0] if help_lines else ""
            result.append("%*s%s\n" % (indent_first, "", help_line))
            result.extend(
                [
                    "%*s%s\n" % (help_position, "", line)
                    for line in help_lines[1:]
                ]
            )
        formatter.dedent()

        # Concatenate the original help message with the subcommand
        # list.
        return out + "".join(result)

    def _subcommand_for_name(self, name):
        """Return the subcommand in self.subcommands matching the
        given name. The name may either be the name of a subcommand or
        an alias. If no subcommand matches, returns None.
        """
        for subcommand in self.subcommands:
            if name == subcommand.name or name in subcommand.aliases:
                return subcommand
        return None

    def parse_global_options(self, args):
        """Parse options up to the subcommand argument. Returns a tuple
        of the options object and the remaining arguments.
        """
        options, subargs = self.parse_args(args)

        # Force the help command
        if options.help:
            subargs = ["help"]
        elif options.version:
            subargs = ["version"]
        return options, subargs

    def parse_subcommand(self, args):
        """Given the `args` left unused by a `parse_global_options`,
        return the invoked subcommand, the subcommand options, and the
        subcommand arguments.
        """
        # Help is default command
        if not args:
            args = ["help"]

        cmdname = args.pop(0)
        subcommand = self._subcommand_for_name(cmdname)
        if not subcommand:
            raise UserError(f"unknown command '{cmdname}'")

        suboptions, subargs = subcommand.parse_args(args)
        return subcommand, suboptions, subargs


optparse.Option.ALWAYS_TYPED_ACTIONS += ("callback",)


# The main entry point and bootstrapping.


def _load_plugins(options, config):
    """Load the plugins specified on the command line or in the configuration."""
    paths = config["pluginpath"].as_str_seq(split=False)
    paths = [util.normpath(p) for p in paths]
    log.debug("plugin paths: {0}", util.displayable_path(paths))

    # On Python 3, the search paths need to be unicode.
    paths = [os.fsdecode(p) for p in paths]

    # Extend the `beetsplug` package to include the plugin paths.
    import beetsplug

    beetsplug.__path__ = paths + list(beetsplug.__path__)

    # For backwards compatibility, also support plugin paths that
    # *contain* a `beetsplug` package.
    sys.path += paths

    # If we were given any plugins on the command line, use those.
    if options.plugins is not None:
        plugin_list = (
            options.plugins.split(",") if len(options.plugins) > 0 else []
        )
    else:
        plugin_list = config["plugins"].as_str_seq()

    # Exclude any plugins that were specified on the command line
    if options.exclude is not None:
        plugin_list = [
            p for p in plugin_list if p not in options.exclude.split(",")
        ]

    plugins.load_plugins(plugin_list)
    return plugins


def _setup(options, lib=None):
    """Prepare and global state and updates it with command line options.

    Returns a list of subcommands, a list of plugins, and a library instance.
    """
    # Configure the MusicBrainz API.
    mb.configure()

    config = _configure(options)

    plugins = _load_plugins(options, config)

    # Add types and queries defined by plugins.
    plugin_types_album = plugins.types(library.Album)
    library.Album._types.update(plugin_types_album)
    item_types = plugin_types_album.copy()
    item_types.update(library.Item._types)
    item_types.update(plugins.types(library.Item))
    library.Item._types = item_types

    library.Item._queries.update(plugins.named_queries(library.Item))
    library.Album._queries.update(plugins.named_queries(library.Album))

    plugins.send("pluginload")

    # Get the default subcommands.
    from beets.ui.commands import default_commands

    subcommands = list(default_commands)
    subcommands.extend(plugins.commands())

    if lib is None:
        lib = _open_library(config)
        plugins.send("library_opened", lib=lib)

    return subcommands, plugins, lib


def _configure(options):
    """Amend the global configuration object with command line options."""
    # Add any additional config files specified with --config. This
    # special handling lets specified plugins get loaded before we
    # finish parsing the command line.
    if getattr(options, "config", None) is not None:
        overlay_path = options.config
        del options.config
        config.set_file(overlay_path)
    else:
        overlay_path = None
    config.set_args(options)

    # Configure the logger.
    if config["verbose"].get(int):
        log.set_global_level(logging.DEBUG)
    else:
        log.set_global_level(logging.INFO)

    if overlay_path:
        log.debug(
            "overlaying configuration: {0}", util.displayable_path(overlay_path)
        )

    config_path = config.user_config_path()
    if os.path.isfile(config_path):
        log.debug("user configuration: {0}", util.displayable_path(config_path))
    else:
        log.debug(
            "no user configuration found at {0}",
            util.displayable_path(config_path),
        )

    log.debug("data directory: {0}", util.displayable_path(config.config_dir()))
    return config


def _ensure_db_directory_exists(path):
    if path == b":memory:":  # in memory db
        return
    newpath = os.path.dirname(path)
    if not os.path.isdir(newpath):
        if input_yn(
            "The database directory {} does not \
                       exist. Create it (Y/n)?".format(
                util.displayable_path(newpath)
            )
        ):
            os.makedirs(newpath)


def _open_library(config):
    """Create a new library instance from the configuration."""
    dbpath = util.bytestring_path(config["library"].as_filename())
    _ensure_db_directory_exists(dbpath)
    try:
        lib = library.Library(
            dbpath,
            config["directory"].as_filename(),
            get_path_formats(),
            get_replacements(),
        )
        lib.get_item(0)  # Test database connection.
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as db_error:
        log.debug("{}", traceback.format_exc())
        raise UserError(
            "database file {} cannot not be opened: {}".format(
                util.displayable_path(dbpath), db_error
            )
        )
    log.debug(
        "library database: {0}\n" "library directory: {1}",
        util.displayable_path(lib.path),
        util.displayable_path(lib.directory),
    )
    return lib


def _raw_main(args, lib=None):
    """A helper function for `main` without top-level exception
    handling.
    """
    parser = SubcommandsOptionParser()
    parser.add_format_option(flags=("--format-item",), target=library.Item)
    parser.add_format_option(flags=("--format-album",), target=library.Album)
    parser.add_option(
        "-l", "--library", dest="library", help="library database file to use"
    )
    parser.add_option(
        "-d",
        "--directory",
        dest="directory",
        help="destination music directory",
    )
    parser.add_option(
        "-v",
        "--verbose",
        dest="verbose",
        action="count",
        help="log more details (use twice for even more)",
    )
    parser.add_option(
        "-c", "--config", dest="config", help="path to configuration file"
    )
    parser.add_option(
        "-p",
        "--plugins",
        dest="plugins",
        help="a comma-separated list of plugins to load",
    )
    parser.add_option(
        "-P",
        "--disable-plugins",
        dest="exclude",
        help="a comma-separated list of plugins to disable",
    )
    parser.add_option(
        "-h",
        "--help",
        dest="help",
        action="store_true",
        help="show this help message and exit",
    )
    parser.add_option(
        "--version",
        dest="version",
        action="store_true",
        help=optparse.SUPPRESS_HELP,
    )

    options, subargs = parser.parse_global_options(args)

    # Special case for the `config --edit` command: bypass _setup so
    # that an invalid configuration does not prevent the editor from
    # starting.
    if (
        subargs
        and subargs[0] == "config"
        and ("-e" in subargs or "--edit" in subargs)
    ):
        from beets.ui.commands import config_edit

        return config_edit()

    test_lib = bool(lib)
    subcommands, plugins, lib = _setup(options, lib)
    parser.add_subcommand(*subcommands)

    subcommand, suboptions, subargs = parser.parse_subcommand(subargs)
    subcommand.func(lib, suboptions, subargs)

    plugins.send("cli_exit", lib=lib)
    if not test_lib:
        # Clean up the library unless it came from the test harness.
        lib._close()


def main(args=None):
    """Run the main command-line interface for beets. Includes top-level
    exception handlers that print friendly error messages.
    """
    if "AppData\\Local\\Microsoft\\WindowsApps" in sys.exec_prefix:
        log.error(
            "error: beets is unable to use the Microsoft Store version of "
            "Python. Please install Python from https://python.org.\n"
            "error: More details can be found here "
            "https://beets.readthedocs.io/en/stable/guides/main.html"
        )
        sys.exit(1)
    try:
        _raw_main(args)
    except UserError as exc:
        message = exc.args[0] if exc.args else None
        log.error("error: {0}", message)
        sys.exit(1)
    except util.HumanReadableError as exc:
        exc.log(log)
        sys.exit(1)
    except library.FileOperationError as exc:
        # These errors have reasonable human-readable descriptions, but
        # we still want to log their tracebacks for debugging.
        log.debug("{}", traceback.format_exc())
        log.error("{}", exc)
        sys.exit(1)
    except confuse.ConfigError as exc:
        log.error("configuration error: {0}", exc)
        sys.exit(1)
    except db_query.InvalidQueryError as exc:
        log.error("invalid query: {0}", exc)
        sys.exit(1)
    except OSError as exc:
        if exc.errno == errno.EPIPE:
            # "Broken pipe". End silently.
            sys.stderr.close()
        else:
            raise
    except KeyboardInterrupt:
        # Silently ignore ^C except in verbose mode.
        log.debug("{}", traceback.format_exc())
    except db.DBAccessError as exc:
        log.error(
            "database access error: {0}\n"
            "the library file might have a permissions problem",
            exc,
        )
        sys.exit(1)
