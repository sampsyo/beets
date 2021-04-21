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

"""Miscellaneous utility functions."""

from __future__ import division, absolute_import, print_function
import os
import sys
import errno
import locale
import re
import shutil
import fnmatch
import functools
from collections import Counter, namedtuple
from multiprocessing.pool import ThreadPool
import traceback
import subprocess
import platform
import shlex
import six
from unidecode import unidecode
from enum import Enum

# This whole block can be removed once Python <3.3 support is dropped
try:
    from shutil import which
except ImportError:
    from distutils.spawn import find_executable as which

from beets import config
from beets.util import hidden


MAX_FILENAME_LENGTH = 200
WINDOWS_MAGIC_PREFIX = u'\\\\?\\'
SNI_SUPPORTED = sys.version_info >= (2, 7, 9)


class HumanReadableException(Exception):
    """An Exception that can include a human-readable error message to
    be logged without a traceback. Can preserve a traceback for
    debugging purposes as well.

    Has at least two fields: `reason`, the underlying exception or a
    string describing the problem; and `verb`, the action being
    performed during the error.

    If `tb` is provided, it is a string containing a traceback for the
    associated exception. (Note that this is not necessary in Python 3.x
    and should be removed when we make the transition.)
    """
    error_kind = 'Error'  # Human-readable description of error type.

    def __init__(self, reason, verb, tb=None):
        self.reason = reason
        self.verb = verb
        self.tb = tb
        super(HumanReadableException, self).__init__(self.get_message())

    def _gerund(self):
        """Generate a (likely) gerund form of the English verb.
        """
        if u' ' in self.verb:
            return self.verb
        gerund = self.verb[:-1] if self.verb.endswith(u'e') else self.verb
        gerund += u'ing'
        return gerund

    def _reasonstr(self):
        """Get the reason as a string."""
        if isinstance(self.reason, six.text_type):
            return self.reason
        elif isinstance(self.reason, bytes):
            return self.reason.decode('utf-8', 'ignore')
        elif hasattr(self.reason, 'strerror'):  # i.e., EnvironmentError
            return self.reason.strerror
        else:
            return u'"{0}"'.format(six.text_type(self.reason))

    def get_message(self):
        """Create the human-readable description of the error, sans
        introduction.
        """
        raise NotImplementedError

    def log(self, logger):
        """Log to the provided `logger` a human-readable message as an
        error and a verbose traceback as a debug message.
        """
        if self.tb:
            logger.debug(self.tb)
        logger.error(u'{0}: {1}', self.error_kind, self.args[0])


class FilesystemError(HumanReadableException):
    """An error that occurred while performing a filesystem manipulation
    via a function in this module. The `paths` field is a sequence of
    pathnames involved in the operation.
    """
    def __init__(self, reason, verb, paths, tb=None):
        self.paths = paths
        super(FilesystemError, self).__init__(reason, verb, tb)

    def get_message(self):
        # Use a nicer English phrasing for some specific verbs.
        if self.verb in ('move', 'copy', 'rename'):
            clause = u'while {0} {1} to {2}'.format(
                self._gerund(),
                displayable_path(self.paths[0]),
                displayable_path(self.paths[1])
            )
        elif self.verb in ('delete', 'write', 'create', 'read'):
            clause = u'while {0} {1}'.format(
                self._gerund(),
                displayable_path(self.paths[0])
            )
        else:
            clause = u'during {0} of paths {1}'.format(
                self.verb, u', '.join(displayable_path(p) for p in self.paths)
            )

        return u'{0} {1}'.format(self._reasonstr(), clause)


class MoveOperation(Enum):
    """The file operations that e.g. various move functions can carry out.
    """
    MOVE = 0
    COPY = 1
    LINK = 2
    HARDLINK = 3
    REFLINK = 4
    REFLINK_AUTO = 5


def normpath(path):
    """Provide the canonical form of the path suitable for storing in
    the database.
    """
    path = syspath(path, prefix=False)
    path = os.path.normpath(os.path.abspath(os.path.expanduser(path)))
    return bytestring_path(path)


