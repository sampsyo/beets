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

"""Tests for BPD's implementation of the MPD protocol."""

import importlib.util
import multiprocessing as mp
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager

# Mock GstPlayer so that the forked process doesn't attempt to import gi:
from unittest import mock

import confuse
import pytest
import yaml

from beets.test.helper import PluginTestCase
from beets.util import bluelet
from beetsplug import bpd

gstplayer = importlib.util.module_from_spec(
    importlib.util.find_spec("beetsplug.bpd.gstplayer")
)


def _gstplayer_play(*_):
    bpd.gstplayer._GstPlayer.playing = True
    return mock.DEFAULT


gstplayer._GstPlayer = mock.MagicMock(
    spec_set=[
        "time",
        "volume",
        "playing",
        "run",
        "play_file",
        "pause",
        "stop",
        "seek",
        "play",
        "get_decoders",
    ],
    **{
        "playing": False,
        "volume": 0,
        "time.return_value": (0, 0),
        "play_file.side_effect": _gstplayer_play,
        "play.side_effect": _gstplayer_play,
        "get_decoders.return_value": {"default": ({"audio/mpeg"}, {"mp3"})},
    },
)
gstplayer.GstPlayer = lambda _: gstplayer._GstPlayer
sys.modules["beetsplug.bpd.gstplayer"] = gstplayer
bpd.gstplayer = gstplayer


class CommandParseTest(unittest.TestCase):
    def test_no_args(self):
        s = r"command"
        c = bpd.Command(s)
        assert c.name == "command"
        assert c.args == []

    def test_one_unquoted_arg(self):
        s = r"command hello"
        c = bpd.Command(s)
        assert c.name == "command"
        assert c.args == ["hello"]

    def test_two_unquoted_args(self):
        s = r"command hello there"
        c = bpd.Command(s)
        assert c.name == "command"
        assert c.args == ["hello", "there"]

    def test_one_quoted_arg(self):
        s = r'command "hello there"'
        c = bpd.Command(s)
        assert c.name == "command"
        assert c.args == ["hello there"]

    def test_heterogenous_args(self):
        s = r'command "hello there" sir'
        c = bpd.Command(s)
        assert c.name == "command"
        assert c.args == ["hello there", "sir"]

    def test_quote_in_arg(self):
        s = r'command "hello \" there"'
        c = bpd.Command(s)
        assert c.args == ['hello " there']

    def test_backslash_in_arg(self):
        s = r'command "hello \\ there"'
        c = bpd.Command(s)
        assert c.args == ["hello \\ there"]


class MPCResponse:
    def __init__(self, raw_response):
        body = b"\n".join(raw_response.split(b"\n")[:-2]).decode("utf-8")
        self.data = self._parse_body(body)
        status = raw_response.split(b"\n")[-2].decode("utf-8")
        self.ok, self.err_data = self._parse_status(status)

    def _parse_status(self, status):
        """Parses the first response line, which contains the status."""
        if status.startswith("OK") or status.startswith("list_OK"):
            return True, None
        elif status.startswith("ACK"):
            code, rest = status[5:].split("@", 1)
            pos, rest = rest.split("]", 1)
            cmd, rest = rest[2:].split("}")
            return False, (int(code), int(pos), cmd, rest[1:])
        else:
            raise RuntimeError(f"Unexpected status: {status!r}")

    def _parse_body(self, body):
        """Messages are generally in the format "header: content".
        Convert them into a dict, storing the values for repeated headers as
        lists of strings, and non-repeated ones as string.
        """
        data = {}
        repeated_headers = set()
        for line in body.split("\n"):
            if not line:
                continue
            if ":" not in line:
                raise RuntimeError(f"Unexpected line: {line!r}")
            header, content = line.split(":", 1)
            content = content.lstrip()
            if header in repeated_headers:
                data[header].append(content)
            elif header in data:
                data[header] = [data[header], content]
                repeated_headers.add(header)
            else:
                data[header] = content
        return data


