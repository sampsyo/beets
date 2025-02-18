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

"""A clone of the Music Player Daemon (MPD) that plays music from a
Beets library. Attempts to implement a compatible protocol to allow
use of the wide range of MPD clients.
"""

import inspect
import math
import random
import re
import socket
import sys
import time
import traceback
from string import Template
from typing import TYPE_CHECKING

import beets
import beets.ui
from beets import dbcore, vfs
from beets.library import Item
from beets.plugins import BeetsPlugin
from beets.util import as_string, bluelet

if TYPE_CHECKING:
    from beets.dbcore.query import Query

PROTOCOL_VERSION = "0.16.0"
BUFSIZE = 1024

HELLO = "OK MPD %s" % PROTOCOL_VERSION
CLIST_BEGIN = "command_list_begin"
CLIST_VERBOSE_BEGIN = "command_list_ok_begin"
CLIST_END = "command_list_end"
RESP_OK = "OK"
RESP_CLIST_VERBOSE = "list_OK"
RESP_ERR = "ACK"

NEWLINE = "\n"

ERROR_NOT_LIST = 1
ERROR_ARG = 2
ERROR_PASSWORD = 3
ERROR_PERMISSION = 4
ERROR_UNKNOWN = 5
ERROR_NO_EXIST = 50
ERROR_PLAYLIST_MAX = 51
ERROR_SYSTEM = 52
ERROR_PLAYLIST_LOAD = 53
ERROR_UPDATE_ALREADY = 54
ERROR_PLAYER_SYNC = 55
ERROR_EXIST = 56

VOLUME_MIN = 0
VOLUME_MAX = 100

SAFE_COMMANDS = (
    # Commands that are available when unauthenticated.
    "close",
    "commands",
    "notcommands",
    "password",
    "ping",
)

# List of subsystems/events used by the `idle` command.
SUBSYSTEMS = [
    "update",
    "player",
    "mixer",
    "options",
    "playlist",
    "database",
    # Related to unsupported commands:
    "stored_playlist",
    "output",
    "subscription",
    "sticker",
    "message",
    "partition",
]


# Gstreamer import error.
class NoGstreamerError(Exception):
    pass


# Error-handling, exceptions, parameter parsing.


class BPDError(Exception):
    """An error that should be exposed to the client to the BPD
    server.
    """

    def __init__(self, code, message, cmd_name="", index=0):
        self.code = code
        self.message = message
        self.cmd_name = cmd_name
        self.index = index

    template = Template("$resp [$code@$index] {$cmd_name} $message")

    def response(self):
        """Returns a string to be used as the response code for the
        erring command.
        """
        return self.template.substitute(
            {
                "resp": RESP_ERR,
                "code": self.code,
                "index": self.index,
                "cmd_name": self.cmd_name,
                "message": self.message,
            }
        )


def make_bpd_error(s_code, s_message):
    """Create a BPDError subclass for a static code and message."""

    class NewBPDError(BPDError):
        code = s_code
        message = s_message
        cmd_name = ""
        index = 0

        def __init__(self):
            pass

    return NewBPDError


ArgumentTypeError = make_bpd_error(ERROR_ARG, "invalid type for argument")
ArgumentIndexError = make_bpd_error(ERROR_ARG, "argument out of range")
ArgumentNotFoundError = make_bpd_error(ERROR_NO_EXIST, "argument not found")


def cast_arg(t, val):
    """Attempts to call t on val, raising a ArgumentTypeError
    on ValueError.

    If 't' is the special string 'intbool', attempts to cast first
    to an int and then to a bool (i.e., 1=True, 0=False).
    """
    if t == "intbool":
        return cast_arg(bool, cast_arg(int, val))
    else:
        try:
            return t(val)
        except ValueError:
            raise ArgumentTypeError()


class BPDCloseError(Exception):
    """Raised by a command invocation to indicate that the connection
    should be closed.
    """


class BPDIdleError(Exception):
    """Raised by a command to indicate the client wants to enter the idle state
    and should be notified when a relevant event happens.
    """

    def __init__(self, subsystems):
        super().__init__()
        self.subsystems = set(subsystems)


# Generic server infrastructure, implementing the basic protocol.