def ancestry(path):
    """Return a list consisting of path's parent directory, its
    grandparent, and so on. For instance:

       >>> ancestry('/a/b/c')
       ['/', '/a', '/a/b']

    The argument should *not* be the result of a call to `syspath`.
    """
    out = []
    last_path = None
    while path:
        path = os.path.dirname(path)

        if path == last_path:
            break
        last_path = path

        if path:
            # don't yield ''
            out.insert(0, path)
    return out


def sorted_walk(path, ignore=(), ignore_hidden=False, logger=None):
    """Like `os.walk`, but yields things in case-insensitive sorted,
    breadth-first order.  Directory and file names matching any glob
    pattern in `ignore` are skipped. If `logger` is provided, then
    warning messages are logged there when a directory cannot be listed.
    """
    # Make sure the pathes aren't Unicode strings.
    path = bytestring_path(path)
    ignore = [bytestring_path(i) for i in ignore]

    # Get all the directories and files at this level.
    try:
        contents = os.listdir(syspath(path))
    except OSError as exc:
        if logger:
            logger.warning(u'could not list directory {0}: {1}'.format(
                displayable_path(path), exc.strerror
            ))
        return
    dirs = []
    files = []
    for base in contents:
        base = bytestring_path(base)

        # Skip ignored filenames.
        skip = False
        for pat in ignore:
            if fnmatch.fnmatch(base, pat):
                if logger:
                    logger.debug(u'ignoring {0} due to ignore rule {1}'.format(
                        base, pat
                    ))
                skip = True
                break
        if skip:
            continue

        # Add to output as either a file or a directory.
        cur = os.path.join(path, base)
        if (ignore_hidden and not hidden.is_hidden(cur)) or not ignore_hidden:
            if os.path.isdir(syspath(cur)):
                dirs.append(base)
            else:
                files.append(base)

    # Sort lists (case-insensitive) and yield the current level.
    dirs.sort(key=bytes.lower)
    files.sort(key=bytes.lower)
    yield (path, dirs, files)

    # Recurse into directories.
    for base in dirs:
        cur = os.path.join(path, base)
        # yield from sorted_walk(...)
        for res in sorted_walk(cur, ignore, ignore_hidden, logger):
            yield res


def path_as_posix(path):
    """Return the string representation of the path with forward (/)
    slashes.
    """
    return path.replace(b'\\', b'/')


def mkdirall(path):
    """Make all the enclosing directories of path (like mkdir -p on the
    parent).
    """
    for ancestor in ancestry(path):
        if not os.path.isdir(syspath(ancestor)):
            try:
                os.mkdir(syspath(ancestor))
            except (OSError, IOError) as exc:
                raise FilesystemError(exc, 'create', (ancestor,),
                                      traceback.format_exc())


def fnmatch_all(names, patterns):
    """Determine whether all strings in `names` match at least one of
    the `patterns`, which should be shell glob expressions.
    """
    for name in names:
        matches = False
        for pattern in patterns:
            matches = fnmatch.fnmatch(name, pattern)
            if matches:
                break
        if not matches:
            return False
    return True


def prune_dirs(path, root=None, clutter=('.DS_Store', 'Thumbs.db')):
    """If path is an empty directory, then remove it. Recursively remove
    path's ancestry up to root (which is never removed) where there are
    empty directories. If path is not contained in root, then nothing is
    removed. Glob patterns in clutter are ignored when determining
    emptiness. If root is not provided, then only path may be removed
    (i.e., no recursive removal).
    """
    path = normpath(path)
    if root is not None:
        root = normpath(root)

    ancestors = ancestry(path)
    if root is None:
        # Only remove the top directory.
        ancestors = []
    elif root in ancestors:
        # Only remove directories below the root.
        ancestors = ancestors[ancestors.index(root) + 1:]
    else:
        # Remove nothing.
        return

    # Traverse upward from path.
    ancestors.append(path)
    ancestors.reverse()
    for directory in ancestors:
        directory = syspath(directory)
        if not os.path.exists(directory):
            # Directory gone already.
            continue
        clutter = [bytestring_path(c) for c in clutter]
        match_paths = [bytestring_path(d) for d in os.listdir(directory)]
        try:
            if fnmatch_all(match_paths, clutter):
                # Directory contains only clutter (or nothing).
                shutil.rmtree(directory)
            else:
                break
        except OSError:
            break


