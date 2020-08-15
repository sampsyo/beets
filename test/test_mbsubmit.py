# -*- coding: utf-8 -*-
# This file is part of beets.
# Copyright 2016, Adrian Sampson and Diego Moreda.
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

import unittest
from beets.util import text_string
from test.helper import capture_stdout, control_stdin, TestHelper
from test.test_importer import ImportHelper, AutotagStub
from test.test_ui_importer import TerminalImportSessionSetup


class MBSubmitPluginTest(TerminalImportSessionSetup, unittest.TestCase,
                         ImportHelper, TestHelper):
    def setUp(self):
        self.setup_beets()
        self.load_plugins('mbsubmit')
        self._create_import_dir(2)
        self._setup_import_session()
        self.matcher = AutotagStub().install()

    def tearDown(self):
        self.unload_plugins()
        self.teardown_beets()
        self.matcher.restore()

    def test_print_tracks_output(self):
        """Test the output of the "print tracks" choice."""
        self.matcher.matching = AutotagStub.BAD

        with capture_stdout() as output:
            with control_stdin('\n'.join(['p', 's'])):
                # Print tracks; Skip
                self.importer.run()

        # Manually build the string for comparing the output.
        tracklist = (u'Print tracks? '
                     u'01. Tag Title 1 - Tag Artist (0:01)\n'
                     u'02. Tag Title 2 - Tag Artist (0:01)')
        self.assertIn(tracklist, text_string(output.getvalue()))

    def test_print_tracks_output_as_tracks(self):
        """Test the output of the "print tracks" choice, as singletons."""
        self.matcher.matching = AutotagStub.BAD

        with capture_stdout() as output:
            with control_stdin('\n'.join(['t', 's', 'p', 's'])):
                # as Tracks; Skip; Print tracks; Skip
                self.importer.run()

        # Manually build the string for comparing the output.
        tracklist = (u'Print tracks? '
                     u'02. Tag Title 2 - Tag Artist (0:01)')
        self.assertIn(tracklist, text_string(output.getvalue()))


def suite():
    return unittest.TestLoader().loadTestsFromName(__name__)

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
