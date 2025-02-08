# This file is part of beets.
# Copyright 2016, Fabrice Laporte, Yevgeny Bezman, and Adrian Sampson.
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


from __future__ import annotations

import collections
import enum
import math
import os
import queue
import signal
import subprocess
import sys
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from multiprocessing.pool import ThreadPool
from threading import Event, Thread
from typing import TYPE_CHECKING, Any, Callable, TypeVar, cast

from beets import ui
from beets.plugins import BeetsPlugin
from beets.util import command_output, displayable_path, syspath

if TYPE_CHECKING:
    import optparse
    from collections.abc import Sequence
    from logging import Logger

    from confuse import ConfigView

    from beets.importer import ImportSession, ImportTask
    from beets.library import Album, Item, Library

# Utilities.


class ReplayGainError(Exception):
    """Raised when a local (to a track or an album) error occurs in one
    of the backends.
    """


class FatalReplayGainError(Exception):
    """Raised when a fatal error occurs in one of the backends."""


class FatalGstreamerPluginReplayGainError(FatalReplayGainError):
    """Raised when a fatal error occurs in the GStreamerBackend when
    loading the required plugins."""


def call(args: list[Any], log: Logger, **kwargs: Any):
    """Execute the command and return its output or raise a
    ReplayGainError on failure.
    """
    try:
        return command_output(args, **kwargs)
    except subprocess.CalledProcessError as e:
        log.debug(e.output.decode("utf8", "ignore"))
        raise ReplayGainError(
            "{} exited with status {}".format(args[0], e.returncode)
        )
    except UnicodeEncodeError:
        # Due to a bug in Python 2's subprocess on Windows, Unicode
        # filenames can fail to encode on that platform. See:
        # https://github.com/google-code-export/beets/issues/499
        raise ReplayGainError("argument encoding failed")


def db_to_lufs(db: float) -> float:
    """Convert db to LUFS.

    According to https://wiki.hydrogenaud.io/index.php?title=
      ReplayGain_2.0_specification#Reference_level
    """
    return db - 107


def lufs_to_db(db: float) -> float:
    """Convert LUFS to db.

    According to https://wiki.hydrogenaud.io/index.php?title=
      ReplayGain_2.0_specification#Reference_level
    """
    return db + 107


# Backend base and plumbing classes.


@dataclass
class Gain:
    # gain: in LU to reference level
    gain: float
    # peak: part of full scale (FS is 1.0)
    peak: float


class PeakMethod(enum.Enum):
    true = 1
    sample = 2


class RgTask:
    """State and methods for a single replaygain calculation (rg version).

    Bundles the state (parameters and results) of a single replaygain
    calculation (either for one item, one disk, or one full album).

    This class provides methods to store the resulting gains and peaks as plain
    old rg tags.
    """

    def __init__(
        self,
        items: Sequence[Item],
        album: Album | None,
        target_level: float,
        peak_method: PeakMethod | None,
        backend_name: str,
        log: Logger,
    ):
        self.items = items
        self.album = album
        self.target_level = target_level
        self.peak_method = peak_method
        self.backend_name = backend_name
        self._log = log
        self.album_gain: Gain | None = None
        self.track_gains: list[Gain] | None = None

    def _store_track_gain(self, item: Item, track_gain: Gain):
        """Store track gain for a single item in the database."""
        item.rg_track_gain = track_gain.gain
        item.rg_track_peak = track_gain.peak
        item.store()
        self._log.debug(
            "applied track gain {0} LU, peak {1} of FS",
            item.rg_track_gain,
            item.rg_track_peak,
        )

    def _store_album_gain(self, item: Item, album_gain: Gain):
        """Store album gain for a single item in the database.

        The caller needs to ensure that `self.album_gain is not None`.
        """
        item.rg_album_gain = album_gain.gain
        item.rg_album_peak = album_gain.peak
        item.store()
        self._log.debug(
            "applied album gain {0} LU, peak {1} of FS",
            item.rg_album_gain,
            item.rg_album_peak,
        )

    def _store_track(self, write: bool):
        """Store track gain for the first track of the task in the database."""
        item = self.items[0]
        if self.track_gains is None or len(self.track_gains) != 1:
            # In some cases, backends fail to produce a valid
            # `track_gains` without throwing FatalReplayGainError
            #  => raise non-fatal exception & continue
            raise ReplayGainError(
                "ReplayGain backend `{}` failed for track {}".format(
                    self.backend_name, item
                )
            )

        self._store_track_gain(item, self.track_gains[0])
        if write:
            item.try_write()
        self._log.debug("done analyzing {0}", item)

    def _store_album(self, write: bool):
        """Store track/album gains for all tracks of the task in the database."""
        if (
            self.album_gain is None
            or self.track_gains is None
            or len(self.track_gains) != len(self.items)
        ):
            # In some cases, backends fail to produce a valid
            # `album_gain` without throwing FatalReplayGainError
            #  => raise non-fatal exception & continue
            raise ReplayGainError(
                "ReplayGain backend `{}` failed "
                "for some tracks in album {}".format(
                    self.backend_name, self.album
                )
            )
        for item, track_gain in zip(self.items, self.track_gains):
            self._store_track_gain(item, track_gain)
            self._store_album_gain(item, self.album_gain)
            if write:
                item.try_write()
            self._log.debug("done analyzing {0}", item)

    def store(self, write: bool):
        """Store computed gains for the items of this task in the database."""
        if self.album is not None:
            self._store_album(write)
        else:
            self._store_track(write)


