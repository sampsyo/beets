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
import logging
import os
import shlex
import subprocess
import tempfile
import threading
from string import Template

import mediafile
from confuse import ConfigTypeError, Optional

from beets import art, config, plugins, ui, util
from beets.library import Item, parse_query_string
from beets.plugins import BeetsPlugin
from beets.util import arg_encoding, par_map
from beets.util.artresizer import ArtResizer
from beets.util.m3u import M3UFile

_fs_lock = threading.Lock()
_temp_files = []  # Keep track of temporary transcoded files for deletion.

# Some convenient alternate names for formats.
ALIASES = {
    "windows media": "wma",
    "vorbis": "ogg",
}

LOSSLESS_FORMATS = ["ape", "flac", "alac", "wave", "aiff"]


def replace_ext(path, ext):
    """Return the path with its extension replaced by `ext`.

    The new extension must not contain a leading dot.
    """
    ext_dot = b"." + ext
    return os.path.splitext(path)[0] + ext_dot


def get_format(fmt=None):
    """Return the command template and the extension from the config."""
    if not fmt:
        fmt = config["convert"]["format"].as_str().lower()
    fmt = ALIASES.get(fmt, fmt)

    try:
        format_info = config["convert"]["formats"][fmt].get(dict)
        command = format_info["command"]
        extension = format_info.get("extension", fmt)
    except KeyError:
        raise ui.UserError(
            'convert: format {} needs the "command" field'.format(fmt)
        )
    except ConfigTypeError:
        command = config["convert"]["formats"][fmt].get(str)
        extension = fmt

    # Convenience and backwards-compatibility shortcuts.
    keys = config["convert"].keys()
    if "command" in keys:
        command = config["convert"]["command"].as_str()
    elif "opts" in keys:
        # Undocumented option for backwards compatibility with < 1.3.1.
        command = "ffmpeg -i $source -y {} $dest".format(
            config["convert"]["opts"].as_str()
        )
    if "extension" in keys:
        extension = config["convert"]["extension"].as_str()

    return (command.encode("utf-8"), extension.encode("utf-8"))


def should_transcode(item, fmt):
    """Determine whether the item should be transcoded as part of
    conversion (i.e., its bitrate is high or it has the wrong format).
    """
    no_convert_queries = config["convert"]["no_convert"].as_str_seq()
    if no_convert_queries:
        for query_string in no_convert_queries:
            query, _ = parse_query_string(query_string, Item)
            if query.match(item):
                return False
    if config["convert"]["never_convert_lossy_files"] and not (
        item.format.lower() in LOSSLESS_FORMATS
    ):
        return False
    maxbr = config["convert"]["max_bitrate"].get(Optional(int))
    if maxbr is not None and item.bitrate >= 1000 * maxbr:
        return True
    return fmt.lower() != item.format.lower()


class ConvertPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()
        self.config.add(
            {
                "dest": None,
                "pretend": False,
                "link": False,
                "hardlink": False,
                "threads": os.cpu_count(),
                "format": "mp3",
                "id3v23": "inherit",
                "formats": {
                    "aac": {
                        "command": "ffmpeg -i $source -y -vn -acodec aac "
                        "-aq 1 $dest",
                        "extension": "m4a",
                    },
                    "alac": {
                        "command": "ffmpeg -i $source -y -vn -acodec alac $dest",
                        "extension": "m4a",
                    },
                    "flac": "ffmpeg -i $source -y -vn -acodec flac $dest",
                    "mp3": "ffmpeg -i $source -y -vn -aq 2 $dest",
                    "opus": "ffmpeg -i $source -y -vn -acodec libopus -ab 96k $dest",
                    "ogg": "ffmpeg -i $source -y -vn -acodec libvorbis -aq 3 $dest",
                    "wma": "ffmpeg -i $source -y -vn -acodec wmav2 -vn $dest",
                },
                "max_bitrate": None,
                "auto": False,
                "auto_keep": False,
                "tmpdir": None,
                "quiet": False,
                "embed": True,
                "paths": {},
                "no_convert": "",
                "never_convert_lossy_files": False,
                "copy_album_art": False,
                "album_art_maxwidth": 0,
                "delete_originals": False,
                "playlist": None,
            }
        )
        self.early_import_stages = [self.auto_convert, self.auto_convert_keep]

        self.register_listener("import_task_files", self._cleanup)

    def commands(self):
        cmd = ui.Subcommand("convert", help="convert to external location")
        cmd.parser.add_option(
            "-p",
            "--pretend",
            action="store_true",
            help="show actions but do nothing",
        )
        cmd.parser.add_option(
            "-t",
            "--threads",
            action="store",
            type="int",
            help="change the number of threads, \
                              defaults to maximum available processors",
        )
        cmd.parser.add_option(
            "-k",
            "--keep-new",
            action="store_true",
            dest="keep_new",
            help="keep only the converted \
                              and move the old files",
        )
        cmd.parser.add_option(
            "-d", "--dest", action="store", help="set the destination directory"
        )
        cmd.parser.add_option(
            "-f",
            "--format",
            action="store",
            dest="format",
            help="set the target format of the tracks",
        )
        cmd.parser.add_option(
            "-y",
            "--yes",
            action="store_true",
            dest="yes",
            help="do not ask for confirmation",
        )
        cmd.parser.add_option(
            "-l",
            "--link",
            action="store_true",
            dest="link",
            help="symlink files that do not \
                              need transcoding.",
        )
        cmd.parser.add_option(
            "-H",
            "--hardlink",
            action="store_true",
            dest="hardlink",
            help="hardlink files that do not \
                              need transcoding. Overrides --link.",
        )
        cmd.parser.add_option(
            "-m",
            "--playlist",
            action="store",
            help="""create an m3u8 playlist file containing
                              the converted files. The playlist file will be
                              saved below the destination directory, thus
                              PLAYLIST could be a file name or a relative path.
                              To ensure a working playlist when transferred to
                              a different computer, or opened from an external
                              drive, relative paths pointing to media files
                              will be used.""",
        )
        cmd.parser.add_album_option()
        cmd.func = self.convert_func
        return [cmd]

    def auto_convert(self, config, task):
        if self.config["auto"]:
            par_map(
                lambda item: self.convert_on_import(config.lib, item),
                task.imported_items(),
            )

    def auto_convert_keep(self, config, task):
        if self.config["auto_keep"]:
            empty_opts = self.commands()[0].parser.get_default_values()
            (
                dest,
                threads,
                path_formats,
                fmt,
                pretend,
                hardlink,
                link,
                playlist,
            ) = self._get_opts_and_config(empty_opts)

            items = task.imported_items()
            self._parallel_convert(
                dest,
                False,
                path_formats,
                fmt,
                pretend,
                link,
                hardlink,
                threads,
                items,
            )

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

        quiet = self.config["quiet"].get(bool)

        if not quiet and not pretend:
            self._log.info("Encoding {0}", util.displayable_path(source))

        command = command.decode(arg_encoding(), "surrogateescape")
        source = os.fsdecode(source)
        dest = os.fsdecode(dest)

        # Substitute $source and $dest in the argument list.
        args = shlex.split(command)
        encode_cmd = []
        for i, arg in enumerate(args):
            args[i] = Template(arg).safe_substitute(
                {
                    "source": source,
                    "dest": dest,
                }
            )
            encode_cmd.append(args[i].encode(util.arg_encoding()))

        if pretend:
            self._log.info("{0}", " ".join(ui.decargs(args)))
            return

        try:
            util.command_output(encode_cmd)
        except subprocess.CalledProcessError as exc:
            # Something went wrong (probably Ctrl+C), remove temporary files
            self._log.info(
                "Encoding {0} failed. Cleaning up...",
                util.displayable_path(source),
            )
            self._log.debug(
                "Command {0} exited with status {1}: {2}",
                args,
                exc.returncode,
                exc.output,
            )
            util.remove(dest)
            util.prune_dirs(os.path.dirname(dest))
            raise
        except OSError as exc:
            raise ui.UserError(
                "convert: couldn't invoke '{}': {}".format(
                    " ".join(ui.decargs(args)), exc
                )
            )

        if not quiet and not pretend:
            self._log.info(
                "Finished encoding {0}", util.displayable_path(source)
            )

    def convert_item(
        self,
        dest_dir,
        keep_new,
        path_formats,
        fmt,
        pretend=False,
        link=False,
        hardlink=False,
    ):
        """A pipeline thread that converts `Item` objects from a
        library.
        """
        command, ext = get_format(fmt)
        item, original, converted = None, None, None
        while True:
            item = yield (item, original, converted)
            dest = item.destination(basedir=dest_dir, path_formats=path_formats)

            # Ensure that desired item is readable before processing it. Needed
            # to avoid any side-effect of the conversion (linking, keep_new,
            # refresh) if we already know that it will fail.
            try:
                mf = mediafile.MediaFile(util.syspath(item.path))
            except mediafile.UnreadableFileError as exc:
                self._log.error("Could not open file to convert: {0}", exc)
                continue

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
                self._log.info(
                    "Skipping {0} (target file exists)",
                    util.displayable_path(item.path),
                )
                continue

            if keep_new:
                if pretend:
                    self._log.info(
                        "mv {0} {1}",
                        util.displayable_path(item.path),
                        util.displayable_path(original),
                    )
                else:
                    self._log.info(
                        "Moving to {0}", util.displayable_path(original)
                    )
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
                    msg = "ln" if hardlink else ("ln -s" if link else "cp")

                    self._log.info(
                        "{2} {0} {1}",
                        util.displayable_path(original),
                        util.displayable_path(converted),
                        msg,
                    )
                else:
                    # No transcoding necessary.
                    msg = (
                        "Hardlinking"
                        if hardlink
                        else ("Linking" if link else "Copying")
                    )

                    self._log.info(
                        "{1} {0}", util.displayable_path(item.path), msg
                    )

                    if hardlink:
                        util.hardlink(original, converted)
                    elif link:
                        util.link(original, converted)
                    else:
                        util.copy(original, converted)

            if pretend:
                continue

            id3v23 = self.config["id3v23"].as_choice([True, False, "inherit"])
            if id3v23 == "inherit":
                id3v23 = None

            # Write tags from the database to the converted file.
            item.try_write(path=converted, id3v23=id3v23)

            if keep_new:
                # If we're keeping the transcoded file, read it again (after
                # writing) to get new bitrate, duration, etc.
                item.path = converted
                item.read()
                item.store()  # Store new path and audio data.

            if self.config["embed"] and not linked:
                album = item._cached_album
                if album and album.artpath:
                    maxwidth = self._get_art_resize(album.artpath)
                    self._log.debug(
                        "embedding album art from {}",
                        util.displayable_path(album.artpath),
                    )
                    art.embed_item(
                        self._log,
                        item,
                        album.artpath,
                        maxwidth,
                        itempath=converted,
                        id3v23=id3v23,
                    )

            if keep_new:
                plugins.send(
                    "after_convert", item=item, dest=dest, keepnew=True
                )
            else:
                plugins.send(
                    "after_convert", item=item, dest=converted, keepnew=False
                )

    def copy_album_art(
        self,
        album,
        dest_dir,
        path_formats,
        pretend=False,
        link=False,
        hardlink=False,
    ):
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
        dest = album_item.destination(
            basedir=dest_dir, path_formats=path_formats
        )

        # Remove item from the path.
        dest = os.path.join(*util.components(dest)[:-1])

        dest = album.art_destination(album.artpath, item_dir=dest)
        if album.artpath == dest:
            return

        if not pretend:
            util.mkdirall(dest)

        if os.path.exists(util.syspath(dest)):
            self._log.info(
                "Skipping {0} (target file exists)",
                util.displayable_path(album.artpath),
            )
            return

        # Decide whether we need to resize the cover-art image.
        maxwidth = self._get_art_resize(album.artpath)

        # Either copy or resize (while copying) the image.
        if maxwidth is not None:
            self._log.info(
                "Resizing cover art from {0} to {1}",
                util.displayable_path(album.artpath),
                util.displayable_path(dest),
            )
            if not pretend:
                ArtResizer.shared.resize(maxwidth, album.artpath, dest)
        else:
            if pretend:
                msg = "ln" if hardlink else ("ln -s" if link else "cp")

                self._log.info(
                    "{2} {0} {1}",
                    util.displayable_path(album.artpath),
                    util.displayable_path(dest),
                    msg,
                )
            else:
                msg = (
                    "Hardlinking"
                    if hardlink
                    else ("Linking" if link else "Copying")
                )

                self._log.info(
                    "{2} cover art from {0} to {1}",
                    util.displayable_path(album.artpath),
                    util.displayable_path(dest),
                    msg,
                )
                if hardlink:
                    util.hardlink(album.artpath, dest)
                elif link:
                    util.link(album.artpath, dest)
                else:
                    util.copy(album.artpath, dest)

    def convert_func(self, lib, opts, args):
        (
            dest,
            threads,
            path_formats,
            fmt,
            pretend,
            hardlink,
            link,
            playlist,
        ) = self._get_opts_and_config(opts)

        if opts.album:
            albums = lib.albums(ui.decargs(args))
            items = [i for a in albums for i in a.items()]
            if not pretend:
                for a in albums:
                    ui.print_(format(a, ""))
        else:
            items = list(lib.items(ui.decargs(args)))
            if not pretend:
                for i in items:
                    ui.print_(format(i, ""))

        if not items:
            self._log.error("Empty query result.")
            return
        if not (pretend or opts.yes or ui.input_yn("Convert? (Y/n)")):
            return

        if opts.album and self.config["copy_album_art"]:
            for album in albums:
                self.copy_album_art(
                    album, dest, path_formats, pretend, link, hardlink
                )

        self._parallel_convert(
            dest,
            opts.keep_new,
            path_formats,
            fmt,
            pretend,
            link,
            hardlink,
            threads,
            items,
        )

        if playlist:
            # Playlist paths are understood as relative to the dest directory.
            pl_normpath = util.normpath(playlist)
            pl_dir = os.path.dirname(pl_normpath)
            self._log.info("Creating playlist file {0}", pl_normpath)
            # Generates a list of paths to media files, ensures the paths are
            # relative to the playlist's location and translates the unicode
            # strings we get from item.destination to bytes.
            items_paths = [
                os.path.relpath(
                    util.bytestring_path(
                        item.destination(
                            basedir=dest,
                            path_formats=path_formats,
                            fragment=False,
                        )
                    ),
                    pl_dir,
                )
                for item in items
            ]
            if not pretend:
                m3ufile = M3UFile(playlist)
                m3ufile.set_contents(items_paths)
                m3ufile.write()

    def convert_on_import(self, lib, item):
        """Transcode a file automatically after it is imported into the
        library.
        """
        fmt = self.config["format"].as_str().lower()
        if should_transcode(item, fmt):
            command, ext = get_format()

            # Create a temporary file for the conversion.
            tmpdir = self.config["tmpdir"].get()
            if tmpdir:
                tmpdir = os.fsdecode(util.bytestring_path(tmpdir))
            fd, dest = tempfile.mkstemp(os.fsdecode(b"." + ext), dir=tmpdir)
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

            if self.config["delete_originals"]:
                self._log.log(
                    logging.DEBUG if self.config["quiet"] else logging.INFO,
                    "Removing original file {0}",
                    source_path,
                )
                util.remove(source_path, False)

    def _get_art_resize(self, artpath):
        """For a given piece of album art, determine whether or not it needs
        to be resized according to the user's settings. If so, returns the
        new size. If not, returns None.
        """
        newwidth = None
        if self.config["album_art_maxwidth"]:
            maxwidth = self.config["album_art_maxwidth"].get(int)
            size = ArtResizer.shared.get_size(artpath)
            self._log.debug("image size: {}", size)
            if size:
                if size[0] > maxwidth:
                    newwidth = maxwidth
            else:
                self._log.warning(
                    "Could not get size of image (please see "
                    "documentation for dependencies)."
                )
        return newwidth

    def _cleanup(self, task, session):
        for path in task.old_paths:
            if path in _temp_files:
                if os.path.isfile(util.syspath(path)):
                    util.remove(path)
                _temp_files.remove(path)

    def _get_opts_and_config(self, opts):
        """Returns parameters needed for convert function.
        Get parameters from command line if available,
        default to config if not available.
        """
        dest = opts.dest or self.config["dest"].get()
        if not dest:
            raise ui.UserError("no convert destination set")
        dest = util.bytestring_path(dest)

        threads = opts.threads or self.config["threads"].get(int)

        path_formats = ui.get_path_formats(self.config["paths"] or None)

        fmt = opts.format or self.config["format"].as_str().lower()

        playlist = opts.playlist or self.config["playlist"].get()
        if playlist is not None:
            playlist = os.path.join(dest, util.bytestring_path(playlist))

        if opts.pretend is not None:
            pretend = opts.pretend
        else:
            pretend = self.config["pretend"].get(bool)

        if opts.hardlink is not None:
            hardlink = opts.hardlink
            link = False
        elif opts.link is not None:
            hardlink = False
            link = opts.link
        else:
            hardlink = self.config["hardlink"].get(bool)
            link = self.config["link"].get(bool)

        return (
            dest,
            threads,
            path_formats,
            fmt,
            pretend,
            hardlink,
            link,
            playlist,
        )

    def _parallel_convert(
        self,
        dest,
        keep_new,
        path_formats,
        fmt,
        pretend,
        link,
        hardlink,
        threads,
        items,
    ):
        """Run the convert_item function for every items on as many thread as
        defined in threads
        """
        convert = [
            self.convert_item(
                dest, keep_new, path_formats, fmt, pretend, link, hardlink
            )
            for _ in range(threads)
        ]
        pipe = util.pipeline.Pipeline([iter(items), convert])
        pipe.run_parallel()
