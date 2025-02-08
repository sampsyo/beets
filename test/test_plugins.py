# This file is part of beets.
# Copyright 2016, Thomas Scholtes.
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


import itertools
import os
import unittest
from unittest.mock import ANY, Mock, patch

import pytest
from mediafile import MediaFile

from beets import config, plugins, ui
from beets.dbcore import types
from beets.importer import (
    ArchiveImportTask,
    SentinelImportTask,
    SingletonImportTask,
    action,
)
from beets.library import Item
from beets.plugins import MetadataSourcePlugin
from beets.test import helper
from beets.test.helper import AutotagStub, ImportHelper, TerminalImportMixin
from beets.test.helper import PluginTestCase as BasePluginTestCase
from beets.util import displayable_path, syspath
from beets.util.id_extractors import (
    beatport_id_regex,
    deezer_id_regex,
    spotify_id_regex,
)


class PluginLoaderTestCase(BasePluginTestCase):
    def setup_plugin_loader(self):
        # FIXME the mocking code is horrific, but this is the lowest and
        # earliest level of the plugin mechanism we can hook into.
        self._plugin_loader_patch = patch("beets.plugins.load_plugins")
        self._plugin_classes = set()
        load_plugins = self._plugin_loader_patch.start()

        def myload(names=()):
            plugins._classes.update(self._plugin_classes)

        load_plugins.side_effect = myload

    def teardown_plugin_loader(self):
        self._plugin_loader_patch.stop()

    def register_plugin(self, plugin_class):
        self._plugin_classes.add(plugin_class)

    def setUp(self):
        self.setup_plugin_loader()
        super().setUp()

    def tearDown(self):
        self.teardown_plugin_loader()
        super().tearDown()


class PluginImportTestCase(ImportHelper, PluginLoaderTestCase):
    def setUp(self):
        super().setUp()
        self.prepare_album_for_import(2)


class ItemTypesTest(PluginLoaderTestCase):
    def test_flex_field_type(self):
        class RatingPlugin(plugins.BeetsPlugin):
            item_types = {"rating": types.Float()}

        self.register_plugin(RatingPlugin)
        self.config["plugins"] = "rating"

        item = Item(path="apath", artist="aaa")
        item.add(self.lib)

        # Do not match unset values
        out = self.run_with_output("ls", "rating:1..3")
        assert "aaa" not in out

        self.run_command("modify", "rating=2", "--yes")

        # Match in range
        out = self.run_with_output("ls", "rating:1..3")
        assert "aaa" in out

        # Don't match out of range
        out = self.run_with_output("ls", "rating:3..5")
        assert "aaa" not in out


class ItemWriteTest(PluginLoaderTestCase):
    def setUp(self):
        super().setUp()

        class EventListenerPlugin(plugins.BeetsPlugin):
            pass

        self.event_listener_plugin = EventListenerPlugin()
        self.register_plugin(EventListenerPlugin)

    def test_change_tags(self):
        def on_write(item=None, path=None, tags=None):
            if tags["artist"] == "XXX":
                tags["artist"] = "YYY"

        self.register_listener("write", on_write)

        item = self.add_item_fixture(artist="XXX")
        item.write()

        mediafile = MediaFile(syspath(item.path))
        assert mediafile.artist == "YYY"

    def register_listener(self, event, func):
        self.event_listener_plugin.register_listener(event, func)


class ItemTypeConflictTest(PluginLoaderTestCase):
    def test_mismatch(self):
        class EventListenerPlugin(plugins.BeetsPlugin):
            item_types = {"duplicate": types.INTEGER}

        class AdventListenerPlugin(plugins.BeetsPlugin):
            item_types = {"duplicate": types.FLOAT}

        self.event_listener_plugin = EventListenerPlugin
        self.advent_listener_plugin = AdventListenerPlugin
        self.register_plugin(EventListenerPlugin)
        self.register_plugin(AdventListenerPlugin)
        with pytest.raises(plugins.PluginConflictError):
            plugins.types(Item)

    def test_match(self):
        class EventListenerPlugin(plugins.BeetsPlugin):
            item_types = {"duplicate": types.INTEGER}

        class AdventListenerPlugin(plugins.BeetsPlugin):
            item_types = {"duplicate": types.INTEGER}

        self.event_listener_plugin = EventListenerPlugin
        self.advent_listener_plugin = AdventListenerPlugin
        self.register_plugin(EventListenerPlugin)
        self.register_plugin(AdventListenerPlugin)
        assert plugins.types(Item) is not None