class MPCClient:
    def __init__(self, sock, do_hello=True):
        self.sock = sock
        self.buf = b""
        if do_hello:
            hello = self.get_response()
            if not hello.ok:
                raise RuntimeError("Bad hello")

    def get_response(self, force_multi=None):
        """Wait for a full server response and wrap it in a helper class.
        If the request was a batch request then this will return a list of
        `MPCResponse`s, one for each processed subcommand.
        """

        response = b""
        responses = []
        while True:
            line = self.readline()
            response += line
            if line.startswith(b"OK") or line.startswith(b"ACK"):
                if force_multi or any(responses):
                    if line.startswith(b"ACK"):
                        responses.append(MPCResponse(response))
                        n_remaining = force_multi - len(responses)
                        responses.extend([None] * n_remaining)
                    return responses
                else:
                    return MPCResponse(response)
            if line.startswith(b"list_OK"):
                responses.append(MPCResponse(response))
                response = b""
            elif not line:
                raise RuntimeError(f"Unexpected response: {line!r}")

    def serialise_command(self, command, *args):
        cmd = [command.encode("utf-8")]
        for arg in [a.encode("utf-8") for a in args]:
            if b" " in arg:
                cmd.append(b'"' + arg + b'"')
            else:
                cmd.append(arg)
        return b" ".join(cmd) + b"\n"

    def send_command(self, command, *args):
        request = self.serialise_command(command, *args)
        self.sock.sendall(request)
        return self.get_response()

    def send_commands(self, *commands):
        """Use MPD command batching to send multiple commands at once.
        Each item of commands is a tuple containing a command followed by
        any arguments.
        """

        requests = []
        for command_and_args in commands:
            command = command_and_args[0]
            args = command_and_args[1:]
            requests.append(self.serialise_command(command, *args))
        requests.insert(0, b"command_list_ok_begin\n")
        requests.append(b"command_list_end\n")
        request = b"".join(requests)
        self.sock.sendall(request)
        return self.get_response(force_multi=len(commands))

    def readline(self, terminator=b"\n", bufsize=1024):
        """Reads a line of data from the socket."""

        while True:
            if terminator in self.buf:
                line, self.buf = self.buf.split(terminator, 1)
                line += terminator
                return line
            self.sock.settimeout(1)
            data = self.sock.recv(bufsize)
            if data:
                self.buf += data
            else:
                line = self.buf
                self.buf = b""
                return line


def implements(commands, fail=False):
    def _test(self):
        with self.run_bpd() as client:
            response = client.send_command("commands")
        self._assert_ok(response)
        implemented = response.data["command"]
        assert commands.intersection(implemented) == commands

    return unittest.expectedFailure(_test) if fail else _test


bluelet_listener = bluelet.Listener


@mock.patch("beets.util.bluelet.Listener")
def start_server(args, assigned_port, listener_patch):
    """Start the bpd server, writing the port to `assigned_port`."""

    def listener_wrap(host, port):
        """Wrap `bluelet.Listener`, writing the port to `assigend_port`."""
        # `bluelet.Listener` has previously been saved to
        # `bluelet_listener` as this function will replace it at its
        # original location.
        listener = bluelet_listener(host, port)
        # read port assigned by OS
        assigned_port.put_nowait(listener.sock.getsockname()[1])
        return listener

    listener_patch.side_effect = listener_wrap

    import beets.ui

    beets.ui.main(args)


