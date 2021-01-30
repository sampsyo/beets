# -*- coding: utf-8 -*-
# This file is part of beets.
# Copyright 2016, Jakob Schnitzer.
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

"""Converts tracks or albums to external directory
"""
from __future__ import division, absolute_import, print_function
from beets.util import par_map

import os
import threading
import subprocess
import tempfile
import shlex
import six
from string import Template
import platform

from beets import ui, util, plugins, config
from beets.plugins import BeetsPlugin
from confuse import ConfigTypeError
from beets import art
from beets.util.artresizer import ArtResizer
from beets.library import parse_query_string
from beets.library import Item

_fs_lock = threading.Lock()
_temp_files = []  # Keep track of temporary transcoded files for deletion.

# Some convenient alternate names for formats.
ALIASES = {
    u'wma': u'windows media',
    u'vorbis': u'ogg',
}

LOSSLESS_FORMATS = ['ape', 'flac', 'alac', 'wav', 'aiff']


def replace_ext(path, ext):
    """Return the path with its extension replaced by `ext`.

    The new extension must not contain a leading dot.
    """
    ext_dot = b'.' + ext
    return os.path.splitext(path)[0] + ext_dot


def get_format(fmt=None):
    """Return the command template and the extension from the config.
    """
    if not fmt:
        fmt = config['convert']['format'].as_str().lower()
    fmt = ALIASES.get(fmt, fmt)

    try:
        format_info = config['convert']['formats'][fmt].get(dict)
        command = format_info['command']
        extension = format_info.get('extension', fmt)
    except KeyError:
        raise ui.UserError(
            u'convert: format {0} needs the "command" field'
            .format(fmt)
        )
    except ConfigTypeError:
        command = config['convert']['formats'][fmt].get(str)
        extension = fmt

    # Convenience and backwards-compatibility shortcuts.
    keys = config['convert'].keys()
    if 'command' in keys:
        command = config['convert']['command'].as_str()
    elif 'opts' in keys:
        # Undocumented option for backwards compatibility with < 1.3.1.
        command = u'ffmpeg -i $source -y {0} $dest'.format(
            config['convert']['opts'].as_str()
        )
    if 'extension' in keys:
        extension = config['convert']['extension'].as_str()

    return (command.encode('utf-8'), extension.encode('utf-8'))


def should_transcode(item, fmt):
    """Determine whether the item should be transcoded as part of
    conversion (i.e., its bitrate is high or it has the wrong format).
    """
    no_convert_queries = config['convert']['no_convert'].as_str_seq()
    if no_convert_queries:
        for query_string in no_convert_queries:
            query, _ = parse_query_string(query_string, Item)
            if query.match(item):
                return False
    if config['convert']['never_convert_lossy_files'] and \
            not (item.format.lower() in LOSSLESS_FORMATS):
        return False
    maxbr = config['convert']['max_bitrate'].get(int)
    return fmt.lower() != item.format.lower() or \
        item.bitrate >= 1000 * maxbr


