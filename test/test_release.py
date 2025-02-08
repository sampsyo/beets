"""Tests for the release utils."""

import os
import shutil
import sys

import pytest

release = pytest.importorskip("extra.release")


pytestmark = pytest.mark.skipif(
    not (
        (os.environ.get("GITHUB_ACTIONS") == "true" and sys.platform != "win32")
        or bool(shutil.which("pandoc"))
    ),
    reason="pandoc isn't available",
)


@pytest.fixture
def rst_changelog():
    return """New features:

* :doc:`/plugins/substitute`: Some substitute
  multi-line change.
  :bug:`5467`
* :ref:`list-cmd` Update.

You can do something with this command::

    $ do-something

Bug fixes:

* Some fix that refers to an issue.
  :bug:`5467`
* Some fix that mentions user :user:`username`.
* Some fix thanks to
  :user:`username`. :bug:`5467`
* Some fix with its own bullet points using incorrect indentation:
   * First nested bullet point
     with some text that wraps to the next line
   * Second nested bullet point
* Another fix with its own bullet points using correct indentation:
  * First
  * Second

Section naaaaaaaaaaaaaaaaaaaaaaaammmmmmmmmmmmmmmmeeeeeeeeeeeeeee with over 80
characters:

Empty section:

Other changes:

* Changed `bitesize` label to `good first issue`. Our `contribute`_ page is now
  automatically populated with these issues. :bug:`4855`

.. _contribute: https://github.com/beetbox/beets/contribute

2.1.0 (November 22, 2024)
-------------------------

Bug fixes:

* Fixed something."""


@pytest.fixture
def md_changelog():
    return r"""### New features

- [Substitute Plugin](https://beets.readthedocs.io/en/stable/plugins/substitute.html): Some substitute multi-line change. :bug: (#5467)
- [list](https://beets.readthedocs.io/en/stable/reference/cli.html#list-cmd) Update.

You can do something with this command:

    $ do-something

### Bug fixes

- Another fix with its own bullet points using correct indentation:
  - First
  - Second
- Some fix thanks to @username. :bug: (#5467)
- Some fix that mentions user @username.
- Some fix that refers to an issue. :bug: (#5467)
- Some fix with its own bullet points using incorrect indentation:
  - First nested bullet point with some text that wraps to the next line
  - Second nested bullet point

**Section naaaaaaaaaaaaaaaaaaaaaaaammmmmmmmmmmmmmmmeeeeeeeeeeeeeee with over 80 characters**

### Other changes

- Changed `bitesize` label to `good first issue`. Our [contribute](https://github.com/beetbox/beets/contribute) page is now automatically populated with these issues. :bug: (#4855)

# 2.1.0 (November 22, 2024)

### Bug fixes

- Fixed something."""  # noqa: E501


def test_convert_rst_to_md(rst_changelog, md_changelog):
    actual = release.changelog_as_markdown(rst_changelog)

    assert actual == md_changelog