class BaseServer:
    """A MPD-compatible music player server.

    The functions with the `cmd_` prefix are invoked in response to
    client commands. For instance, if the client says `status`,
    `cmd_status` will be invoked. The arguments to the client's commands
    are used as function arguments following the connection issuing the
    command. The functions may send data on the connection. They may
    also raise BPDError exceptions to report errors.

    This is a generic superclass and doesn't support many commands.
    """

    def __init__(self, host, port, password, ctrl_port, log, ctrl_host=None):
        """Create a new server bound to address `host` and listening
        on port `port`. If `password` is given, it is required to do
        anything significant on the server.
        A separate control socket is established listening to `ctrl_host` on
        port `ctrl_port` which is used to forward notifications from the player
        and can be sent debug commands (e.g. using netcat).
        """
        self.host, self.port, self.password = host, port, password
        self.ctrl_host, self.ctrl_port = ctrl_host or host, ctrl_port
        self.ctrl_sock = None
        self._log = log

        # Default server values.
        self.random = False
        self.repeat = False
        self.consume = False
        self.single = False
        self.volume = VOLUME_MAX
        self.crossfade = 0
        self.mixrampdb = 0.0
        self.mixrampdelay = float("nan")
        self.replay_gain_mode = "off"
        self.playlist = []
        self.playlist_version = 0
        self.current_index = -1
        self.paused = False
        self.error = None

        # Current connections
        self.connections = set()

        # Object for random numbers generation
        self.random_obj = random.Random()

    def connect(self, conn):
        """A new client has connected."""
        self.connections.add(conn)

    def disconnect(self, conn):
        """Client has disconnected; clean up residual state."""
        self.connections.remove(conn)

    def run(self):
        """Block and start listening for connections from clients. An
        interrupt (^C) closes the server.
        """
        self.startup_time = time.time()

        def start():
            yield bluelet.spawn(
                bluelet.server(
                    self.ctrl_host,
                    self.ctrl_port,
                    ControlConnection.handler(self),
                )
            )
            yield bluelet.server(
                self.host, self.port, MPDConnection.handler(self)
            )

        bluelet.run(start())

    def dispatch_events(self):
        """If any clients have idle events ready, send them."""
        # We need a copy of `self.connections` here since clients might
        # disconnect once we try and send to them, changing `self.connections`.
        for conn in list(self.connections):
            yield bluelet.spawn(conn.send_notifications())

    def _ctrl_send(self, message):
        """Send some data over the control socket.
        If it's our first time, open the socket. The message should be a
        string without a terminal newline.
        """
        if not self.ctrl_sock:
            self.ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.ctrl_sock.connect((self.ctrl_host, self.ctrl_port))
        self.ctrl_sock.sendall((message + "\n").encode("utf-8"))

    def _send_event(self, event):
        """Notify subscribed connections of an event."""
        for conn in self.connections:
            conn.notify(event)

    def _item_info(self, item):
        """An abstract method that should response lines containing a
        single song's metadata.
        """
        raise NotImplementedError

    def _item_id(self, item):
        """An abstract method returning the integer id for an item."""
        raise NotImplementedError

    def _id_to_index(self, track_id):
        """Searches the playlist for a song with the given id and
        returns its index in the playlist.
        """
        track_id = cast_arg(int, track_id)
        for index, track in enumerate(self.playlist):
            if self._item_id(track) == track_id:
                return index
        # Loop finished with no track found.
        raise ArgumentNotFoundError()

    def _random_idx(self):
        """Returns a random index different from the current one.
        If there are no songs in the playlist it returns -1.
        If there is only one song in the playlist it returns 0.
        """
        if len(self.playlist) < 2:
            return len(self.playlist) - 1
        new_index = self.random_obj.randint(0, len(self.playlist) - 1)
        while new_index == self.current_index:
            new_index = self.random_obj.randint(0, len(self.playlist) - 1)
        return new_index

    def _succ_idx(self):
        """Returns the index for the next song to play.
        It also considers random, single and repeat flags.
        No boundaries are checked.
        """
        if self.repeat and self.single:
            return self.current_index
        if self.random:
            return self._random_idx()
        return self.current_index + 1

    def _prev_idx(self):
        """Returns the index for the previous song to play.
        It also considers random and repeat flags.
        No boundaries are checked.
        """
        if self.repeat and self.single:
            return self.current_index
        if self.random:
            return self._random_idx()
        return self.current_index - 1

    def cmd_ping(self, conn):
        """Succeeds."""
        pass

    def cmd_idle(self, conn, *subsystems):
        subsystems = subsystems or SUBSYSTEMS
        for system in subsystems:
            if system not in SUBSYSTEMS:
                raise BPDError(ERROR_ARG, f"Unrecognised idle event: {system}")
        raise BPDIdleError(subsystems)  # put the connection into idle mode

    def cmd_kill(self, conn):
        """Exits the server process."""
        sys.exit(0)

    def cmd_close(self, conn):
        """Closes the connection."""
        raise BPDCloseError()

    def cmd_password(self, conn, password):
        """Attempts password authentication."""
        if password == self.password:
            conn.authenticated = True
        else:
            conn.authenticated = False
            raise BPDError(ERROR_PASSWORD, "incorrect password")

    def cmd_commands(self, conn):
        """Lists the commands available to the user."""
        if self.password and not conn.authenticated:
            # Not authenticated. Show limited list of commands.
            for cmd in SAFE_COMMANDS:
                yield "command: " + cmd

        else:
            # Authenticated. Show all commands.
            for func in dir(self):
                if func.startswith("cmd_"):
                    yield "command: " + func[4:]

    def cmd_notcommands(self, conn):
        """Lists all unavailable commands."""
        if self.password and not conn.authenticated:
            # Not authenticated. Show privileged commands.
            for func in dir(self):
                if func.startswith("cmd_"):
                    cmd = func[4:]
                    if cmd not in SAFE_COMMANDS:
                        yield "command: " + cmd

        else:
            # Authenticated. No commands are unavailable.
            pass

    def cmd_status(self, conn):
        """Returns some status information for use with an
        implementation of cmd_status.

        Gives a list of response-lines for: volume, repeat, random,
        playlist, playlistlength, and xfade.
        """
        yield (
            "repeat: " + str(int(self.repeat)),
            "random: " + str(int(self.random)),
            "consume: " + str(int(self.consume)),
            "single: " + str(int(self.single)),
            "playlist: " + str(self.playlist_version),
            "playlistlength: " + str(len(self.playlist)),
            "mixrampdb: " + str(self.mixrampdb),
        )

        if self.volume > 0:
            yield "volume: " + str(self.volume)

        if not math.isnan(self.mixrampdelay):
            yield "mixrampdelay: " + str(self.mixrampdelay)
        if self.crossfade > 0:
            yield "xfade: " + str(self.crossfade)

        if self.current_index == -1:
            state = "stop"
        elif self.paused:
            state = "pause"
        else:
            state = "play"
        yield "state: " + state

        if self.current_index != -1:  # i.e., paused or playing
            current_id = self._item_id(self.playlist[self.current_index])
            yield "song: " + str(self.current_index)
            yield "songid: " + str(current_id)
            if len(self.playlist) > self.current_index + 1:
                # If there's a next song, report its index too.
                next_id = self._item_id(self.playlist[self.current_index + 1])
                yield "nextsong: " + str(self.current_index + 1)
                yield "nextsongid: " + str(next_id)

        if self.error:
            yield "error: " + self.error

    def cmd_clearerror(self, conn):
        """Removes the persistent error state of the server. This
        error is set when a problem arises not in response to a
        command (for instance, when playing a file).
        """
        self.error = None

    def cmd_random(self, conn, state):
        """Set or unset random (shuffle) mode."""
        self.random = cast_arg("intbool", state)
        self._send_event("options")

    def cmd_repeat(self, conn, state):
        """Set or unset repeat mode."""
        self.repeat = cast_arg("intbool", state)
        self._send_event("options")

    def cmd_consume(self, conn, state):
        """Set or unset consume mode."""
        self.consume = cast_arg("intbool", state)
        self._send_event("options")

    def cmd_single(self, conn, state):
        """Set or unset single mode."""
        # TODO support oneshot in addition to 0 and 1 [MPD 0.20]
        self.single = cast_arg("intbool", state)
        self._send_event("options")

    def cmd_setvol(self, conn, vol):
        """Set the player's volume level (0-100)."""
        vol = cast_arg(int, vol)
        if vol < VOLUME_MIN or vol > VOLUME_MAX:
            raise BPDError(ERROR_ARG, "volume out of range")
        self.volume = vol
        self._send_event("mixer")

    def cmd_volume(self, conn, vol_delta):
        """Deprecated command to change the volume by a relative amount."""
        vol_delta = cast_arg(int, vol_delta)
        return self.cmd_setvol(conn, self.volume + vol_delta)

    def cmd_crossfade(self, conn, crossfade):
        """Set the number of seconds of crossfading."""
        crossfade = cast_arg(int, crossfade)
        if crossfade < 0:
            raise BPDError(ERROR_ARG, "crossfade time must be nonnegative")
        self._log.warning("crossfade is not implemented in bpd")
        self.crossfade = crossfade
        self._send_event("options")

    def cmd_mixrampdb(self, conn, db):
        """Set the mixramp normalised max volume in dB."""
        db = cast_arg(float, db)
        if db > 0:
            raise BPDError(ERROR_ARG, "mixrampdb time must be negative")
        self._log.warning("mixramp is not implemented in bpd")
        self.mixrampdb = db
        self._send_event("options")

    def cmd_mixrampdelay(self, conn, delay):
        """Set the mixramp delay in seconds."""
        delay = cast_arg(float, delay)
        if delay < 0:
            raise BPDError(ERROR_ARG, "mixrampdelay time must be nonnegative")
        self._log.warning("mixramp is not implemented in bpd")
        self.mixrampdelay = delay
        self._send_event("options")

    def cmd_replay_gain_mode(self, conn, mode):
        """Set the replay gain mode."""
        if mode not in ["off", "track", "album", "auto"]:
            raise BPDError(ERROR_ARG, "Unrecognised replay gain mode")
        self._log.warning("replay gain is not implemented in bpd")
        self.replay_gain_mode = mode
        self._send_event("options")

    def cmd_replay_gain_status(self, conn):
        """Get the replaygain mode."""
        yield "replay_gain_mode: " + str(self.replay_gain_mode)

    def cmd_clear(self, conn):
        """Clear the playlist."""
        self.playlist = []
        self.playlist_version += 1
        self.cmd_stop(conn)
        self._send_event("playlist")

    def cmd_delete(self, conn, index):
        """Remove the song at index from the playlist."""
        index = cast_arg(int, index)
        try:
            del self.playlist[index]
        except IndexError:
            raise ArgumentIndexError()
        self.playlist_version += 1

        if self.current_index == index:  # Deleted playing song.
            self.cmd_stop(conn)
        elif index < self.current_index:  # Deleted before playing.
            # Shift playing index down.
            self.current_index -= 1
        self._send_event("playlist")

    def cmd_deleteid(self, conn, track_id):
        self.cmd_delete(conn, self._id_to_index(track_id))

    def cmd_move(self, conn, idx_from, idx_to):
        """Move a track in the playlist."""
        idx_from = cast_arg(int, idx_from)
        idx_to = cast_arg(int, idx_to)
        try:
            track = self.playlist.pop(idx_from)
            self.playlist.insert(idx_to, track)
        except IndexError:
            raise ArgumentIndexError()

        # Update currently-playing song.
        if idx_from == self.current_index:
            self.current_index = idx_to
        elif idx_from < self.current_index <= idx_to:
            self.current_index -= 1
        elif idx_from > self.current_index >= idx_to:
            self.current_index += 1

        self.playlist_version += 1
        self._send_event("playlist")

    def cmd_moveid(self, conn, idx_from, idx_to):
        idx_from = self._id_to_index(idx_from)
        return self.cmd_move(conn, idx_from, idx_to)

    def cmd_swap(self, conn, i, j):
        """Swaps two tracks in the playlist."""
        i = cast_arg(int, i)
        j = cast_arg(int, j)
        try:
            track_i = self.playlist[i]
            track_j = self.playlist[j]
        except IndexError:
            raise ArgumentIndexError()

        self.playlist[j] = track_i
        self.playlist[i] = track_j

        # Update currently-playing song.
        if self.current_index == i:
            self.current_index = j
        elif self.current_index == j:
            self.current_index = i

        self.playlist_version += 1
        self._send_event("playlist")

    def cmd_swapid(self, conn, i_id, j_id):
        i = self._id_to_index(i_id)
        j = self._id_to_index(j_id)
        return self.cmd_swap(conn, i, j)

    def cmd_urlhandlers(self, conn):
        """Indicates supported URL schemes. None by default."""
        pass

    def cmd_playlistinfo(self, conn, index=None):
        """Gives metadata information about the entire playlist or a
        single track, given by its index.
        """
        if index is None:
            for track in self.playlist:
                yield self._item_info(track)
        else:
            indices = self._parse_range(index, accept_single_number=True)
            try:
                tracks = [self.playlist[i] for i in indices]
            except IndexError:
                raise ArgumentIndexError()
            for track in tracks:
                yield self._item_info(track)

    def cmd_playlistid(self, conn, track_id=None):
        if track_id is not None:
            track_id = cast_arg(int, track_id)
            track_id = self._id_to_index(track_id)
        return self.cmd_playlistinfo(conn, track_id)

    def cmd_plchanges(self, conn, version):
        """Sends playlist changes since the given version.

        This is a "fake" implementation that ignores the version and
        just returns the entire playlist (rather like version=0). This
        seems to satisfy many clients.
        """
        return self.cmd_playlistinfo(conn)

    def cmd_plchangesposid(self, conn, version):
        """Like plchanges, but only sends position and id.

        Also a dummy implementation.
        """
        for idx, track in enumerate(self.playlist):
            yield "cpos: " + str(idx)
            yield "Id: " + str(track.id)

    def cmd_currentsong(self, conn):
        """Sends information about the currently-playing song."""
        if self.current_index != -1:  # -1 means stopped.
            track = self.playlist[self.current_index]
            yield self._item_info(track)

    def cmd_next(self, conn):
        """Advance to the next song in the playlist."""
        old_index = self.current_index
        self.current_index = self._succ_idx()
        if self.consume:
            # TODO how does consume interact with single+repeat?
            self.playlist.pop(old_index)
            if self.current_index > old_index:
                self.current_index -= 1
            self.playlist_version += 1
            self._send_event("playlist")
        if self.current_index >= len(self.playlist):
            # Fallen off the end. Move to stopped state or loop.
            if self.repeat:
                self.current_index = -1
                return self.cmd_play(conn)
            return self.cmd_stop(conn)
        elif self.single and not self.repeat:
            return self.cmd_stop(conn)
        else:
            return self.cmd_play(conn)

    def cmd_previous(self, conn):
        """Step back to the last song."""
        old_index = self.current_index
        self.current_index = self._prev_idx()
        if self.consume:
            self.playlist.pop(old_index)
        if self.current_index < 0:
            if self.repeat:
                self.current_index = len(self.playlist) - 1
            else:
                self.current_index = 0
        return self.cmd_play(conn)

    def cmd_pause(self, conn, state=None):
        """Set the pause state playback."""
        if state is None:
            self.paused = not self.paused  # Toggle.
        else:
            self.paused = cast_arg("intbool", state)
        self._send_event("player")

    def cmd_play(self, conn, index=-1):
        """Begin playback, possibly at a specified playlist index."""
        index = cast_arg(int, index)

        if index < -1 or index >= len(self.playlist):
            raise ArgumentIndexError()

        if index == -1:  # No index specified: start where we are.
            if not self.playlist:  # Empty playlist: stop immediately.
                return self.cmd_stop(conn)
            if self.current_index == -1:  # No current song.
                self.current_index = 0  # Start at the beginning.
            # If we have a current song, just stay there.

        else:  # Start with the specified index.
            self.current_index = index

        self.paused = False
        self._send_event("player")

    def cmd_playid(self, conn, track_id=0):
        track_id = cast_arg(int, track_id)
        if track_id == -1:
            index = -1
        else:
            index = self._id_to_index(track_id)
        return self.cmd_play(conn, index)

    def cmd_stop(self, conn):
        """Stop playback."""
        self.current_index = -1
        self.paused = False
        self._send_event("player")

    def cmd_seek(self, conn, index, pos):
        """Seek to a specified point in a specified song."""
        index = cast_arg(int, index)
        if index < 0 or index >= len(self.playlist):
            raise ArgumentIndexError()
        self.current_index = index
        self._send_event("player")

    def cmd_seekid(self, conn, track_id, pos):
        index = self._id_to_index(track_id)
        return self.cmd_seek(conn, index, pos)

    # Additions to the MPD protocol.

    def cmd_crash(self, conn):
        """Deliberately trigger a TypeError for testing purposes.
        We want to test that the server properly responds with ERROR_SYSTEM
        without crashing, and that this is not treated as ERROR_ARG (since it
        is caused by a programming error, not a protocol error).
        """
        raise TypeError