def components(path):
    """Return a list of the path components in path. For instance:

       >>> components('/a/b/c')
       ['a', 'b', 'c']

    The argument should *not* be the result of a call to `syspath`.
    """
    comps = []
    ances = ancestry(path)
    for anc in ances:
        comp = os.path.basename(anc)
        if comp:
            comps.append(comp)
        else:  # root
            comps.append(anc)

    last = os.path.basename(path)
    if last:
        comps.append(last)

    return comps


def arg_encoding():
    """Get the encoding for command-line arguments (and other OS
    locale-sensitive strings).
    """
    try:
        return locale.getdefaultlocale()[1] or 'utf-8'
    except ValueError:
        # Invalid locale environment variable setting. To avoid
        # failing entirely for no good reason, assume UTF-8.
        return 'utf-8'


def _fsencoding():
    """Get the system's filesystem encoding. On Windows, this is always
    UTF-8 (not MBCS).
    """
    encoding = sys.getfilesystemencoding() or sys.getdefaultencoding()
    if encoding == 'mbcs':
        # On Windows, a broken encoding known to Python as "MBCS" is
        # used for the filesystem. However, we only use the Unicode API
        # for Windows paths, so the encoding is actually immaterial so
        # we can avoid dealing with this nastiness. We arbitrarily
        # choose UTF-8.
        encoding = 'utf-8'
    return encoding


def bytestring_path(path):
    """Given a path, which is either a bytes or a unicode, returns a str
    path (ensuring that we never deal with Unicode pathnames).
    """
    # Pass through bytestrings.
    if isinstance(path, bytes):
        return path

    # On Windows, remove the magic prefix added by `syspath`. This makes
    # ``bytestring_path(syspath(X)) == X``, i.e., we can safely
    # round-trip through `syspath`.
    if os.path.__name__ == 'ntpath' and path.startswith(WINDOWS_MAGIC_PREFIX):
        path = path[len(WINDOWS_MAGIC_PREFIX):]

    # Try to encode with default encodings, but fall back to utf-8.
    try:
        return path.encode(_fsencoding())
    except (UnicodeError, LookupError):
        return path.encode('utf-8')


PATH_SEP = bytestring_path(os.sep)


def displayable_path(path, separator=u'; '):
    """Attempts to decode a bytestring path to a unicode object for the
    purpose of displaying it to the user. If the `path` argument is a
    list or a tuple, the elements are joined with `separator`.
    """
    if isinstance(path, (list, tuple)):
        return separator.join(displayable_path(p) for p in path)
    elif isinstance(path, six.text_type):
        return path
    elif not isinstance(path, bytes):
        # A non-string object: just get its unicode representation.
        return six.text_type(path)

    try:
        return path.decode(_fsencoding(), 'ignore')
    except (UnicodeError, LookupError):
        return path.decode('utf-8', 'ignore')


def syspath(path, prefix=True):
    """Convert a path for use by the operating system. In particular,
    paths on Windows must receive a magic prefix and must be converted
    to Unicode before they are sent to the OS. To disable the magic
    prefix on Windows, set `prefix` to False---but only do this if you
    *really* know what you're doing.
    """
    # Don't do anything if we're not on windows
    if os.path.__name__ != 'ntpath':
        return path

    if not isinstance(path, six.text_type):
        # Beets currently represents Windows paths internally with UTF-8
        # arbitrarily. But earlier versions used MBCS because it is
        # reported as the FS encoding by Windows. Try both.
        try:
            path = path.decode('utf-8')
        except UnicodeError:
            # The encoding should always be MBCS, Windows' broken
            # Unicode representation.
            encoding = sys.getfilesystemencoding() or sys.getdefaultencoding()
            path = path.decode(encoding, 'replace')

    # Add the magic prefix if it isn't already there.
    # https://msdn.microsoft.com/en-us/library/windows/desktop/aa365247.aspx
    if prefix and not path.startswith(WINDOWS_MAGIC_PREFIX):
        if path.startswith(u'\\\\'):
            # UNC path. Final path should look like \\?\UNC\...
            path = u'UNC' + path[1:]
        path = WINDOWS_MAGIC_PREFIX + path

    return path


def samefile(p1, p2):
    """Safer equality for paths."""
    if p1 == p2:
        return True
    return shutil._samefile(syspath(p1), syspath(p2))