class R128Task(RgTask):
    """State and methods for a single replaygain calculation (r128 version).

    Bundles the state (parameters and results) of a single replaygain
    calculation (either for one item, one disk, or one full album).

    This class provides methods to store the resulting gains and peaks as R128
    tags.
    """

    def __init__(
        self,
        items: Sequence[Item],
        album: Album | None,
        target_level: float,
        backend_name: str,
        log: Logger,
    ):
        # R128_* tags do not store the track/album peak
        super().__init__(items, album, target_level, None, backend_name, log)

    def _store_track_gain(self, item: Item, track_gain: Gain):
        item.r128_track_gain = track_gain.gain
        item.store()
        self._log.debug("applied r128 track gain {0} LU", item.r128_track_gain)

    def _store_album_gain(self, item: Item, album_gain: Gain):
        """

        The caller needs to ensure that `self.album_gain is not None`.
        """
        item.r128_album_gain = album_gain.gain
        item.store()
        self._log.debug("applied r128 album gain {0} LU", item.r128_album_gain)


AnyRgTask = TypeVar("AnyRgTask", bound=RgTask)


class Backend(ABC):
    """An abstract class representing engine for calculating RG values."""

    NAME = ""
    do_parallel = False

    def __init__(self, config: ConfigView, log: Logger):
        """Initialize the backend with the configuration view for the
        plugin.
        """
        self._log = log

    @abstractmethod
    def compute_track_gain(self, task: AnyRgTask) -> AnyRgTask:
        """Computes the track gain for the tracks belonging to `task`, and sets
        the `track_gains` attribute on the task. Returns `task`.
        """
        raise NotImplementedError()

    @abstractmethod
    def compute_album_gain(self, task: AnyRgTask) -> AnyRgTask:
        """Computes the album gain for the album belonging to `task`, and sets
        the `album_gain` attribute on the task. Returns `task`.
        """
        raise NotImplementedError()


# ffmpeg backend
class FfmpegBackend(Backend):
    """A replaygain backend using ffmpeg's ebur128 filter."""

    NAME = "ffmpeg"
    do_parallel = True

    def __init__(self, config: ConfigView, log: Logger):
        super().__init__(config, log)
        self._ffmpeg_path = "ffmpeg"

        # check that ffmpeg is installed
        try:
            ffmpeg_version_out = call([self._ffmpeg_path, "-version"], log)
        except OSError:
            raise FatalReplayGainError(
                f"could not find ffmpeg at {self._ffmpeg_path}"
            )
        incompatible_ffmpeg = True
        for line in ffmpeg_version_out.stdout.splitlines():
            if line.startswith(b"configuration:"):
                if b"--enable-libebur128" in line:
                    incompatible_ffmpeg = False
            if line.startswith(b"libavfilter"):
                version = line.split(b" ", 1)[1].split(b"/", 1)[0].split(b".")
                version = tuple(map(int, version))
                if version >= (6, 67, 100):
                    incompatible_ffmpeg = False
        if incompatible_ffmpeg:
            raise FatalReplayGainError(
                "Installed FFmpeg version does not support ReplayGain."
                "calculation. Either libavfilter version 6.67.100 or above or"
                "the --enable-libebur128 configuration option is required."
            )

    def compute_track_gain(self, task: AnyRgTask) -> AnyRgTask:
        """Computes the track gain for the tracks belonging to `task`, and sets
        the `track_gains` attribute on the task. Returns `task`.
        """
        task.track_gains = [
            self._analyse_item(
                item,
                task.target_level,
                task.peak_method,
                count_blocks=False,
            )[0]  # take only the gain, discarding number of gating blocks
            for item in task.items
        ]

        return task

    def compute_album_gain(self, task: AnyRgTask) -> AnyRgTask:
        """Computes the album gain for the album belonging to `task`, and sets
        the `album_gain` attribute on the task. Returns `task`.
        """
        target_level_lufs = db_to_lufs(task.target_level)

        # analyse tracks
        # Gives a list of tuples (track_gain, track_n_blocks)
        track_results: list[tuple[Gain, int]] = [
            self._analyse_item(
                item,
                task.target_level,
                task.peak_method,
                count_blocks=True,
            )
            for item in task.items
        ]

        track_gains: list[Gain] = [tg for tg, _nb in track_results]

        # Album peak is maximum track peak
        album_peak = max(tg.peak for tg in track_gains)

        # Total number of BS.1770 gating blocks
        n_blocks = sum(nb for _tg, nb in track_results)

        def sum_of_track_powers(track_gain: Gain, track_n_blocks: int):
            # convert `LU to target_level` -> LUFS
            loudness = target_level_lufs - track_gain.gain

            # This reverses ITU-R BS.1770-4 p. 6 equation (5) to convert
            # from loudness to power. The result is the average gating
            # block power.
            power = 10 ** ((loudness + 0.691) / 10)

            # Multiply that average power by the number of gating blocks to get
            # the sum of all block powers in this track.
            return track_n_blocks * power

        # calculate album gain
        if n_blocks > 0:
            # Sum over all tracks to get the sum of BS.1770 gating block powers
            # for the entire album.
            sum_powers = sum(
                sum_of_track_powers(tg, nb) for tg, nb in track_results
            )

            # compare ITU-R BS.1770-4 p. 6 equation (5)
            # Album gain is the replaygain of the concatenation of all tracks.
            album_gain = -0.691 + 10 * math.log10(sum_powers / n_blocks)
        else:
            album_gain = -70

        # convert LUFS -> `LU to target_level`
        album_gain = target_level_lufs - album_gain

        self._log.debug(
            "{}: gain {} LU, peak {}",
            task.album,
            album_gain,
            album_peak,
        )

        task.album_gain = Gain(album_gain, album_peak)
        task.track_gains = track_gains

        return task

    def _construct_cmd(
        self, item: Item, peak_method: PeakMethod | None
    ) -> list[str | bytes]:
        """Construct the shell command to analyse items."""
        return [
            self._ffmpeg_path,
            "-nostats",
            "-hide_banner",
            "-i",
            item.path,
            "-map",
            "a:0",
            "-filter",
            "ebur128=peak={}".format(
                "none" if peak_method is None else peak_method.name
            ),
            "-f",
            "null",
            "-",
        ]

    def _analyse_item(
        self,
        item: Item,
        target_level: float,
        peak_method: PeakMethod | None,
        count_blocks: bool = True,
    ) -> tuple[Gain, int]:
        """Analyse item. Return a pair of a Gain object and the number
        of gating blocks above the threshold.

        If `count_blocks` is False, the number of gating blocks returned
        will be 0.
        """
        target_level_lufs = db_to_lufs(target_level)

        # call ffmpeg
        self._log.debug(f"analyzing {item}")
        cmd = self._construct_cmd(item, peak_method)
        self._log.debug("executing {0}", " ".join(map(displayable_path, cmd)))
        output = call(cmd, self._log).stderr.splitlines()

        # parse output

        if peak_method is None:
            peak = 0.0
        else:
            line_peak = self._find_line(
                output,
                # `peak_method` is non-`None` in this arm of the conditional
                f"  {peak_method.name.capitalize()} peak:".encode(),
                start_line=len(output) - 1,
                step_size=-1,
            )
            peak = self._parse_float(
                output[
                    self._find_line(
                        output,
                        b"    Peak:",
                        line_peak,
                    )
                ]
            )
            # convert TPFS -> part of FS
            peak = 10 ** (peak / 20)

        line_integrated_loudness = self._find_line(
            output,
            b"  Integrated loudness:",
            start_line=len(output) - 1,
            step_size=-1,
        )
        gain = self._parse_float(
            output[
                self._find_line(
                    output,
                    b"    I:",
                    line_integrated_loudness,
                )
            ]
        )
        # convert LUFS -> LU from target level
        gain = target_level_lufs - gain

        # count BS.1770 gating blocks
        n_blocks = 0
        if count_blocks:
            gating_threshold = self._parse_float(
                output[
                    self._find_line(
                        output,
                        b"    Threshold:",
                        start_line=line_integrated_loudness,
                    )
                ]
            )
            for line in output:
                if not line.startswith(b"[Parsed_ebur128"):
                    continue
                if line.endswith(b"Summary:"):
                    continue
                line = line.split(b"M:", 1)
                if len(line) < 2:
                    continue
                if self._parse_float(b"M: " + line[1]) >= gating_threshold:
                    n_blocks += 1
            self._log.debug(
                "{}: {} blocks over {} LUFS".format(
                    item, n_blocks, gating_threshold
                )
            )

        self._log.debug("{}: gain {} LU, peak {}".format(item, gain, peak))

        return Gain(gain, peak), n_blocks

    def _find_line(
        self,
        output: Sequence[bytes],
        search: bytes,
        start_line: int = 0,
        step_size: int = 1,
    ) -> int:
        """Return index of line beginning with `search`.

        Begins searching at index `start_line` in `output`.
        """
        end_index = len(output) if step_size > 0 else -1
        for i in range(start_line, end_index, step_size):
            if output[i].startswith(search):
                return i
        raise ReplayGainError(
            "ffmpeg output: missing {} after line {}".format(
                repr(search), start_line
            )
        )

    def _parse_float(self, line: bytes) -> float:
        """Extract a float from a key value pair in `line`.

        This format is expected: /[^:]:[[:space:]]*value.*/, where `value` is
        the float.
        """
        # extract value
        parts = line.split(b":", 1)
        if len(parts) < 2:
            raise ReplayGainError(
                f"ffmpeg output: expected key value pair, found {line!r}"
            )
        value = parts[1].lstrip()
        # strip unit
        value = value.split(b" ", 1)[0]
        # cast value to float
        try:
            return float(value)
        except ValueError:
            raise ReplayGainError(
                f"ffmpeg output: expected float value, found {value!r}"
            )