class Connection:
    """A connection between a client and the server."""

    def __init__(self, server, sock):
        """Create a new connection for the accepted socket `client`."""
        self.server = server
        self.sock = sock
        self.address = "{}:{}".format(*sock.sock.getpeername())

    def debug(self, message, kind=" "):
        """Log a debug message about this connection."""
        self.server._log.debug("{}[{}]: {}", kind, self.address, message)

    def run(self):
        pass

    def send(self, lines):
        """Send lines, which which is either a single string or an
        iterable consisting of strings, to the client. A newline is
        added after every string. Returns a Bluelet event that sends
        the data.
        """
        if isinstance(lines, str):
            lines = [lines]
        out = NEWLINE.join(lines) + NEWLINE
        for line in out.split(NEWLINE)[:-1]:
            self.debug(line, kind=">")
        if isinstance(out, str):
            out = out.encode("utf-8")
        return self.sock.sendall(out)

    @classmethod
    def handler(cls, server):
        def _handle(sock):
            """Creates a new `Connection` and runs it."""
            return cls(server, sock).run()

        return _handle


class MPDConnection(Connection):
    """A connection that receives commands from an MPD-compatible client."""

    def __init__(self, server, sock):
        """Create a new connection for the accepted socket `client`."""
        super().__init__(server, sock)
        self.authenticated = False
        self.notifications = set()
        self.idle_subscriptions = set()

    def do_command(self, command):
        """A coroutine that runs the given command and sends an
        appropriate response."""
        try:
            yield bluelet.call(command.run(self))
        except BPDError as e:
            # Send the error.
            yield self.send(e.response())
        else:
            # Send success code.
            yield self.send(RESP_OK)

    def disconnect(self):
        """The connection has closed for any reason."""
        self.server.disconnect(self)
        self.debug("disconnected", kind="*")

    def notify(self, event):
        """Queue up an event for sending to this client."""
        self.notifications.add(event)

    def send_notifications(self, force_close_idle=False):
        """Send the client any queued events now."""
        pending = self.notifications.intersection(self.idle_subscriptions)
        try:
            for event in pending:
                yield self.send(f"changed: {event}")
            if pending or force_close_idle:
                self.idle_subscriptions = set()
                self.notifications = self.notifications.difference(pending)
                yield self.send(RESP_OK)
        except bluelet.SocketClosedError:
            self.disconnect()  # Client disappeared.

    def run(self):
        """Send a greeting to the client and begin processing commands
        as they arrive.
        """
        self.debug("connected", kind="*")
        self.server.connect(self)
        yield self.send(HELLO)

        clist = None  # Initially, no command list is being constructed.
        while True:
            line = yield self.sock.readline()
            if not line:
                self.disconnect()  # Client disappeared.
                break
            line = line.strip()
            if not line:
                err = BPDError(ERROR_UNKNOWN, "No command given")
                yield self.send(err.response())
                self.disconnect()  # Client sent a blank line.
                break
            line = line.decode("utf8")  # MPD protocol uses UTF-8.
            for line in line.split(NEWLINE):
                self.debug(line, kind="<")

            if self.idle_subscriptions:
                # The connection is in idle mode.
                if line == "noidle":
                    yield bluelet.call(self.send_notifications(True))
                else:
                    err = BPDError(
                        ERROR_UNKNOWN, f"Got command while idle: {line}"
                    )
                    yield self.send(err.response())
                    break
                continue
            if line == "noidle":
                # When not in idle, this command sends no response.
                continue

            if clist is not None:
                # Command list already opened.
                if line == CLIST_END:
                    yield bluelet.call(self.do_command(clist))
                    clist = None  # Clear the command list.
                    yield bluelet.call(self.server.dispatch_events())
                else:
                    clist.append(Command(line))

            elif line == CLIST_BEGIN or line == CLIST_VERBOSE_BEGIN:
                # Begin a command list.
                clist = CommandList([], line == CLIST_VERBOSE_BEGIN)

            else:
                # Ordinary command.
                try:
                    yield bluelet.call(self.do_command(Command(line)))
                except BPDCloseError:
                    # Command indicates that the conn should close.
                    self.sock.close()
                    self.disconnect()  # Client explicitly closed.
                    return
                except BPDIdleError as e:
                    self.idle_subscriptions = e.subsystems
                    self.debug(
                        "awaiting: {}".format(" ".join(e.subsystems)), kind="z"
                    )
                yield bluelet.call(self.server.dispatch_events())


