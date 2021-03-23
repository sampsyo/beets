# -*- coding: utf-8 -*-
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

from __future__ import division, absolute_import, print_function

import collections
import enum
import math
import os
import subprocess
import sys
import warnings
from concurrent import futures
from concurrent.futures import CancelledError
from six.moves import zip

from beets import ui
from beets.plugins import BeetsPlugin
from beets.util import (syspath, command_output, displayable_path,
                        py3_path, cpu_count)
from beets.util.concurrency import combine_futures, pool


# Utilities.

class ReplayGainError(Exception):
    """Raised when a local (to a track or an album) error occurs in one
    of the backends.
    """


class FatalReplayGainError(Exception):
    """Raised when a fatal error occurs in one of the backends.
    """


class FatalGstreamerPluginReplayGainError(FatalReplayGainError):
    """Raised when a fatal error occurs in the GStreamerBackend when
    loading the required plugins."""


def call(args, **kwargs):
    """Execute the command and return its output or raise a
    ReplayGainError on failure.
    """
    try:
        return command_output(args, **kwargs)
    except subprocess.CalledProcessError as e:
        raise ReplayGainError(
            u"{0} exited with status {1}".format(args[0], e.returncode)
        )
    except UnicodeEncodeError:
        # Due to a bug in Python 2's subprocess on Windows, Unicode
        # filenames can fail to encode on that platform. See:
        # https://github.com/google-code-export/beets/issues/499
        raise ReplayGainError(u"argument encoding failed")


def after_version(version_a, version_b):
    return tuple(int(s) for s in version_a.split('.')) \
            >= tuple(int(s) for s in version_b.split('.'))


def db_to_lufs(db):
    """Convert db to LUFS.

    According to https://wiki.hydrogenaud.io/index.php?title=
      ReplayGain_2.0_specification#Reference_level
    """
    return db - 107


def lufs_to_db(db):
    """Convert LUFS to db.

    According to https://wiki.hydrogenaud.io/index.php?title=
      ReplayGain_2.0_specification#Reference_level
    """
    return db + 107


# Backend base and plumbing classes.

# gain: in LU to reference level
# peak: part of full scale (FS is 1.0)
Gain = collections.namedtuple("Gain", "gain peak")


ALL_PEAK_METHODS = ["true", "sample"]
Peak = enum.Enum("Peak", ["none"] + ALL_PEAK_METHODS)


class Backend(object):
    """An abstract class representing engine for calculating RG values.
    """

    NAME = ""
    do_parallel = False

    def __init__(self, config, log):
        """Initialize the backend with the configuration view for the
        plugin.
        """
        self._log = log

    def compute_track_gain(self, task):
        """Computes the track gain for the tracks belonging to `task`, and sets
        the `track_gains` attribute on the task. Returns `task`.
        """
        raise NotImplementedError()

    def compute_album_gain(self, task):
        """Computes the album gain for the album belonging to `task`, and sets
        the `album_gain` attribute on the task. Returns `task`.
        """
        raise NotImplementedError()