def remove(path, soft=True, use_trash=True):
    """Remove the file specified at `path`, using `trash` executable by default
    (if found) or via the command specified in the `remove_command` setting if
    found on $PATH. Otherwise, delete the file immediately. If `soft`, then no
    error will be raised if the file does not exist.
    """
    path = syspath(path)
    if soft and not os.path.exists(path):
        return
    # If `use_trash` is invoked and the `remove_command` configuration setting
    # (which defaults to `trash`) is found on $PATH, use that command to remove
    # the specified file. Otherwise, delete it immediately.
    # Change which() to shutil.which() once Python <3.3 support is dropped
    remove_command = config["remove_command"].as_str()
    if use_trash and which(remove_command) is not None:
        try:
            command_output([remove_command, path])
        except (ValueError, OSError, subprocess.CalledProcessError) as exc:
            raise FilesystemError(
                exc, 'delete', (path,), traceback.format_exc()
            )
    else:
        try:
            os.remove(path)
        except (OSError, IOError) as exc:
            raise FilesystemError(
                exc, 'delete', (path,), traceback.format_exc()
            )


def copy(path, dest, replace=False):
    """Copy a plain file. Permissions are not copied. If `dest` already
    exists, raises a FilesystemError unless `replace` is True. Has no
    effect if `path` is the same as `dest`. Paths are translated to
    system paths before the syscall.
    """
    if samefile(path, dest):
        return
    path = syspath(path)
    dest = syspath(dest)
    if not replace and os.path.exists(dest):
        raise FilesystemError(u'file exists', 'copy', (path, dest))
    try:
        shutil.copyfile(path, dest)
    except (OSError, IOError) as exc:
        raise FilesystemError(exc, 'copy', (path, dest),
                              traceback.format_exc())


def move(path, dest, replace=False):
    """Rename a file. `dest` may not be a directory. If `dest` already
    exists, raises an OSError unless `replace` is True. Has no effect if
    `path` is the same as `dest`. If the paths are on different
    filesystems (or the rename otherwise fails), a copy is attempted
    instead, in which case metadata will *not* be preserved. Paths are
    translated to system paths.
    """
    if samefile(path, dest):
        return
    path = syspath(path)
    dest = syspath(dest)
    if os.path.exists(dest) and not replace:
        raise FilesystemError(u'file exists', 'rename', (path, dest))

    # First, try renaming the file.
    try:
        os.rename(path, dest)
    except OSError:
        # Otherwise, copy and delete the original.
        try:
            shutil.copyfile(path, dest)
            os.remove(path)
        except (OSError, IOError) as exc:
            raise FilesystemError(exc, 'move', (path, dest),
                                  traceback.format_exc())


def link(path, dest, replace=False):
    """Create a symbolic link from path to `dest`. Raises an OSError if
    `dest` already exists, unless `replace` is True. Does nothing if
    `path` == `dest`.
    """
    if samefile(path, dest):
        return

    if os.path.exists(syspath(dest)) and not replace:
        raise FilesystemError(u'file exists', 'rename', (path, dest))
    try:
        os.symlink(syspath(path), syspath(dest))
    except NotImplementedError:
        # raised on python >= 3.2 and Windows versions before Vista
        raise FilesystemError(u'OS does not support symbolic links.'
                              'link', (path, dest), traceback.format_exc())
    except OSError as exc:
        # TODO: Windows version checks can be removed for python 3
        if hasattr('sys', 'getwindowsversion'):
            if sys.getwindowsversion()[0] < 6:  # is before Vista
                exc = u'OS does not support symbolic links.'
        raise FilesystemError(exc, 'link', (path, dest),
                              traceback.format_exc())


def hardlink(path, dest, replace=False):
    """Create a hard link from path to `dest`. Raises an OSError if
    `dest` already exists, unless `replace` is True. Does nothing if
    `path` == `dest`.
    """
    if samefile(path, dest):
        return

    if os.path.exists(syspath(dest)) and not replace:
        raise FilesystemError(u'file exists', 'rename', (path, dest))
    try:
        os.link(syspath(path), syspath(dest))
    except NotImplementedError:
        raise FilesystemError(u'OS does not support hard links.'
                              'link', (path, dest), traceback.format_exc())
    except OSError as exc:
        if exc.errno == errno.EXDEV:
            raise FilesystemError(u'Cannot hard link across devices.'
                                  'link', (path, dest), traceback.format_exc())
        else:
            raise FilesystemError(exc, 'link', (path, dest),
                                  traceback.format_exc())


