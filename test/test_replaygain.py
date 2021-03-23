# -*- coding: utf-8 -*-
# This file is part of beets.
# Copyright 2016, Thomas Scholtes
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

import six
import unittest
from mediafile import MediaFile

from beets import config
from beetsplug.replaygain import (FatalGstreamerPluginReplayGainError,
                                  GStreamerBackend)
from test.helper import TestHelper, has_program

try:
    import gi
    gi.require_version('Gst', '1.0')
    GST_AVAILABLE = True
except (ImportError, ValueError):
    GST_AVAILABLE = False

if any(has_program(cmd, ['-v']) for cmd in ['mp3gain', 'aacgain']):
    GAIN_PROG_AVAILABLE = True
else:
    GAIN_PROG_AVAILABLE = False

FFMPEG_AVAILABLE = has_program('ffmpeg', ['-version'])


def reset_replaygain(item):
    item['rg_track_peak'] = None
    item['rg_track_gain'] = None
    item['rg_album_gain'] = None
    item['rg_album_gain'] = None
    item['r128_track_gain'] = None
    item['r128_album_gain'] = None
    item.write()
    item.store()


class GstBackendMixin():
    backend = u'gstreamer'
    has_r128_support = True

    def test_backend(self):
        """Check whether the backend actually has all required functionality.
        """
        try:
            # Check if required plugins can be loaded by instantiating a
            # GStreamerBackend (via its .__init__).
            config['replaygain']['targetlevel'] = 89
            GStreamerBackend(config['replaygain'], None)
        except FatalGstreamerPluginReplayGainError as e:
            # Skip the test if plugins could not be loaded.
            self.skipTest(str(e))


class CmdBackendMixin():
    backend = u'command'
    has_r128_support = False

    def test_backend(self):
        """Check whether the backend actually has all required functionality.
        """
        pass


class FfmpegBackendMixin():
    backend = u'ffmpeg'
    has_r128_support = True

    def test_backend(self):
        """Check whether the backend actually has all required functionality.
        """
        pass


