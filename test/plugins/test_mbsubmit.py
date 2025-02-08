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


from beets.test.helper import (
    AutotagStub,
    ImportTestCase,
    PluginMixin,
    TerminalImportMixin,
    capture_stdout,
    control_stdin,
)


class MBSubmitPluginTest(PluginMixin, TerminalImportMixin, ImportTestCase):
    plugin = "mbsubmit"

    def setUp(self):
        super().setUp()
        self.prepare_album_for_import(2)
        self.setup_importer()
        self.matcher = AutotagStub().install()

    def tearDown(self):
        super().tearDown()
        self.matcher.restore()

    def test_print_tracks_output(self):
        """Test the output of the "print tracks" choice."""
        self.matcher.matching = AutotagStub.BAD

        with capture_stdout() as output:
            with control_stdin("\n".join(["p", "s"])):
                # Print tracks; Skip
                self.importer.run()

        # Manually build the string for comparing the output.
        tracklist = (
            "Open files with Picard? "
            "01. Tag Track 1 - Tag Artist (0:01)\n"
            "02. Tag Track 2 - Tag Artist (0:01)"
        )
        assert tracklist in output.getvalue()

    def test_print_tracks_output_as_tracks(self):
        """Test the output of the "print tracks" choice, as singletons."""
        self.matcher.matching = AutotagStub.BAD

        with capture_stdout() as output:
            with control_stdin("\n".join(["t", "s", "p", "s"])):
                # as Tracks; Skip; Print tracks; Skip
                self.importer.run()

        # Manually build the string for comparing the output.
        tracklist = (
            "Open files with Picard? " "02. Tag Track 2 - Tag Artist (0:01)"
        )
        assert tracklist in output.getvalue()