# ffmpeg backend
class FfmpegBackend(Backend):
    """A replaygain backend using ffmpeg's ebur128 filter.
    """

    NAME = "ffmpeg"
    do_parallel = True

    def __init__(self, config, log):
        super(FfmpegBackend, self).__init__(config, log)
        self._ffmpeg_path = "ffmpeg"

        # check that ffmpeg is installed
        try:
            ffmpeg_version_out = call([self._ffmpeg_path, "-version"])
        except OSError:
            raise FatalReplayGainError(
                u"could not find ffmpeg at {0}".format(self._ffmpeg_path)
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
                u"Installed FFmpeg version does not support ReplayGain."
                u"calculation. Either libavfilter version 6.67.100 or above or"
                u"the --enable-libebur128 configuration option is required."
            )

    def compute_track_gain(self, task):
        """Computes the track gain for the tracks belonging to `task`, and sets
        the `track_gains` attribute on the task. Returns `task`.
        """
        gains = []
        for item in task.items:
            gains.append(
                self._analyse_item(
                    item,
                    task.target_level,
                    task.peak,
                    count_blocks=False,
                )[0]  # take only the gain, discarding number of gating blocks
            )
        task.track_gains = gains
        return task

    def compute_album_gain(self, task):
        """Computes the album gain for the album belonging to `task`, and sets
        the `album_gain` attribute on the task. Returns `task`.
        """
        target_level_lufs = db_to_lufs(task.target_level)

        # analyse tracks
        # list of track Gain objects
        track_gains = []
        # maximum peak
        album_peak = 0
        # sum of BS.1770 gating block powers
        sum_powers = 0
        # total number of BS.1770 gating blocks
        n_blocks = 0

        for item in task.items:
            track_gain, track_n_blocks = self._analyse_item(
                item, task.target_level, task.peak
            )
            track_gains.append(track_gain)

            # album peak is maximum track peak
            album_peak = max(album_peak, track_gain.peak)

            # prepare album_gain calculation
            # total number of blocks is sum of track blocks
            n_blocks += track_n_blocks

            # convert `LU to target_level` -> LUFS
            track_loudness = target_level_lufs - track_gain.gain
            # This reverses ITU-R BS.1770-4 p. 6 equation (5) to convert
            # from loudness to power. The result is the average gating
            # block power.
            track_power = 10**((track_loudness + 0.691) / 10)

            # Weight that average power by the number of gating blocks to
            # get the sum of all their powers. Add that to the sum of all
            # block powers in this album.
            sum_powers += track_power * track_n_blocks

        # calculate album gain
        if n_blocks > 0:
            # compare ITU-R BS.1770-4 p. 6 equation (5)
            # Album gain is the replaygain of the concatenation of all tracks.
            album_gain = -0.691 + 10 * math.log10(sum_powers / n_blocks)
        else:
            album_gain = -70
        # convert LUFS -> `LU to target_level`
        album_gain = target_level_lufs - album_gain

        self._log.debug(
            u"{0}: gain {1} LU, peak {2}"
            .format(task.items, album_gain, album_peak)
            )

        task.album_gain = Gain(album_gain, album_peak)
        task.track_gains = track_gains
        return task

    def _construct_cmd(self, item, peak_method):
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
            "ebur128=peak={0}".format(peak_method),
            "-f",
            "null",
            "-",
        ]

    def _analyse_item(self, item, target_level, peak, count_blocks=True):
        """Analyse item. Return a pair of a Gain object and the number
        of gating blocks above the threshold.

        If `count_blocks` is False, the number of gating blocks returned
        will be 0.
        """
        target_level_lufs = db_to_lufs(target_level)
        peak_method = peak.name

        # call ffmpeg
        self._log.debug(u"analyzing {0}".format(item))
        cmd = self._construct_cmd(item, peak_method)
        self._log.debug(
            u'executing {0}', u' '.join(map(displayable_path, cmd))
        )
        output = call(cmd).stderr.splitlines()

        # parse output

        if peak == Peak.none:
            peak = 0
        else:
            line_peak = self._find_line(
                output,
                "  {0} peak:".format(peak_method.capitalize()).encode(),
                start_line=len(output) - 1, step_size=-1,
            )
            peak = self._parse_float(
                output[self._find_line(
                    output, b"    Peak:",
                    line_peak,
                )]
            )
            # convert TPFS -> part of FS
            peak = 10**(peak / 20)

        line_integrated_loudness = self._find_line(
            output, b"  Integrated loudness:",
            start_line=len(output) - 1, step_size=-1,
        )
        gain = self._parse_float(
            output[self._find_line(
                output, b"    I:",
                line_integrated_loudness,
            )]
        )
        # convert LUFS -> LU from target level
        gain = target_level_lufs - gain

        # count BS.1770 gating blocks
        n_blocks = 0
        if count_blocks:
            gating_threshold = self._parse_float(
                output[self._find_line(
                    output, b"    Threshold:",
                    start_line=line_integrated_loudness,
                )]
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
                u"{0}: {1} blocks over {2} LUFS"
                .format(item, n_blocks, gating_threshold)
            )

        self._log.debug(
            u"{0}: gain {1} LU, peak {2}"
            .format(item, gain, peak)
        )

        return Gain(gain, peak), n_blocks

    def _find_line(self, output, search, start_line=0, step_size=1):
        """Return index of line beginning with `search`.

        Begins searching at index `start_line` in `output`.
        """
        end_index = len(output) if step_size > 0 else -1
        for i in range(start_line, end_index, step_size):
            if output[i].startswith(search):
                return i
        raise ReplayGainError(
            u"ffmpeg output: missing {0} after line {1}"
            .format(repr(search), start_line)
            )

    def _parse_float(self, line):
        """Extract a float from a key value pair in `line`.

        This format is expected: /[^:]:[[:space:]]*value.*/, where `value` is
        the float.
        """
        # extract value
        value = line.split(b":", 1)
        if len(value) < 2:
            raise ReplayGainError(
                u"ffmpeg output: expected key value pair, found {0}"
                .format(line)
                )
        value = value[1].lstrip()
        # strip unit
        value = value.split(b" ", 1)[0]
        # cast value to float
        try:
            return float(value)
        except ValueError:
            raise ReplayGainError(
                u"ffmpeg output: expected float value, found {0}"
                .format(value)
                )