class ReplayGainCliTestBase(TestHelper):
    def setUp(self):
        # Implemented by Mixins, see above. This may decide to skip the test.
        self.test_backend()

        self.setup_beets(disk=True)
        self.config['replaygain']['backend'] = self.backend

        try:
            self.load_plugins('replaygain')
        except Exception:
            import sys
            # store exception info so an error in teardown does not swallow it
            exc_info = sys.exc_info()
            try:
                self.teardown_beets()
                self.unload_plugins()
            except Exception:
                # if load_plugins() failed then setup is incomplete and
                # teardown operations may fail. In particular # {Item,Album}
                # may not have the _original_types attribute in unload_plugins
                pass
            six.reraise(exc_info[1], None, exc_info[2])

    def _add_album(self, *args, **kwargs):
        album = self.add_album_fixture(*args, **kwargs)
        for item in album.items():
            reset_replaygain(item)

        return album

    def tearDown(self):
        self.teardown_beets()
        self.unload_plugins()

    def test_cli_saves_track_gain(self):
        self._add_album(2)

        for item in self.lib.items():
            self.assertIsNone(item.rg_track_peak)
            self.assertIsNone(item.rg_track_gain)
            mediafile = MediaFile(item.path)
            self.assertIsNone(mediafile.rg_track_peak)
            self.assertIsNone(mediafile.rg_track_gain)

        self.run_command('replaygain')

        # Skip the test if rg_track_peak and rg_track gain is None, assuming
        # that it could only happen if the decoder plugins are missing.
        if all(i.rg_track_peak is None and i.rg_track_gain is None
               for i in self.lib.items()):
            self.skipTest(u'decoder plugins could not be loaded.')

        for item in self.lib.items():
            self.assertIsNotNone(item.rg_track_peak)
            self.assertIsNotNone(item.rg_track_gain)
            mediafile = MediaFile(item.path)
            self.assertAlmostEqual(
                mediafile.rg_track_peak, item.rg_track_peak, places=6)
            self.assertAlmostEqual(
                mediafile.rg_track_gain, item.rg_track_gain, places=2)

    def test_cli_skips_calculated_tracks(self):
        album_rg = self._add_album(1)
        item_rg = album_rg.items()[0]

        if self.has_r128_support:
            album_r128 = self._add_album(1, ext="opus")
            item_r128 = album_r128.items()[0]

        self.run_command(u'replaygain')

        item_rg.load()
        self.assertIsNotNone(item_rg.rg_track_gain)
        self.assertIsNotNone(item_rg.rg_track_peak)
        self.assertIsNone(item_rg.r128_track_gain)

        item_rg.rg_track_gain += 1.0
        item_rg.rg_track_peak += 1.0
        item_rg.store()
        rg_track_gain = item_rg.rg_track_gain
        rg_track_peak = item_rg.rg_track_peak

        if self.has_r128_support:
            item_r128.load()
            self.assertIsNotNone(item_r128.r128_track_gain)
            self.assertIsNone(item_r128.rg_track_gain)
            self.assertIsNone(item_r128.rg_track_peak)

            item_r128.r128_track_gain += 1.0
            item_r128.store()
            r128_track_gain = item_r128.r128_track_gain

        self.run_command(u'replaygain')

        item_rg.load()
        self.assertEqual(item_rg.rg_track_gain, rg_track_gain)
        self.assertEqual(item_rg.rg_track_peak, rg_track_peak)

        if self.has_r128_support:
            item_r128.load()
            self.assertEqual(item_r128.r128_track_gain, r128_track_gain)

    def test_cli_does_not_skip_wrong_tag_type(self):
        """Check that items that have tags of the wrong type won't be skipped.
        """
        if not self.has_r128_support:
            # This test is a lot less interesting if the backend cannot write
            # both tag types.
            self.skipTest("r128 tags for opus not supported on backend {}"
                          .format(self.backend))

        album_rg = self._add_album(1)
        item_rg = album_rg.items()[0]

        album_r128 = self._add_album(1, ext="opus")
        item_r128 = album_r128.items()[0]

        item_rg.r128_track_gain = 0.0
        item_rg.store()

        item_r128.rg_track_gain = 0.0
        item_r128.rg_track_peak = 42.0
        item_r128.store()

        self.run_command(u'replaygain')
        item_rg.load()
        item_r128.load()

        self.assertIsNotNone(item_rg.rg_track_gain)
        self.assertIsNotNone(item_rg.rg_track_peak)
        # FIXME: Should the plugin null this field?
        # self.assertIsNone(item_rg.r128_track_gain)

        self.assertIsNotNone(item_r128.r128_track_gain)
        # FIXME: Should the plugin null these fields?
        # self.assertIsNone(item_r128.rg_track_gain)
        # self.assertIsNone(item_r128.rg_track_peak)

    def test_cli_saves_album_gain_to_file(self):
        self._add_album(2)

        for item in self.lib.items():
            mediafile = MediaFile(item.path)
            self.assertIsNone(mediafile.rg_album_peak)
            self.assertIsNone(mediafile.rg_album_gain)

        self.run_command(u'replaygain', u'-a')

        peaks = []
        gains = []
        for item in self.lib.items():
            mediafile = MediaFile(item.path)
            peaks.append(mediafile.rg_album_peak)
            gains.append(mediafile.rg_album_gain)

        # Make sure they are all the same
        self.assertEqual(max(peaks), min(peaks))
        self.assertEqual(max(gains), min(gains))

        self.assertNotEqual(max(gains), 0.0)
        self.assertNotEqual(max(peaks), 0.0)

    def test_cli_writes_only_r128_tags(self):
        if not self.has_r128_support:
            self.skipTest("r128 tags for opus not supported on backend {}"
                          .format(self.backend))

        album = self._add_album(2, ext="opus")

        self.run_command(u'replaygain', u'-a')

        for item in album.items():
            mediafile = MediaFile(item.path)
            # does not write REPLAYGAIN_* tags
            self.assertIsNone(mediafile.rg_track_gain)
            self.assertIsNone(mediafile.rg_album_gain)
            # writes R128_* tags
            self.assertIsNotNone(mediafile.r128_track_gain)
            self.assertIsNotNone(mediafile.r128_album_gain)

    def test_targetlevel_has_effect(self):
        album = self._add_album(1)
        item = album.items()[0]

        def analyse(target_level):
            self.config['replaygain']['targetlevel'] = target_level
            self.run_command(u'replaygain', '-f')
            item.load()
            return item.rg_track_gain

        gain_relative_to_84 = analyse(84)
        gain_relative_to_89 = analyse(89)

        self.assertNotEqual(gain_relative_to_84, gain_relative_to_89)

    def test_r128_targetlevel_has_effect(self):
        if not self.has_r128_support:
            self.skipTest("r128 tags for opus not supported on backend {}"
                          .format(self.backend))

        album = self._add_album(1, ext="opus")
        item = album.items()[0]

        def analyse(target_level):
            self.config['replaygain']['r128_targetlevel'] = target_level
            self.run_command(u'replaygain', '-f')
            item.load()
            return item.r128_track_gain

        gain_relative_to_84 = analyse(84)
        gain_relative_to_89 = analyse(89)

        self.assertNotEqual(gain_relative_to_84, gain_relative_to_89)

    def test_per_disc(self):
        # Use the per_disc option and add a little more concurrency.
        album = self._add_album(track_count=4, disc_count=3)
        self.config['replaygain']['per_disc'] = True
        self.run_command(u'replaygain', '-a')

        # FIXME: Add fixtures with known track/album gain so that we can
        # actually check per-disc operation here.
        for item in album.items():
            self.assertIsNotNone(item.rg_track_gain)
            self.assertIsNotNone(item.rg_album_gain)


