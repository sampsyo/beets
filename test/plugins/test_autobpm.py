import importlib.util
import os

import pytest

from beets.test.helper import ImportHelper, PluginMixin

github_ci = os.environ.get("GITHUB_ACTIONS") == "true"
if not github_ci and not importlib.util.find_spec("librosa"):
    pytest.skip("librosa isn't available", allow_module_level=True)


class TestAutoBPMPlugin(PluginMixin, ImportHelper):
    plugin = "autobpm"

    @pytest.fixture(scope="class", name="lib")
    def fixture_lib(self):
        self.setup_beets()

        yield self.lib

        self.teardown_beets()

    @pytest.fixture(scope="class")
    def item(self):
        return self.add_item_fixture()

    @pytest.fixture(scope="class")
    def importer(self, lib):
        self.import_media = []
        self.prepare_album_for_import(1)
        track = self.import_media[0]
        track.bpm = None
        track.save()
        return self.setup_importer(autotag=False)

    def test_command(self, lib, item):
        self.run_command("autobpm", lib=lib)

        item.load()
        assert item.bpm == 117

    def test_import(self, lib, importer):
        importer.run()

        assert lib.items().get().bpm == 117
