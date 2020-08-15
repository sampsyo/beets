# -*- coding: utf-8 -*-
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

from __future__ import division, absolute_import, print_function

import optparse
import textwrap
import sys
from difflib import SequenceMatcher
import sqlite3
import errno
import re
import struct
import traceback
import os.path
from six.moves import input

from beets import logging
from beets import library
from beets import plugins
from beets import util
from beets.util.functemplate import template
from beets import config
from beets.util import as_string
from beets.autotag import mb
from beets.dbcore import query as db_query
from beets.dbcore import db
import confuse
import six

# On Windows platforms, use colorama to support "ANSI" terminal colors.
if sys.platform == 'win32':
    try:
        import colorama
    except ImportError:
        pass
    else:
        colorama.init()


log = logging.getLogger('beets')
if not log.handlers:
    log.addHandler(logging.StreamHandler())
log.propagate = False  # Don't propagate to root handler.


PF_KEY_QUERIES = {
    'comp': u'comp:true',
    'singleton': u'singleton:true',
}


class UserError(Exception):
    """UI exception. Commands should throw this in order to display
    nonrecoverable errors to the user.
    """


# Encoding utilities.


def _in_encoding():
    """Get the encoding to use for *inputting* strings from the console.
    """
    return _stream_encoding(sys.stdin)


def _out_encoding():
    """Get the encoding to use for *outputting* strings to the console.
    """
    return _stream_encoding(sys.stdout)


def _stream_encoding(stream, default='utf-8'):
    """A helper for `_in_encoding` and `_out_encoding`: get the stream's
    preferred encoding, using a configured override or a default
    fallback if neither is not specified.
    """
    # Configured override?
    encoding = config['terminal_encoding'].get()
    if encoding:
        return encoding

    # For testing: When sys.stdout or sys.stdin is a StringIO under the
    # test harness, it doesn't have an `encoding` attribute. Just use
    # UTF-8.
    if not hasattr(stream, 'encoding'):
        return default

    # Python's guessed output stream encoding, or UTF-8 as a fallback
    # (e.g., when piped to a file).
    return stream.encoding or default


def decargs(arglist):
    """Given a list of command-line argument bytestrings, attempts to
    decode them to Unicode strings when running under Python 2.
    """
    if six.PY2:
        return [s.decode(util.arg_encoding()) for s in arglist]
    else:
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
        strings = [u'']
    assert isinstance(strings[0], six.text_type)

    txt = u' '.join(strings)
    txt += kwargs.get('end', u'\n')

    # Encode the string and write it to stdout.
    if six.PY2:
        # On Python 2, sys.stdout expects bytes.
        out = txt.encode(_out_encoding(), 'replace')
        sys.stdout.write(out)
    else:
        # On Python 3, sys.stdout expects text strings and uses the
        # exception-throwing encoding error policy. To avoid throwing
        # errors and use our configurable encoding override, we use the
        # underlying bytes buffer instead.
        if hasattr(sys.stdout, 'buffer'):
            out = txt.encode(_out_encoding(), 'replace')
            sys.stdout.buffer.write(out)
            sys.stdout.buffer.flush()
        else:
            # In our test harnesses (e.g., DummyOut), sys.stdout.buffer
            # does not exist. We instead just record the text string.
            sys.stdout.write(txt)


# Configuration wrappers.

def _bool_fallback(a, b):
    """Given a boolean or None, return the original value or a fallback.
    """
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
    return _bool_fallback(write_opt, config['import']['write'].get(bool))


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
        config['import']['move'].get(bool) or
        config['import']['copy'].get(bool)
    )


# Input prompts.

def indent(count):
    """Returns a string with `count` many spaces.
    """
    return u' ' * count


def indent_str(count, string):
    """Returns `string`, indented with `count` many spaces.
    """
    return indent(count) + string


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
        print_(prompt, end=u' ')

    try:
        resp = input()
    except EOFError:
        raise UserError(u'stdin stream ended while input required')

    if six.PY2:
        return resp.decode(_in_encoding(), 'ignore')
    else:
        return resp