class BPDTestHelper(PluginTestCase):
    db_on_disk = True
    plugin = "bpd"

    def setUp(self):
        super().setUp()
        self.item1 = self.add_item(
            title="Track One Title",
            track=1,
            album="Album Title",
            artist="Artist Name",
        )
        self.item2 = self.add_item(
            title="Track Two Title",
            track=2,
            album="Album Title",
            artist="Artist Name",
        )
        self.lib.add_album([self.item1, self.item2])

    @contextmanager
    def run_bpd(
        self,
        host="localhost",
        password=None,
        do_hello=True,
        second_client=False,
    ):
        """Runs BPD in another process, configured with the same library
        database as we created in the setUp method. Exposes a client that is
        connected to the server, and kills the server at the end.
        """
        # Create a config file:
        config = {
            "pluginpath": [os.fsdecode(self.temp_dir)],
            "plugins": "bpd",
            # use port 0 to let the OS choose a free port
            "bpd": {"host": host, "port": 0, "control_port": 0},
        }
        if password:
            config["bpd"]["password"] = password
        config_file = tempfile.NamedTemporaryFile(
            mode="wb",
            dir=os.fsdecode(self.temp_dir),
            suffix=".yaml",
            delete=False,
        )
        config_file.write(
            yaml.dump(config, Dumper=confuse.Dumper, encoding="utf-8")
        )
        config_file.close()

        # Fork and launch BPD in the new process:
        assigned_port = mp.Queue(2)  # 2 slots, `control_port` and `port`
        server = mp.Process(
            target=start_server,
            args=(
                [
                    "--library",
                    self.config["library"].as_filename(),
                    "--directory",
                    os.fsdecode(self.libdir),
                    "--config",
                    os.fsdecode(config_file.name),
                    "bpd",
                ],
                assigned_port,
            ),
        )
        server.start()

        try:
            assigned_port.get(timeout=1)  # skip control_port
            port = assigned_port.get(timeout=0.5)  # read port

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.connect((host, port))

                if second_client:
                    sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    try:
                        sock2.connect((host, port))
                        yield (
                            MPCClient(sock, do_hello),
                            MPCClient(sock2, do_hello),
                        )
                    finally:
                        sock2.close()

                else:
                    yield MPCClient(sock, do_hello)
            finally:
                sock.close()
        finally:
            server.terminate()
            server.join(timeout=0.2)

    def _assert_ok(self, *responses):
        for response in responses:
            assert response is not None
            assert response.ok, f"Response failed: {response.err_data}"

    def _assert_failed(self, response, code, pos=None):
        """Check that a command failed with a specific error code. If this
        is a list of responses, first check all preceding commands were OK.
        """
        if pos is not None:
            previous_commands = response[0:pos]
            self._assert_ok(*previous_commands)
            response = response[pos]
        assert not response.ok
        if pos is not None:
            assert pos == response.err_data[1]
        if code is not None:
            assert code == response.err_data[0]

    def _bpd_add(self, client, *items, **kwargs):
        """Add the given item to the BPD playlist or queue."""
        paths = [
            "/".join(
                [
                    item.artist,
                    item.album,
                    os.fsdecode(os.path.basename(item.path)),
                ]
            )
            for item in items
        ]
        playlist = kwargs.get("playlist")
        if playlist:
            commands = [("playlistadd", playlist, path) for path in paths]
        else:
            commands = [("add", path) for path in paths]
        responses = client.send_commands(*commands)
        self._assert_ok(*responses)


class BPDTest(BPDTestHelper):
    def test_server_hello(self):
        with self.run_bpd(do_hello=False) as client:
            assert client.readline() == b"OK MPD 0.16.0\n"

    def test_unknown_cmd(self):
        with self.run_bpd() as client:
            response = client.send_command("notacommand")
        self._assert_failed(response, bpd.ERROR_UNKNOWN)

    def test_unexpected_argument(self):
        with self.run_bpd() as client:
            response = client.send_command("ping", "extra argument")
        self._assert_failed(response, bpd.ERROR_ARG)

    def test_missing_argument(self):
        with self.run_bpd() as client:
            response = client.send_command("add")
        self._assert_failed(response, bpd.ERROR_ARG)

    def test_system_error(self):
        with self.run_bpd() as client:
            response = client.send_command("crash")
        self._assert_failed(response, bpd.ERROR_SYSTEM)

    def test_empty_request(self):
        with self.run_bpd() as client:
            response = client.send_command("")
        self._assert_failed(response, bpd.ERROR_UNKNOWN)