# mpgain/aacgain CLI tool backend.
class CommandBackend(Backend):
    NAME = "command"
    do_parallel = True

    def __init__(self, config, log):
        super(CommandBackend, self).__init__(config, log)
        config.add({
            'command': u"",
            'noclip': True,
        })

        self.command = config["command"].as_str()

        if self.command:
            # Explicit executable path.
            if not os.path.isfile(self.command):
                raise FatalReplayGainError(
                    u'replaygain command does not exist: {0}'.format(
                        self.command)
                )
        else:
            # Check whether the program is in $PATH.
            for cmd in ('mp3gain', 'aacgain'):
                try:
                    call([cmd, '-v'])
                    self.command = cmd
                except OSError:
                    pass
        if not self.command:
            raise FatalReplayGainError(
                u'no replaygain command found: install mp3gain or aacgain'
            )

        self.noclip = config['noclip'].get(bool)

    def compute_track_gain(self, task):
        """Computes the track gain for the tracks belonging to `task`, and sets
        the `track_gains` attribute on the task. Returns `task`.
        """
        supported_items = list(filter(self.format_supported, task.items))
        output = self.compute_gain(supported_items, task.target_level, False)
        task.track_gains = output
        return task

    def compute_album_gain(self, task):
        """Computes the album gain for the album belonging to `task`, and sets
        the `album_gain` attribute on the task. Returns `task`.
        """
        # TODO: What should be done when not all tracks in the album are
        # supported?

        supported_items = list(filter(self.format_supported, task.items))
        if len(supported_items) != len(task.items):
            self._log.debug(u'tracks are of unsupported format')
            task.album_gain = None
            task.track_gains = None
            return task

        output = self.compute_gain(supported_items, task.target_level, True)
        task.album_gain = output[-1]
        task.track_gains = output[:-1]
        return task

    def format_supported(self, item):
        """Checks whether the given item is supported by the selected tool.
        """
        if 'mp3gain' in self.command and item.format != 'MP3':
            return False
        elif 'aacgain' in self.command and item.format not in ('MP3', 'AAC'):
            return False
        return True

    def compute_gain(self, items, target_level, is_album):
        """Computes the track or album gain of a list of items, returns
        a list of TrackGain objects.

        When computing album gain, the last TrackGain object returned is
        the album gain
        """
        if len(items) == 0:
            self._log.debug(u'no supported tracks to analyze')
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
        cmd = [self.command, '-o', '-s', 's']
        if self.noclip:
            # Adjust to avoid clipping.
            cmd = cmd + ['-k']
        else:
            # Disable clipping warning.
            cmd = cmd + ['-c']
        cmd = cmd + ['-d', str(int(target_level - 89))]
        cmd = cmd + [syspath(i.path) for i in items]

        self._log.debug(u'analyzing {0} files', len(items))
        self._log.debug(u"executing {0}", " ".join(map(displayable_path, cmd)))
        output = call(cmd).stdout
        self._log.debug(u'analysis finished')
        return self.parse_tool_output(output,
                                      len(items) + (1 if is_album else 0))

    def parse_tool_output(self, text, num_lines):
        """Given the tab-delimited output from an invocation of mp3gain
        or aacgain, parse the text and return a list of dictionaries
        containing information about each analyzed file.
        """
        out = []
        for line in text.split(b'\n')[1:num_lines + 1]:
            parts = line.split(b'\t')
            if len(parts) != 6 or parts[0] == b'File':
                self._log.debug(u'bad tool output: {0}', text)
                raise ReplayGainError(u'mp3gain failed')
            d = {
                'file': parts[0],
                'mp3gain': int(parts[1]),
                'gain': float(parts[2]),
                'peak': float(parts[3]) / (1 << 15),
                'maxgain': int(parts[4]),
                'mingain': int(parts[5]),

            }
            out.append(Gain(d['gain'], d['peak']))
        return out


