import os

import beets
import beets.logging as blog
from beets.test import _common
from beets.test.helper import BeetsTestCase, capture_log


class DatabaseChangeTestBase(BeetsTestCase):
    def test_item_added_one_database_change(self):
        self.item = _common.item()
        self.item.path = beets.util.normpath(
            os.path.join(
                self.temp_dir,
                b"a",
                b"b.mp3",
            )
        )
        self.item.album = "a"
        self.item.title = "b"

        blog.getLogger("beets").set_global_level(blog.DEBUG)
        with capture_log() as logs:
            self.lib.add(self.item)

        assert logs.count("Sending event: database_change") == 1