@unittest.skipIf(not GST_AVAILABLE, u'gstreamer cannot be found')
class ReplayGainGstCliTest(ReplayGainCliTestBase, unittest.TestCase,
                           GstBackendMixin):
    pass


@unittest.skipIf(not GAIN_PROG_AVAILABLE, u'no *gain command found')
class ReplayGainCmdCliTest(ReplayGainCliTestBase, unittest.TestCase,
                           CmdBackendMixin):
    pass


@unittest.skipIf(not FFMPEG_AVAILABLE, u'ffmpeg cannot be found')
class ReplayGainFfmpegCliTest(ReplayGainCliTestBase, unittest.TestCase,
                              FfmpegBackendMixin):
    pass


class ImportTest(TestHelper):
    threaded = False

    def setUp(self):
        # Implemented by Mixins, see above. This may decide to skip the test.
        self.test_backend()

        self.setup_beets(disk=True)
        self.config['threaded'] = self.threaded
        self.config['replaygain'] = {
                'backend': self.backend,
        }

        try:
            self.load_plugins('replaygain')
        except Exception:
            import sys
            # store exception info so an error in teardown does not swallow it
            exc_info = sys.exc_info()
            try:
                self.teardown_beets()
                self.unload_plugins()
            except Exception:
                # if load_plugins() failed then setup is incomplete and
                # teardown operations may fail. In particular # {Item,Album}
                # may not have the _original_types attribute in unload_plugins
                pass
            six.reraise(exc_info[1], None, exc_info[2])

        self.importer = self.create_importer()

    def tearDown(self):
        self.unload_plugins()
        self.teardown_beets()

    def test_import_converted(self):
        self.importer.run()
        for item in self.lib.items():
            # FIXME: Add fixtures with known track/album gain so that we can
            # actually check correct operation here.
            self.assertIsNotNone(item.rg_track_gain)
            self.assertIsNotNone(item.rg_album_gain)


@unittest.skipIf(not GST_AVAILABLE, u'gstreamer cannot be found')
class ReplayGainGstImportTest(ImportTest, unittest.TestCase,
                              GstBackendMixin):
    pass


@unittest.skipIf(not GAIN_PROG_AVAILABLE, u'no *gain command found')
class ReplayGainCmdImportTest(ImportTest, unittest.TestCase,
                              CmdBackendMixin):
    pass


@unittest.skipIf(not FFMPEG_AVAILABLE, u'ffmpeg cannot be found')
class ReplayGainFfmpegImportTest(ImportTest, unittest.TestCase,
                                 FfmpegBackendMixin):
    pass


@unittest.skipIf(not FFMPEG_AVAILABLE, u'ffmpeg cannot be found')
class ReplayGainFfmpegThreadedImportTest(ImportTest, unittest.TestCase,
                                         FfmpegBackendMixin):
    threaded = True


def suite():
    return unittest.TestLoader().loadTestsFromName(__name__)

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
