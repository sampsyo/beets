MBSync Plugin
=============

This plugin provides the ``mbsync`` command, which lets you synchronize
metadata for albums and tracks that have external data source IDs.

This is useful for syncing your library with online data or when changing
configuration options that affect tag writing. If your music library already
contains correct tags, you can speed up the initial import by importing files
"as-is" and then using ``mbsync`` to write tags according to your beets
configuration.


Usage
-----

Enable the ``mbsync`` plugin in your configuration (see :ref:`using-plugins`)
and then run ``beet mbsync QUERY`` to fetch updated metadata for a part of your
collection (or omit the query to run over your whole library).

This plugin treats albums and singletons (non-album tracks) separately. It
first processes all matching singletons and then proceeds on to full albums.
The same query is used to search for both kinds of entities.

The command has a few command-line options:

* To preview the changes that would be made without applying them, use the
  ``-p`` (``--pretend``) flag.
* By default, files will be moved (renamed) according to their metadata if
  they are inside your beets library directory. To disable this, use the
  ``-M`` (``--nomove``) command-line option.
* If you have the ``import.write`` configuration option enabled, then this
  plugin will write new metadata to files' tags. To disable this, use the
  ``-W`` (``--nowrite``) option.
* To customize the output of unrecognized items, use the ``-f``
  (``--format``) option. The default output is ``format_item`` or
  ``format_album`` for items and albums, respectively.