class ControlConnection(Connection):
    """A connection used to control BPD for debugging and internal events."""

    def __init__(self, server, sock):
        """Create a new connection for the accepted socket `client`."""
        super().__init__(server, sock)

    def debug(self, message, kind=" "):
        self.server._log.debug("CTRL {}[{}]: {}", kind, self.address, message)

    def run(self):
        """Listen for control commands and delegate to `ctrl_*` methods."""
        self.debug("connected", kind="*")
        while True:
            line = yield self.sock.readline()
            if not line:
                break  # Client disappeared.
            line = line.strip()
            if not line:
                break  # Client sent a blank line.
            line = line.decode("utf8")  # Protocol uses UTF-8.
            for line in line.split(NEWLINE):
                self.debug(line, kind="<")
            command = Command(line)
            try:
                func = command.delegate("ctrl_", self)
                yield bluelet.call(func(*command.args))
            except (AttributeError, TypeError) as e:
                yield self.send("ERROR: {}".format(e.args[0]))
            except Exception:
                yield self.send(
                    ["ERROR: server error", traceback.format_exc().rstrip()]
                )

    def ctrl_play_finished(self):
        """Callback from the player signalling a song finished playing."""
        yield bluelet.call(self.server.dispatch_events())

    def ctrl_profile(self):
        """Memory profiling for debugging."""
        from guppy import hpy

        heap = hpy().heap()
        yield self.send(heap)

    def ctrl_nickname(self, oldlabel, newlabel):
        """Rename a client in the log messages."""
        for c in self.server.connections:
            if c.address == oldlabel:
                c.address = newlabel
                break
        else:
            yield self.send(f"ERROR: no such client: {oldlabel}")