class EventsTest(PluginImportTestCase):
    def setUp(self):
        super().setUp()

    def test_import_task_created(self):
        self.importer = self.setup_importer(pretend=True)

        with helper.capture_log() as logs:
            self.importer.run()

        # Exactly one event should have been imported (for the album).
        # Sentinels do not get emitted.
        assert logs.count("Sending event: import_task_created") == 1

        logs = [line for line in logs if not line.startswith("Sending event:")]
        assert logs == [
            f'Album: {displayable_path(os.path.join(self.import_dir, b"album"))}',
            f"  {displayable_path(self.import_media[0].path)}",
            f"  {displayable_path(self.import_media[1].path)}",
        ]

    def test_import_task_created_with_plugin(self):
        class ToSingletonPlugin(plugins.BeetsPlugin):
            def __init__(self):
                super().__init__()

                self.register_listener(
                    "import_task_created", self.import_task_created_event
                )

            def import_task_created_event(self, session, task):
                if (
                    isinstance(task, SingletonImportTask)
                    or isinstance(task, SentinelImportTask)
                    or isinstance(task, ArchiveImportTask)
                ):
                    return task

                new_tasks = []
                for item in task.items:
                    new_tasks.append(SingletonImportTask(task.toppath, item))

                return new_tasks

        to_singleton_plugin = ToSingletonPlugin
        self.register_plugin(to_singleton_plugin)

        self.importer = self.setup_importer(pretend=True)

        with helper.capture_log() as logs:
            self.importer.run()

        # Exactly one event should have been imported (for the album).
        # Sentinels do not get emitted.
        assert logs.count("Sending event: import_task_created") == 1

        logs = [line for line in logs if not line.startswith("Sending event:")]
        assert logs == [
            f"Singleton: {displayable_path(self.import_media[0].path)}",
            f"Singleton: {displayable_path(self.import_media[1].path)}",
        ]


class HelpersTest(unittest.TestCase):
    def test_sanitize_choices(self):
        assert plugins.sanitize_choices(["A", "Z"], ("A", "B")) == ["A"]
        assert plugins.sanitize_choices(["A", "A"], ("A")) == ["A"]
        assert plugins.sanitize_choices(
            ["D", "*", "A"], ("A", "B", "C", "D")
        ) == ["D", "B", "C", "A"]


class ListenersTest(PluginLoaderTestCase):
    def test_register(self):
        class DummyPlugin(plugins.BeetsPlugin):
            def __init__(self):
                super().__init__()
                self.register_listener("cli_exit", self.dummy)
                self.register_listener("cli_exit", self.dummy)

            def dummy(self):
                pass

        d = DummyPlugin()
        assert DummyPlugin._raw_listeners["cli_exit"] == [d.dummy]

        d2 = DummyPlugin()
        assert DummyPlugin._raw_listeners["cli_exit"] == [d.dummy, d2.dummy]

        d.register_listener("cli_exit", d2.dummy)
        assert DummyPlugin._raw_listeners["cli_exit"] == [d.dummy, d2.dummy]

    @patch("beets.plugins.find_plugins")
    @patch("inspect.getfullargspec")
    def test_events_called(self, mock_gfa, mock_find_plugins):
        mock_gfa.return_value = Mock(
            args=(),
            varargs="args",
            varkw="kwargs",
        )

        class DummyPlugin(plugins.BeetsPlugin):
            def __init__(self):
                super().__init__()
                self.foo = Mock(__name__="foo")
                self.register_listener("event_foo", self.foo)
                self.bar = Mock(__name__="bar")
                self.register_listener("event_bar", self.bar)

        d = DummyPlugin()
        mock_find_plugins.return_value = (d,)

        plugins.send("event")
        d.foo.assert_has_calls([])
        d.bar.assert_has_calls([])

        plugins.send("event_foo", var="tagada")
        d.foo.assert_called_once_with(var="tagada")
        d.bar.assert_has_calls([])

    @patch("beets.plugins.find_plugins")
    def test_listener_params(self, mock_find_plugins):
        class DummyPlugin(plugins.BeetsPlugin):
            def __init__(self):
                super().__init__()
                for i in itertools.count(1):
                    try:
                        meth = getattr(self, f"dummy{i}")
                    except AttributeError:
                        break
                    self.register_listener(f"event{i}", meth)

            def dummy1(self, foo):
                assert foo == 5

            def dummy2(self, foo=None):
                assert foo == 5

            def dummy3(self):
                # argument cut off
                pass

            def dummy4(self, bar=None):
                # argument cut off
                pass

            def dummy5(self, bar):
                assert not True

            # more complex examples

            def dummy6(self, foo, bar=None):
                assert foo == 5
                assert bar is None

            def dummy7(self, foo, **kwargs):
                assert foo == 5
                assert kwargs == {}

            def dummy8(self, foo, bar, **kwargs):
                assert not True

            def dummy9(self, **kwargs):
                assert kwargs == {"foo": 5}

        d = DummyPlugin()
        mock_find_plugins.return_value = (d,)

        plugins.send("event1", foo=5)
        plugins.send("event2", foo=5)
        plugins.send("event3", foo=5)
        plugins.send("event4", foo=5)

        with pytest.raises(TypeError):
            plugins.send("event5", foo=5)

        plugins.send("event6", foo=5)
        plugins.send("event7", foo=5)

        with pytest.raises(TypeError):
            plugins.send("event8", foo=5)

        plugins.send("event9", foo=5)