def reflink(path, dest, replace=False, fallback=False):
    """Create a reflink from `dest` to `path`.

    Raise an `OSError` if `dest` already exists, unless `replace` is
    True. If `path` == `dest`, then do nothing.

    If reflinking fails and `fallback` is enabled, try copying the file
    instead. Otherwise, raise an error without trying a plain copy.

    May raise an `ImportError` if the `reflink` module is not available.
    """
    import reflink as pyreflink

    if samefile(path, dest):
        return

    if os.path.exists(syspath(dest)) and not replace:
        raise FilesystemError(u'file exists', 'rename', (path, dest))

    try:
        pyreflink.reflink(path, dest)
    except (NotImplementedError, pyreflink.ReflinkImpossibleError):
        if fallback:
            copy(path, dest, replace)
        else:
            raise FilesystemError(u'OS/filesystem does not support reflinks.',
                                  'link', (path, dest), traceback.format_exc())


def unique_path(path):
    """Returns a version of ``path`` that does not exist on the
    filesystem. Specifically, if ``path` itself already exists, then
    something unique is appended to the path.
    """
    if not os.path.exists(syspath(path)):
        return path

    base, ext = os.path.splitext(path)
    match = re.search(br'\.(\d)+$', base)
    if match:
        num = int(match.group(1))
        base = base[:match.start()]
    else:
        num = 0
    while True:
        num += 1
        suffix = u'.{}'.format(num).encode() + ext
        new_path = base + suffix
        if not os.path.exists(new_path):
            return new_path

# Note: The Windows "reserved characters" are, of course, allowed on
# Unix. They are forbidden here because they cause problems on Samba
# shares, which are sufficiently common as to cause frequent problems.
# https://msdn.microsoft.com/en-us/library/windows/desktop/aa365247.aspx
CHAR_REPLACE = [
    (re.compile(r'[\\/]'), u'_'),  # / and \ -- forbidden everywhere.
    (re.compile(r'^\.'), u'_'),  # Leading dot (hidden files on Unix).
    (re.compile(r'[\x00-\x1f]'), u''),  # Control characters.
    (re.compile(r'[<>:"\?\*\|]'), u'_'),  # Windows "reserved characters".
    (re.compile(r'\.$'), u'_'),  # Trailing dots.
    (re.compile(r'\s+$'), u''),  # Trailing whitespace.
]


def sanitize_path(path, replacements=None):
    """Takes a path (as a Unicode string) and makes sure that it is
    legal. Returns a new path. Only works with fragments; won't work
    reliably on Windows when a path begins with a drive letter. Path
    separators (including altsep!) should already be cleaned from the
    path components. If replacements is specified, it is used *instead*
    of the default set of replacements; it must be a list of (compiled
    regex, replacement string) pairs.
    """
    replacements = replacements or CHAR_REPLACE

    comps = components(path)
    if not comps:
        return ''
    for i, comp in enumerate(comps):
        for regex, repl in replacements:
            comp = regex.sub(repl, comp)
        comps[i] = comp
    return os.path.join(*comps)


def truncate_path(path, length=MAX_FILENAME_LENGTH):
    """Given a bytestring path or a Unicode path fragment, truncate the
    components to a legal length. In the last component, the extension
    is preserved.
    """
    comps = components(path)

    out = [c[:length] for c in comps]
    base, ext = os.path.splitext(comps[-1])
    if ext:
        # Last component has an extension.
        base = base[:length - len(ext)]
        out[-1] = base + ext

    return os.path.join(*out)


def _legalize_stage(path, replacements, length, extension, fragment):
    """Perform a single round of path legalization steps
    (sanitation/replacement, encoding from Unicode to bytes,
    extension-appending, and truncation). Return the path (Unicode if
    `fragment` is set, `bytes` otherwise) and whether truncation was
    required.
    """
    # Perform an initial sanitization including user replacements.
    path = sanitize_path(path, replacements)

    # Encode for the filesystem.
    if not fragment:
        path = bytestring_path(path)

    # Preserve extension.
    path += extension.lower()

    # Truncate too-long components.
    pre_truncate_path = path
    path = truncate_path(path, length)

    return path, path != pre_truncate_path