# GStreamer-based backend.

class GStreamerBackend(Backend):
    NAME = "gstreamer"

    def __init__(self, config, log):
        super(GStreamerBackend, self).__init__(config, log)
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

        if self._src is None or self._decbin is None or self._conv is None \
           or self._res is None or self._rg is None:
            raise FatalGstreamerPluginReplayGainError(
                u"Failed to load required GStreamer plugins"
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

        self._files = []

    def _import_gst(self):
        """Import the necessary GObject-related modules and assign `Gst`
        and `GObject` fields on this object.
        """

        try:
            import gi
        except ImportError:
            raise FatalReplayGainError(
                u"Failed to load GStreamer: python-gi not found"
            )

        try:
            gi.require_version('Gst', '1.0')
        except ValueError as e:
            raise FatalReplayGainError(
                u"Failed to load GStreamer 1.0: {0}".format(e)
            )

        from gi.repository import GObject, Gst, GLib
        # Calling GObject.threads_init() is not needed for
        # PyGObject 3.10.2+
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            GObject.threads_init()
        Gst.init([sys.argv[0]])

        self.GObject = GObject
        self.GLib = GLib
        self.Gst = Gst

    def compute(self, files, target_level, album):
        self._error = None
        self._files = list(files)

        if len(self._files) == 0:
            return

        self._file_tags = collections.defaultdict(dict)

        self._rg.set_property("reference-level", target_level)

        if album:
            self._rg.set_property("num-tracks", len(self._files))

        if self._set_first_file():
            self._main_loop.run()
            if self._error is not None:
                raise self._error

    def compute_track_gain(self, task):
        """Computes the track gain for the tracks belonging to `task`, and sets
        the `track_gains` attribute on the task. Returns `task`.
        """
        self.compute(task.items, task.target_level, False)
        if len(self._file_tags) != len(task.items):
            raise ReplayGainError(u"Some tracks did not receive tags")

        ret = []
        for item in task.items:
            ret.append(Gain(self._file_tags[item]["TRACK_GAIN"],
                            self._file_tags[item]["TRACK_PEAK"]))

        task.track_gains = ret
        return task

    def compute_album_gain(self, task):
        """Computes the album gain for the album belonging to `task`, and sets
        the `album_gain` attribute on the task. Returns `task`.
        """
        items = list(task.items)
        self.compute(items, task.target_level, True)
        if len(self._file_tags) != len(items):
            raise ReplayGainError(u"Some items in album did not receive tags")

        # Collect track gains.
        track_gains = []
        for item in items:
            try:
                gain = self._file_tags[item]["TRACK_GAIN"]
                peak = self._file_tags[item]["TRACK_PEAK"]
            except KeyError:
                raise ReplayGainError(u"results missing for track")
            track_gains.append(Gain(gain, peak))

        # Get album gain information from the last track.
        last_tags = self._file_tags[items[-1]]
        try:
            gain = last_tags["ALBUM_GAIN"]
            peak = last_tags["ALBUM_PEAK"]
        except KeyError:
            raise ReplayGainError(u"results missing for album")

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
            u"Error {0!r} - {1!r} on file {2!r}".format(err, debug, f)
        )

    def _on_tag(self, bus, message):
        tags = message.parse_tag()

        def handle_tag(taglist, tag, userdata):
            # The rganalysis element provides both the existing tags for
            # files and the new computes tags.  In order to ensure we
            # store the computed tags, we overwrite the RG values of
            # received a second time.
            if tag == self.Gst.TAG_TRACK_GAIN:
                self._file_tags[self._file]["TRACK_GAIN"] = \
                    taglist.get_double(tag)[1]
            elif tag == self.Gst.TAG_TRACK_PEAK:
                self._file_tags[self._file]["TRACK_PEAK"] = \
                    taglist.get_double(tag)[1]
            elif tag == self.Gst.TAG_ALBUM_GAIN:
                self._file_tags[self._file]["ALBUM_GAIN"] = \
                    taglist.get_double(tag)[1]
            elif tag == self.Gst.TAG_ALBUM_PEAK:
                self._file_tags[self._file]["ALBUM_PEAK"] = \
                    taglist.get_double(tag)[1]
            elif tag == self.Gst.TAG_REFERENCE_LEVEL:
                self._file_tags[self._file]["REFERENCE_LEVEL"] = \
                    taglist.get_double(tag)[1]

        tags.foreach(handle_tag, None)

    def _set_first_file(self):
        if len(self._files) == 0:
            return False

        self._file = self._files.pop(0)
        self._pipe.set_state(self.Gst.State.NULL)
        self._src.set_property("location", py3_path(syspath(self._file.path)))
        self._pipe.set_state(self.Gst.State.PLAYING)
        return True

    def _set_file(self):
        """Initialize the filesrc element with the next file to be analyzed.
        """
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
        self._src.set_property("location", py3_path(syspath(self._file.path)))

        self._decbin.link(self._conv)
        self._pipe.set_state(self.Gst.State.READY)

        return True

    def _set_next_file(self):
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
            self._pipe.seek_simple(self.Gst.Format.TIME,
                                   self.Gst.SeekFlags.FLUSH,
                                   0)
            self._pipe.set_state(self.Gst.State.PLAYING)

        return ret

    def _on_pad_added(self, decbin, pad):
        sink_pad = self._conv.get_compatible_pad(pad, None)
        assert(sink_pad is not None)
        pad.link(sink_pad)

    def _on_pad_removed(self, decbin, pad):
        # Called when the decodebin element is disconnected from the
        # rest of the pipeline while switching input files
        peer = pad.get_peer()
        assert(peer is None)


