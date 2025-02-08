MetaSync Plugin
===============

This plugin provides the ``metasync`` command, which lets you fetch certain
metadata from other sources: for example, your favorite audio player.

Currently, the plugin supports synchronizing with the `Amarok`_ music player,
and with `iTunes`_.
It can fetch the rating, score, first-played date, last-played date, play
count, and track uid from Amarok.

.. _Amarok: https://amarok.kde.org/
.. _iTunes: https://www.apple.com/itunes/


Installation
------------

Enable the ``metasync`` plugin in your configuration (see
:ref:`using-plugins`).

To synchronize with Amarok, you'll need the `dbus-python`_ library. In such
case, install ``beets`` with ``metasync`` extra

.. code-block:: bash

    pip install "beets[metasync]"

.. _dbus-python: https://dbus.freedesktop.org/releases/dbus-python/


Configuration
-------------

To configure the plugin, make a ``metasync:`` section in your configuration
file. The available options are:

- **source**: A list of comma-separated sources to fetch metadata from.
  Set this to "amarok" or "itunes" to enable synchronization with that player.
  Default: empty

The follow subsections describe additional configure required for some players.

itunes
''''''

The path to your iTunes library **xml** file has to be configured, e.g.::

    metasync:
        source: itunes
        itunes:
            library: ~/Music/iTunes Library.xml

Please note the indentation.

Usage
-----

Run ``beet metasync QUERY`` to fetch metadata from the configured list of
sources.

The command has a few command-line options:

* To preview the changes that would be made without applying them, use the
  ``-p`` (``--pretend``) flag.
* To specify temporary sources to fetch metadata from, use the ``-s``
  (``--source``) flag with a comma-separated list of a sources.