class BPDQueryTest(BPDTestHelper):
    test_implements_query = implements(
        {
            "clearerror",
        }
    )

    def test_cmd_currentsong(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1)
            responses = client.send_commands(
                ("play",), ("currentsong",), ("stop",), ("currentsong",)
            )
        self._assert_ok(*responses)
        assert "1" == responses[1].data["Id"]
        assert "Id" not in responses[3].data

    def test_cmd_currentsong_tagtypes(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1)
            responses = client.send_commands(("play",), ("currentsong",))
        self._assert_ok(*responses)
        assert BPDConnectionTest.TAGTYPES.union(BPDQueueTest.METADATA) == set(
            responses[1].data.keys()
        )

    def test_cmd_status(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1, self.item2)
            responses = client.send_commands(
                ("status",), ("play",), ("status",)
            )
        self._assert_ok(*responses)
        fields_not_playing = {
            "repeat",
            "random",
            "single",
            "consume",
            "playlist",
            "playlistlength",
            "mixrampdb",
            "state",
            "volume",
        }
        assert fields_not_playing == set(responses[0].data.keys())
        fields_playing = fields_not_playing | {
            "song",
            "songid",
            "time",
            "elapsed",
            "bitrate",
            "duration",
            "audio",
            "nextsong",
            "nextsongid",
        }
        assert fields_playing == set(responses[2].data.keys())

    def test_cmd_stats(self):
        with self.run_bpd() as client:
            response = client.send_command("stats")
        self._assert_ok(response)
        details = {
            "artists",
            "albums",
            "songs",
            "uptime",
            "db_playtime",
            "db_update",
            "playtime",
        }
        assert details == set(response.data.keys())

    def test_cmd_idle(self):
        def _toggle(c):
            for _ in range(3):
                rs = c.send_commands(("play",), ("pause",))
                # time.sleep(0.05)  # uncomment if test is flaky
                if any(not r.ok for r in rs):
                    raise RuntimeError("Toggler failed")

        with self.run_bpd(second_client=True) as (client, client2):
            self._bpd_add(client, self.item1, self.item2)
            toggler = threading.Thread(target=_toggle, args=(client2,))
            toggler.start()
            # Idling will hang until the toggler thread changes the play state.
            # Since the client sockets have a 1s timeout set at worst this will
            # raise a socket.timeout and fail the test if the toggler thread
            # manages to finish before the idle command is sent here.
            response = client.send_command("idle", "player")
            toggler.join()
        self._assert_ok(response)

    def test_cmd_idle_with_pending(self):
        with self.run_bpd(second_client=True) as (client, client2):
            response1 = client.send_command("random", "1")
            response2 = client2.send_command("idle")
        self._assert_ok(response1, response2)
        assert "options" == response2.data["changed"]

    def test_cmd_noidle(self):
        with self.run_bpd() as client:
            # Manually send a command without reading a response.
            request = client.serialise_command("idle")
            client.sock.sendall(request)
            time.sleep(0.01)
            response = client.send_command("noidle")
        self._assert_ok(response)

    def test_cmd_noidle_when_not_idle(self):
        with self.run_bpd() as client:
            # Manually send a command without reading a response.
            request = client.serialise_command("noidle")
            client.sock.sendall(request)
            response = client.send_command("notacommand")
        self._assert_failed(response, bpd.ERROR_UNKNOWN)