class Command:
    """A command issued by the client for processing by the server."""

    command_re = re.compile(r"^([^ \t]+)[ \t]*")
    arg_re = re.compile(r'"((?:\\"|[^"])+)"|([^ \t"]+)')

    def __init__(self, s):
        """Creates a new `Command` from the given string, `s`, parsing
        the string for command name and arguments.
        """
        command_match = self.command_re.match(s)
        self.name = command_match.group(1)

        self.args = []
        arg_matches = self.arg_re.findall(s[command_match.end() :])
        for match in arg_matches:
            if match[0]:
                # Quoted argument.
                arg = match[0]
                arg = arg.replace('\\"', '"').replace("\\\\", "\\")
            else:
                # Unquoted argument.
                arg = match[1]
            self.args.append(arg)

    def delegate(self, prefix, target, extra_args=0):
        """Get the target method that corresponds to this command.
        The `prefix` is prepended to the command name and then the resulting
        name is used to search `target` for a method with a compatible number
        of arguments.
        """
        # Attempt to get correct command function.
        func_name = prefix + self.name
        if not hasattr(target, func_name):
            raise AttributeError(f'unknown command "{self.name}"')
        func = getattr(target, func_name)

        argspec = inspect.getfullargspec(func)

        # Check that `func` is able to handle the number of arguments sent
        # by the client (so we can raise ERROR_ARG instead of ERROR_SYSTEM).
        # Maximum accepted arguments: argspec includes "self".
        max_args = len(argspec.args) - 1 - extra_args
        # Minimum accepted arguments: some arguments might be optional.
        min_args = max_args
        if argspec.defaults:
            min_args -= len(argspec.defaults)
        wrong_num = (len(self.args) > max_args) or (len(self.args) < min_args)
        # If the command accepts a variable number of arguments skip the check.
        if wrong_num and not argspec.varargs:
            raise TypeError(
                'wrong number of arguments for "{}"'.format(self.name),
                self.name,
            )

        return func

    def run(self, conn):
        """A coroutine that executes the command on the given
        connection.
        """
        try:
            # `conn` is an extra argument to all cmd handlers.
            func = self.delegate("cmd_", conn.server, extra_args=1)
        except AttributeError as e:
            raise BPDError(ERROR_UNKNOWN, e.args[0])
        except TypeError as e:
            raise BPDError(ERROR_ARG, e.args[0], self.name)

        # Ensure we have permission for this command.
        if (
            conn.server.password
            and not conn.authenticated
            and self.name not in SAFE_COMMANDS
        ):
            raise BPDError(ERROR_PERMISSION, "insufficient privileges")

        try:
            args = [conn] + self.args
            results = func(*args)
            if results:
                for data in results:
                    yield conn.send(data)

        except BPDError as e:
            # An exposed error. Set the command name and then let
            # the Connection handle it.
            e.cmd_name = self.name
            raise e

        except BPDCloseError:
            # An indication that the connection should close. Send
            # it on the Connection.
            raise

        except BPDIdleError:
            raise

        except Exception:
            # An "unintentional" error. Hide it from the client.
            conn.server._log.error("{}", traceback.format_exc())
            raise BPDError(ERROR_SYSTEM, "server error", self.name)


