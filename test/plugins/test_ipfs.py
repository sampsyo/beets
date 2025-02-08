# This file is part of beets.
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


import os
from unittest.mock import Mock, patch

from beets.test import _common
from beets.test.helper import PluginTestCase
from beets.util import _fsencoding, bytestring_path
from beetsplug.ipfs import IPFSPlugin


@patch("beets.util.command_output", Mock())
class IPFSPluginTest(PluginTestCase):
    plugin = "ipfs"

    def test_stored_hashes(self):
        test_album = self.mk_test_album()
        ipfs = IPFSPlugin()
        added_albums = ipfs.ipfs_added_albums(self.lib, self.lib.path)
        added_album = added_albums.get_album(1)
        assert added_album.ipfs == test_album.ipfs
        found = False
        want_item = test_album.items()[2]
        for check_item in added_album.items():
            try:
                if check_item.get("ipfs", with_album=False):
                    ipfs_item = os.path.basename(want_item.path).decode(
                        _fsencoding(),
                    )
                    want_path = "/ipfs/{}/{}".format(test_album.ipfs, ipfs_item)
                    want_path = bytestring_path(want_path)
                    assert check_item.path == want_path
                    assert (
                        check_item.get("ipfs", with_album=False)
                        == want_item.ipfs
                    )
                    assert check_item.title == want_item.title
                    found = True
            except AttributeError:
                pass
        assert found

    def mk_test_album(self):
        items = [_common.item() for _ in range(3)]
        items[0].title = "foo bar"
        items[0].artist = "1one"
        items[0].album = "baz"
        items[0].year = 2001
        items[0].comp = True
        items[1].title = "baz qux"
        items[1].artist = "2two"
        items[1].album = "baz"
        items[1].year = 2002
        items[1].comp = True
        items[2].title = "beets 4 eva"
        items[2].artist = "3three"
        items[2].album = "foo"
        items[2].year = 2003
        items[2].comp = False
        items[2].ipfs = "QmfM9ic5LJj7V6ecozFx1MkSoaaiq3PXfhJoFvyqzpLXSk"

        for item in items:
            self.lib.add(item)

        album = self.lib.add_album(items)
        album.ipfs = "QmfM9ic5LJj7V6ecozFx1MkSoaaiq3PXfhJoFvyqzpLXSf"
        album.store(inherit=False)

        return album