def input_options(options, require=False, prompt=None, fallback_prompt=None,
                  numrange=None, default=None, max_width=72):
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
                raise ValueError(u'no unambiguous lettering found')

        letters[found_letter.lower()] = option
        index = option.index(found_letter)

        # Mark the option's shortcut letter for display.
        if not require and (
            (default is None and not numrange and first) or
            (isinstance(default, six.string_types) and
             found_letter.lower() == default.lower())):
            # The first option is the default; mark it.
            show_letter = '[%s]' % found_letter.upper()
            is_default = True
        else:
            show_letter = found_letter.upper()
            is_default = False

        # Colorize the letter shortcut.
        show_letter = colorize('action_default' if is_default else 'action',
                               show_letter)

        # Insert the highlighted letter back into the word.
        descr_color = 'action_default' if is_default else 'action_description'
        capitalized.append(
            colorize(descr_color, option[:index]) +
            show_letter +
            colorize(descr_color, option[index + 1:])
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
                default_name = six.text_type(default)
                default_name = colorize('action_default', default_name)
                tmpl = '# selection (default %s)'
                prompt_parts.append(tmpl % default_name)
                prompt_part_lengths.append(len(tmpl % six.text_type(default)))
            else:
                prompt_parts.append('# selection')
                prompt_part_lengths.append(len(prompt_parts[-1]))
        prompt_parts += capitalized
        prompt_part_lengths += [len(s) for s in options]

        # Wrap the query text.
        # Start prompt with U+279C: Heavy Round-Tipped Rightwards Arrow
        prompt = colorize('action', '\u279C ')
        line_length = 0
        for i, (part, length) in enumerate(zip(prompt_parts,
                                               prompt_part_lengths)):
            # Add punctuation.
            if i == len(prompt_parts) - 1:
                part += colorize('action_description', '?')
            else:
                part += colorize('action_description', ',')
            length += 1

            # Choose either the current line or the beginning of the next.
            if line_length + length + 1 > max_width:
                prompt += '\n'
                line_length = 0

            if line_length != 0:
                # Not the beginning of the line; need a space.
                part = ' ' + part
                length += 1

            prompt += part
            line_length += length

    # Make a fallback prompt too. This is displayed if the user enters
    # something that is not recognized.
    if not fallback_prompt:
        fallback_prompt = u'Enter one of '
        if numrange:
            fallback_prompt += u'%i-%i, ' % numrange
        fallback_prompt += ', '.join(display_letters) + ':'

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
    yesno = colorize('action', '\u279C ') + \
            colorize('action_description', 'Enter Y or N:')
    sel = input_options(
        ('y', 'n'), require, prompt, yesno
    )
    return sel == u'y'


def input_select_objects(prompt, objs, rep):
    """Prompt to user to choose all, none, or some of the given objects.
    Return the list of selected objects.

    `prompt` is the prompt string to use for each question (it should be
    phrased as an imperative verb). `rep` is a function to call on each
    object to print it out when confirming objects individually.
    """
    choice = input_options(
        (u'y', u'n', u's'), False,
        u'%s? (Yes/no/select)' % prompt)
    print()  # Blank line.

    if choice == u'y':  # Yes.
        return objs

    elif choice == u's':  # Select.
        out = []
        for obj in objs:
            rep(obj)
            answer = input_options(
                ('y', 'n', 'q'), True, u'%s? (yes/no/quit)' % prompt,
                u'Enter Y or N:'
            )
            if answer == u'y':
                out.append(obj)
            elif answer == u'q':
                return out
        return out

    else:  # No.
        return []


# Human output formatting.

def human_bytes(size):
    """Formats size, a number of bytes, in a human-readable way."""
    powers = [u'', u'K', u'M', u'G', u'T', u'P', u'E', u'Z', u'Y', u'H']
    unit = 'B'
    for power in powers:
        if size < 1024:
            return u"%3.1f %s%s" % (size, power, unit)
        size /= 1024.0
        unit = u'iB'
    return u"big"


def human_seconds(interval):
    """Formats interval, a number of seconds, as a human-readable time
    interval using English words.
    """
    units = [
        (1, u'second'),
        (60, u'minute'),
        (60, u'hour'),
        (24, u'day'),
        (7, u'week'),
        (52, u'year'),
        (10, u'decade'),
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

    return u"%3.1f %ss" % (interval, suffix)


def human_seconds_short(interval):
    """Formats a number of seconds as a short human-readable M:SS
    string.
    """
    interval = int(interval)
    return u'%i:%02i' % (interval // 60, interval % 60)


# Colorization.

# ANSI terminal colorization code heavily inspired by pygments:
# https://bitbucket.org/birkenfeld/pygments-main/src/default/pygments/console.py
# (pygments is by Tim Hatch, Armin Ronacher, et al.)
COLOR_ESCAPE = "\x1b["
LEGACY_COLORS = {
    "black":       ['black'],
    "darkred":     ['red'],
    "darkgreen":   ['green'],
    "brown":       ['yellow'],
    "darkyellow":  ['yellow'],
    "darkblue":    ['blue'],
    "purple":      ['magenta'],
    "darkmagenta": ['magenta'],
    "teal":        ['cyan'],
    "darkcyan":    ['cyan'],
    "lightgray":   ['white'],
    "darkgray":    ['bold', 'black'],
    "red":         ['bold', 'red'],
    "green":       ['bold', 'green'],
    "yellow":      ['bold', 'yellow'],
    "blue":        ['bold', 'blue'],
    "fuchsia":     ['bold', 'magenta'],
    "magenta":     ['bold', 'magenta'],
    "turquoise":   ['bold', 'cyan'],
    "cyan":        ['bold', 'cyan'],
    "white":       ['bold', 'white']
}
# All ANSI Colors.
ANSI_CODES = {
    # Styles.
    "normal":       0,
    "bold":         1,
    "faint":        2,
    #"italic":       3,
    "underline":    4,
    #"blink_slow":   5,
    #"blink_rapid":  6,
    "inverse":      7,
    #"conceal":      8,
    #"crossed_out":  9
    # Text colors.
    "black":       30,
    "red":         31,
    "green":       32,
    "yellow":      33,
    "blue":        34,
    "magenta":     35,
    "cyan":        36,
    "white":       37,
    # Background colors.
    "bg_black":    40,
    "bg_red":      41,
    "bg_green":    42,
    "bg_yellow":   43,
    "bg_blue":     44,
    "bg_magenta":  45,
    "bg_cyan":     46,
    "bg_white":    47
}
RESET_COLOR = COLOR_ESCAPE + "39;49;00m"

# These abstract COLOR_NAMES are lazily mapped on to the actual color in COLORS
# as they are defined in the configuration files, see function: colorize
COLOR_NAMES = ['text_success', 'text_warning', 'text_error', 'text_highlight',
               'text_highlight_minor', 'action_default', 'action',
               # New Colors
               'text', 'text_faint',
               'import_path', 'import_path_items',
               'action_description',
               'added', 'removed', 'changed',
               'added_highlight', 'removed_highlight', 'changed_highlight',
               'text_diff_added', 'text_diff_removed', 'text_diff_changed']
COLORS = None


def _colorize(color, text):
    """Returns a string that prints the given text in the given color
    in a terminal that is ANSI color-aware. The color must be a list of strings
    out of ANSI_CODES.
    """
    # Construct escape sequence to be put before the text by iterating
    # over all "ANSI codes" in `color`.
    escape = ""
    for code in color:
        if code in ANSI_CODES.keys():
            escape = escape + COLOR_ESCAPE + "%im" % ANSI_CODES[code]
        else:
            raise ValueError('no such ANSI code %s', code)
    return escape + text + RESET_COLOR


def colorize(color_name, text):
    """Colorize text if colored output is enabled. (Like _colorize but
    conditional.)
    """
    if config['ui']['color']:
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
                    color_def = config['ui']['colors'][name].get(unicode)
                except (confuse.ConfigTypeError, NameError):
                    # Normal color definition (type: list of unicode).
                    color_def = config['ui']['colors'][name].get(list)
                else:
                    # Legacy color definition (type: unicode). Convert.
                    if color_def in LEGACY_COLORS:
                        color_def = LEGACY_COLORS[color_def]
                    else:
                        raise ValueError('no such color %s', color)

                COLORS[name] = color_def
        # In case a 3rd party plugin is still passing the actual color ('red')
        # instead of the abstract color name ('text_error')
        color = COLORS.get(color_name)
        if not color:
            log.debug(u'Invalid color_name: {0}', color_name)
            color = color_name
        return _colorize(color, text)
    else:
        return text


def uncolorize(colored_text):
    """Remove colors from a string.
    """
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
    text = ansi_code_regex.sub(u'', colored_text)
    return text


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
    # Set highlight colors.
    highlight_added = 'text_diff_added'
    highlight_removed = 'text_diff_removed'
    minor_highlight = 'text_highlight_minor'

    if not isinstance(a, six.string_types) or not isinstance(b, six.string_types):
        # Non-strings: use ordinary equality.
        a = six.text_type(a)
        b = six.text_type(b)
        if a == b:
            return a, b
        else:
            return colorize(highlight_removed, a), colorize(highlight_added, b)

    if isinstance(a, bytes) or isinstance(b, bytes):
        # A path field.
        a = util.displayable_path(a)
        b = util.displayable_path(b)

    a_out = []
    b_out = []

    add_mapper    = lambda w: w if re.match('(\s)', w) else colorize(highlight_added, w)
    remove_mapper = lambda w: w if re.match('(\s)', w) else colorize(highlight_removed, w)
    minor_mapper  = lambda w: w if re.match('(\s)', w) else colorize(minor_highlight, w)

    matcher = SequenceMatcher(lambda x: False, a, b)
    for op, a_start, a_end, b_start, b_end in matcher.get_opcodes():
        if op == 'equal':
            # In both strings.
            a_out.append(a[a_start:a_end])
            b_out.append(b[b_start:b_end])
        elif op == 'insert':
            # Right only.
            words = re.split('(\s)', b[b_start:b_end])
            words_colorized = map(add_mapper, words)
            b_out.append(''.join(words_colorized))
        elif op == 'delete':
            # Left only.
            words = re.split('(\s)', a[a_start:a_end])
            words_colorized = map(remove_mapper, words)
            a_out.append(''.join(words_colorized))
        elif op == 'replace':
            # Right and left differ. Colorise with second highlight if
            # it's just a case change.
            words_a = re.split('(\s)', a[a_start:a_end])
            words_b = re.split('(\s)', b[b_start:b_end])
            if a[a_start:a_end].lower() != b[b_start:b_end].lower():
                words_a_colorized = map(remove_mapper, words_a)
                words_b_colorized = map(add_mapper, words_b)
            else:
                words_a_colorized = map(minor_mapper, words_a)
                words_b_colorized = map(minor_mapper, words_b)
            a_out.append(''.join(words_a_colorized))
            b_out.append(''.join(words_b_colorized))
        else:
            assert(False)

    return u''.join(a_out), u''.join(b_out)


def colordiff(a, b):
    """Colorize differences between two values if color is enabled.
    (Like _colordiff but conditional.)
    """
    if config['ui']['color']:
        return _colordiff(a, b)
    else:
        return six.text_type(a), six.text_type(b)


def get_path_formats(subview=None):
    """Get the configuration's path formats as a list of query/template
    pairs.
    """
    path_formats = []
    subview = subview or config['paths']
    for query, view in subview.items():
        query = PF_KEY_QUERIES.get(query, query)  # Expand common queries.
        path_formats.append((query, template(view.as_str())))
    return path_formats


def get_replacements():
    """Confuse validation function that reads regex/string pairs.
    """
    replacements = []
    for pattern, repl in config['replace'].get(dict).items():
        repl = repl or ''
        try:
            replacements.append((re.compile(pattern), repl))
        except re.error:
            raise UserError(
                u'malformed regular expression in replace: {0}'.format(
                    pattern
                )
            )
    return replacements


def term_width():
    """Get the width (columns) of the terminal."""
    fallback = config['ui']['terminal_width'].get(int)

    # The fcntl and termios modules are not available on non-Unix
    # platforms, so we fall back to a constant.
    try:
        import fcntl
        import termios
    except ImportError:
        return fallback

    try:
        buf = fcntl.ioctl(0, termios.TIOCGWINSZ, ' ' * 4)
    except IOError:
        return fallback
    try:
        height, width = struct.unpack('hh', buf)
    except struct.error:
        return fallback
    return width


def split_into_lines(string, raw_string, width_tuple):
    """Splits string into a list of substrings at whitespace.

    `width_tuple` is a 3-tuple of `(first_width, last_width, middle_width)`.
    The first substring has a length not longer than `first_width`, the last
    substring has a length not longer than `last_width`, and all other
    substrings have a length not longer than `middle_width`.

    `raw_string` and `string` are two strings that contain the same words,
    but `string` may contain ANSI codes at word borders. Use `raw_string`
    to find substrings, but return the words in `string`.
    """
    first_width, middle_width, last_width = width_tuple

    words_raw = raw_string.split()
    words     = string.split()
    assert len(words_raw) == len(words)
    result = { 'col': [], 'raw': [] }
    next_substr_raw = u''
    next_substr     = u''

    # Iterate over all words.
    for i in range(len(words_raw)):
        if i == 0:
            pot_substr_raw = words_raw[i]
            pot_substr     = words[i]
        else:
            pot_substr_raw = ' '.join([next_substr_raw, words_raw[i]])
            pot_substr     = ' '.join([next_substr,     words[i]])

        # Find out if the pot(ential)_substr fits into the next substring.
        fits_first = \
            (len(result['raw']) == 0 and len(pot_substr_raw) <= first_width)
        fits_middle = \
            (len(result['raw']) != 0 and len(pot_substr_raw) <= middle_width)
        if fits_first or fits_middle:
            next_substr_raw = pot_substr_raw
            next_substr     = pot_substr
        else:
            result['raw'].append(next_substr_raw)
            result['col'].append(next_substr)
            next_substr_raw = words_raw[i]
            next_substr     = words[i]

    # We finished constructing the substrings, but the last substring
    # has not yet been added to the result.
    result['raw'].append(next_substr_raw)
    result['col'].append(next_substr)

    # Also, the length of the last substring was only checked against
    # `middle_width`. Append an empty substring as the new last substring if
    # the last substring is too long.
    if not len(next_substr_raw) <= last_width:
        result['raw'].append(u'')
        result['col'].append(u'')

    return result


FLOAT_EPSILON = 0.01


def _field_diff(field, old, new):
    """Given two Model objects, format their values for `field` and
    highlight changes among them. Return a human-readable string. If the
    value has not changed, return None instead.
    """
    oldval = old.get(field)
    newval = new.get(field)

    # If no change, abort.
    if isinstance(oldval, float) and isinstance(newval, float) and \
            abs(oldval - newval) < FLOAT_EPSILON:
        return None
    elif oldval == newval:
        return None

    # Get formatted values for output.
    oldstr = old.formatted().get(field, u'')
    newstr = new.formatted().get(field, u'')

    # For strings, highlight changes. For others, colorize the whole
    # thing.
    if isinstance(oldval, six.string_types):
        oldstr, newstr = colordiff(oldval, newstr)
    else:
        oldstr = colorize('text_error', oldstr)
        newstr = colorize('text_error', newstr)

    return u'{0} -> {1}'.format(oldstr, newstr)


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

    # Build up lines showing changed fields.
    changes = []
    for field in old:
        # Subset of the fields. Never show mtime.
        if field == 'mtime' or (fields and field not in fields):
            continue

        # Detect and show difference for this field.
        line = _field_diff(field, old, new)
        if line:
            changes.append(u'  {0}: {1}'.format(field, line))

    # New fields.
    for field in set(new) - set(old):
        if fields and field not in fields:
            continue

        changes.append(u'  {0}: {1}'.format(
            field,
            colorize('text_highlight', new.formatted()[field])
        ))

    # Print changes.
    if changes or always:
        print_(format(old))
    if changes:
        print_(u'\n'.join(changes))

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
    col_width = (term_width() - len(' -> ')) // 2
    max_width = len(max(sources + destinations, key=len))

    if max_width > col_width:
        # Print every change over two lines
        for source, dest in zip(sources, destinations):
            log.info(u'{0} \n  -> {1}', source, dest)
    else:
        # Print every change on a single line, and add a header
        title_pad = max_width - len('Source ') + len(' -> ')

        log.info(u'Source {0} Destination', ' ' * title_pad)
        for source, dest in zip(sources, destinations):
            pad = max_width - len(source)
            log.info(u'{0} {1} -> {2}', source, ' ' * pad, dest)


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
        setattr(parser.values, dest, dict())
        option_values = getattr(parser.values, dest)

    try:
        key, value = map(lambda s: util.text_string(s), value.split('='))
        if not (key and value):
            raise ValueError
    except ValueError:
        raise UserError(
            "supplied argument `{0}' is not of the form `key=value'"
            .format(value))

    option_values[key] = value


class CommonOptionsParser(optparse.OptionParser, object):
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
        super(CommonOptionsParser, self).__init__(*args, **kwargs)
        self._album_flags = False
        # this serves both as an indicator that we offer the feature AND allows
        # us to check whether it has been specified on the CLI - bypassing the
        # fact that arguments may be in any order

    def add_album_option(self, flags=('-a', '--album')):
        """Add a -a/--album option to match albums instead of tracks.

        If used then the format option can auto-detect whether we're setting
        the format for items or albums.
        Sets the album property on the options extracted from the CLI.
        """
        album = optparse.Option(*flags, action='store_true',
                                help=u'match albums instead of tracks')
        self.add_option(album)
        self._album_flags = set(flags)

    def _set_format(self, option, opt_str, value, parser, target=None,
                    fmt=None, store_true=False):
        """Internal callback that sets the correct format while parsing CLI
        arguments.
        """
        if store_true:
            setattr(parser.values, option.dest, True)

        # Use the explicitly specified format, or the string from the option.
        if fmt:
            value = fmt
        elif value:
            value, = decargs([value])
        else:
            value = u''

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

    def add_path_option(self, flags=('-p', '--path')):
        """Add a -p/--path option to display the path instead of the default
        format.

        By default this affects both items and albums. If add_album_option()
        is used then the target will be autodetected.

        Sets the format property to u'$path' on the options extracted from the
        CLI.
        """
        path = optparse.Option(*flags, nargs=0, action='callback',
                               callback=self._set_format,
                               callback_kwargs={'fmt': u'$path',
                                                'store_true': True},
                               help=u'print paths for matched items or albums')
        self.add_option(path)

    def add_format_option(self, flags=('-f', '--format'), target=None):
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
            if isinstance(target, six.string_types):
                target = {'item': library.Item,
                          'album': library.Album}[target]
            kwargs['target'] = target

        opt = optparse.Option(*flags, action='callback',
                              callback=self._set_format,
                              callback_kwargs=kwargs,
                              help=u'print with custom format')
        self.add_option(opt)

    def add_all_common_options(self):
        """Add album, path and format options.
        """
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

class Subcommand(object):
    """A subcommand of a root command-line application that may be
    invoked by a SubcommandOptionParser.
    """
    def __init__(self, name, parser=None, help='', aliases=(), hide=False):
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
        self.parser.prog = '{0} {1}'.format(
            as_string(root_parser.get_prog_name()), self.name)


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
        if 'usage' not in kwargs:
            kwargs['usage'] = u"""
  %prog COMMAND [ARGS...]
  %prog help COMMAND"""
        kwargs['add_help_option'] = False

        # Super constructor.
        super(SubcommandsOptionParser, self).__init__(*args, **kwargs)

        # Our root parser needs to stop on the first unrecognized argument.
        self.disable_interspersed_args()

        self.subcommands = []

    def add_subcommand(self, *cmds):
        """Adds a Subcommand object to the parser's list of commands.
        """
        for cmd in cmds:
            cmd.root_parser = self
            self.subcommands.append(cmd)

    # Add the list of subcommands to the help message.
    def format_help(self, formatter=None):
        # Get the original help message, to which we will append.
        out = super(SubcommandsOptionParser, self).format_help(formatter)
        if formatter is None:
            formatter = self.formatter

        # Subcommands header.
        result = ["\n"]
        result.append(formatter.format_heading('Commands'))
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
                name += ' (%s)' % ', '.join(subcommand.aliases)
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
                name = "%*s%-*s  " % (formatter.current_indent, "",
                                      name_width, name)
                indent_first = 0
            result.append(name)
            help_width = formatter.width - help_position
            help_lines = textwrap.wrap(subcommand.help, help_width)
            help_line = help_lines[0] if help_lines else ''
            result.append("%*s%s\n" % (indent_first, "", help_line))
            result.extend(["%*s%s\n" % (help_position, "", line)
                           for line in help_lines[1:]])
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
            if name == subcommand.name or \
               name in subcommand.aliases:
                return subcommand
        return None

    def parse_global_options(self, args):
        """Parse options up to the subcommand argument. Returns a tuple
        of the options object and the remaining arguments.
        """
        options, subargs = self.parse_args(args)

        # Force the help command
        if options.help:
            subargs = ['help']
        elif options.version:
            subargs = ['version']
        return options, subargs

    def parse_subcommand(self, args):
        """Given the `args` left unused by a `parse_global_options`,
        return the invoked subcommand, the subcommand options, and the
        subcommand arguments.
        """
        # Help is default command
        if not args:
            args = ['help']

        cmdname = args.pop(0)
        subcommand = self._subcommand_for_name(cmdname)
        if not subcommand:
            raise UserError(u"unknown command '{0}'".format(cmdname))

        suboptions, subargs = subcommand.parse_args(args)
        return subcommand, suboptions, subargs


optparse.Option.ALWAYS_TYPED_ACTIONS += ('callback',)


# The main entry point and bootstrapping.

def _load_plugins(config):
    """Load the plugins specified in the configuration.
    """
    paths = config['pluginpath'].as_str_seq(split=False)
    paths = [util.normpath(p) for p in paths]
    log.debug(u'plugin paths: {0}', util.displayable_path(paths))

    # On Python 3, the search paths need to be unicode.
    paths = [util.py3_path(p) for p in paths]

    # Extend the `beetsplug` package to include the plugin paths.
    import beetsplug
    beetsplug.__path__ = paths + beetsplug.__path__

    # For backwards compatibility, also support plugin paths that
    # *contain* a `beetsplug` package.
    sys.path += paths

    plugins.load_plugins(config['plugins'].as_str_seq())
    plugins.send("pluginload")
    return plugins


def _setup(options, lib=None):
    """Prepare and global state and updates it with command line options.

    Returns a list of subcommands, a list of plugins, and a library instance.
    """
    # Configure the MusicBrainz API.
    mb.configure()

    config = _configure(options)

    plugins = _load_plugins(config)

    # Get the default subcommands.
    from beets.ui.commands import default_commands

    subcommands = list(default_commands)
    subcommands.extend(plugins.commands())

    if lib is None:
        lib = _open_library(config)
        plugins.send("library_opened", lib=lib)

    # Add types and queries defined by plugins.
    library.Item._types.update(plugins.types(library.Item))
    library.Album._types.update(plugins.types(library.Album))
    library.Item._queries.update(plugins.named_queries(library.Item))
    library.Album._queries.update(plugins.named_queries(library.Album))

    return subcommands, plugins, lib


def _configure(options):
    """Amend the global configuration object with command line options.
    """
    # Add any additional config files specified with --config. This
    # special handling lets specified plugins get loaded before we
    # finish parsing the command line.
    if getattr(options, 'config', None) is not None:
        overlay_path = options.config
        del options.config
        config.set_file(overlay_path)
    else:
        overlay_path = None
    config.set_args(options)

    # Configure the logger.
    if config['verbose'].get(int):
        log.set_global_level(logging.DEBUG)
    else:
        log.set_global_level(logging.INFO)

    if overlay_path:
        log.debug(u'overlaying configuration: {0}',
                  util.displayable_path(overlay_path))

    config_path = config.user_config_path()
    if os.path.isfile(config_path):
        log.debug(u'user configuration: {0}',
                  util.displayable_path(config_path))
    else:
        log.debug(u'no user configuration found at {0}',
                  util.displayable_path(config_path))

    log.debug(u'data directory: {0}',
              util.displayable_path(config.config_dir()))
    return config


def _open_library(config):
    """Create a new library instance from the configuration.
    """
    dbpath = util.bytestring_path(config['library'].as_filename())
    try:
        lib = library.Library(
            dbpath,
            config['directory'].as_filename(),
            get_path_formats(),
            get_replacements(),
        )
        lib.get_item(0)  # Test database connection.
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as db_error:
        log.debug(u'{}', traceback.format_exc())
        raise UserError(u"database file {0} cannot not be opened: {1}".format(
            util.displayable_path(dbpath),
            db_error
        ))
    log.debug(u'library database: {0}\n'
              u'library directory: {1}',
              util.displayable_path(lib.path),
              util.displayable_path(lib.directory))
    return lib


def _raw_main(args, lib=None):
    """A helper function for `main` without top-level exception
    handling.
    """
    parser = SubcommandsOptionParser()
    parser.add_format_option(flags=('--format-item',), target=library.Item)
    parser.add_format_option(flags=('--format-album',), target=library.Album)
    parser.add_option('-l', '--library', dest='library',
                      help=u'library database file to use')
    parser.add_option('-d', '--directory', dest='directory',
                      help=u"destination music directory")
    parser.add_option('-v', '--verbose', dest='verbose', action='count',
                      help=u'log more details (use twice for even more)')
    parser.add_option('-c', '--config', dest='config',
                      help=u'path to configuration file')
    parser.add_option('-h', '--help', dest='help', action='store_true',
                      help=u'show this help message and exit')
    parser.add_option('--version', dest='version', action='store_true',
                      help=optparse.SUPPRESS_HELP)

    options, subargs = parser.parse_global_options(args)

    # Special case for the `config --edit` command: bypass _setup so
    # that an invalid configuration does not prevent the editor from
    # starting.
    if subargs and subargs[0] == 'config' \
       and ('-e' in subargs or '--edit' in subargs):
        from beets.ui.commands import config_edit
        return config_edit()

    test_lib = bool(lib)
    subcommands, plugins, lib = _setup(options, lib)
    parser.add_subcommand(*subcommands)

    subcommand, suboptions, subargs = parser.parse_subcommand(subargs)
    subcommand.func(lib, suboptions, subargs)

    plugins.send('cli_exit', lib=lib)
    if not test_lib:
        # Clean up the library unless it came from the test harness.
        lib._close()


def main(args=None):
    """Run the main command-line interface for beets. Includes top-level
    exception handlers that print friendly error messages.
    """
    try:
        _raw_main(args)
    except UserError as exc:
        message = exc.args[0] if exc.args else None
        log.error(u'error: {0}', message)
        sys.exit(1)
    except util.HumanReadableException as exc:
        exc.log(log)
        sys.exit(1)
    except library.FileOperationError as exc:
        # These errors have reasonable human-readable descriptions, but
        # we still want to log their tracebacks for debugging.
        log.debug('{}', traceback.format_exc())
        log.error('{}', exc)
        sys.exit(1)
    except confuse.ConfigError as exc:
        log.error(u'configuration error: {0}', exc)
        sys.exit(1)
    except db_query.InvalidQueryError as exc:
        log.error(u'invalid query: {0}', exc)
        sys.exit(1)
    except IOError as exc:
        if exc.errno == errno.EPIPE:
            # "Broken pipe". End silently.
            sys.stderr.close()
        else:
            raise
    except KeyboardInterrupt:
        # Silently ignore ^C except in verbose mode.
        log.debug(u'{}', traceback.format_exc())
    except db.DBAccessError as exc:
        log.error(
            u'database access error: {0}\n'
            u'the library file might have a permissions problem',
            exc
        )
        sys.exit(1)
