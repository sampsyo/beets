"""Tests for the 'zero' plugin"""

from mediafile import MediaFile

from beets.library import Item
from beets.test.helper import PluginTestCase, control_stdin
from beets.util import syspath
from beetsplug.zero import ZeroPlugin


class ZeroPluginTest(PluginTestCase):
    plugin = "zero"
    preload_plugin = False

    def test_no_patterns(self):
        item = self.add_item_fixture(
            comments="test comment",
            title="Title",
            month=1,
            year=2000,
        )
        item.write()

        with self.configure_plugin({"fields": ["comments", "month"]}):
            item.write()

        mf = MediaFile(syspath(item.path))
        assert mf.comments is None
        assert mf.month is None
        assert mf.title == "Title"
        assert mf.year == 2000

    def test_pattern_match(self):
        item = self.add_item_fixture(comments="encoded by encoder")
        item.write()

        with self.configure_plugin(
            {"fields": ["comments"], "comments": ["encoded by"]}
        ):
            item.write()

        mf = MediaFile(syspath(item.path))
        assert mf.comments is None

    def test_pattern_nomatch(self):
        item = self.add_item_fixture(comments="recorded at place")
        item.write()

        with self.configure_plugin(
            {"fields": ["comments"], "comments": ["encoded_by"]}
        ):
            item.write()

        mf = MediaFile(syspath(item.path))
        assert mf.comments == "recorded at place"

    def test_do_not_change_database(self):
        item = self.add_item_fixture(year=2000)
        item.write()

        with self.configure_plugin({"fields": ["year"]}):
            item.write()

        assert item["year"] == 2000

    def test_change_database(self):
        item = self.add_item_fixture(year=2000)
        item.write()

        with self.configure_plugin(
            {"fields": ["year"], "update_database": True}
        ):
            item.write()

        assert item["year"] == 0

    def test_album_art(self):
        path = self.create_mediafile_fixture(images=["jpg"])
        item = Item.from_path(path)

        with self.configure_plugin({"fields": ["images"]}):
            item.write()

        mf = MediaFile(syspath(path))
        assert not mf.images

    def test_auto_false(self):
        item = self.add_item_fixture(year=2000)
        item.write()

        with self.configure_plugin(
            {"fields": ["year"], "update_database": True, "auto": False}
        ):
            item.write()

        assert item["year"] == 2000

    def test_subcommand_update_database_true(self):
        item = self.add_item_fixture(
            year=2016, day=13, month=3, comments="test comment"
        )
        item.write()
        item_id = item.id

        with (
            self.configure_plugin(
                {"fields": ["comments"], "update_database": True, "auto": False}
            ),
            control_stdin("y"),
        ):
            self.run_command("zero")

        mf = MediaFile(syspath(item.path))
        item = self.lib.get_item(item_id)

        assert item["year"] == 2016
        assert mf.year == 2016
        assert mf.comments is None
        assert item["comments"] == ""

    def test_subcommand_update_database_false(self):
        item = self.add_item_fixture(
            year=2016, day=13, month=3, comments="test comment"
        )
        item.write()
        item_id = item.id

        with (
            self.configure_plugin(
                {
                    "fields": ["comments"],
                    "update_database": False,
                    "auto": False,
                }
            ),
            control_stdin("y"),
        ):
            self.run_command("zero")

        mf = MediaFile(syspath(item.path))
        item = self.lib.get_item(item_id)

        assert item["year"] == 2016
        assert mf.year == 2016
        assert item["comments"] == "test comment"
        assert mf.comments is None

    def test_subcommand_query_include(self):
        item = self.add_item_fixture(
            year=2016, day=13, month=3, comments="test comment"
        )

        item.write()

        with self.configure_plugin(
            {"fields": ["comments"], "update_database": False, "auto": False}
        ):
            self.run_command("zero", "year: 2016")

        mf = MediaFile(syspath(item.path))

        assert mf.year == 2016
        assert mf.comments is None

    def test_subcommand_query_exclude(self):
        item = self.add_item_fixture(
            year=2016, day=13, month=3, comments="test comment"
        )

        item.write()

        with self.configure_plugin(
            {"fields": ["comments"], "update_database": False, "auto": False}
        ):
            self.run_command("zero", "year: 0000")

        mf = MediaFile(syspath(item.path))

        assert mf.year == 2016
        assert mf.comments == "test comment"

    def test_no_fields(self):
        item = self.add_item_fixture(year=2016)
        item.write()
        mediafile = MediaFile(syspath(item.path))
        assert mediafile.year == 2016

        item_id = item.id

        with self.configure_plugin({"fields": []}), control_stdin("y"):
            self.run_command("zero")

        item = self.lib.get_item(item_id)

        assert item["year"] == 2016
        assert mediafile.year == 2016

    def test_whitelist_and_blacklist(self):
        item = self.add_item_fixture(year=2016)
        item.write()
        mf = MediaFile(syspath(item.path))
        assert mf.year == 2016

        item_id = item.id

        with (
            self.configure_plugin(
                {"fields": ["year"], "keep_fields": ["comments"]}
            ),
            control_stdin("y"),
        ):
            self.run_command("zero")

        item = self.lib.get_item(item_id)

        assert item["year"] == 2016
        assert mf.year == 2016

    def test_keep_fields(self):
        item = self.add_item_fixture(year=2016, comments="test comment")
        tags = {
            "comments": "test comment",
            "year": 2016,
        }

        with self.configure_plugin(
            {"fields": None, "keep_fields": ["year"], "update_database": True}
        ):
            z = ZeroPlugin()
            z.write_event(item, item.path, tags)

        assert tags["comments"] is None
        assert tags["year"] == 2016

    def test_keep_fields_removes_preserved_tags(self):
        self.config["zero"]["keep_fields"] = ["year"]
        self.config["zero"]["fields"] = None
        self.config["zero"]["update_database"] = True

        z = ZeroPlugin()

        assert "id" not in z.fields_to_progs

    def test_fields_removes_preserved_tags(self):
        self.config["zero"]["fields"] = ["year id"]
        self.config["zero"]["update_database"] = True

        z = ZeroPlugin()

        assert "id" not in z.fields_to_progs

    def test_empty_query_n_response_no_changes(self):
        item = self.add_item_fixture(
            year=2016, day=13, month=3, comments="test comment"
        )
        item.write()
        item_id = item.id
        with (
            self.configure_plugin(
                {"fields": ["comments"], "update_database": True, "auto": False}
            ),
            control_stdin("n"),
        ):
            self.run_command("zero")

        mf = MediaFile(syspath(item.path))
        item = self.lib.get_item(item_id)

        assert item["year"] == 2016
        assert mf.year == 2016
        assert mf.comments == "test comment"
        assert item["comments"] == "test comment"
