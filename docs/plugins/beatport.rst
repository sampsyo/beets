Beatport Plugin
===============

The ``beatport`` plugin adds support for querying the `Beatport`_ catalogue
during the autotagging process. This can potentially be helpful for users
whose collection includes a lot of diverse electronic music releases, for which
both MusicBrainz and (to a lesser degree) `Discogs`_ show no matches.

.. _Discogs: https://discogs.com

Installation
------------
To use the ``beatport`` plugin, first enable it in your configuration (see
:ref:`using-plugins`). Then, install ``beets`` with ``beatport`` extra

.. code-block:: bash

    pip install "beets[beatport]"

You will also need to register for a `Beatport`_ account. The first time you
run the :ref:`import-cmd` command after enabling the plugin, it will ask you
to authorize with Beatport by visiting the site in a browser. On the site
you will be asked to enter your username and password to authorize beets
to query the Beatport API. You will then be displayed with a single line of
text that you should paste as a whole into your terminal. This will store the
authentication data for subsequent runs and you will not be required to repeat
the above steps.

Matches from Beatport should now show up alongside matches
from MusicBrainz and other sources.

If you have a Beatport ID or a URL for a release or track you want to tag, you
can just enter one of the two at the "enter Id" prompt in the importer. You can
also search for an id like so::

    beet import path/to/music/library --search-id id

Configuration
-------------

This plugin can be configured like other metadata source plugins as described in :ref:`metadata-source-plugin-configuration`.

.. _Beatport: https://www.beatport.com/