# mpgain/aacgain CLI tool backend.
class CommandBackend(Backend):
    NAME = "command"
    do_parallel = True

    def __init__(self, config: ConfigView, log: Logger):
        super().__init__(config, log)
        config.add(
            {
                "command": "",
                "noclip": True,
            }
        )

        self.command = cast(str, config["command"].as_str())

        if self.command:
            # Explicit executable path.
            if not os.path.isfile(self.command):
                raise FatalReplayGainError(
                    "replaygain command does not exist: {}".format(self.command)
                )
        else:
            # Check whether the program is in $PATH.
            for cmd in ("mp3gain", "aacgain"):
                try:
                    call([cmd, "-v"], self._log)
                    self.command = cmd
                except OSError:
                    pass
        if not self.command:
            raise FatalReplayGainError(
                "no replaygain command found: install mp3gain or aacgain"
            )

        self.noclip = config["noclip"].get(bool)

    def compute_track_gain(self, task: AnyRgTask) -> AnyRgTask:
        """Computes the track gain for the tracks belonging to `task`, and sets
        the `track_gains` attribute on the task. Returns `task`.
        """
        supported_items = list(filter(self.format_supported, task.items))
        output = self.compute_gain(supported_items, task.target_level, False)
        task.track_gains = output
        return task

    def compute_album_gain(self, task: AnyRgTask) -> AnyRgTask:
        """Computes the album gain for the album belonging to `task`, and sets
        the `album_gain` attribute on the task. Returns `task`.
        """
        # TODO: What should be done when not all tracks in the album are
        # supported?

        supported_items = list(filter(self.format_supported, task.items))
        if len(supported_items) != len(task.items):
            self._log.debug("tracks are of unsupported format")
            task.album_gain = None
            task.track_gains = None
            return task

        output = self.compute_gain(supported_items, task.target_level, True)
        task.album_gain = output[-1]
        task.track_gains = output[:-1]
        return task

    def format_supported(self, item: Item) -> bool:
        """Checks whether the given item is supported by the selected tool."""
        if "mp3gain" in self.command and item.format != "MP3":
            return False
        elif "aacgain" in self.command and item.format not in ("MP3", "AAC"):
            return False
        return True

    def compute_gain(
        self,
        items: Sequence[Item],
        target_level: float,
        is_album: bool,
    ) -> list[Gain]:
        """Computes the track or album gain of a list of items, returns
        a list of TrackGain objects.

        When computing album gain, the last TrackGain object returned is
        the album gain
        """
        if not items:
            self._log.debug("no supported tracks to analyze")
            return []

        """Compute ReplayGain values and return a list of results
        dictionaries as given by `parse_tool_output`.
        """
        # Construct shell command. The "-o" option makes the output
        # easily parseable (tab-delimited). "-s s" forces gain
        # recalculation even if tags are already present and disables
        # tag-writing; this turns the mp3gain/aacgain tool into a gain
        # calculator rather than a tag manipulator because we take care
        # of changing tags ourselves.
        cmd: list[bytes | str] = [self.command, "-o", "-s", "s"]
        if self.noclip:
            # Adjust to avoid clipping.
            cmd = cmd + ["-k"]
        else:
            # Disable clipping warning.
            cmd = cmd + ["-c"]
        cmd = cmd + ["-d", str(int(target_level - 89))]
        cmd = cmd + [syspath(i.path) for i in items]

        self._log.debug("analyzing {0} files", len(items))
        self._log.debug("executing {0}", " ".join(map(displayable_path, cmd)))
        output = call(cmd, self._log).stdout
        self._log.debug("analysis finished")
        return self.parse_tool_output(
            output, len(items) + (1 if is_album else 0)
        )

    def parse_tool_output(self, text: bytes, num_lines: int) -> list[Gain]:
        """Given the tab-delimited output from an invocation of mp3gain
        or aacgain, parse the text and return a list of dictionaries
        containing information about each analyzed file.
        """
        out = []
        for line in text.split(b"\n")[1 : num_lines + 1]:
            parts = line.split(b"\t")
            if len(parts) != 6 or parts[0] == b"File":
                self._log.debug("bad tool output: {0}", text)
                raise ReplayGainError("mp3gain failed")

            # _file = parts[0]
            # _mp3gain = int(parts[1])
            gain = float(parts[2])
            peak = float(parts[3]) / (1 << 15)
            # _maxgain = int(parts[4])
            # _mingain = int(parts[5])

            out.append(Gain(gain, peak))
        return out


