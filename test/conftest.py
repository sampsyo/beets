import os

import pytest


def skip_marked_items(items: list[pytest.Item], marker_name: str, reason: str):
    for item in (i for i in items if i.get_closest_marker(marker_name)):
        test_name = item.nodeid.split("::", 1)[-1]
        item.add_marker(pytest.mark.skip(f"{reason}: {test_name}"))


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
):
    if not os.environ.get("INTEGRATION_TEST") == "true":
        skip_marked_items(
            items, "integration_test", "INTEGRATION_TEST=1 required"
        )

    if not os.environ.get("LYRICS_UPDATED") == "true":
        skip_marked_items(
            items, "on_lyrics_update", "No change in lyrics source code"
        )
