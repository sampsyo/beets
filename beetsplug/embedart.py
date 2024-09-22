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

"""Allows beets to embed album art into file metadata."""

import os.path
import tempfile
from mimetypes import guess_extension

import requests

from beets import art, config, ui
from beets.plugins import BeetsPlugin
from beets.ui import decargs, print_
from beets.util import bytestring_path, displayable_path, normpath, syspath
from beets.util.artresizer import ArtResizer


def _confirm(objs, album):
    """Show the list of affected objects (items or albums) and confirm
    that the user wants to modify their artwork.

    `album` is a Boolean indicating whether these are albums (as opposed
    to items).
    """
    noun = "album" if album else "file"
    prompt = "Modify artwork for {} {}{} (Y/n)?".format(
        len(objs), noun, "s" if len(objs) > 1 else ""
    )

    # Show all the items or albums.
    for obj in objs:
        print_(format(obj))

    # Confirm with user.
    return ui.input_yn(prompt)


class EmbedCoverArtPlugin(BeetsPlugin):
    """Allows albumart to be embedded into the actual files."""

    def __init__(self):
        super().__init__()
        self.config.add(
            {
                "maxwidth": 0,
                "auto": True,
                "compare_threshold": 0,
                "ifempty": False,
                "remove_art_file": False,
                "quality": 0,
            }
        )

        if self.config["maxwidth"].get(int) and not ArtResizer.shared.local:
            self.config["maxwidth"] = 0
            self._log.warning(
                "ImageMagick or PIL not found; " "'maxwidth' option ignored"
            )
        if (
            self.config["compare_threshold"].get(int)
            and not ArtResizer.shared.can_compare
        ):
            self.config["compare_threshold"] = 0
            self._log.warning(
                "ImageMagick 6.8.7 or higher not installed; "
                "'compare_threshold' option ignored"
            )

        self.register_listener("art_set", self.process_album)

    def commands(self):
        # Embed command.
        embed_cmd = ui.Subcommand(
            "embedart", help="embed image files into file metadata"
        )
        embed_cmd.parser.add_option(
            "-f", "--file", metavar="PATH", help="the image file to embed"
        )

        embed_cmd.parser.add_option(
            "-y", "--yes", action="store_true", help="skip confirmation"
        )

        embed_cmd.parser.add_option(
            "-u",
            "--url",
            metavar="URL",
            help="the URL of the image file to embed",
        )

        maxwidth = self.config["maxwidth"].get(int)
        quality = self.config["quality"].get(int)
        compare_threshold = self.config["compare_threshold"].get(int)
        ifempty = self.config["ifempty"].get(bool)

        def embed_func(lib, opts, args):
            if opts.file:
                imagepath = normpath(opts.file)
                if not os.path.isfile(syspath(imagepath)):
                    raise ui.UserError(
                        "image file {} not found".format(
                            displayable_path(imagepath)
                        )
                    )

                items = lib.items(decargs(args))

                # Confirm with user.
                if not opts.yes and not _confirm(items, not opts.file):
                    return

                for item in items:
                    art.embed_item(
                        self._log,
                        item,
                        imagepath,
                        maxwidth,
                        None,
                        compare_threshold,
                        ifempty,
                        quality=quality,
                    )
            elif opts.url:
                try:
                    response = requests.get(opts.url, timeout=5)
                    response.raise_for_status()
                except requests.exceptions.RequestException as e:
                    self._log.error(str(e))
                    return
                extension = guess_extension(response.headers["Content-Type"])
                if extension is None:
                    self._log.error("Invalid image file")
                    return
                file = f"image{extension}"
                tempimg = os.path.join(tempfile.gettempdir(), file)
                try:
                    with open(tempimg, "wb") as f:
                        f.write(response.content)
                except Exception as e:
                    self._log.error("Unable to save image: {}", e)
                    return
                items = lib.items(decargs(args))
                # Confirm with user.
                if not opts.yes and not _confirm(items, not opts.url):
                    os.remove(tempimg)
                    return
                for item in items:
                    art.embed_item(
                        self._log,
                        item,
                        tempimg,
                        maxwidth,
                        None,
                        compare_threshold,
                        ifempty,
                        quality=quality,
                    )
                os.remove(tempimg)
            else:
                albums = lib.albums(decargs(args))
                # Confirm with user.
                if not opts.yes and not _confirm(albums, not opts.file):
                    return
                for album in albums:
                    art.embed_album(
                        self._log,
                        album,
                        maxwidth,
                        False,
                        compare_threshold,
                        ifempty,
                        quality=quality,
                    )
                    self.remove_artfile(album)

        embed_cmd.func = embed_func

        # Extract command.
        extract_cmd = ui.Subcommand(
            "extractart",
            help="extract an image from file metadata",
        )
        extract_cmd.parser.add_option(
            "-o",
            dest="outpath",
            help="image output file",
        )
        extract_cmd.parser.add_option(
            "-n",
            dest="filename",
            help="image filename to create for all matched albums",
        )
        extract_cmd.parser.add_option(
            "-a",
            dest="associate",
            action="store_true",
            help="associate the extracted images with the album",
        )

        def extract_func(lib, opts, args):
            if opts.outpath:
                art.extract_first(
                    self._log, normpath(opts.outpath), lib.items(decargs(args))
                )
            else:
                filename = bytestring_path(
                    opts.filename or config["art_filename"].get()
                )
                if os.path.dirname(filename) != b"":
                    self._log.error(
                        "Only specify a name rather than a path for -n"
                    )
                    return
                for album in lib.albums(decargs(args)):
                    artpath = normpath(os.path.join(album.path, filename))
                    artpath = art.extract_first(
                        self._log, artpath, album.items()
                    )
                    if artpath and opts.associate:
                        album.set_art(artpath)
                        album.store()

        extract_cmd.func = extract_func

        # Clear command.
        clear_cmd = ui.Subcommand(
            "clearart",
            help="remove images from file metadata",
        )
        clear_cmd.parser.add_option(
            "-y", "--yes", action="store_true", help="skip confirmation"
        )

        def clear_func(lib, opts, args):
            items = lib.items(decargs(args))
            # Confirm with user.
            if not opts.yes and not _confirm(items, False):
                return
            art.clear(self._log, lib, decargs(args))

        clear_cmd.func = clear_func

        return [embed_cmd, extract_cmd, clear_cmd]

    def process_album(self, album):
        """Automatically embed art after art has been set"""
        if self.config["auto"] and ui.should_write():
            max_width = self.config["maxwidth"].get(int)
            art.embed_album(
                self._log,
                album,
                max_width,
                True,
                self.config["compare_threshold"].get(int),
                self.config["ifempty"].get(bool),
            )
            self.remove_artfile(album)

    def remove_artfile(self, album):
        """Possibly delete the album art file for an album (if the
        appropriate configuration option is enabled).
        """
        if self.config["remove_art_file"] and album.artpath:
            if os.path.isfile(syspath(album.artpath)):
                self._log.debug("Removing album art file for {0}", album)
                os.remove(syspath(album.artpath))
                album.artpath = None
                album.store()