# GStreamer-based backend.


class GStreamerBackend(Backend):
    NAME = "gstreamer"

    def __init__(self, config: ConfigView, log: Logger):
        super().__init__(config, log)
        self._import_gst()

        # Initialized a GStreamer pipeline of the form filesrc ->
        # decodebin -> audioconvert -> audioresample -> rganalysis ->
        # fakesink The connection between decodebin and audioconvert is
        # handled dynamically after decodebin figures out the type of
        # the input file.
        self._src = self.Gst.ElementFactory.make("filesrc", "src")
        self._decbin = self.Gst.ElementFactory.make("decodebin", "decbin")
        self._conv = self.Gst.ElementFactory.make("audioconvert", "conv")
        self._res = self.Gst.ElementFactory.make("audioresample", "res")
        self._rg = self.Gst.ElementFactory.make("rganalysis", "rg")

        if (
            self._src is None
            or self._decbin is None
            or self._conv is None
            or self._res is None
            or self._rg is None
        ):
            raise FatalGstreamerPluginReplayGainError(
                "Failed to load required GStreamer plugins"
            )

        # We check which files need gain ourselves, so all files given
        # to rganalsys should have their gain computed, even if it
        # already exists.
        self._rg.set_property("forced", True)
        self._sink = self.Gst.ElementFactory.make("fakesink", "sink")

        self._pipe = self.Gst.Pipeline()
        self._pipe.add(self._src)
        self._pipe.add(self._decbin)
        self._pipe.add(self._conv)
        self._pipe.add(self._res)
        self._pipe.add(self._rg)
        self._pipe.add(self._sink)

        self._src.link(self._decbin)
        self._conv.link(self._res)
        self._res.link(self._rg)
        self._rg.link(self._sink)

        self._bus = self._pipe.get_bus()
        self._bus.add_signal_watch()
        self._bus.connect("message::eos", self._on_eos)
        self._bus.connect("message::error", self._on_error)
        self._bus.connect("message::tag", self._on_tag)
        # Needed for handling the dynamic connection between decodebin
        # and audioconvert
        self._decbin.connect("pad-added", self._on_pad_added)
        self._decbin.connect("pad-removed", self._on_pad_removed)

        self._main_loop = self.GLib.MainLoop()

        self._files: list[bytes] = []

    def _import_gst(self):
        """Import the necessary GObject-related modules and assign `Gst`
        and `GObject` fields on this object.
        """

        try:
            import gi
        except ImportError:
            raise FatalReplayGainError(
                "Failed to load GStreamer: python-gi not found"
            )

        try:
            gi.require_version("Gst", "1.0")
        except ValueError as e:
            raise FatalReplayGainError(f"Failed to load GStreamer 1.0: {e}")

        from gi.repository import GLib, GObject, Gst

        # Calling GObject.threads_init() is not needed for
        # PyGObject 3.10.2+
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            GObject.threads_init()
        Gst.init([sys.argv[0]])

        self.GObject = GObject
        self.GLib = GLib
        self.Gst = Gst

    def compute(self, items: Sequence[Item], target_level: float, album: bool):
        if len(items) == 0:
            return

        self._error = None
        self._files = [i.path for i in items]

        # FIXME: Turn this into DefaultDict[bytes, Gain]
        self._file_tags: collections.defaultdict[bytes, dict[str, float]] = (
            collections.defaultdict(dict)
        )

        self._rg.set_property("reference-level", target_level)

        if album:
            self._rg.set_property("num-tracks", len(self._files))

        if self._set_first_file():
            self._main_loop.run()
            if self._error is not None:
                raise self._error

    def compute_track_gain(self, task: AnyRgTask) -> AnyRgTask:
        """Computes the track gain for the tracks belonging to `task`, and sets
        the `track_gains` attribute on the task. Returns `task`.
        """
        self.compute(task.items, task.target_level, False)
        if len(self._file_tags) != len(task.items):
            raise ReplayGainError("Some tracks did not receive tags")

        ret = []
        for item in task.items:
            ret.append(
                Gain(
                    self._file_tags[item.path]["TRACK_GAIN"],
                    self._file_tags[item.path]["TRACK_PEAK"],
                )
            )

        task.track_gains = ret
        return task

    def compute_album_gain(self, task: AnyRgTask) -> AnyRgTask:
        """Computes the album gain for the album belonging to `task`, and sets
        the `album_gain` attribute on the task. Returns `task`.
        """
        items = list(task.items)
        self.compute(items, task.target_level, True)
        if len(self._file_tags) != len(items):
            raise ReplayGainError("Some items in album did not receive tags")

        # Collect track gains.
        track_gains = []
        for item in items:
            try:
                gain = self._file_tags[item.path]["TRACK_GAIN"]
                peak = self._file_tags[item.path]["TRACK_PEAK"]
            except KeyError:
                raise ReplayGainError("results missing for track")
            track_gains.append(Gain(gain, peak))

        # Get album gain information from the last track.
        last_tags = self._file_tags[items[-1].path]
        try:
            gain = last_tags["ALBUM_GAIN"]
            peak = last_tags["ALBUM_PEAK"]
        except KeyError:
            raise ReplayGainError("results missing for album")

        task.album_gain = Gain(gain, peak)
        task.track_gains = track_gains
        return task

    def close(self):
        self._bus.remove_signal_watch()

    def _on_eos(self, bus, message):
        # A file finished playing in all elements of the pipeline. The
        # RG tags have already been propagated.  If we don't have a next
        # file, we stop processing.
        if not self._set_next_file():
            self._pipe.set_state(self.Gst.State.NULL)
            self._main_loop.quit()

    def _on_error(self, bus, message):
        self._pipe.set_state(self.Gst.State.NULL)
        self._main_loop.quit()
        err, debug = message.parse_error()
        f = self._src.get_property("location")
        # A GStreamer error, either an unsupported format or a bug.
        self._error = ReplayGainError(
            f"Error {err!r} - {debug!r} on file {f!r}"
        )

    def _on_tag(self, bus, message):
        tags = message.parse_tag()

        def handle_tag(taglist, tag, userdata):
            # The rganalysis element provides both the existing tags for
            # files and the new computes tags.  In order to ensure we
            # store the computed tags, we overwrite the RG values of
            # received a second time.
            if tag == self.Gst.TAG_TRACK_GAIN:
                self._file_tags[self._file]["TRACK_GAIN"] = taglist.get_double(
                    tag
                )[1]
            elif tag == self.Gst.TAG_TRACK_PEAK:
                self._file_tags[self._file]["TRACK_PEAK"] = taglist.get_double(
                    tag
                )[1]
            elif tag == self.Gst.TAG_ALBUM_GAIN:
                self._file_tags[self._file]["ALBUM_GAIN"] = taglist.get_double(
                    tag
                )[1]
            elif tag == self.Gst.TAG_ALBUM_PEAK:
                self._file_tags[self._file]["ALBUM_PEAK"] = taglist.get_double(
                    tag
                )[1]
            elif tag == self.Gst.TAG_REFERENCE_LEVEL:
                self._file_tags[self._file]["REFERENCE_LEVEL"] = (
                    taglist.get_double(tag)[1]
                )

        tags.foreach(handle_tag, None)

    def _set_first_file(self) -> bool:
        if len(self._files) == 0:
            return False

        self._file = self._files.pop(0)
        self._pipe.set_state(self.Gst.State.NULL)
        self._src.set_property("location", os.fsdecode(syspath(self._file)))
        self._pipe.set_state(self.Gst.State.PLAYING)
        return True

    def _set_file(self) -> bool:
        """Initialize the filesrc element with the next file to be analyzed."""
        # No more files, we're done
        if len(self._files) == 0:
            return False

        self._file = self._files.pop(0)

        # Ensure the filesrc element received the paused state of the
        # pipeline in a blocking manner
        self._src.sync_state_with_parent()
        self._src.get_state(self.Gst.CLOCK_TIME_NONE)

        # Ensure the decodebin element receives the paused state of the
        # pipeline in a blocking manner
        self._decbin.sync_state_with_parent()
        self._decbin.get_state(self.Gst.CLOCK_TIME_NONE)

        # Disconnect the decodebin element from the pipeline, set its
        # state to READY to to clear it.
        self._decbin.unlink(self._conv)
        self._decbin.set_state(self.Gst.State.READY)

        # Set a new file on the filesrc element, can only be done in the
        # READY state
        self._src.set_state(self.Gst.State.READY)
        self._src.set_property("location", os.fsdecode(syspath(self._file)))

        self._decbin.link(self._conv)
        self._pipe.set_state(self.Gst.State.READY)

        return True

    def _set_next_file(self) -> bool:
        """Set the next file to be analyzed while keeping the pipeline
        in the PAUSED state so that the rganalysis element can correctly
        handle album gain.
        """
        # A blocking pause
        self._pipe.set_state(self.Gst.State.PAUSED)
        self._pipe.get_state(self.Gst.CLOCK_TIME_NONE)

        # Try setting the next file
        ret = self._set_file()
        if ret:
            # Seek to the beginning in order to clear the EOS state of the
            # various elements of the pipeline
            self._pipe.seek_simple(
                self.Gst.Format.TIME, self.Gst.SeekFlags.FLUSH, 0
            )
            self._pipe.set_state(self.Gst.State.PLAYING)

        return ret

    def _on_pad_added(self, decbin, pad):
        sink_pad = self._conv.get_compatible_pad(pad, None)
        assert sink_pad is not None
        pad.link(sink_pad)

    def _on_pad_removed(self, decbin, pad):
        # Called when the decodebin element is disconnected from the
        # rest of the pipeline while switching input files
        peer = pad.get_peer()
        assert peer is None