class BPDPlaybackTest(BPDTestHelper):
    test_implements_playback = implements(
        {
            "random",
        }
    )

    def test_cmd_consume(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1, self.item2)
            responses = client.send_commands(
                ("consume", "0"),
                ("playlistinfo",),
                ("next",),
                ("playlistinfo",),
                ("consume", "1"),
                ("playlistinfo",),
                ("play", "0"),
                ("next",),
                ("playlistinfo",),
                ("status",),
            )
        self._assert_ok(*responses)
        assert responses[1].data["Id"] == responses[3].data["Id"]
        assert ["1", "2"] == responses[5].data["Id"]
        assert "2" == responses[8].data["Id"]
        assert "1" == responses[9].data["consume"]
        assert "play" == responses[9].data["state"]

    def test_cmd_consume_in_reverse(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1, self.item2)
            responses = client.send_commands(
                ("consume", "1"),
                ("play", "1"),
                ("playlistinfo",),
                ("previous",),
                ("playlistinfo",),
                ("status",),
            )
        self._assert_ok(*responses)
        assert ["1", "2"] == responses[2].data["Id"]
        assert "1" == responses[4].data["Id"]
        assert "play" == responses[5].data["state"]

    def test_cmd_single(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1, self.item2)
            responses = client.send_commands(
                ("status",),
                ("single", "1"),
                ("play",),
                ("status",),
                ("next",),
                ("status",),
            )
        self._assert_ok(*responses)
        assert "0" == responses[0].data["single"]
        assert "1" == responses[3].data["single"]
        assert "play" == responses[3].data["state"]
        assert "stop" == responses[5].data["state"]

    def test_cmd_repeat(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1, self.item2)
            responses = client.send_commands(
                ("repeat", "1"),
                ("play",),
                ("currentsong",),
                ("next",),
                ("currentsong",),
                ("next",),
                ("currentsong",),
            )
        self._assert_ok(*responses)
        assert "1" == responses[2].data["Id"]
        assert "2" == responses[4].data["Id"]
        assert "1" == responses[6].data["Id"]

    def test_cmd_repeat_with_single(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1, self.item2)
            responses = client.send_commands(
                ("repeat", "1"),
                ("single", "1"),
                ("play",),
                ("currentsong",),
                ("next",),
                ("status",),
                ("currentsong",),
            )
        self._assert_ok(*responses)
        assert "1" == responses[3].data["Id"]
        assert "play" == responses[5].data["state"]
        assert "1" == responses[6].data["Id"]

    def test_cmd_repeat_in_reverse(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1, self.item2)
            responses = client.send_commands(
                ("repeat", "1"),
                ("play",),
                ("currentsong",),
                ("previous",),
                ("currentsong",),
            )
        self._assert_ok(*responses)
        assert "1" == responses[2].data["Id"]
        assert "2" == responses[4].data["Id"]

    def test_cmd_repeat_with_single_in_reverse(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1, self.item2)
            responses = client.send_commands(
                ("repeat", "1"),
                ("single", "1"),
                ("play",),
                ("currentsong",),
                ("previous",),
                ("status",),
                ("currentsong",),
            )
        self._assert_ok(*responses)
        assert "1" == responses[3].data["Id"]
        assert "play" == responses[5].data["state"]
        assert "1" == responses[6].data["Id"]

    def test_cmd_crossfade(self):
        with self.run_bpd() as client:
            responses = client.send_commands(
                ("status",),
                ("crossfade", "123"),
                ("status",),
                ("crossfade", "-2"),
            )
            response = client.send_command("crossfade", "0.5")
        self._assert_failed(responses, bpd.ERROR_ARG, pos=3)
        self._assert_failed(response, bpd.ERROR_ARG)
        assert "xfade" not in responses[0].data
        assert 123 == pytest.approx(int(responses[2].data["xfade"]))

    def test_cmd_mixrampdb(self):
        with self.run_bpd() as client:
            responses = client.send_commands(("mixrampdb", "-17"), ("status",))
        self._assert_ok(*responses)
        assert -17 == pytest.approx(float(responses[1].data["mixrampdb"]))

    def test_cmd_mixrampdelay(self):
        with self.run_bpd() as client:
            responses = client.send_commands(
                ("mixrampdelay", "2"),
                ("status",),
                ("mixrampdelay", "nan"),
                ("status",),
                ("mixrampdelay", "-2"),
            )
        self._assert_failed(responses, bpd.ERROR_ARG, pos=4)
        assert 2 == pytest.approx(float(responses[1].data["mixrampdelay"]))
        assert "mixrampdelay" not in responses[3].data

    def test_cmd_setvol(self):
        with self.run_bpd() as client:
            responses = client.send_commands(
                ("setvol", "67"),
                ("status",),
                ("setvol", "32"),
                ("status",),
                ("setvol", "101"),
            )
        self._assert_failed(responses, bpd.ERROR_ARG, pos=4)
        assert "67" == responses[1].data["volume"]
        assert "32" == responses[3].data["volume"]

    def test_cmd_volume(self):
        with self.run_bpd() as client:
            responses = client.send_commands(
                ("setvol", "10"), ("volume", "5"), ("volume", "-2"), ("status",)
            )
        self._assert_ok(*responses)
        assert "13" == responses[3].data["volume"]

    def test_cmd_replay_gain(self):
        with self.run_bpd() as client:
            responses = client.send_commands(
                ("replay_gain_mode", "track"),
                ("replay_gain_status",),
                ("replay_gain_mode", "notanoption"),
            )
        self._assert_failed(responses, bpd.ERROR_ARG, pos=2)
        assert "track" == responses[1].data["replay_gain_mode"]