class AudioToolsBackend(Backend):
    """ReplayGain backend that uses `Python Audio Tools
    <http://audiotools.sourceforge.net/>`_ and its capabilities to read more
    file formats and compute ReplayGain values using it replaygain module.
    """
    NAME = "audiotools"

    def __init__(self, config, log):
        super(AudioToolsBackend, self).__init__(config, log)
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
                u"Failed to load audiotools: audiotools not found"
            )
        self._mod_audiotools = audiotools
        self._mod_replaygain = audiotools.replaygain

    def open_audio_file(self, item):
        """Open the file to read the PCM stream from the using
        ``item.path``.

        :return: the audiofile instance
        :rtype: :class:`audiotools.AudioFile`
        :raises :exc:`ReplayGainError`: if the file is not found or the
        file format is not supported
        """
        try:
            audiofile = self._mod_audiotools.open(py3_path(syspath(item.path)))
        except IOError:
            raise ReplayGainError(
                u"File {} was not found".format(item.path)
            )
        except self._mod_audiotools.UnsupportedFile:
            raise ReplayGainError(
                u"Unsupported file type {}".format(item.format)
            )

        return audiofile

    def init_replaygain(self, audiofile, item):
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
            raise ReplayGainError(
                u"Unsupported sample rate {}".format(item.samplerate))
            return
        return rg

    def compute_track_gain(self, task):
        """Computes the track gain for the tracks belonging to `task`, and sets
        the `track_gains` attribute on the task. Returns `task`.
        """
        gains = [self._compute_track_gain(i, task.target_level)
                 for i in task.items]
        task.track_gains = gains
        return task

    def _with_target_level(self, gain, target_level):
        """Return `gain` relative to `target_level`.

        Assumes `gain` is relative to 89 db.
        """
        return gain + (target_level - 89)

    def _title_gain(self, rg, audiofile, target_level):
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
            self._log.debug(u'error in rg.title_gain() call: {}', exc)
            raise ReplayGainError(u'audiotools audio data error')
        return self._with_target_level(gain, target_level), peak

    def _compute_track_gain(self, item, target_level):
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

        self._log.debug(u'ReplayGain for track {0} - {1}: {2:.2f}, {3:.2f}',
                        item.artist, item.title, rg_track_gain, rg_track_peak)
        return Gain(gain=rg_track_gain, peak=rg_track_peak)

    def compute_album_gain(self, task):
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
            track_gains.append(
                Gain(gain=rg_track_gain, peak=rg_track_peak)
            )
            self._log.debug(u'ReplayGain for track {0}: {1:.2f}, {2:.2f}',
                            item, rg_track_gain, rg_track_peak)

        # After getting the values for all tracks, it's possible to get the
        # album values.
        rg_album_gain, rg_album_peak = rg.album_gain()
        rg_album_gain = self._with_target_level(
                rg_album_gain, task.target_level)
        self._log.debug(u'ReplayGain for album {0}: {1:.2f}, {2:.2f}',
                        task.items[0].album, rg_album_gain, rg_album_peak)

        task.album_gain = Gain(gain=rg_album_gain, peak=rg_album_peak)
        task.track_gains = track_gains
        return task