class CommandList(list[Command]):
    """A list of commands issued by the client for processing by the
    server. May be verbose, in which case the response is delimited, or
    not. Should be a list of `Command` objects.
    """

    def __init__(self, sequence=None, verbose=False):
        """Create a new `CommandList` from the given sequence of
        `Command`s. If `verbose`, this is a verbose command list.
        """
        if sequence:
            for item in sequence:
                self.append(item)
        self.verbose = verbose

    def run(self, conn):
        """Coroutine executing all the commands in this list."""
        for i, command in enumerate(self):
            try:
                yield bluelet.call(command.run(conn))
            except BPDError as e:
                # If the command failed, stop executing.
                e.index = i  # Give the error the correct index.
                raise e

            # Otherwise, possibly send the output delimiter if we're in a
            # verbose ("OK") command list.
            if self.verbose:
                yield conn.send(RESP_CLIST_VERBOSE)


# A subclass of the basic, protocol-handling server that actually plays
# music.


class Server(BaseServer):
    """An MPD-compatible server using GStreamer to play audio and beets
    to store its library.
    """

    def __init__(self, library, host, port, password, ctrl_port, log):
        try:
            from beetsplug.bpd import gstplayer
        except ImportError as e:
            # This is a little hacky, but it's the best I know for now.
            if e.args[0].endswith(" gst"):
                raise NoGstreamerError()
            else:
                raise
        log.info("Starting server...")
        super().__init__(host, port, password, ctrl_port, log)
        self.lib = library
        self.player = gstplayer.GstPlayer(self.play_finished)
        self.cmd_update(None)
        log.info("Server ready and listening on {}:{}".format(host, port))
        log.debug(
            "Listening for control signals on {}:{}".format(host, ctrl_port)
        )

    def run(self):
        self.player.run()
        super().run()

    def play_finished(self):
        """A callback invoked every time our player finishes a track."""
        self.cmd_next(None)
        self._ctrl_send("play_finished")

    # Metadata helper functions.

    def _item_info(self, item):
        info_lines = [
            "file: " + as_string(item.destination(relative_to_libdir=True)),
            "Time: " + str(int(item.length)),
            "duration: " + f"{item.length:.3f}",
            "Id: " + str(item.id),
        ]

        try:
            pos = self._id_to_index(item.id)
            info_lines.append("Pos: " + str(pos))
        except ArgumentNotFoundError:
            # Don't include position if not in playlist.
            pass

        for tagtype, field in self.tagtype_map.items():
            info_lines.append(
                "{}: {}".format(tagtype, str(getattr(item, field)))
            )

        return info_lines

    def _parse_range(self, items, accept_single_number=False):
        """Convert a range of positions to a list of item info.
        MPD specifies ranges as START:STOP (endpoint excluded) for some
        commands. Sometimes a single number can be provided instead.
        """
        try:
            start, stop = str(items).split(":", 1)
        except ValueError:
            if accept_single_number:
                return [cast_arg(int, items)]
            raise BPDError(ERROR_ARG, "bad range syntax")
        start = cast_arg(int, start)
        stop = cast_arg(int, stop)
        return range(start, stop)

    def _item_id(self, item):
        return item.id

    # Database updating.

    def cmd_update(self, conn, path="/"):
        """Updates the catalog to reflect the current database state."""
        # Path is ignored. Also, the real MPD does this asynchronously;
        # this is done inline.
        self._log.debug("Building directory tree...")
        self.tree = vfs.libtree(self.lib)
        self._log.debug("Finished building directory tree.")
        self.updated_time = time.time()
        self._send_event("update")
        self._send_event("database")

    # Path (directory tree) browsing.

    def _resolve_path(self, path):
        """Returns a VFS node or an item ID located at the path given.
        If the path does not exist, raises a
        """
        components = path.split("/")
        node = self.tree

        for component in components:
            if not component:
                continue

            if isinstance(node, int):
                # We're trying to descend into a file node.
                raise ArgumentNotFoundError()

            if component in node.files:
                node = node.files[component]
            elif component in node.dirs:
                node = node.dirs[component]
            else:
                raise ArgumentNotFoundError()

        return node

    def _path_join(self, p1, p2):
        """Smashes together two BPD paths."""
        out = p1 + "/" + p2
        return out.replace("//", "/").replace("//", "/")

    def cmd_lsinfo(self, conn, path="/"):
        """Sends info on all the items in the path."""
        node = self._resolve_path(path)
        if isinstance(node, int):
            # Trying to list a track.
            raise BPDError(ERROR_ARG, "this is not a directory")
        else:
            for name, itemid in iter(sorted(node.files.items())):
                item = self.lib.get_item(itemid)
                yield self._item_info(item)
            for name, _ in iter(sorted(node.dirs.items())):
                dirpath = self._path_join(path, name)
                if dirpath.startswith("/"):
                    # Strip leading slash (libmpc rejects this).
                    dirpath = dirpath[1:]
                yield "directory: %s" % dirpath

    def _listall(self, basepath, node, info=False):
        """Helper function for recursive listing. If info, show
        tracks' complete info; otherwise, just show items' paths.
        """
        if isinstance(node, int):
            # List a single file.
            if info:
                item = self.lib.get_item(node)
                yield self._item_info(item)
            else:
                yield "file: " + basepath
        else:
            # List a directory. Recurse into both directories and files.
            for name, itemid in sorted(node.files.items()):
                newpath = self._path_join(basepath, name)
                # "yield from"
                yield from self._listall(newpath, itemid, info)
            for name, subdir in sorted(node.dirs.items()):
                newpath = self._path_join(basepath, name)
                yield "directory: " + newpath
                yield from self._listall(newpath, subdir, info)

    def cmd_listall(self, conn, path="/"):
        """Send the paths all items in the directory, recursively."""
        return self._listall(path, self._resolve_path(path), False)

    def cmd_listallinfo(self, conn, path="/"):
        """Send info on all the items in the directory, recursively."""
        return self._listall(path, self._resolve_path(path), True)

    # Playlist manipulation.

    def _all_items(self, node):
        """Generator yielding all items under a VFS node."""
        if isinstance(node, int):
            # Could be more efficient if we built up all the IDs and
            # then issued a single SELECT.
            yield self.lib.get_item(node)
        else:
            # Recurse into a directory.
            for name, itemid in sorted(node.files.items()):
                # "yield from"
                yield from self._all_items(itemid)
            for name, subdir in sorted(node.dirs.items()):
                yield from self._all_items(subdir)

    def _add(self, path, send_id=False):
        """Adds a track or directory to the playlist, specified by the
        path. If `send_id`, write each item's id to the client.
        """
        for item in self._all_items(self._resolve_path(path)):
            self.playlist.append(item)
            if send_id:
                yield "Id: " + str(item.id)
        self.playlist_version += 1
        self._send_event("playlist")

    def cmd_add(self, conn, path):
        """Adds a track or directory to the playlist, specified by a
        path.
        """
        return self._add(path, False)

    def cmd_addid(self, conn, path):
        """Same as `cmd_add` but sends an id back to the client."""
        return self._add(path, True)

    # Server info.

    def cmd_status(self, conn):
        yield from super().cmd_status(conn)
        if self.current_index > -1:
            item = self.playlist[self.current_index]

            yield (
                "bitrate: " + str(item.bitrate / 1000),
                "audio: {}:{}:{}".format(
                    str(item.samplerate),
                    str(item.bitdepth),
                    str(item.channels),
                ),
            )

            (pos, total) = self.player.time()
            yield (
                "time: {}:{}".format(
                    str(int(pos)),
                    str(int(total)),
                ),
                "elapsed: " + f"{pos:.3f}",
                "duration: " + f"{total:.3f}",
            )

        # Also missing 'updating_db'.

    def cmd_stats(self, conn):
        """Sends some statistics about the library."""
        with self.lib.transaction() as tx:
            statement = (
                "SELECT COUNT(DISTINCT artist), "
                "COUNT(DISTINCT album), "
                "COUNT(id), "
                "SUM(length) "
                "FROM items"
            )
            artists, albums, songs, totaltime = tx.query(statement)[0]

        yield (
            "artists: " + str(artists),
            "albums: " + str(albums),
            "songs: " + str(songs),
            "uptime: " + str(int(time.time() - self.startup_time)),
            "playtime: " + "0",  # Missing.
            "db_playtime: " + str(int(totaltime)),
            "db_update: " + str(int(self.updated_time)),
        )

    def cmd_decoders(self, conn):
        """Send list of supported decoders and formats."""
        decoders = self.player.get_decoders()
        for name, (mimes, exts) in decoders.items():
            yield f"plugin: {name}"
            for ext in exts:
                yield f"suffix: {ext}"
            for mime in mimes:
                yield f"mime_type: {mime}"

    # Searching.

    tagtype_map = {
        "Artist": "artist",
        "ArtistSort": "artist_sort",
        "Album": "album",
        "Title": "title",
        "Track": "track",
        "AlbumArtist": "albumartist",
        "AlbumArtistSort": "albumartist_sort",
        "Label": "label",
        "Genre": "genre",
        "Date": "year",
        "OriginalDate": "original_year",
        "Composer": "composer",
        "Disc": "disc",
        "Comment": "comments",
        "MUSICBRAINZ_TRACKID": "mb_trackid",
        "MUSICBRAINZ_ALBUMID": "mb_albumid",
        "MUSICBRAINZ_ARTISTID": "mb_artistid",
        "MUSICBRAINZ_ALBUMARTISTID": "mb_albumartistid",
        "MUSICBRAINZ_RELEASETRACKID": "mb_releasetrackid",
    }

    def cmd_tagtypes(self, conn):
        """Returns a list of the metadata (tag) fields available for
        searching.
        """
        for tag in self.tagtype_map:
            yield "tagtype: " + tag

    def _tagtype_lookup(self, tag):
        """Uses `tagtype_map` to look up the beets column name for an
        MPD tagtype (or throw an appropriate exception). Returns both
        the canonical name of the MPD tagtype and the beets column
        name.
        """
        for test_tag, key in self.tagtype_map.items():
            # Match case-insensitively.
            if test_tag.lower() == tag.lower():
                return test_tag, key
        raise BPDError(ERROR_UNKNOWN, "no such tagtype")

    def _metadata_query(self, query_type, kv, allow_any_query: bool = False):
        """Helper function returns a query object that will find items
        according to the library query type provided and the key-value
        pairs specified. The any_query_type is used for queries of
        type "any"; if None, then an error is thrown.
        """
        if kv:  # At least one key-value pair.
            queries: list[Query] = []
            # Iterate pairwise over the arguments.
            it = iter(kv)
            for tag, value in zip(it, it):
                if tag.lower() == "any":
                    if allow_any_query:
                        queries.append(
                            Item.any_writable_media_field_query(
                                query_type, value
                            )
                        )
                    else:
                        raise BPDError(ERROR_UNKNOWN, "no such tagtype")
                else:
                    _, key = self._tagtype_lookup(tag)
                    queries.append(Item.field_query(key, value, query_type))
            return dbcore.query.AndQuery(queries)
        else:  # No key-value pairs.
            return dbcore.query.TrueQuery()

    def cmd_search(self, conn, *kv):
        """Perform a substring match for items."""
        query = self._metadata_query(
            dbcore.query.SubstringQuery, kv, allow_any_query=True
        )
        for item in self.lib.items(query):
            yield self._item_info(item)

    def cmd_find(self, conn, *kv):
        """Perform an exact match for items."""
        query = self._metadata_query(dbcore.query.MatchQuery, kv)
        for item in self.lib.items(query):
            yield self._item_info(item)

    def cmd_list(self, conn, show_tag, *kv):
        """List distinct metadata values for show_tag, possibly
        filtered by matching match_tag to match_term.
        """
        show_tag_canon, show_key = self._tagtype_lookup(show_tag)
        if len(kv) == 1:
            if show_tag_canon == "Album":
                # If no tag was given, assume artist. This is because MPD
                # supports a short version of this command for fetching the
                # albums belonging to a particular artist, and some clients
                # rely on this behaviour (e.g. MPDroid, M.A.L.P.).
                kv = ("Artist", kv[0])
            else:
                raise BPDError(ERROR_ARG, 'should be "Album" for 3 arguments')
        elif len(kv) % 2 != 0:
            raise BPDError(ERROR_ARG, "Incorrect number of filter arguments")
        query = self._metadata_query(dbcore.query.MatchQuery, kv)

        clause, subvals = query.clause()
        statement = (
            "SELECT DISTINCT "
            + show_key
            + " FROM items WHERE "
            + clause
            + " ORDER BY "
            + show_key
        )
        self._log.debug(statement)
        with self.lib.transaction() as tx:
            rows = tx.query(statement, subvals)

        for row in rows:
            if not row[0]:
                # Skip any empty values of the field.
                continue
            yield show_tag_canon + ": " + str(row[0])

    def cmd_count(self, conn, tag, value):
        """Returns the number and total time of songs matching the
        tag/value query.
        """
        _, key = self._tagtype_lookup(tag)
        songs = 0
        playtime = 0.0
        for item in self.lib.items(
            Item.field_query(key, value, dbcore.query.MatchQuery)
        ):
            songs += 1
            playtime += item.length
        yield "songs: " + str(songs)
        yield "playtime: " + str(int(playtime))

    # Persistent playlist manipulation. In MPD this is an optional feature so
    # these dummy implementations match MPD's behaviour with the feature off.

    def cmd_listplaylist(self, conn, playlist):
        raise BPDError(ERROR_NO_EXIST, "No such playlist")

    def cmd_listplaylistinfo(self, conn, playlist):
        raise BPDError(ERROR_NO_EXIST, "No such playlist")

    def cmd_listplaylists(self, conn):
        raise BPDError(ERROR_UNKNOWN, "Stored playlists are disabled")

    def cmd_load(self, conn, playlist):
        raise BPDError(ERROR_NO_EXIST, "Stored playlists are disabled")

    def cmd_playlistadd(self, conn, playlist, uri):
        raise BPDError(ERROR_UNKNOWN, "Stored playlists are disabled")

    def cmd_playlistclear(self, conn, playlist):
        raise BPDError(ERROR_UNKNOWN, "Stored playlists are disabled")

    def cmd_playlistdelete(self, conn, playlist, index):
        raise BPDError(ERROR_UNKNOWN, "Stored playlists are disabled")

    def cmd_playlistmove(self, conn, playlist, from_index, to_index):
        raise BPDError(ERROR_UNKNOWN, "Stored playlists are disabled")

    def cmd_rename(self, conn, playlist, new_name):
        raise BPDError(ERROR_UNKNOWN, "Stored playlists are disabled")

    def cmd_rm(self, conn, playlist):
        raise BPDError(ERROR_UNKNOWN, "Stored playlists are disabled")

    def cmd_save(self, conn, playlist):
        raise BPDError(ERROR_UNKNOWN, "Stored playlists are disabled")

    # "Outputs." Just a dummy implementation because we don't control
    # any outputs.

    def cmd_outputs(self, conn):
        """List the available outputs."""
        yield (
            "outputid: 0",
            "outputname: gstreamer",
            "outputenabled: 1",
        )

    def cmd_enableoutput(self, conn, output_id):
        output_id = cast_arg(int, output_id)
        if output_id != 0:
            raise ArgumentIndexError()

    def cmd_disableoutput(self, conn, output_id):
        output_id = cast_arg(int, output_id)
        if output_id == 0:
            raise BPDError(ERROR_ARG, "cannot disable this output")
        else:
            raise ArgumentIndexError()

    # Playback control. The functions below hook into the
    # half-implementations provided by the base class. Together, they're
    # enough to implement all normal playback functionality.

    def cmd_play(self, conn, index=-1):
        new_index = index != -1 and index != self.current_index
        was_paused = self.paused
        super().cmd_play(conn, index)

        if self.current_index > -1:  # Not stopped.
            if was_paused and not new_index:
                # Just unpause.
                self.player.play()
            else:
                self.player.play_file(self.playlist[self.current_index].path)

    def cmd_pause(self, conn, state=None):
        super().cmd_pause(conn, state)
        if self.paused:
            self.player.pause()
        elif self.player.playing:
            self.player.play()

    def cmd_stop(self, conn):
        super().cmd_stop(conn)
        self.player.stop()

    def cmd_seek(self, conn, index, pos):
        """Seeks to the specified position in the specified song."""
        index = cast_arg(int, index)
        pos = cast_arg(float, pos)
        super().cmd_seek(conn, index, pos)
        self.player.seek(pos)

    # Volume control.

    def cmd_setvol(self, conn, vol):
        vol = cast_arg(int, vol)
        super().cmd_setvol(conn, vol)
        self.player.volume = float(vol) / 100


