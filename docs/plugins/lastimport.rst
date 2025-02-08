LastImport Plugin
=================

The ``lastimport`` plugin downloads play-count data from your `Last.fm`_
library into beets' database. You can later create :doc:`smart playlists
</plugins/smartplaylist>` by querying ``play_count`` and do other fun stuff
with this field.

.. _Last.fm: https://last.fm

Installation
------------

To use the ``lastimport`` plugin, first enable it in your configuration (see
:ref:`using-plugins`). Then, install ``beets`` with ``lastimport`` extra

.. code-block:: bash

    pip install "beets[lastimport]"

Next, add your Last.fm username to your beets configuration file::

    lastfm:
        user: beetsfanatic

Importing Play Counts
---------------------

Simply run ``beet lastimport`` and wait for the plugin to request tracks from
Last.fm and match them to your beets library. (You will be notified of tracks
in your Last.fm profile that do not match any songs in your library.)

Then, your matched tracks will be populated with the ``play_count`` field,
which you can use in any query or template. For example::

    $ beet ls -f '$title: $play_count' play_count:5..
    Eple (Melody A.M.): 60

To see more information (namely, the specific play counts for matched tracks),
use the ``-v`` option.

Configuration
-------------

Aside from the required ``lastfm.user`` field, this plugin has some specific
options under the ``lastimport:`` section:

* **per_page**: The number of tracks to request from the API at once.
  Default: 500.
* **retry_limit**: How many times should we re-send requests to Last.fm on
  failure?
  Default: 3.

By default, the plugin will use beets's own Last.fm API key. You can also
override it with your own API key::

    lastfm:
        api_key: your_api_key