class BPDControlTest(BPDTestHelper):
    test_implements_control = implements(
        {
            "seek",
            "seekid",
            "seekcur",
        },
        fail=True,
    )

    def test_cmd_play(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1, self.item2)
            responses = client.send_commands(
                ("status",),
                ("play",),
                ("status",),
                ("play", "1"),
                ("currentsong",),
            )
        self._assert_ok(*responses)
        assert "stop" == responses[0].data["state"]
        assert "play" == responses[2].data["state"]
        assert "2" == responses[4].data["Id"]

    def test_cmd_playid(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1, self.item2)
            responses = client.send_commands(
                ("playid", "2"), ("currentsong",), ("clear",)
            )
            self._bpd_add(client, self.item2, self.item1)
            responses.extend(
                client.send_commands(("playid", "2"), ("currentsong",))
            )
        self._assert_ok(*responses)
        assert "2" == responses[1].data["Id"]
        assert "2" == responses[4].data["Id"]

    def test_cmd_pause(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1)
            responses = client.send_commands(
                ("play",), ("pause",), ("status",), ("currentsong",)
            )
        self._assert_ok(*responses)
        assert "pause" == responses[2].data["state"]
        assert "1" == responses[3].data["Id"]

    def test_cmd_stop(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1)
            responses = client.send_commands(
                ("play",), ("stop",), ("status",), ("currentsong",)
            )
        self._assert_ok(*responses)
        assert "stop" == responses[2].data["state"]
        assert "Id" not in responses[3].data

    def test_cmd_next(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1, self.item2)
            responses = client.send_commands(
                ("play",),
                ("currentsong",),
                ("next",),
                ("currentsong",),
                ("next",),
                ("status",),
            )
        self._assert_ok(*responses)
        assert "1" == responses[1].data["Id"]
        assert "2" == responses[3].data["Id"]
        assert "stop" == responses[5].data["state"]

    def test_cmd_previous(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1, self.item2)
            responses = client.send_commands(
                ("play", "1"),
                ("currentsong",),
                ("previous",),
                ("currentsong",),
                ("previous",),
                ("status",),
                ("currentsong",),
            )
        self._assert_ok(*responses)
        assert "2" == responses[1].data["Id"]
        assert "1" == responses[3].data["Id"]
        assert "play" == responses[5].data["state"]
        assert "1" == responses[6].data["Id"]


class BPDQueueTest(BPDTestHelper):
    test_implements_queue = implements(
        {
            "addid",
            "clear",
            "delete",
            "deleteid",
            "move",
            "moveid",
            "playlist",
            "playlistfind",
            "playlistsearch",
            "plchanges",
            "plchangesposid",
            "prio",
            "prioid",
            "rangeid",
            "shuffle",
            "swap",
            "swapid",
            "addtagid",
            "cleartagid",
        },
        fail=True,
    )

    METADATA = {"Pos", "Time", "Id", "file", "duration"}

    def test_cmd_add(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1)

    def test_cmd_playlistinfo(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1, self.item2)
            responses = client.send_commands(
                ("playlistinfo",),
                ("playlistinfo", "0"),
                ("playlistinfo", "0:2"),
                ("playlistinfo", "200"),
            )
        self._assert_failed(responses, bpd.ERROR_ARG, pos=3)
        assert "1" == responses[1].data["Id"]
        assert ["1", "2"] == responses[2].data["Id"]

    def test_cmd_playlistinfo_tagtypes(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1)
            response = client.send_command("playlistinfo", "0")
        self._assert_ok(response)
        assert BPDConnectionTest.TAGTYPES.union(BPDQueueTest.METADATA) == set(
            response.data.keys()
        )

    def test_cmd_playlistid(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1, self.item2)
            responses = client.send_commands(
                ("playlistid", "2"), ("playlistid",)
            )
        self._assert_ok(*responses)
        assert "Track Two Title" == responses[0].data["Title"]
        assert ["1", "2"] == responses[1].data["Track"]