def legalize_path(path, replacements, length, extension, fragment):
    """Given a path-like Unicode string, produce a legal path. Return
    the path and a flag indicating whether some replacements had to be
    ignored (see below).

    The legalization process (see `_legalize_stage`) consists of
    applying the sanitation rules in `replacements`, encoding the string
    to bytes (unless `fragment` is set), truncating components to
    `length`, appending the `extension`.

    This function performs up to three calls to `_legalize_stage` in
    case truncation conflicts with replacements (as can happen when
    truncation creates whitespace at the end of the string, for
    example). The limited number of iterations iterations avoids the
    possibility of an infinite loop of sanitation and truncation
    operations, which could be caused by replacement rules that make the
    string longer. The flag returned from this function indicates that
    the path has to be truncated twice (indicating that replacements
    made the string longer again after it was truncated); the
    application should probably log some sort of warning.
    """

    if fragment:
        # Outputting Unicode.
        extension = extension.decode('utf-8', 'ignore')

    first_stage_path, _ = _legalize_stage(
        path, replacements, length, extension, fragment
    )

    # Convert back to Unicode with extension removed.
    first_stage_path, _ = os.path.splitext(displayable_path(first_stage_path))

    # Re-sanitize following truncation (including user replacements).
    second_stage_path, retruncated = _legalize_stage(
        first_stage_path, replacements, length, extension, fragment
    )

    # If the path was once again truncated, discard user replacements
    # and run through one last legalization stage.
    if retruncated:
        second_stage_path, _ = _legalize_stage(
            first_stage_path, None, length, extension, fragment
        )

    return second_stage_path, retruncated


def py3_path(path):
    """Convert a bytestring path to Unicode on Python 3 only. On Python
    2, return the bytestring path unchanged.

    This helps deal with APIs on Python 3 that *only* accept Unicode
    (i.e., `str` objects). I philosophically disagree with this
    decision, because paths are sadly bytes on Unix, but that's the way
    it is. So this function helps us "smuggle" the true bytes data
    through APIs that took Python 3's Unicode mandate too seriously.
    """
    if isinstance(path, six.text_type):
        return path
    assert isinstance(path, bytes)
    if six.PY2:
        return path
    return os.fsdecode(path)


def str2bool(value):
    """Returns a boolean reflecting a human-entered string."""
    return value.lower() in (u'yes', u'1', u'true', u't', u'y')


def as_string(value):
    """Convert a value to a Unicode object for matching with a query.
    None becomes the empty string. Bytestrings are silently decoded.
    """
    if six.PY2:
        buffer_types = buffer, memoryview  # noqa: F821
    else:
        buffer_types = memoryview

    if value is None:
        return u''
    elif isinstance(value, buffer_types):
        return bytes(value).decode('utf-8', 'ignore')
    elif isinstance(value, bytes):
        return value.decode('utf-8', 'ignore')
    else:
        return six.text_type(value)


def text_string(value, encoding='utf-8'):
    """Convert a string, which can either be bytes or unicode, to
    unicode.

    Text (unicode) is left untouched; bytes are decoded. This is useful
    to convert from a "native string" (bytes on Python 2, str on Python
    3) to a consistently unicode value.
    """
    if isinstance(value, bytes):
        return value.decode(encoding)
    return value


def plurality(objs):
    """Given a sequence of hashble objects, returns the object that
    is most common in the set and the its number of appearance. The
    sequence must contain at least one object.
    """
    c = Counter(objs)
    if not c:
        raise ValueError(u'sequence must be non-empty')
    return c.most_common(1)[0]


def cpu_count():
    """Return the number of hardware thread contexts (cores or SMT
    threads) in the system.
    """
    # Adapted from the soundconverter project:
    # https://github.com/kassoulet/soundconverter
    if sys.platform == 'win32':
        try:
            num = int(os.environ['NUMBER_OF_PROCESSORS'])
        except (ValueError, KeyError):
            num = 0
    elif sys.platform == 'darwin':
        try:
            num = int(command_output([
                '/usr/sbin/sysctl',
                '-n',
                'hw.ncpu',
                ]).stdout)
        except (ValueError, OSError, subprocess.CalledProcessError):
            num = 0
    else:
        try:
            num = os.sysconf('SC_NPROCESSORS_ONLN')
        except (ValueError, OSError, AttributeError):
            num = 0
    if num >= 1:
        return num
    else:
        return 1