class RgTask():
    def __init__(self, items, album, target_level, peak, backend_name, log):
        self.items = items
        self.album = album
        self.target_level = target_level
        self.peak = peak
        self.backend_name = backend_name
        self._log = log
        self.album_gain = None
        self.track_gains = None

    def _store_track_gain(self, item, track_gain):
        item.rg_track_gain = track_gain.gain
        item.rg_track_peak = track_gain.peak
        item.store()
        self._log.debug(u'applied track gain {0} LU, peak {1} of FS',
                        item.rg_track_gain, item.rg_track_peak)

    def _store_album_gain(self, item):
        """

        The caller needs to ensure that `self.album_gain is not None`.
        """
        item.rg_album_gain = self.album_gain.gain
        item.rg_album_peak = self.album_gain.peak
        item.store()
        self._log.debug(u'applied album gain {0} LU, peak {1} of FS',
                        item.rg_album_gain, item.rg_album_peak)

    def store_track(self, write):
        item = self.items[0]
        if self.track_gains is None or len(self.track_gains) != 1:
            # In some cases, backends fail to produce a valid
            # `track_gains` without throwing FatalReplayGainError
            #  => raise non-fatal exception & continue
            raise ReplayGainError(
                u"ReplayGain backend `{}` failed for track {}"
                .format(self.backend_name, item)
            )

        self._store_track_gain(item, self.track_gains[0])
        if write:
            item.try_write()
        self._log.debug(u'done analyzing {0}', item)

    def store_album(self, write):
        if (self.album_gain is None or self.track_gains is None
                or len(self.track_gains) != len(self.items)):
            # In some cases, backends fail to produce a valid
            # `album_gain` without throwing FatalReplayGainError
            #  => raise non-fatal exception & continue
            raise ReplayGainError(
                u"ReplayGain backend `{}` failed "
                u"for some tracks in album {}"
                .format(self.backend_name, self.album)
            )
        for item, track_gain in zip(self.items, self.track_gains):
            self._store_track_gain(item, track_gain)
            self._store_album_gain(item)
            if write:
                item.try_write()
            self._log.debug(u'done analyzing {0}', item)

    def store(self, write):
        if self.album is not None:
            self.store_album(write)
        else:
            self.store_track(write)


class R128Task(RgTask):
    def _store_track_gain(self, item, track_gain):
        item.r128_track_gain = track_gain.gain
        item.store()
        self._log.debug(u'applied r128 track gain {0} LU',
                        item.r128_track_gain)

    def _store_album_gain(self, item):
        """

        The caller needs to ensure that `self.album_gain is not None`.
        """
        item.r128_album_gain = self.album_gain.gain
        item.store()
        self._log.debug(u'applied r128 album gain {0} LU',
                        item.r128_album_gain)