class BPDPlaylistsTest(BPDTestHelper):
    test_implements_playlists = implements({"playlistadd"})

    def test_cmd_listplaylist(self):
        with self.run_bpd() as client:
            response = client.send_command("listplaylist", "anything")
        self._assert_failed(response, bpd.ERROR_NO_EXIST)

    def test_cmd_listplaylistinfo(self):
        with self.run_bpd() as client:
            response = client.send_command("listplaylistinfo", "anything")
        self._assert_failed(response, bpd.ERROR_NO_EXIST)

    def test_cmd_listplaylists(self):
        with self.run_bpd() as client:
            response = client.send_command("listplaylists")
        self._assert_failed(response, bpd.ERROR_UNKNOWN)

    def test_cmd_load(self):
        with self.run_bpd() as client:
            response = client.send_command("load", "anything")
        self._assert_failed(response, bpd.ERROR_NO_EXIST)

    @unittest.skip
    def test_cmd_playlistadd(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1, playlist="anything")

    def test_cmd_playlistclear(self):
        with self.run_bpd() as client:
            response = client.send_command("playlistclear", "anything")
        self._assert_failed(response, bpd.ERROR_UNKNOWN)

    def test_cmd_playlistdelete(self):
        with self.run_bpd() as client:
            response = client.send_command("playlistdelete", "anything", "0")
        self._assert_failed(response, bpd.ERROR_UNKNOWN)

    def test_cmd_playlistmove(self):
        with self.run_bpd() as client:
            response = client.send_command("playlistmove", "anything", "0", "1")
        self._assert_failed(response, bpd.ERROR_UNKNOWN)

    def test_cmd_rename(self):
        with self.run_bpd() as client:
            response = client.send_command("rename", "anything", "newname")
        self._assert_failed(response, bpd.ERROR_UNKNOWN)

    def test_cmd_rm(self):
        with self.run_bpd() as client:
            response = client.send_command("rm", "anything")
        self._assert_failed(response, bpd.ERROR_UNKNOWN)

    def test_cmd_save(self):
        with self.run_bpd() as client:
            self._bpd_add(client, self.item1)
            response = client.send_command("save", "newplaylist")
        self._assert_failed(response, bpd.ERROR_UNKNOWN)


class BPDDatabaseTest(BPDTestHelper):
    test_implements_database = implements(
        {
            "albumart",
            "find",
            "findadd",
            "listall",
            "listallinfo",
            "listfiles",
            "readcomments",
            "searchadd",
            "searchaddpl",
            "update",
            "rescan",
        },
        fail=True,
    )

    def test_cmd_search(self):
        with self.run_bpd() as client:
            response = client.send_command("search", "track", "1")
        self._assert_ok(response)
        assert self.item1.title == response.data["Title"]

    def test_cmd_list(self):
        with self.run_bpd() as client:
            responses = client.send_commands(
                ("list", "album"),
                ("list", "track"),
                ("list", "album", "artist", "Artist Name", "track"),
            )
        self._assert_failed(responses, bpd.ERROR_ARG, pos=2)
        assert "Album Title" == responses[0].data["Album"]
        assert ["1", "2"] == responses[1].data["Track"]

    def test_cmd_list_three_arg_form(self):
        with self.run_bpd() as client:
            responses = client.send_commands(
                ("list", "album", "artist", "Artist Name"),
                ("list", "album", "Artist Name"),
                ("list", "track", "Artist Name"),
            )
        self._assert_failed(responses, bpd.ERROR_ARG, pos=2)
        assert responses[0].data == responses[1].data

    def test_cmd_lsinfo(self):
        with self.run_bpd() as client:
            response1 = client.send_command("lsinfo")
            self._assert_ok(response1)
            response2 = client.send_command(
                "lsinfo", response1.data["directory"]
            )
            self._assert_ok(response2)
            response3 = client.send_command(
                "lsinfo", response2.data["directory"]
            )
            self._assert_ok(response3)
        assert self.item1.title in response3.data["Title"]

    def test_cmd_count(self):
        with self.run_bpd() as client:
            response = client.send_command("count", "track", "1")
        self._assert_ok(response)
        assert "1" == response.data["songs"]
        assert "0" == response.data["playtime"]