# Beets plugin hooks.


class BPDPlugin(BeetsPlugin):
    """Provides the "beet bpd" command for running a music player
    server.
    """

    def __init__(self):
        super().__init__()
        self.config.add(
            {
                "host": "",
                "port": 6600,
                "control_port": 6601,
                "password": "",
                "volume": VOLUME_MAX,
            }
        )
        self.config["password"].redact = True

    def start_bpd(self, lib, host, port, password, volume, ctrl_port):
        """Starts a BPD server."""
        try:
            server = Server(lib, host, port, password, ctrl_port, self._log)
            server.cmd_setvol(None, volume)
            server.run()
        except NoGstreamerError:
            self._log.error("Gstreamer Python bindings not found.")
            self._log.error(
                'Install "gstreamer1.0" and "python-gi"'
                "or similar package to use BPD."
            )

    def commands(self):
        cmd = beets.ui.Subcommand(
            "bpd", help="run an MPD-compatible music player server"
        )

        def func(lib, opts, args):
            host = self.config["host"].as_str()
            host = args.pop(0) if args else host
            port = args.pop(0) if args else self.config["port"].get(int)
            if args:
                ctrl_port = args.pop(0)
            else:
                ctrl_port = self.config["control_port"].get(int)
            if args:
                raise beets.ui.UserError("too many arguments")
            password = self.config["password"].as_str()
            volume = self.config["volume"].get(int)
            self.start_bpd(
                lib, host, int(port), password, volume, int(ctrl_port)
            )

        cmd.func = func
        return [cmd]