def convert_command_args(args):
    """Convert command arguments to bytestrings on Python 2 and
    surrogate-escaped strings on Python 3."""
    assert isinstance(args, list)

    def convert(arg):
        if six.PY2:
            if isinstance(arg, six.text_type):
                arg = arg.encode(arg_encoding())
        else:
            if isinstance(arg, bytes):
                arg = arg.decode(arg_encoding(), 'surrogateescape')
        return arg

    return [convert(a) for a in args]


# stdout and stderr as bytes
CommandOutput = namedtuple("CommandOutput", ("stdout", "stderr"))


def command_output(cmd, shell=False):
    """Runs the command and returns its output after it has exited.

    Returns a CommandOutput. The attributes ``stdout`` and ``stderr`` contain
    byte strings of the respective output streams.

    ``cmd`` is a list of arguments starting with the command names. The
    arguments are bytes on Unix and strings on Windows.
    If ``shell`` is true, ``cmd`` is assumed to be a string and passed to a
    shell to execute.

    If the process exits with a non-zero return code
    ``subprocess.CalledProcessError`` is raised. May also raise
    ``OSError``.

    This replaces `subprocess.check_output` which can have problems if lots of
    output is sent to stderr.
    """
    cmd = convert_command_args(cmd)

    try:  # python >= 3.3
        devnull = subprocess.DEVNULL
    except AttributeError:
        devnull = open(os.devnull, 'r+b')

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=devnull,
        close_fds=platform.system() != 'Windows',
        shell=shell
    )
    stdout, stderr = proc.communicate()
    if proc.returncode:
        raise subprocess.CalledProcessError(
            returncode=proc.returncode,
            cmd=' '.join(cmd),
            output=stdout + stderr,
        )
    return CommandOutput(stdout, stderr)


def max_filename_length(path, limit=MAX_FILENAME_LENGTH):
    """Attempt to determine the maximum filename length for the
    filesystem containing `path`. If the value is greater than `limit`,
    then `limit` is used instead (to prevent errors when a filesystem
    misreports its capacity). If it cannot be determined (e.g., on
    Windows), return `limit`.
    """
    if hasattr(os, 'statvfs'):
        try:
            res = os.statvfs(path)
        except OSError:
            return limit
        return min(res[9], limit)
    else:
        return limit


def open_anything():
    """Return the system command that dispatches execution to the correct
    program.
    """
    sys_name = platform.system()
    if sys_name == 'Darwin':
        base_cmd = 'open'
    elif sys_name == 'Windows':
        base_cmd = 'start'
    else:  # Assume Unix
        base_cmd = 'xdg-open'
    return base_cmd


def editor_command():
    """Get a command for opening a text file.

    Use the `EDITOR` environment variable by default. If it is not
    present, fall back to `open_anything()`, the platform-specific tool
    for opening files in general.
    """
    editor = os.environ.get('EDITOR')
    if editor:
        return editor
    return open_anything()


def shlex_split(s):
    """Split a Unicode or bytes string according to shell lexing rules.

    Raise `ValueError` if the string is not a well-formed shell string.
    This is a workaround for a bug in some versions of Python.
    """
    if not six.PY2 or isinstance(s, bytes):  # Shlex works fine.
        return shlex.split(s)

    elif isinstance(s, six.text_type):
        # Work around a Python bug.
        # http://bugs.python.org/issue6988
        bs = s.encode('utf-8')
        return [c.decode('utf-8') for c in shlex.split(bs)]

    else:
        raise TypeError(u'shlex_split called with non-string')


def interactive_open(targets, command):
    """Open the files in `targets` by `exec`ing a new `command`, given
    as a Unicode string. (The new program takes over, and Python
    execution ends: this does not fork a subprocess.)

    Can raise `OSError`.
    """
    assert command

    # Split the command string into its arguments.
    try:
        args = shlex_split(command)
    except ValueError:  # Malformed shell tokens.
        args = [command]

    args.insert(0, args[0])  # for argv[0]

    args += targets

    return os.execlp(*args)


