"""Tests for the 'web' plugin"""

import json
import os.path
import platform
import shutil
from collections import Counter

from beets import logging
from beets.library import Album, Item
from beets.test import _common
from beets.test.helper import ItemInDBTestCase
from beetsplug import web


class WebPluginTest(ItemInDBTestCase):
    def setUp(self):
        super().setUp()
        self.log = logging.getLogger("beets.web")

        if platform.system() == "Windows":
            self.path_prefix = "C:"
        else:
            self.path_prefix = ""

        # Add fixtures
        for track in self.lib.items():
            track.remove()

        # Add library elements. Note that self.lib.add overrides any "id=<n>"
        # and assigns the next free id number.
        # The following adds will create items #1, #2 and #3
        path1 = (
            self.path_prefix + os.sep + os.path.join(b"path_1").decode("utf-8")
        )
        self.lib.add(
            Item(title="title", path=path1, album_id=2, artist="AAA Singers")
        )
        path2 = (
            self.path_prefix
            + os.sep
            + os.path.join(b"somewhere", b"a").decode("utf-8")
        )
        self.lib.add(
            Item(title="another title", path=path2, artist="AAA Singers")
        )
        path3 = (
            self.path_prefix
            + os.sep
            + os.path.join(b"somewhere", b"abc").decode("utf-8")
        )
        self.lib.add(
            Item(title="and a third", testattr="ABC", path=path3, album_id=2)
        )
        # The following adds will create albums #1 and #2
        self.lib.add(Album(album="album", albumtest="xyz"))
        path4 = (
            self.path_prefix
            + os.sep
            + os.path.join(b"somewhere2", b"art_path_2").decode("utf-8")
        )
        self.lib.add(Album(album="other album", artpath=path4))

        web.app.config["TESTING"] = True
        web.app.config["lib"] = self.lib
        web.app.config["INCLUDE_PATHS"] = False
        web.app.config["READONLY"] = True
        self.client = web.app.test_client()

    def test_config_include_paths_true(self):
        web.app.config["INCLUDE_PATHS"] = True
        response = self.client.get("/item/1")
        res_json = json.loads(response.data.decode("utf-8"))
        expected_path = (
            self.path_prefix + os.sep + os.path.join(b"path_1").decode("utf-8")
        )

        assert response.status_code == 200
        assert res_json["path"] == expected_path

        web.app.config["INCLUDE_PATHS"] = False

    def test_config_include_artpaths_true(self):
        web.app.config["INCLUDE_PATHS"] = True
        response = self.client.get("/album/2")
        res_json = json.loads(response.data.decode("utf-8"))
        expected_path = (
            self.path_prefix
            + os.sep
            + os.path.join(b"somewhere2", b"art_path_2").decode("utf-8")
        )

        assert response.status_code == 200
        assert res_json["artpath"] == expected_path

        web.app.config["INCLUDE_PATHS"] = False

    def test_config_include_paths_false(self):
        web.app.config["INCLUDE_PATHS"] = False
        response = self.client.get("/item/1")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert "path" not in res_json

    def test_config_include_artpaths_false(self):
        web.app.config["INCLUDE_PATHS"] = False
        response = self.client.get("/album/2")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert "artpath" not in res_json

    def test_get_all_items(self):
        response = self.client.get("/item/")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert len(res_json["items"]) == 3

    def test_get_single_item_by_id(self):
        response = self.client.get("/item/1")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert res_json["id"] == 1
        assert res_json["title"] == "title"

    def test_get_multiple_items_by_id(self):
        response = self.client.get("/item/1,2")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert len(res_json["items"]) == 2
        response_titles = {item["title"] for item in res_json["items"]}
        assert response_titles == {"title", "another title"}

    def test_get_single_item_not_found(self):
        response = self.client.get("/item/4")
        assert response.status_code == 404

    def test_get_single_item_by_path(self):
        data_path = os.path.join(_common.RSRC, b"full.mp3")
        self.lib.add(Item.from_path(data_path))
        response = self.client.get("/item/path/" + data_path.decode("utf-8"))
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert res_json["title"] == "full"

    def test_get_single_item_by_path_not_found_if_not_in_library(self):
        data_path = os.path.join(_common.RSRC, b"full.mp3")
        # data_path points to a valid file, but we have not added the file
        # to the library.
        response = self.client.get("/item/path/" + data_path.decode("utf-8"))

        assert response.status_code == 404

    def test_get_item_empty_query(self):
        """testing item query: <empty>"""
        response = self.client.get("/item/query/")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert len(res_json["items"]) == 3

    def test_get_simple_item_query(self):
        """testing item query: another"""
        response = self.client.get("/item/query/another")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert len(res_json["results"]) == 1
        assert res_json["results"][0]["title"] == "another title"

    def test_query_item_string(self):
        """testing item query: testattr:ABC"""
        response = self.client.get("/item/query/testattr%3aABC")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert len(res_json["results"]) == 1
        assert res_json["results"][0]["title"] == "and a third"

    def test_query_item_regex(self):
        """testing item query: testattr::[A-C]+"""
        response = self.client.get("/item/query/testattr%3a%3a[A-C]%2b")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert len(res_json["results"]) == 1
        assert res_json["results"][0]["title"] == "and a third"

    def test_query_item_regex_backslash(self):
        # """ testing item query: testattr::\w+ """
        response = self.client.get("/item/query/testattr%3a%3a%5cw%2b")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert len(res_json["results"]) == 1
        assert res_json["results"][0]["title"] == "and a third"

    def test_query_item_path(self):
        # """ testing item query: path:\somewhere\a """
        """Note: path queries are special: the query item must match the path
        from the root all the way to a directory, so this matches 1 item"""
        """ Note: filesystem separators in the query must be '\' """

        response = self.client.get(
            "/item/query/path:" + self.path_prefix + "\\somewhere\\a"
        )
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert len(res_json["results"]) == 1
        assert res_json["results"][0]["title"] == "another title"

    def test_get_all_albums(self):
        response = self.client.get("/album/")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        response_albums = [album["album"] for album in res_json["albums"]]
        assert Counter(response_albums) == {"album": 1, "other album": 1}

    def test_get_single_album_by_id(self):
        response = self.client.get("/album/2")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert res_json["id"] == 2
        assert res_json["album"] == "other album"

    def test_get_multiple_albums_by_id(self):
        response = self.client.get("/album/1,2")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        response_albums = [album["album"] for album in res_json["albums"]]
        assert Counter(response_albums) == {"album": 1, "other album": 1}

    def test_get_album_empty_query(self):
        response = self.client.get("/album/query/")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert len(res_json["albums"]) == 2

    def test_get_simple_album_query(self):
        response = self.client.get("/album/query/other")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert len(res_json["results"]) == 1
        assert res_json["results"][0]["album"] == "other album"
        assert res_json["results"][0]["id"] == 2

    def test_get_album_details(self):
        response = self.client.get("/album/2?expand")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert len(res_json["items"]) == 2
        assert res_json["items"][0]["album"] == "other album"
        assert res_json["items"][1]["album"] == "other album"
        response_track_titles = {item["title"] for item in res_json["items"]}
        assert response_track_titles == {"title", "and a third"}

    def test_query_album_string(self):
        """testing query: albumtest:xy"""
        response = self.client.get("/album/query/albumtest%3axy")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert len(res_json["results"]) == 1
        assert res_json["results"][0]["album"] == "album"

    def test_query_album_artpath_regex(self):
        """testing query: artpath::art_"""
        response = self.client.get("/album/query/artpath%3a%3aart_")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert len(res_json["results"]) == 1
        assert res_json["results"][0]["album"] == "other album"

    def test_query_album_regex_backslash(self):
        # """ testing query: albumtest::\w+ """
        response = self.client.get("/album/query/albumtest%3a%3a%5cw%2b")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert len(res_json["results"]) == 1
        assert res_json["results"][0]["album"] == "album"

    def test_get_stats(self):
        response = self.client.get("/stats")
        res_json = json.loads(response.data.decode("utf-8"))

        assert response.status_code == 200
        assert res_json["items"] == 3
        assert res_json["albums"] == 2

    def test_delete_item_id(self):
        web.app.config["READONLY"] = False

        # Create a temporary item
        item_id = self.lib.add(
            Item(title="test_delete_item_id", test_delete_item_id=1)
        )

        # Check we can find the temporary item we just created
        response = self.client.get("/item/" + str(item_id))
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert res_json["id"] == item_id

        # Delete item by id
        response = self.client.delete("/item/" + str(item_id))
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200

        # Check the item has gone
        response = self.client.get("/item/" + str(item_id))
        assert response.status_code == 404
        # Note: if this fails, the item may still be around
        # and may cause other tests to fail

    def test_delete_item_without_file(self):
        web.app.config["READONLY"] = False

        # Create an item with a file
        ipath = os.path.join(self.temp_dir, b"testfile1.mp3")
        shutil.copy(os.path.join(_common.RSRC, b"full.mp3"), ipath)
        assert os.path.exists(ipath)
        item_id = self.lib.add(Item.from_path(ipath))

        # Check we can find the temporary item we just created
        response = self.client.get("/item/" + str(item_id))
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert res_json["id"] == item_id

        # Delete item by id, without deleting file
        response = self.client.delete("/item/" + str(item_id))
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200

        # Check the item has gone
        response = self.client.get("/item/" + str(item_id))
        assert response.status_code == 404

        # Check the file has not gone
        assert os.path.exists(ipath)
        os.remove(ipath)

    def test_delete_item_with_file(self):
        web.app.config["READONLY"] = False

        # Create an item with a file
        ipath = os.path.join(self.temp_dir, b"testfile2.mp3")
        shutil.copy(os.path.join(_common.RSRC, b"full.mp3"), ipath)
        assert os.path.exists(ipath)
        item_id = self.lib.add(Item.from_path(ipath))

        # Check we can find the temporary item we just created
        response = self.client.get("/item/" + str(item_id))
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert res_json["id"] == item_id

        # Delete item by id, with file
        response = self.client.delete("/item/" + str(item_id) + "?delete")
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200

        # Check the item has gone
        response = self.client.get("/item/" + str(item_id))
        assert response.status_code == 404

        # Check the file has gone
        assert not os.path.exists(ipath)

    def test_delete_item_query(self):
        web.app.config["READONLY"] = False

        # Create a temporary item
        self.lib.add(
            Item(title="test_delete_item_query", test_delete_item_query=1)
        )

        # Check we can find the temporary item we just created
        response = self.client.get("/item/query/test_delete_item_query")
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert len(res_json["results"]) == 1

        # Delete item by query
        response = self.client.delete("/item/query/test_delete_item_query")
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200

        # Check the item has gone
        response = self.client.get("/item/query/test_delete_item_query")
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert len(res_json["results"]) == 0

    def test_delete_item_all_fails(self):
        """DELETE is not supported for list all"""

        web.app.config["READONLY"] = False

        # Delete all items
        response = self.client.delete("/item/")
        assert response.status_code == 405

        # Note: if this fails, all items have gone and rest of
        # tests will fail!

    def test_delete_item_id_readonly(self):
        web.app.config["READONLY"] = True

        # Create a temporary item
        item_id = self.lib.add(
            Item(title="test_delete_item_id_ro", test_delete_item_id_ro=1)
        )

        # Check we can find the temporary item we just created
        response = self.client.get("/item/" + str(item_id))
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert res_json["id"] == item_id

        # Try to delete item by id
        response = self.client.delete("/item/" + str(item_id))
        assert response.status_code == 405

        # Check the item has not gone
        response = self.client.get("/item/" + str(item_id))
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert res_json["id"] == item_id

        # Remove it
        self.lib.get_item(item_id).remove()

    def test_delete_item_query_readonly(self):
        web.app.config["READONLY"] = True

        # Create a temporary item
        item_id = self.lib.add(
            Item(title="test_delete_item_q_ro", test_delete_item_q_ro=1)
        )

        # Check we can find the temporary item we just created
        response = self.client.get("/item/query/test_delete_item_q_ro")
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert len(res_json["results"]) == 1

        # Try to delete item by query
        response = self.client.delete("/item/query/test_delete_item_q_ro")
        assert response.status_code == 405

        # Check the item has not gone
        response = self.client.get("/item/query/test_delete_item_q_ro")
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert len(res_json["results"]) == 1

        # Remove it
        self.lib.get_item(item_id).remove()

    def test_delete_album_id(self):
        web.app.config["READONLY"] = False

        # Create a temporary album
        album_id = self.lib.add(
            Album(album="test_delete_album_id", test_delete_album_id=1)
        )

        # Check we can find the temporary album we just created
        response = self.client.get("/album/" + str(album_id))
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert res_json["id"] == album_id

        # Delete album by id
        response = self.client.delete("/album/" + str(album_id))
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200

        # Check the album has gone
        response = self.client.get("/album/" + str(album_id))
        assert response.status_code == 404
        # Note: if this fails, the album may still be around
        # and may cause other tests to fail

    def test_delete_album_query(self):
        web.app.config["READONLY"] = False

        # Create a temporary album
        self.lib.add(
            Album(album="test_delete_album_query", test_delete_album_query=1)
        )

        # Check we can find the temporary album we just created
        response = self.client.get("/album/query/test_delete_album_query")
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert len(res_json["results"]) == 1

        # Delete album
        response = self.client.delete("/album/query/test_delete_album_query")
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200

        # Check the album has gone
        response = self.client.get("/album/query/test_delete_album_query")
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert len(res_json["results"]) == 0

    def test_delete_album_all_fails(self):
        """DELETE is not supported for list all"""

        web.app.config["READONLY"] = False

        # Delete all albums
        response = self.client.delete("/album/")
        assert response.status_code == 405

        # Note: if this fails, all albums have gone and rest of
        # tests will fail!

    def test_delete_album_id_readonly(self):
        web.app.config["READONLY"] = True

        # Create a temporary album
        album_id = self.lib.add(
            Album(album="test_delete_album_id_ro", test_delete_album_id_ro=1)
        )

        # Check we can find the temporary album we just created
        response = self.client.get("/album/" + str(album_id))
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert res_json["id"] == album_id

        # Try to delete album by id
        response = self.client.delete("/album/" + str(album_id))
        assert response.status_code == 405

        # Check the item has not gone
        response = self.client.get("/album/" + str(album_id))
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert res_json["id"] == album_id

        # Remove it
        self.lib.get_album(album_id).remove()

    def test_delete_album_query_readonly(self):
        web.app.config["READONLY"] = True

        # Create a temporary album
        album_id = self.lib.add(
            Album(
                album="test_delete_album_query_ro", test_delete_album_query_ro=1
            )
        )

        # Check we can find the temporary album we just created
        response = self.client.get("/album/query/test_delete_album_query_ro")
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert len(res_json["results"]) == 1

        # Try to delete album
        response = self.client.delete("/album/query/test_delete_album_query_ro")
        assert response.status_code == 405

        # Check the album has not gone
        response = self.client.get("/album/query/test_delete_album_query_ro")
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert len(res_json["results"]) == 1

        # Remove it
        self.lib.get_album(album_id).remove()

    def test_patch_item_id(self):
        # Note: PATCH is currently only implemented for track items, not albums

        web.app.config["READONLY"] = False

        # Create a temporary item
        item_id = self.lib.add(
            Item(
                title="test_patch_item_id", test_patch_f1=1, test_patch_f2="Old"
            )
        )

        # Check we can find the temporary item we just created
        response = self.client.get("/item/" + str(item_id))
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert res_json["id"] == item_id
        assert res_json["test_patch_f1"] == "1"
        assert res_json["test_patch_f2"] == "Old"

        # Patch item by id
        # patch_json = json.JSONEncoder().encode({"test_patch_f2": "New"}]})
        response = self.client.patch(
            "/item/" + str(item_id), json={"test_patch_f2": "New"}
        )
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert res_json["id"] == item_id
        assert res_json["test_patch_f1"] == "1"
        assert res_json["test_patch_f2"] == "New"

        # Check the update has really worked
        response = self.client.get("/item/" + str(item_id))
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert res_json["id"] == item_id
        assert res_json["test_patch_f1"] == "1"
        assert res_json["test_patch_f2"] == "New"

        # Remove the item
        self.lib.get_item(item_id).remove()

    def test_patch_item_id_readonly(self):
        # Note: PATCH is currently only implemented for track items, not albums

        web.app.config["READONLY"] = True

        # Create a temporary item
        item_id = self.lib.add(
            Item(
                title="test_patch_item_id_ro",
                test_patch_f1=2,
                test_patch_f2="Old",
            )
        )

        # Check we can find the temporary item we just created
        response = self.client.get("/item/" + str(item_id))
        res_json = json.loads(response.data.decode("utf-8"))
        assert response.status_code == 200
        assert res_json["id"] == item_id
        assert res_json["test_patch_f1"] == "2"
        assert res_json["test_patch_f2"] == "Old"

        # Patch item by id
        # patch_json = json.JSONEncoder().encode({"test_patch_f2": "New"})
        response = self.client.patch(
            "/item/" + str(item_id), json={"test_patch_f2": "New"}
        )
        assert response.status_code == 405

        # Remove the item
        self.lib.get_item(item_id).remove()

    def test_get_item_file(self):
        ipath = os.path.join(self.temp_dir, b"testfile2.mp3")
        shutil.copy(os.path.join(_common.RSRC, b"full.mp3"), ipath)
        assert os.path.exists(ipath)
        item_id = self.lib.add(Item.from_path(ipath))

        response = self.client.get("/item/" + str(item_id) + "/file")

        assert response.status_code == 200