class BPDMountsTest(BPDTestHelper):
    test_implements_mounts = implements(
        {
            "mount",
            "unmount",
            "listmounts",
            "listneighbors",
        },
        fail=True,
    )


class BPDStickerTest(BPDTestHelper):
    test_implements_stickers = implements(
        {
            "sticker",
        },
        fail=True,
    )


class BPDConnectionTest(BPDTestHelper):
    test_implements_connection = implements(
        {
            "close",
            "kill",
        }
    )

    ALL_MPD_TAGTYPES = {
        "Artist",
        "ArtistSort",
        "Album",
        "AlbumSort",
        "AlbumArtist",
        "AlbumArtistSort",
        "Title",
        "Track",
        "Name",
        "Genre",
        "Date",
        "Composer",
        "Performer",
        "Comment",
        "Disc",
        "Label",
        "OriginalDate",
        "MUSICBRAINZ_ARTISTID",
        "MUSICBRAINZ_ALBUMID",
        "MUSICBRAINZ_ALBUMARTISTID",
        "MUSICBRAINZ_TRACKID",
        "MUSICBRAINZ_RELEASETRACKID",
        "MUSICBRAINZ_WORKID",
    }
    UNSUPPORTED_TAGTYPES = {
        "MUSICBRAINZ_WORKID",  # not tracked by beets
        "Performer",  # not tracked by beets
        "AlbumSort",  # not tracked by beets
        "Name",  # junk field for internet radio
    }
    TAGTYPES = ALL_MPD_TAGTYPES.difference(UNSUPPORTED_TAGTYPES)

    def test_cmd_password(self):
        with self.run_bpd(password="abc123") as client:
            response = client.send_command("status")
            self._assert_failed(response, bpd.ERROR_PERMISSION)

            response = client.send_command("password", "wrong")
            self._assert_failed(response, bpd.ERROR_PASSWORD)

            responses = client.send_commands(
                ("password", "abc123"), ("status",)
            )
        self._assert_ok(*responses)

    def test_cmd_ping(self):
        with self.run_bpd() as client:
            response = client.send_command("ping")
        self._assert_ok(response)

    def test_cmd_tagtypes(self):
        with self.run_bpd() as client:
            response = client.send_command("tagtypes")
        self._assert_ok(response)
        assert self.TAGTYPES == set(response.data["tagtype"])

    @unittest.skip
    def test_tagtypes_mask(self):
        with self.run_bpd() as client:
            response = client.send_command("tagtypes", "clear")
        self._assert_ok(response)


class BPDPartitionTest(BPDTestHelper):
    test_implements_partitions = implements(
        {
            "partition",
            "listpartitions",
            "newpartition",
        },
        fail=True,
    )


class BPDDeviceTest(BPDTestHelper):
    test_implements_devices = implements(
        {
            "disableoutput",
            "enableoutput",
            "toggleoutput",
            "outputs",
        },
        fail=True,
    )


class BPDReflectionTest(BPDTestHelper):
    test_implements_reflection = implements(
        {
            "config",
            "commands",
            "notcommands",
            "urlhandlers",
        },
        fail=True,
    )

    def test_cmd_decoders(self):
        with self.run_bpd() as client:
            response = client.send_command("decoders")
        self._assert_ok(response)
        assert "default" == response.data["plugin"]
        assert "mp3" == response.data["suffix"]
        assert "audio/mpeg" == response.data["mime_type"]


class BPDPeersTest(BPDTestHelper):
    test_implements_peers = implements(
        {
            "subscribe",
            "unsubscribe",
            "channels",
            "readmessages",
            "sendmessage",
        },
        fail=True,
    )