class PromptChoicesTest(TerminalImportMixin, PluginImportTestCase):
    def setUp(self):
        super().setUp()
        self.setup_importer()
        self.matcher = AutotagStub().install()
        # keep track of ui.input_option() calls
        self.input_options_patcher = patch(
            "beets.ui.input_options", side_effect=ui.input_options
        )
        self.mock_input_options = self.input_options_patcher.start()

    def tearDown(self):
        super().tearDown()
        self.input_options_patcher.stop()
        self.matcher.restore()

    def test_plugin_choices_in_ui_input_options_album(self):
        """Test the presence of plugin choices on the prompt (album)."""

        class DummyPlugin(plugins.BeetsPlugin):
            def __init__(self):
                super().__init__()
                self.register_listener(
                    "before_choose_candidate", self.return_choices
                )

            def return_choices(self, session, task):
                return [
                    ui.commands.PromptChoice("f", "Foo", None),
                    ui.commands.PromptChoice("r", "baR", None),
                ]

        self.register_plugin(DummyPlugin)
        # Default options + extra choices by the plugin ('Foo', 'Bar')
        opts = (
            "Apply",
            "More candidates",
            "Skip",
            "Use as-is",
            "as Tracks",
            "Group albums",
            "Enter search",
            "enter Id",
            "aBort",
        ) + ("Foo", "baR")

        self.importer.add_choice(action.SKIP)
        self.importer.run()
        self.mock_input_options.assert_called_once_with(
            opts, default="a", require=ANY
        )

    def test_plugin_choices_in_ui_input_options_singleton(self):
        """Test the presence of plugin choices on the prompt (singleton)."""

        class DummyPlugin(plugins.BeetsPlugin):
            def __init__(self):
                super().__init__()
                self.register_listener(
                    "before_choose_candidate", self.return_choices
                )

            def return_choices(self, session, task):
                return [
                    ui.commands.PromptChoice("f", "Foo", None),
                    ui.commands.PromptChoice("r", "baR", None),
                ]

        self.register_plugin(DummyPlugin)
        # Default options + extra choices by the plugin ('Foo', 'Bar')
        opts = (
            "Apply",
            "More candidates",
            "Skip",
            "Use as-is",
            "Enter search",
            "enter Id",
            "aBort",
        ) + ("Foo", "baR")

        config["import"]["singletons"] = True
        self.importer.add_choice(action.SKIP)
        self.importer.run()
        self.mock_input_options.assert_called_with(
            opts, default="a", require=ANY
        )

    def test_choices_conflicts(self):
        """Test the short letter conflict solving."""

        class DummyPlugin(plugins.BeetsPlugin):
            def __init__(self):
                super().__init__()
                self.register_listener(
                    "before_choose_candidate", self.return_choices
                )

            def return_choices(self, session, task):
                return [
                    ui.commands.PromptChoice("a", "A foo", None),  # dupe
                    ui.commands.PromptChoice("z", "baZ", None),  # ok
                    ui.commands.PromptChoice("z", "Zupe", None),  # dupe
                    ui.commands.PromptChoice("z", "Zoo", None),
                ]  # dupe

        self.register_plugin(DummyPlugin)
        # Default options + not dupe extra choices by the plugin ('baZ')
        opts = (
            "Apply",
            "More candidates",
            "Skip",
            "Use as-is",
            "as Tracks",
            "Group albums",
            "Enter search",
            "enter Id",
            "aBort",
        ) + ("baZ",)
        self.importer.add_choice(action.SKIP)
        self.importer.run()
        self.mock_input_options.assert_called_once_with(
            opts, default="a", require=ANY
        )

    def test_plugin_callback(self):
        """Test that plugin callbacks are being called upon user choice."""

        class DummyPlugin(plugins.BeetsPlugin):
            def __init__(self):
                super().__init__()
                self.register_listener(
                    "before_choose_candidate", self.return_choices
                )

            def return_choices(self, session, task):
                return [ui.commands.PromptChoice("f", "Foo", self.foo)]

            def foo(self, session, task):
                pass

        self.register_plugin(DummyPlugin)
        # Default options + extra choices by the plugin ('Foo', 'Bar')
        opts = (
            "Apply",
            "More candidates",
            "Skip",
            "Use as-is",
            "as Tracks",
            "Group albums",
            "Enter search",
            "enter Id",
            "aBort",
        ) + ("Foo",)

        # DummyPlugin.foo() should be called once
        with patch.object(DummyPlugin, "foo", autospec=True) as mock_foo:
            with helper.control_stdin("\n".join(["f", "s"])):
                self.importer.run()
            assert mock_foo.call_count == 1

        # input_options should be called twice, as foo() returns None
        assert self.mock_input_options.call_count == 2
        self.mock_input_options.assert_called_with(
            opts, default="a", require=ANY
        )

    def test_plugin_callback_return(self):
        """Test that plugin callbacks that return a value exit the loop."""

        class DummyPlugin(plugins.BeetsPlugin):
            def __init__(self):
                super().__init__()
                self.register_listener(
                    "before_choose_candidate", self.return_choices
                )

            def return_choices(self, session, task):
                return [ui.commands.PromptChoice("f", "Foo", self.foo)]

            def foo(self, session, task):
                return action.SKIP

        self.register_plugin(DummyPlugin)
        # Default options + extra choices by the plugin ('Foo', 'Bar')
        opts = (
            "Apply",
            "More candidates",
            "Skip",
            "Use as-is",
            "as Tracks",
            "Group albums",
            "Enter search",
            "enter Id",
            "aBort",
        ) + ("Foo",)

        # DummyPlugin.foo() should be called once
        with helper.control_stdin("f\n"):
            self.importer.run()

        # input_options should be called once, as foo() returns SKIP
        self.mock_input_options.assert_called_once_with(
            opts, default="a", require=ANY
        )