class ConvertPlugin(BeetsPlugin):
    def __init__(self):
        super(ConvertPlugin, self).__init__()
        self.config.add({
            u'dest': None,
            u'pretend': False,
            u'link': False,
            u'hardlink': False,
            u'threads': util.cpu_count(),
            u'format': u'mp3',
            u'id3v23': u'inherit',
            u'formats': {
                u'aac': {
                    u'command': u'ffmpeg -i $source -y -vn -acodec aac '
                                u'-aq 1 $dest',
                    u'extension': u'm4a',
                },
                u'alac': {
                    u'command': u'ffmpeg -i $source -y -vn -acodec alac $dest',
                    u'extension': u'm4a',
                },
                u'flac': u'ffmpeg -i $source -y -vn -acodec flac $dest',
                u'mp3': u'ffmpeg -i $source -y -vn -aq 2 $dest',
                u'opus':
                    u'ffmpeg -i $source -y -vn -acodec libopus -ab 96k $dest',
                u'ogg':
                    u'ffmpeg -i $source -y -vn -acodec libvorbis -aq 3 $dest',
                u'wma':
                    u'ffmpeg -i $source -y -vn -acodec wmav2 -vn $dest',
            },
            u'max_bitrate': 500,
            u'auto': False,
            u'tmpdir': None,
            u'quiet': False,
            u'embed': True,
            u'paths': {},
            u'no_convert': u'',
            u'never_convert_lossy_files': False,
            u'copy_album_art': False,
            u'album_art_maxwidth': 0,
            u'delete_originals': False,
        })
        self.early_import_stages = [self.auto_convert]

        self.register_listener('import_task_files', self._cleanup)

    def commands(self):
        cmd = ui.Subcommand('convert', help=u'convert to external location')
        cmd.parser.add_option('-p', '--pretend', action='store_true',
                              help=u'show actions but do nothing')
        cmd.parser.add_option('-t', '--threads', action='store', type='int',
                              help=u'change the number of threads, \
                              defaults to maximum available processors')
        cmd.parser.add_option('-k', '--keep-new', action='store_true',
                              dest='keep_new', help=u'keep only the converted \
                              and move the old files')
        cmd.parser.add_option('-d', '--dest', action='store',
                              help=u'set the destination directory')
        cmd.parser.add_option('-f', '--format', action='store', dest='format',
                              help=u'set the target format of the tracks')
        cmd.parser.add_option('-y', '--yes', action='store_true', dest='yes',
                              help=u'do not ask for confirmation')
        cmd.parser.add_option('-l', '--link', action='store_true', dest='link',
                              help=u'symlink files that do not \
                              need transcoding.')
        cmd.parser.add_option('-H', '--hardlink', action='store_true',
                              dest='hardlink',
                              help=u'hardlink files that do not \
                              need transcoding. Overrides --link.')
        cmd.parser.add_album_option()
        cmd.func = self.convert_func
        return [cmd]

    def auto_convert(self, config, task):
        if self.config['auto']:
            par_map(lambda item: self.convert_on_import(config.lib, item),
                    task.imported_items())

    # Utilities converted from functions to methods on logging overhaul

    def encode(self, command, source, dest, pretend=False):
        """Encode `source` to `dest` using command template `command`.

        Raises `subprocess.CalledProcessError` if the command exited with a
        non-zero status code.
        """
        # The paths and arguments must be bytes.
        assert isinstance(command, bytes)
        assert isinstance(source, bytes)
        assert isinstance(dest, bytes)

        quiet = self.config['quiet'].get(bool)

        if not quiet and not pretend:
            self._log.info(u'Encoding {0}', util.displayable_path(source))

        # On Python 3, we need to construct the command to invoke as a
        # Unicode string. On Unix, this is a little unfortunate---the OS is
        # expecting bytes---so we use surrogate escaping and decode with the
        # argument encoding, which is the same encoding that will then be
        # *reversed* to recover the same bytes before invoking the OS. On
        # Windows, we want to preserve the Unicode filename "as is."
        if not six.PY2:
            command = command.decode(util.arg_encoding(), 'surrogateescape')
            if platform.system() == 'Windows':
                source = source.decode(util._fsencoding())
                dest = dest.decode(util._fsencoding())
            else:
                source = source.decode(util.arg_encoding(), 'surrogateescape')
                dest = dest.decode(util.arg_encoding(), 'surrogateescape')

        # Substitute $source and $dest in the argument list.
        args = shlex.split(command)
        encode_cmd = []
        for i, arg in enumerate(args):
            args[i] = Template(arg).safe_substitute({
                'source': source,
                'dest': dest,
            })
            if six.PY2:
                encode_cmd.append(args[i])
            else:
                encode_cmd.append(args[i].encode(util.arg_encoding()))

        if pretend:
            self._log.info(u'{0}', u' '.join(ui.decargs(args)))
            return

        try:
            util.command_output(encode_cmd)
        except subprocess.CalledProcessError as exc:
            # Something went wrong (probably Ctrl+C), remove temporary files
            self._log.info(u'Encoding {0} failed. Cleaning up...',
                           util.displayable_path(source))
            self._log.debug(u'Command {0} exited with status {1}: {2}',
                            args,
                            exc.returncode,
                            exc.output)
            util.remove(dest)
            util.prune_dirs(os.path.dirname(dest))
            raise
        except OSError as exc:
            raise ui.UserError(
                u"convert: couldn't invoke '{0}': {1}".format(
                    u' '.join(ui.decargs(args)), exc
                )
            )

        if not quiet and not pretend:
            self._log.info(u'Finished encoding {0}',
                           util.displayable_path(source))

    def convert_item(self, dest_dir, keep_new, path_formats, fmt,
                     pretend=False, link=False, hardlink=False):
        """A pipeline thread that converts `Item` objects from a
        library.
        """
        command, ext = get_format(fmt)
        item, original, converted = None, None, None
        while True:
            item = yield (item, original, converted)
            dest = item.destination(basedir=dest_dir,
                                    path_formats=path_formats)

            # When keeping the new file in the library, we first move the
            # current (pristine) file to the destination. We'll then copy it
            # back to its old path or transcode it to a new path.
            if keep_new:
                original = dest
                converted = item.path
                if should_transcode(item, fmt):
                    converted = replace_ext(converted, ext)
            else:
                original = item.path
                if should_transcode(item, fmt):
                    dest = replace_ext(dest, ext)
                converted = dest

            # Ensure that only one thread tries to create directories at a
            # time. (The existence check is not atomic with the directory
            # creation inside this function.)
            if not pretend:
                with _fs_lock:
                    util.mkdirall(dest)

            if os.path.exists(util.syspath(dest)):
                self._log.info(u'Skipping {0} (target file exists)',
                               util.displayable_path(item.path))
                continue

            if keep_new:
                if pretend:
                    self._log.info(u'mv {0} {1}',
                                   util.displayable_path(item.path),
                                   util.displayable_path(original))
                else:
                    self._log.info(u'Moving to {0}',
                                   util.displayable_path(original))
                    util.move(item.path, original)

            if should_transcode(item, fmt):
                linked = False
                try:
                    self.encode(command, original, converted, pretend)
                except subprocess.CalledProcessError:
                    continue
            else:
                linked = link or hardlink
                if pretend:
                    msg = 'ln' if hardlink else ('ln -s' if link else 'cp')

                    self._log.info(u'{2} {0} {1}',
                                   util.displayable_path(original),
                                   util.displayable_path(converted),
                                   msg)
                else:
                    # No transcoding necessary.
                    msg = 'Hardlinking' if hardlink \
                        else ('Linking' if link else 'Copying')

                    self._log.info(u'{1} {0}',
                                   util.displayable_path(item.path),
                                   msg)

                    if hardlink:
                        util.hardlink(original, converted)
                    elif link:
                        util.link(original, converted)
                    else:
                        util.copy(original, converted)

            if pretend:
                continue

            id3v23 = self.config['id3v23'].as_choice([True, False, 'inherit'])
            if id3v23 == 'inherit':
                id3v23 = None

            # Write tags from the database to the converted file.
            item.try_write(path=converted, id3v23=id3v23)

            if keep_new:
                # If we're keeping the transcoded file, read it again (after
                # writing) to get new bitrate, duration, etc.
                item.path = converted
                item.read()
                item.store()  # Store new path and audio data.

            if self.config['embed'] and not linked:
                album = item.get_album()
                if album and album.artpath:
                    self._log.debug(u'embedding album art from {}',
                                    util.displayable_path(album.artpath))
                    art.embed_item(self._log, item, album.artpath,
                                   itempath=converted, id3v23=id3v23)

            if keep_new:
                plugins.send('after_convert', item=item,
                             dest=dest, keepnew=True)
            else:
                plugins.send('after_convert', item=item,
                             dest=converted, keepnew=False)

    def copy_album_art(self, album, dest_dir, path_formats, pretend=False,
                       link=False, hardlink=False):
        """Copies or converts the associated cover art of the album. Album must
        have at least one track.
        """
        if not album or not album.artpath:
            return

        album_item = album.items().get()
        # Album shouldn't be empty.
        if not album_item:
            return

        # Get the destination of the first item (track) of the album, we use
        # this function to format the path accordingly to path_formats.
        dest = album_item.destination(basedir=dest_dir,
                                      path_formats=path_formats)

        # Remove item from the path.
        dest = os.path.join(*util.components(dest)[:-1])

        dest = album.art_destination(album.artpath, item_dir=dest)
        if album.artpath == dest:
            return

        if not pretend:
            util.mkdirall(dest)

        if os.path.exists(util.syspath(dest)):
            self._log.info(u'Skipping {0} (target file exists)',
                           util.displayable_path(album.artpath))
            return

        # Decide whether we need to resize the cover-art image.
        resize = False
        maxwidth = None
        if self.config['album_art_maxwidth']:
            maxwidth = self.config['album_art_maxwidth'].get(int)
            size = ArtResizer.shared.get_size(album.artpath)
            self._log.debug('image size: {}', size)
            if size:
                resize = size[0] > maxwidth
            else:
                self._log.warning(u'Could not get size of image (please see '
                                  u'documentation for dependencies).')

        # Either copy or resize (while copying) the image.
        if resize:
            self._log.info(u'Resizing cover art from {0} to {1}',
                           util.displayable_path(album.artpath),
                           util.displayable_path(dest))
            if not pretend:
                ArtResizer.shared.resize(maxwidth, album.artpath, dest)
        else:
            if pretend:
                msg = 'ln' if hardlink else ('ln -s' if link else 'cp')

                self._log.info(u'{2} {0} {1}',
                               util.displayable_path(album.artpath),
                               util.displayable_path(dest),
                               msg)
            else:
                msg = 'Hardlinking' if hardlink \
                    else ('Linking' if link else 'Copying')

                self._log.info(u'{2} cover art from {0} to {1}',
                               util.displayable_path(album.artpath),
                               util.displayable_path(dest),
                               msg)
                if hardlink:
                    util.hardlink(album.artpath, dest)
                elif link:
                    util.link(album.artpath, dest)
                else:
                    util.copy(album.artpath, dest)

    def convert_func(self, lib, opts, args):
        dest = opts.dest or self.config['dest'].get()
        if not dest:
            raise ui.UserError(u'no convert destination set')
        dest = util.bytestring_path(dest)

        threads = opts.threads or self.config['threads'].get(int)

        path_formats = ui.get_path_formats(self.config['paths'] or None)

        fmt = opts.format or self.config['format'].as_str().lower()

        if opts.pretend is not None:
            pretend = opts.pretend
        else:
            pretend = self.config['pretend'].get(bool)

        if opts.hardlink is not None:
            hardlink = opts.hardlink
            link = False
        elif opts.link is not None:
            hardlink = False
            link = opts.link
        else:
            hardlink = self.config['hardlink'].get(bool)
            link = self.config['link'].get(bool)

        if opts.album:
            albums = lib.albums(ui.decargs(args))
            items = [i for a in albums for i in a.items()]
            if not pretend:
                for a in albums:
                    ui.print_(format(a, u''))
        else:
            items = list(lib.items(ui.decargs(args)))
            if not pretend:
                for i in items:
                    ui.print_(format(i, u''))

        if not items:
            self._log.error(u'Empty query result.')
            return
        if not (pretend or opts.yes or ui.input_yn(u"Convert? (Y/n)")):
            return

        if opts.album and self.config['copy_album_art']:
            for album in albums:
                self.copy_album_art(album, dest, path_formats, pretend,
                                    link, hardlink)

        convert = [self.convert_item(dest,
                                     opts.keep_new,
                                     path_formats,
                                     fmt,
                                     pretend,
                                     link,
                                     hardlink)
                   for _ in range(threads)]
        pipe = util.pipeline.Pipeline([iter(items), convert])
        pipe.run_parallel()

    def convert_on_import(self, lib, item):
        """Transcode a file automatically after it is imported into the
        library.
        """
        fmt = self.config['format'].as_str().lower()
        if should_transcode(item, fmt):
            command, ext = get_format()

            # Create a temporary file for the conversion.
            tmpdir = self.config['tmpdir'].get()
            if tmpdir:
                tmpdir = util.py3_path(util.bytestring_path(tmpdir))
            fd, dest = tempfile.mkstemp(util.py3_path(b'.' + ext), dir=tmpdir)
            os.close(fd)
            dest = util.bytestring_path(dest)
            _temp_files.append(dest)  # Delete the transcode later.

            # Convert.
            try:
                self.encode(command, item.path, dest)
            except subprocess.CalledProcessError:
                return

            # Change the newly-imported database entry to point to the
            # converted file.
            source_path = item.path
            item.path = dest
            item.write()
            item.read()  # Load new audio information data.
            item.store()

            if self.config['delete_originals']:
                self._log.info(u'Removing original file {0}', source_path)
                util.remove(source_path, False)

    def _cleanup(self, task, session):
        for path in task.old_paths:
            if path in _temp_files:
                if os.path.isfile(util.syspath(path)):
                    util.remove(path)
                _temp_files.remove(path)
