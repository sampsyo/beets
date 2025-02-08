# This file is part of beets.
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

"""Adds support for ipfs. Requires go-ipfs and a running ipfs daemon"""

import os
import shutil
import subprocess
import tempfile

from beets import config, library, ui, util
from beets.plugins import BeetsPlugin
from beets.util import syspath


class IPFSPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()
        self.config.add(
            {
                "auto": True,
                "nocopy": False,
            }
        )

        if self.config["auto"]:
            self.import_stages = [self.auto_add]

    def commands(self):
        cmd = ui.Subcommand("ipfs", help="interact with ipfs")
        cmd.parser.add_option(
            "-a", "--add", dest="add", action="store_true", help="Add to ipfs"
        )
        cmd.parser.add_option(
            "-g", "--get", dest="get", action="store_true", help="Get from ipfs"
        )
        cmd.parser.add_option(
            "-p",
            "--publish",
            dest="publish",
            action="store_true",
            help="Publish local library to ipfs",
        )
        cmd.parser.add_option(
            "-i",
            "--import",
            dest="_import",
            action="store_true",
            help="Import remote library from ipfs",
        )
        cmd.parser.add_option(
            "-l",
            "--list",
            dest="_list",
            action="store_true",
            help="Query imported libraries",
        )
        cmd.parser.add_option(
            "-m",
            "--play",
            dest="play",
            action="store_true",
            help="Play music from remote libraries",
        )

        def func(lib, opts, args):
            if opts.add:
                for album in lib.albums(ui.decargs(args)):
                    if len(album.items()) == 0:
                        self._log.info(
                            "{0} does not contain items, aborting", album
                        )

                    self.ipfs_add(album)
                    album.store()

            if opts.get:
                self.ipfs_get(lib, ui.decargs(args))

            if opts.publish:
                self.ipfs_publish(lib)

            if opts._import:
                self.ipfs_import(lib, ui.decargs(args))

            if opts._list:
                self.ipfs_list(lib, ui.decargs(args))

            if opts.play:
                self.ipfs_play(lib, opts, ui.decargs(args))

        cmd.func = func
        return [cmd]

    def auto_add(self, session, task):
        if task.is_album:
            if self.ipfs_add(task.album):
                task.album.store()

    def ipfs_play(self, lib, opts, args):
        from beetsplug.play import PlayPlugin

        jlib = self.get_remote_lib(lib)
        player = PlayPlugin()
        config["play"]["relative_to"] = None
        player.album = True
        player.play_music(jlib, player, args)

    def ipfs_add(self, album):
        try:
            album_dir = album.item_dir()
        except AttributeError:
            return False
        try:
            if album.ipfs:
                self._log.debug("{0} already added", album_dir)
                # Already added to ipfs
                return False
        except AttributeError:
            pass

        self._log.info("Adding {0} to ipfs", album_dir)

        if self.config["nocopy"]:
            cmd = "ipfs add --nocopy -q -r".split()
        else:
            cmd = "ipfs add -q -r".split()
        cmd.append(album_dir)
        try:
            output = util.command_output(cmd).stdout.split()
        except (OSError, subprocess.CalledProcessError) as exc:
            self._log.error("Failed to add {0}, error: {1}", album_dir, exc)
            return False
        length = len(output)

        for linenr, line in enumerate(output):
            line = line.strip()
            if linenr == length - 1:
                # last printed line is the album hash
                self._log.info("album: {0}", line)
                album.ipfs = line
            else:
                try:
                    item = album.items()[linenr]
                    self._log.info("item: {0}", line)
                    item.ipfs = line
                    item.store()
                except IndexError:
                    # if there's non music files in the to-add folder they'll
                    # get ignored here
                    pass

        return True

    def ipfs_get(self, lib, query):
        query = query[0]
        # Check if query is a hash
        # TODO: generalize to other hashes; probably use a multihash
        # implementation
        if query.startswith("Qm") and len(query) == 46:
            self.ipfs_get_from_hash(lib, query)
        else:
            albums = self.query(lib, query)
            for album in albums:
                self.ipfs_get_from_hash(lib, album.ipfs)

    def ipfs_get_from_hash(self, lib, _hash):
        try:
            cmd = "ipfs get".split()
            cmd.append(_hash)
            util.command_output(cmd)
        except (OSError, subprocess.CalledProcessError) as err:
            self._log.error(
                "Failed to get {0} from ipfs.\n{1}", _hash, err.output
            )
            return False

        self._log.info("Getting {0} from ipfs", _hash)
        imp = ui.commands.TerminalImportSession(
            lib, loghandler=None, query=None, paths=[_hash]
        )
        imp.run()
        # This uses a relative path, hence we cannot use util.syspath(_hash,
        # prefix=True). However, that should be fine since the hash will not
        # exceed MAX_PATH.
        shutil.rmtree(syspath(_hash, prefix=False))

    def ipfs_publish(self, lib):
        with tempfile.NamedTemporaryFile() as tmp:
            self.ipfs_added_albums(lib, tmp.name)
            try:
                if self.config["nocopy"]:
                    cmd = "ipfs add --nocopy -q ".split()
                else:
                    cmd = "ipfs add -q ".split()
                cmd.append(tmp.name)
                output = util.command_output(cmd).stdout
            except (OSError, subprocess.CalledProcessError) as err:
                msg = f"Failed to publish library. Error: {err}"
                self._log.error(msg)
                return False
            self._log.info("hash of library: {0}", output)

    def ipfs_import(self, lib, args):
        _hash = args[0]
        if len(args) > 1:
            lib_name = args[1]
        else:
            lib_name = _hash
        lib_root = os.path.dirname(lib.path)
        remote_libs = os.path.join(lib_root, b"remotes")
        if not os.path.exists(remote_libs):
            try:
                os.makedirs(remote_libs)
            except OSError as e:
                msg = f"Could not create {remote_libs}. Error: {e}"
                self._log.error(msg)
                return False
        path = os.path.join(remote_libs, lib_name.encode() + b".db")
        if not os.path.exists(path):
            cmd = f"ipfs get {_hash} -o".split()
            cmd.append(path)
            try:
                util.command_output(cmd)
            except (OSError, subprocess.CalledProcessError):
                self._log.error(f"Could not import {_hash}")
                return False

        # add all albums from remotes into a combined library
        jpath = os.path.join(remote_libs, b"joined.db")
        jlib = library.Library(jpath)
        nlib = library.Library(path)
        for album in nlib.albums():
            if not self.already_added(album, jlib):
                new_album = []
                for item in album.items():
                    item.id = None
                    new_album.append(item)
                added_album = jlib.add_album(new_album)
                added_album.ipfs = album.ipfs
                added_album.store()

    def already_added(self, check, jlib):
        for jalbum in jlib.albums():
            if jalbum.mb_albumid == check.mb_albumid:
                return True
        return False

    def ipfs_list(self, lib, args):
        fmt = config["format_album"].get()
        try:
            albums = self.query(lib, args)
        except OSError:
            ui.print_("No imported libraries yet.")
            return

        for album in albums:
            ui.print_(format(album, fmt), " : ", album.ipfs.decode())

    def query(self, lib, args):
        rlib = self.get_remote_lib(lib)
        albums = rlib.albums(args)
        return albums

    def get_remote_lib(self, lib):
        lib_root = os.path.dirname(lib.path)
        remote_libs = os.path.join(lib_root, b"remotes")
        path = os.path.join(remote_libs, b"joined.db")
        if not os.path.isfile(path):
            raise OSError
        return library.Library(path)

    def ipfs_added_albums(self, rlib, tmpname):
        """Returns a new library with only albums/items added to ipfs"""
        tmplib = library.Library(tmpname)
        for album in rlib.albums():
            try:
                if album.ipfs:
                    self.create_new_album(album, tmplib)
            except AttributeError:
                pass
        return tmplib

    def create_new_album(self, album, tmplib):
        items = []
        for item in album.items():
            try:
                if not item.ipfs:
                    break
            except AttributeError:
                pass
            item_path = os.path.basename(item.path).decode(
                util._fsencoding(), "ignore"
            )
            # Clear current path from item
            item.path = f"/ipfs/{album.ipfs}/{item_path}"

            item.id = None
            items.append(item)
        if len(items) < 1:
            return False
        self._log.info("Adding '{0}' to temporary library", album)
        new_album = tmplib.add_album(items)
        new_album.ipfs = album.ipfs
        new_album.store(inherit=False)