class AudioToolsBackend(Backend):
    """ReplayGain backend that uses `Python Audio Tools
    <http://audiotools.sourceforge.net/>`_ and its capabilities to read more
    file formats and compute ReplayGain values using it replaygain module.
    """

    NAME = "audiotools"

    def __init__(self, config: ConfigView, log: Logger):
        super().__init__(config, log)
        self._import_audiotools()

    def _import_audiotools(self):
        """Check whether it's possible to import the necessary modules.
        There is no check on the file formats at runtime.

        :raises :exc:`ReplayGainError`: if the modules cannot be imported
        """
        try:
            import audiotools
            import audiotools.replaygain
        except ImportError:
            raise FatalReplayGainError(
                "Failed to load audiotools: audiotools not found"
            )
        self._mod_audiotools = audiotools
        self._mod_replaygain = audiotools.replaygain

    def open_audio_file(self, item: Item):
        """Open the file to read the PCM stream from the using
        ``item.path``.

        :return: the audiofile instance
        :rtype: :class:`audiotools.AudioFile`
        :raises :exc:`ReplayGainError`: if the file is not found or the
        file format is not supported
        """
        try:
            audiofile = self._mod_audiotools.open(
                os.fsdecode(syspath(item.path))
            )
        except OSError:
            raise ReplayGainError(f"File {item.path} was not found")
        except self._mod_audiotools.UnsupportedFile:
            raise ReplayGainError(f"Unsupported file type {item.format}")

        return audiofile

    def init_replaygain(self, audiofile, item: Item):
        """Return an initialized :class:`audiotools.replaygain.ReplayGain`
        instance, which requires the sample rate of the song(s) on which
        the ReplayGain values will be computed. The item is passed in case
        the sample rate is invalid to log the stored item sample rate.

        :return: initialized replagain object
        :rtype: :class:`audiotools.replaygain.ReplayGain`
        :raises: :exc:`ReplayGainError` if the sample rate is invalid
        """
        try:
            rg = self._mod_replaygain.ReplayGain(audiofile.sample_rate())
        except ValueError:
            raise ReplayGainError(f"Unsupported sample rate {item.samplerate}")
            return
        return rg

    def compute_track_gain(self, task: AnyRgTask) -> AnyRgTask:
        """Computes the track gain for the tracks belonging to `task`, and sets
        the `track_gains` attribute on the task. Returns `task`.
        """
        gains = [
            self._compute_track_gain(i, task.target_level) for i in task.items
        ]
        task.track_gains = gains
        return task

    def _with_target_level(self, gain: float, target_level: float):
        """Return `gain` relative to `target_level`.

        Assumes `gain` is relative to 89 db.
        """
        return gain + (target_level - 89)

    def _title_gain(self, rg, audiofile, target_level: float):
        """Get the gain result pair from PyAudioTools using the `ReplayGain`
        instance `rg` for the given `audiofile`.

        Wraps `rg.title_gain(audiofile.to_pcm())` and throws a
        `ReplayGainError` when the library fails.
        """
        try:
            # The method needs an audiotools.PCMReader instance that can
            # be obtained from an audiofile instance.
            gain, peak = rg.title_gain(audiofile.to_pcm())
        except ValueError as exc:
            # `audiotools.replaygain` can raise a `ValueError` if the sample
            # rate is incorrect.
            self._log.debug("error in rg.title_gain() call: {}", exc)
            raise ReplayGainError("audiotools audio data error")
        return self._with_target_level(gain, target_level), peak

    def _compute_track_gain(self, item: Item, target_level: float):
        """Compute ReplayGain value for the requested item.

        :rtype: :class:`Gain`
        """
        audiofile = self.open_audio_file(item)
        rg = self.init_replaygain(audiofile, item)

        # Each call to title_gain on a ReplayGain object returns peak and gain
        # of the track.
        rg_track_gain, rg_track_peak = self._title_gain(
            rg, audiofile, target_level
        )

        self._log.debug(
            "ReplayGain for track {0} - {1}: {2:.2f}, {3:.2f}",
            item.artist,
            item.title,
            rg_track_gain,
            rg_track_peak,
        )
        return Gain(gain=rg_track_gain, peak=rg_track_peak)

    def compute_album_gain(self, task: AnyRgTask) -> AnyRgTask:
        """Computes the album gain for the album belonging to `task`, and sets
        the `album_gain` attribute on the task. Returns `task`.
        """
        # The first item is taken and opened to get the sample rate to
        # initialize the replaygain object. The object is used for all the
        # tracks in the album to get the album values.
        item = list(task.items)[0]
        audiofile = self.open_audio_file(item)
        rg = self.init_replaygain(audiofile, item)

        track_gains = []
        for item in task.items:
            audiofile = self.open_audio_file(item)
            rg_track_gain, rg_track_peak = self._title_gain(
                rg, audiofile, task.target_level
            )
            track_gains.append(Gain(gain=rg_track_gain, peak=rg_track_peak))
            self._log.debug(
                "ReplayGain for track {0}: {1:.2f}, {2:.2f}",
                item,
                rg_track_gain,
                rg_track_peak,
            )

        # After getting the values for all tracks, it's possible to get the
        # album values.
        rg_album_gain, rg_album_peak = rg.album_gain()
        rg_album_gain = self._with_target_level(
            rg_album_gain, task.target_level
        )
        self._log.debug(
            "ReplayGain for album {0}: {1:.2f}, {2:.2f}",
            task.items[0].album,
            rg_album_gain,
            rg_album_peak,
        )

        task.album_gain = Gain(gain=rg_album_gain, peak=rg_album_peak)
        task.track_gains = track_gains
        return task


