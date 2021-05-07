Smart Playlist Plugin
=====================

``smartplaylist`` is a plugin to generate smart playlists in m3u format based on
beets queries every time your library changes. This plugin is specifically
created to work well with `MPD's`_ playlist functionality.

.. _MPD's: https://www.musicpd.org/

To use it, enable the ``smartplaylist`` plugin in your configuration
(see :ref:`using-plugins`).
Then configure your smart playlists like the following example::

    smartplaylist:
        relative_to: ~/Music
        playlist_dir: ~/.mpd/playlists
        forward_slash: no
        playlists:
            - name: all.m3u
              query: ''

            - name: beatles.m3u
              query: 'artist:Beatles'

You can generate as many playlists as you want by adding them to the
``playlists`` section, using beets query syntax (see
:doc:`/reference/query`) for ``query`` and the file name to be generated for
``name``. The query will be split using shell-like syntax, so if you need to
use spaces in the query, be sure to quote them (e.g., ``artist:"The Beatles"``).
If you have existing files with the same names, you should back them up---they
will be overwritten when the plugin runs.

For more advanced usage, you can use template syntax (see
:doc:`/reference/pathformat/`) in the ``name`` field. For example::

    - name: 'ReleasedIn$year.m3u'
      query: 'year::201(0|1)'

This will query all the songs in 2010 and 2011 and generate the two playlist
files ``ReleasedIn2010.m3u`` and ``ReleasedIn2011.m3u`` using those songs.

You can also gather the results of several queries by putting them in a list.
(Items that match both queries are not included twice.) For example::

    - name: 'BeatlesUniverse.m3u'
      query: ['artist:beatles', 'genre:"beatles cover"']

Note that since beets query syntax is in effect, you can also use sorting
directives::

    - name: 'Chronological Beatles'
      query: 'artist:Beatles year+'
    - name: 'Mixed Rock'
      query: ['artist:Beatles year+', 'artist:"Led Zeppelin" bitrate+']

The former case behaves as expected, however please note that in the latter the
sorts will be merged: ``year+ bitrate+`` will apply to both the Beatles and Led
Zeppelin. If that bothers you, please get in touch.

For querying albums instead of items (mainly useful with extensible fields),
use the ``album_query`` field. ``query`` and ``album_query`` can be used at the
same time. The following example gathers single items but also items belonging
to albums that have a ``for_travel`` extensible field set to 1::

    - name: 'MyTravelPlaylist.m3u'
      album_query: 'for_travel:1'
      query: 'for_travel:1'

By default, each playlist is automatically regenerated at the end of the
session if an item or album it matches changed in the library database. To
force regeneration, you can invoke it manually from the command line::

    $ beet splupdate

This will regenerate all smart playlists. You can also specify which ones you
want to regenerate::

    $ beet splupdate BeatlesUniverse.m3u MyTravelPlaylist

You can also use this plugin together with the :doc:`mpdupdate`, in order to
automatically notify MPD of the playlist change, by adding ``mpdupdate`` to
the ``plugins`` line in your config file *after* the ``smartplaylist``
plugin.

Configuration
-------------

To configure the plugin, make a ``smartplaylist:`` section in your
configuration file. In addition to the ``playlists`` described above, the
other configuration options are:

- **auto**: Regenerate the playlist after every database change.
  Default: ``yes``.
- **playlist_dir**: Where to put the generated playlist files.
  Default: The current working directory (i.e., ``'.'``).
- **relative_to**: Generate paths in the playlist files relative to a base
  directory. If you intend to use this plugin to generate playlists for MPD,
  point this to your MPD music directory.
  Default: Use absolute paths.
- **forward_slash**: Forces forward slashes in the generated playlist files.
  If you intend to use this plugin to generate playlists for MPD on
  Windows, set this to yes.
  Default: Use system separator.
- **prefix**: Prepend this string to every path in the playlist file. For
  example, you could use the URL for a server where the music is stored.
  Default: empty string.
- **urlencoded**: URL-encode all paths. Default: ``no``.
