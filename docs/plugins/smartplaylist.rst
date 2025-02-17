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

While changing existing playlists in the beets configuration it can help to use
the ``--pretend`` option to find out if the edits work as expected. The results
of the queries will be printed out instead of being written to the playlist
file.

    $ beet splupdate --pretend BeatlesUniverse.m3u

The ``pretend_paths`` configuration option sets whether the items should be
displayed as per the user's ``format_item`` setting or what the file
paths as they would be written to the m3u file look like.

In case you want to export additional fields from the beets database into the
generated playlists, you can do so by specifying them within the ``fields``
configuration option and setting the ``output`` option to ``extm3u``.
For instance the following configuration exports the ``id`` and ``genre``
fields::

    smartplaylist:
        playlist_dir: /data/playlists
        relative_to: /data/playlists
        output: extm3u
        fields:
            - id
            - genre
        playlists:
            - name: all.m3u
              query: ''

Values of additional fields are URL-encoded.
A resulting ``all.m3u`` file could look as follows::

    #EXTM3U
    #EXTINF:805 id="1931" genre="Progressive%20Rock",Led Zeppelin - Stairway to Heaven
    ../music/singles/Led Zeppelin/Stairway to Heaven.mp3

To give a usage example, the `webm3u`_ and `Beetstream`_ plugins read the
exported ``id`` field, allowing you to serve your local m3u playlists via HTTP.

.. _Beetstream: https://github.com/BinaryBrain/Beetstream
.. _webm3u: https://github.com/mgoltzsche/beets-webm3u

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
- **urlencode**: URL-encode all paths. Default: ``no``.
- **pretend_paths**: When running with ``--pretend``, show the actual file
  paths that will be written to the m3u file. Default: ``false``.
- **uri_format**: Template with an ``$id`` placeholder used generate a
  playlist item URI, e.g. ``http://beets:8337/item/$id/file``.
  When this option is specified, the local path-related options ``prefix``,
  ``relative_to``, ``forward_slash`` and ``urlencode`` are ignored.
- **output**: Specify the playlist format: m3u|extm3u. Default ``m3u``.
- **fields**: Specify the names of the additional item fields to export into
  the playlist. This allows using e.g. the ``id`` field within other tools such
  as the `webm3u`_ and `Beetstream`_ plugins.
  To use this option, you must set the ``output`` option to ``extm3u``.

.. _Beetstream: https://github.com/BinaryBrain/Beetstream
.. _webm3u: https://github.com/mgoltzsche/beets-webm3u

For many configuration options, there is a corresponding CLI option, e.g.
``--playlist-dir``, ``--relative-to``, ``--prefix``, ``--forward-slash``,
``--urlencode``, ``--uri-format``, ``--output``, ``--pretend-paths``.
CLI options take precedence over those specified within the configuration file.