class ExceptionWatcher(Thread):
    """Monitors a queue for exceptions asynchronously.
    Once an exception occurs, raise it and execute a callback.
    """

    def __init__(self, queue: queue.Queue, callback: Callable[[], None]):
        self._queue = queue
        self._callback = callback
        self._stopevent = Event()
        Thread.__init__(self)

    def run(self):
        while not self._stopevent.is_set():
            try:
                exc = self._queue.get_nowait()
                self._callback()
                raise exc
            except queue.Empty:
                # No exceptions yet, loop back to check
                #  whether `_stopevent` is set
                pass

    def join(self, timeout: float | None = None):
        self._stopevent.set()
        Thread.join(self, timeout)


# Main plugin logic.

BACKEND_CLASSES: list[type[Backend]] = [
    CommandBackend,
    GStreamerBackend,
    AudioToolsBackend,
    FfmpegBackend,
]
BACKENDS: dict[str, type[Backend]] = {b.NAME: b for b in BACKEND_CLASSES}


class ReplayGainPlugin(BeetsPlugin):
    """Provides ReplayGain analysis."""

    def __init__(self):
        super().__init__()

        # default backend is 'command' for backward-compatibility.
        self.config.add(
            {
                "overwrite": False,
                "auto": True,
                "backend": "command",
                "threads": os.cpu_count(),
                "parallel_on_import": False,
                "per_disc": False,
                "peak": "true",
                "targetlevel": 89,
                "r128": ["Opus"],
                "r128_targetlevel": lufs_to_db(-23),
            }
        )

        # FIXME: Consider renaming the configuration option and deprecating the
        # old name 'overwrite'.
        self.force_on_import = cast(bool, self.config["overwrite"].get(bool))

        # Remember which backend is used for CLI feedback
        self.backend_name = self.config["backend"].as_str()

        if self.backend_name not in BACKENDS:
            raise ui.UserError(
                "Selected ReplayGain backend {} is not supported. "
                "Please select one of: {}".format(
                    self.backend_name, ", ".join(BACKENDS.keys())
                )
            )

        # FIXME: Consider renaming the configuration option to 'peak_method'
        # and deprecating the old name 'peak'.
        peak_method = self.config["peak"].as_str()
        if peak_method not in PeakMethod.__members__:
            raise ui.UserError(
                "Selected ReplayGain peak method {} is not supported. "
                "Please select one of: {}".format(
                    peak_method, ", ".join(PeakMethod.__members__)
                )
            )
        # This only applies to plain old rg tags, r128 doesn't store peak
        # values.
        self.peak_method = PeakMethod[peak_method]

        # On-import analysis.
        if self.config["auto"]:
            self.register_listener("import_begin", self.import_begin)
            self.register_listener("import", self.import_end)
            self.import_stages = [self.imported]

        # Formats to use R128.
        self.r128_whitelist = self.config["r128"].as_str_seq()

        try:
            self.backend_instance = BACKENDS[self.backend_name](
                self.config, self._log
            )
        except (ReplayGainError, FatalReplayGainError) as e:
            raise ui.UserError(f"replaygain initialization failed: {e}")

        # Start threadpool lazily.
        self.pool = None

    def should_use_r128(self, item: Item) -> bool:
        """Checks the plugin setting to decide whether the calculation
        should be done using the EBU R128 standard and use R128_ tags instead.
        """
        return item.format in self.r128_whitelist

    @staticmethod
    def has_r128_track_data(item: Item) -> bool:
        return item.r128_track_gain is not None

    @staticmethod
    def has_rg_track_data(item: Item) -> bool:
        return item.rg_track_gain is not None and item.rg_track_peak is not None

    def track_requires_gain(self, item: Item) -> bool:
        if self.should_use_r128(item):
            if not self.has_r128_track_data(item):
                return True
        else:
            if not self.has_rg_track_data(item):
                return True

        return False

    @staticmethod
    def has_r128_album_data(item: Item) -> bool:
        return (
            item.r128_track_gain is not None
            and item.r128_album_gain is not None
        )

    @staticmethod
    def has_rg_album_data(item: Item) -> bool:
        return item.rg_album_gain is not None and item.rg_album_peak is not None

    def album_requires_gain(self, album: Album) -> bool:
        # Skip calculating gain only when *all* files don't need
        # recalculation. This way, if any file among an album's tracks
        # needs recalculation, we still get an accurate album gain
        # value.
        for item in album.items():
            if self.should_use_r128(item):
                if not self.has_r128_album_data(item):
                    return True
            else:
                if not self.has_rg_album_data(item):
                    return True

        return False

    def create_task(
        self,
        items: Sequence[Item],
        use_r128: bool,
        album: Album | None = None,
    ) -> RgTask:
        if use_r128:
            return R128Task(
                items,
                album,
                self.config["r128_targetlevel"].as_number(),
                self.backend_instance.NAME,
                self._log,
            )
        else:
            return RgTask(
                items,
                album,
                self.config["targetlevel"].as_number(),
                self.peak_method,
                self.backend_instance.NAME,
                self._log,
            )

    def handle_album(self, album: Album, write: bool, force: bool = False):
        """Compute album and track replay gain store it in all of the
        album's items.

        If ``write`` is truthy then ``item.write()`` is called for each
        item. If replay gain information is already present in all
        items, nothing is done.
        """
        if not force and not self.album_requires_gain(album):
            self._log.info("Skipping album {0}", album)
            return

        items_iter = iter(album.items())
        use_r128 = self.should_use_r128(next(items_iter))
        if any(use_r128 != self.should_use_r128(i) for i in items_iter):
            self._log.error(
                "Cannot calculate gain for album {0} (incompatible formats)",
                album,
            )
            return

        self._log.info("analyzing {0}", album)

        discs: dict[int, list[Item]] = {}
        if self.config["per_disc"].get(bool):
            for item in album.items():
                if discs.get(item.disc) is None:
                    discs[item.disc] = []
                discs[item.disc].append(item)
        else:
            discs[1] = album.items()

        def store_cb(task: RgTask):
            task.store(write)

        for discnumber, items in discs.items():
            task = self.create_task(items, use_r128, album=album)
            try:
                self._apply(
                    self.backend_instance.compute_album_gain,
                    args=[task],
                    kwds={},
                    callback=store_cb,
                )
            except ReplayGainError as e:
                self._log.info("ReplayGain error: {0}", e)
            except FatalReplayGainError as e:
                raise ui.UserError(f"Fatal replay gain error: {e}")

    def handle_track(self, item: Item, write: bool, force: bool = False):
        """Compute track replay gain and store it in the item.

        If ``write`` is truthy then ``item.write()`` is called to write
        the data to disk.  If replay gain information is already present
        in the item, nothing is done.
        """
        if not force and not self.track_requires_gain(item):
            self._log.info("Skipping track {0}", item)
            return

        use_r128 = self.should_use_r128(item)

        def store_cb(task: RgTask):
            task.store(write)

        task = self.create_task([item], use_r128)
        try:
            self._apply(
                self.backend_instance.compute_track_gain,
                args=[task],
                kwds={},
                callback=store_cb,
            )
        except ReplayGainError as e:
            self._log.info("ReplayGain error: {0}", e)
        except FatalReplayGainError as e:
            raise ui.UserError(f"Fatal replay gain error: {e}")

    def open_pool(self, threads: int):
        """Open a `ThreadPool` instance in `self.pool`"""
        if self.pool is None and self.backend_instance.do_parallel:
            self.pool = ThreadPool(threads)
            self.exc_queue: queue.Queue = queue.Queue()

            signal.signal(signal.SIGINT, self._interrupt)

            self.exc_watcher = ExceptionWatcher(
                self.exc_queue,  # threads push exceptions here
                self.terminate_pool,  # abort once an exception occurs
            )
            self.exc_watcher.start()

    def _apply(
        self,
        func: Callable[..., AnyRgTask],
        args: list[Any],
        kwds: dict[str, Any],
        callback: Callable[[AnyRgTask], Any],
    ):
        if self.pool is not None:

            def handle_exc(exc):
                """Handle exceptions in the async work."""
                if isinstance(exc, ReplayGainError):
                    self._log.info(exc.args[0])  # Log non-fatal exceptions.
                else:
                    self.exc_queue.put(exc)

            self.pool.apply_async(
                func, args, kwds, callback, error_callback=handle_exc
            )
        else:
            callback(func(*args, **kwds))

    def terminate_pool(self):
        """Forcibly terminate the `ThreadPool` instance in `self.pool`

        Sends SIGTERM to all processes.
        """
        if self.pool is not None:
            self.pool.terminate()
            self.pool.join()
            # Terminating the processes leaves the ExceptionWatcher's queues
            # in an unknown state, so don't wait for it.
            # self.exc_watcher.join()
            self.pool = None

    def _interrupt(self, signal, frame):
        try:
            self._log.info("interrupted")
            self.terminate_pool()
            sys.exit(0)
        except SystemExit:
            # Silence raised SystemExit ~ exit(0)
            pass

    def close_pool(self):
        """Regularly close the `ThreadPool` instance in `self.pool`."""
        if self.pool is not None:
            self.pool.close()
            self.pool.join()
            self.exc_watcher.join()
            self.pool = None

    def import_begin(self, session: ImportSession):
        """Handle `import_begin` event -> open pool"""
        threads = cast(int, self.config["threads"].get(int))

        if (
            self.config["parallel_on_import"]
            and self.config["auto"]
            and threads
        ):
            self.open_pool(threads)

    def import_end(self, paths):
        """Handle `import` event -> close pool"""
        self.close_pool()

    def imported(self, session: ImportSession, task: ImportTask):
        """Add replay gain info to items or albums of ``task``."""
        if self.config["auto"]:
            if task.is_album:
                self.handle_album(task.album, False, self.force_on_import)
            else:
                # Should be a SingletonImportTask
                assert hasattr(task, "item")
                self.handle_track(task.item, False, self.force_on_import)

    def command_func(
        self,
        lib: Library,
        opts: optparse.Values,
        args: list[str],
    ):
        try:
            write = ui.should_write(opts.write)
            force = opts.force

            # Bypass self.open_pool() if called with  `--threads 0`
            if opts.threads != 0:
                threads = opts.threads or cast(
                    int, self.config["threads"].get(int)
                )
                self.open_pool(threads)

            if opts.album:
                albums = lib.albums(ui.decargs(args))
                self._log.info(
                    "Analyzing {} albums ~ {} backend...".format(
                        len(albums), self.backend_name
                    )
                )
                for album in albums:
                    self.handle_album(album, write, force)
            else:
                items = lib.items(ui.decargs(args))
                self._log.info(
                    "Analyzing {} tracks ~ {} backend...".format(
                        len(items), self.backend_name
                    )
                )
                for item in items:
                    self.handle_track(item, write, force)

            self.close_pool()
        except (SystemExit, KeyboardInterrupt):
            # Silence interrupt exceptions
            pass

    def commands(self) -> list[ui.Subcommand]:
        """Return the "replaygain" ui subcommand."""
        cmd = ui.Subcommand("replaygain", help="analyze for ReplayGain")
        cmd.parser.add_album_option()
        cmd.parser.add_option(
            "-t",
            "--threads",
            dest="threads",
            type=int,
            help="change the number of threads, \
            defaults to maximum available processors",
        )
        cmd.parser.add_option(
            "-f",
            "--force",
            dest="force",
            action="store_true",
            default=False,
            help="analyze all files, including those that "
            "already have ReplayGain metadata",
        )
        cmd.parser.add_option(
            "-w",
            "--write",
            default=None,
            action="store_true",
            help="write new metadata to files' tags",
        )
        cmd.parser.add_option(
            "-W",
            "--nowrite",
            dest="write",
            action="store_false",
            help="don't write metadata (opposite of -w)",
        )
        cmd.func = self.command_func
        return [cmd]