def _windows_long_path_name(short_path):
    """Use Windows' `GetLongPathNameW` via ctypes to get the canonical,
    long path given a short filename.
    """
    if not isinstance(short_path, six.text_type):
        short_path = short_path.decode(_fsencoding())

    import ctypes
    buf = ctypes.create_unicode_buffer(260)
    get_long_path_name_w = ctypes.windll.kernel32.GetLongPathNameW
    return_value = get_long_path_name_w(short_path, buf, 260)

    if return_value == 0 or return_value > 260:
        # An error occurred
        return short_path
    else:
        long_path = buf.value
        # GetLongPathNameW does not change the case of the drive
        # letter.
        if len(long_path) > 1 and long_path[1] == ':':
            long_path = long_path[0].upper() + long_path[1:]
        return long_path


def case_sensitive(path):
    """Check whether the filesystem at the given path is case sensitive.

    To work best, the path should point to a file or a directory. If the path
    does not exist, assume a case sensitive file system on every platform
    except Windows.
    """
    # A fallback in case the path does not exist.
    if not os.path.exists(syspath(path)):
        # By default, the case sensitivity depends on the platform.
        return platform.system() != 'Windows'

    # If an upper-case version of the path exists but a lower-case
    # version does not, then the filesystem must be case-sensitive.
    # (Otherwise, we have more work to do.)
    if not (os.path.exists(syspath(path.lower())) and
            os.path.exists(syspath(path.upper()))):
        return True

    # Both versions of the path exist on the file system. Check whether
    # they refer to different files by their inodes. Alas,
    # `os.path.samefile` is only available on Unix systems on Python 2.
    if platform.system() != 'Windows':
        return not os.path.samefile(syspath(path.lower()),
                                    syspath(path.upper()))

    # On Windows, we check whether the canonical, long filenames for the
    # files are the same.
    lower = _windows_long_path_name(path.lower())
    upper = _windows_long_path_name(path.upper())
    return lower != upper


def raw_seconds_short(string):
    """Formats a human-readable M:SS string as a float (number of seconds).

    Raises ValueError if the conversion cannot take place due to `string` not
    being in the right format.
    """
    match = re.match(r'^(\d+):([0-5]\d)$', string)
    if not match:
        raise ValueError(u'String not in M:SS format')
    minutes, seconds = map(int, match.groups())
    return float(minutes * 60 + seconds)


def asciify_path(path, sep_replace):
    """Decodes all unicode characters in a path into ASCII equivalents.

    Substitutions are provided by the unidecode module. Path separators in the
    input are preserved.

    Keyword arguments:
    path -- The path to be asciified.
    sep_replace -- the string to be used to replace extraneous path separators.
    """
    # if this platform has an os.altsep, change it to os.sep.
    if os.altsep:
        path = path.replace(os.altsep, os.sep)
    path_components = path.split(os.sep)
    for index, item in enumerate(path_components):
        path_components[index] = unidecode(item).replace(os.sep, sep_replace)
        if os.altsep:
            path_components[index] = unidecode(item).replace(
                os.altsep,
                sep_replace
            )
    return os.sep.join(path_components)


def par_map(transform, items):
    """Apply the function `transform` to all the elements in the
    iterable `items`, like `map(transform, items)` but with no return
    value. The map *might* happen in parallel: it's parallel on Python 3
    and sequential on Python 2.

    The parallelism uses threads (not processes), so this is only useful
    for IO-bound `transform`s.
    """
    if sys.version_info[0] < 3:
        # multiprocessing.pool.ThreadPool does not seem to work on
        # Python 2. We could consider switching to futures instead.
        for item in items:
            transform(item)
    else:
        pool = ThreadPool()
        pool.map(transform, items)
        pool.close()
        pool.join()


def lazy_property(func):
    """A decorator that creates a lazily evaluated property. On first access,
    the property is assigned the return value of `func`. This first value is
    stored, so that future accesses do not have to evaluate `func` again.

    This behaviour is useful when `func` is expensive to evaluate, and it is
    not certain that the result will be needed.
    """
    field_name = '_' + func.__name__

    @property
    @functools.wraps(func)
    def wrapper(self):
        if hasattr(self, field_name):
            return getattr(self, field_name)

        value = func(self)
        setattr(self, field_name, value)
        return value

    return wrapper