class ParseSpotifyIDTest(unittest.TestCase):
    def test_parse_id_correct(self):
        id_string = "39WqpoPgZxygo6YQjehLJJ"
        out = MetadataSourcePlugin._get_id("album", id_string, spotify_id_regex)
        assert out == id_string

    def test_parse_id_non_id_returns_none(self):
        id_string = "blah blah"
        out = MetadataSourcePlugin._get_id("album", id_string, spotify_id_regex)
        assert out is None

    def test_parse_id_url_finds_id(self):
        id_string = "39WqpoPgZxygo6YQjehLJJ"
        id_url = "https://open.spotify.com/album/%s" % id_string
        out = MetadataSourcePlugin._get_id("album", id_url, spotify_id_regex)
        assert out == id_string


class ParseDeezerIDTest(unittest.TestCase):
    def test_parse_id_correct(self):
        id_string = "176356382"
        out = MetadataSourcePlugin._get_id("album", id_string, deezer_id_regex)
        assert out == id_string

    def test_parse_id_non_id_returns_none(self):
        id_string = "blah blah"
        out = MetadataSourcePlugin._get_id("album", id_string, deezer_id_regex)
        assert out is None

    def test_parse_id_url_finds_id(self):
        id_string = "176356382"
        id_url = "https://www.deezer.com/album/%s" % id_string
        out = MetadataSourcePlugin._get_id("album", id_url, deezer_id_regex)
        assert out == id_string


class ParseBeatportIDTest(unittest.TestCase):
    def test_parse_id_correct(self):
        id_string = "3089651"
        out = MetadataSourcePlugin._get_id(
            "album", id_string, beatport_id_regex
        )
        assert out == id_string

    def test_parse_id_non_id_returns_none(self):
        id_string = "blah blah"
        out = MetadataSourcePlugin._get_id(
            "album", id_string, beatport_id_regex
        )
        assert out is None

    def test_parse_id_url_finds_id(self):
        id_string = "3089651"
        id_url = "https://www.beatport.com/release/album-name/%s" % id_string
        out = MetadataSourcePlugin._get_id("album", id_url, beatport_id_regex)
        assert out == id_string
