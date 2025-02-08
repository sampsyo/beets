# This file is part of beets.
# Copyright 2016
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


from unittest.mock import ANY, Mock, call, patch

from beets import util
from beets.library import Item
from beets.test.helper import PluginTestCase
from beetsplug.mpdstats import MPDStats


class MPDStatsTest(PluginTestCase):
    plugin = "mpdstats"

    def test_update_rating(self):
        item = Item(title="title", path="", id=1)
        item.add(self.lib)

        log = Mock()
        mpdstats = MPDStats(self.lib, log)

        assert not mpdstats.update_rating(item, True)
        assert not mpdstats.update_rating(None, True)

    def test_get_item(self):
        item_path = util.normpath("/foo/bar.flac")
        item = Item(title="title", path=item_path, id=1)
        item.add(self.lib)

        log = Mock()
        mpdstats = MPDStats(self.lib, log)

        assert str(mpdstats.get_item(item_path)) == str(item)
        assert mpdstats.get_item("/some/non-existing/path") is None
        assert "item not found:" in log.info.call_args[0][0]

    FAKE_UNKNOWN_STATE = "some-unknown-one"
    STATUSES = [
        {"state": FAKE_UNKNOWN_STATE},
        {"state": "pause"},
        {"state": "play", "songid": 1, "time": "0:1"},
        {"state": "stop"},
    ]
    EVENTS = [["player"]] * (len(STATUSES) - 1) + [KeyboardInterrupt]
    item_path = util.normpath("/foo/bar.flac")
    songid = 1

    @patch(
        "beetsplug.mpdstats.MPDClientWrapper",
        return_value=Mock(
            **{
                "events.side_effect": EVENTS,
                "status.side_effect": STATUSES,
                "currentsong.return_value": (item_path, songid),
            }
        ),
    )
    def test_run_mpdstats(self, mpd_mock):
        item = Item(title="title", path=self.item_path, id=1)
        item.add(self.lib)

        log = Mock()
        try:
            MPDStats(self.lib, log).run()
        except KeyboardInterrupt:
            pass

        log.debug.assert_has_calls([call('unhandled status "{0}"', ANY)])
        log.info.assert_has_calls(
            [call("pause"), call("playing {0}", ANY), call("stop")]
        )