# Main plugin logic.

BACKEND_CLASSES = [
    CommandBackend,
    GStreamerBackend,
    AudioToolsBackend,
    FfmpegBackend,
]
BACKENDS = {b.NAME: b for b in BACKEND_CLASSES}


class ReplayGainPlugin(BeetsPlugin):
    """Provides ReplayGain analysis.
    """

    def __init__(self):
        super(ReplayGainPlugin, self).__init__()

        # default backend is 'command' for backward-compatibility.
        self.config.add({
            'overwrite': False,
            'auto': True,
            'backend': u'command',
            # FIXME: Respect this again
            'threads': cpu_count(),
            'parallel_on_import': False,
            'per_disc': False,
            'peak': 'true',
            'targetlevel': 89,
            'r128': ['Opus'],
            'r128_targetlevel': lufs_to_db(-23),
        })

        self.overwrite = self.config['overwrite'].get(bool)

        # Remember which backend is used for CLI feedback
        self.backend_name = self.config['backend'].as_str()

        if self.backend_name not in BACKENDS:
            raise ui.UserError(
                u"Selected ReplayGain backend {0} is not supported. "
                u"Please select one of: {1}".format(
                    self.backend_name,
                    u', '.join(BACKENDS.keys())
                )
            )

        peak_method = self.config["peak"].as_str()
        if peak_method not in ALL_PEAK_METHODS:
            raise ui.UserError(
                u"Selected ReplayGain peak method {0} is not supported. "
                u"Please select one of: {1}".format(
                    peak_method,
                    u', '.join(ALL_PEAK_METHODS)
                )
            )

        # The key in these dicts is the `use_r128` flag.
        self.peak_methods = {
            True: Peak.none,
            False: Peak[peak_method]
        }

        # On-import analysis.
        if self.config['auto']:
            self.register_listener('import_begin', self.import_begin)
            self.register_listener('import', self.import_end)
            self.import_stages = [self.imported]

        # Formats to use R128.
        self.r128_whitelist = self.config['r128'].as_str_seq()

        try:
            self.backend_instance = BACKENDS[self.backend_name](
                self.config, self._log
            )
        except (ReplayGainError, FatalReplayGainError) as e:
            raise ui.UserError(
                u'replaygain initialization failed: {0}'.format(e))

    def should_use_r128(self, item):
        """Checks the plugin setting to decide whether the calculation
        should be done using the EBU R128 standard and use R128_ tags instead.
        """
        return item.format in self.r128_whitelist

    @staticmethod
    def has_r128_track_data(item):
        return item.r128_track_gain is not None

    @staticmethod
    def has_rg_track_data(item):
        return (item.rg_track_gain is not None
                and item.rg_track_peak is not None)

    def track_requires_gain(self, item):
        if self.should_use_r128(item):
            if not self.has_r128_track_data(item):
                return True
        else:
            if not self.has_rg_track_data(item):
                return True

        return False

    @staticmethod
    def has_r128_album_data(item):
        return (item.r128_track_gain is not None
                and item.r128_album_gain is not None)

    @staticmethod
    def has_rg_album_data(item):
        return (item.rg_album_gain is not None
                and item.rg_album_peak is not None)

    def album_requires_gain(self, album):
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

    def create_task(self, items, use_r128, album=None):
        if use_r128:
            return R128Task(
                items, album,
                self.config["r128_targetlevel"].as_number(),
                Peak.none,  # R128_* tags do not store the track/album peak
                self.backend_instance.NAME,
                self._log,
            )
        else:
            return RgTask(
                items, album,
                self.config["targetlevel"].as_number(),
                self.peak_methods[use_r128],
                self.backend_instance.NAME,
                self._log,
            )

    def handle_album(self, album, write, force=False):
        """Compute album and track replay gain.

        If replay gain information is already present in all items, nothing is
        done.  Else, the computation is run, and a list of futures for the
        results is returned.
        """
        if not force and not self.album_requires_gain(album):
            self._log.info(u'Skipping album {0}', album)
            return []

        items_iter = iter(album.items())
        use_r128 = self.should_use_r128(next(items_iter))
        if any(use_r128 != self.should_use_r128(i) for i in items_iter):
            self._log.error(
                u"Cannot calculate gain for album {0} (incompatible formats)",
                album)
            return []

        self._log.info(u'analyzing {0}', album)

        discs = {}
        if self.config['per_disc'].get(bool):
            for item in album.items():
                if discs.get(item.disc) is None:
                    discs[item.disc] = []
                discs[item.disc].append(item)
        else:
            discs[1] = album.items()

        fut = []
        for discnumber, items in discs.items():
            task = self.create_task(items, use_r128, album=album)
            fut.append(
                self._submit(self.backend_instance.compute_album_gain, task,
                             parallel=self.backend_instance.do_parallel)
            )

        return fut

    def handle_track(self, item, force=False):
        """Compute track replay gain.

        If replay gain information is already present in the item, nothing is
        done. Else, the computation is run, and a list of futures for the
        result is returned.
        """
        if not force and not self.track_requires_gain(item):
            self._log.info(u'Skipping track {0}', item)
            return []

        use_r128 = self.should_use_r128(item)

        task = self.create_task([item], use_r128)
        return [self._submit(self.backend_instance.compute_track_gain, task,
                             parallel=self.backend_instance.do_parallel)]

    def _submit(self, func, task, parallel=False):
        if parallel:
            return pool.submit(func, task)
        else:
            fut = futures.Future()
            try:
                fut.set_result(func(task))
            except Exception as e:
                fut.set_exception(e)
            return fut

    def import_begin(self, session):
        """Handle `import_begin` event
        """
        pass

    def import_end(self, paths):
        """Handle `import` event
        """
        pass

    def check_and_store(self, fut_iter, write):
        for f in fut_iter:
            try:
                # This will re-raise excpetions that occured during the
                # computation.
                task = f.result()
                task.store(write=write)
            except CancelledError:
                pass
            except ReplayGainError as e:
                self._log.info(u"ReplayGain error: {0}", e)
            except FatalReplayGainError as e:
                raise ui.UserError(u"Fatal replay gain error: {0}".format(e))

    def imported(self, session, task):
        """Add replay gain info to items or albums of ``task``.
        """
        if self.config['auto']:
            if task.is_album:
                fut = self.handle_album(task.album, False)
            else:
                fut = self.handle_track(task.item, False)

            return combine_futures(
                    lambda results: self.check_and_store(results, write=False),
                    fut
            )

    def command_func(self, lib, opts, args):
        try:
            write = ui.should_write(opts.write)
            force = opts.force

            fut = []

            if opts.album:
                albums = lib.albums(ui.decargs(args))
                self._log.info(
                    "Analyzing {} albums ~ {} backend..."
                    .format(len(albums), self.backend_name)
                )
                for album in albums:
                    fut.extend(self.handle_album(album, force))
            else:
                items = lib.items(ui.decargs(args))
                self._log.info(
                    "Analyzing {} tracks ~ {} backend..."
                    .format(len(items), self.backend_name)
                )
                for item in items:
                    fut.extend(self.handle_track(item, force))

            self.check_and_store(futures.as_completed(fut), write=write)
        except (SystemExit, KeyboardInterrupt):
            # Silence interrupt exceptions
            pass

    def commands(self):
        """Return the "replaygain" ui subcommand.
        """
        cmd = ui.Subcommand('replaygain', help=u'analyze for ReplayGain')
        cmd.parser.add_album_option()
        cmd.parser.add_option(
            "-t", "--threads", dest="threads", type=int,
            help=u'change the number of threads, \
            defaults to maximum available processors'
        )
        cmd.parser.add_option(
            "-f", "--force", dest="force", action="store_true", default=False,
            help=u"analyze all files, including those that "
            "already have ReplayGain metadata")
        cmd.parser.add_option(
            "-w", "--write", default=None, action="store_true",
            help=u"write new metadata to files' tags")
        cmd.parser.add_option(
            "-W", "--nowrite", dest="write", action="store_false",
            help=u"don't write metadata (opposite of -w)")
        cmd.func = self.command_func
        return [cmd]
