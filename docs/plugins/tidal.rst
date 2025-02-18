TIDAL Plugin
==============

The ``tidal`` plugin provides metadata matches for the importer and lyrics using the
unofficial `TIDAL`_ client APIs.

.. _TIDAL: https://www.tidal.com
.. _TIDAL API Reference Module: https://github.com/tamland/python-tidal/tree/master

Basic Usage
-----------

First, enable the ``tidal`` plugin (see :ref:`using-plugins`).

Then, login to an active TIDAL account using ``beets tidal --login`` like so::

    Open the following URL to complete login: https://link.tidal.com/ABCDE
    The link expires in 300 seconds!

Click on the link and follow the TIDAL prompts, the plugin should resume after linking is complete.

An unpaid account works for basic metadata queries but for lyrics, you'll need a paid account.

You can enter the URL or ID for an album or song on TIDAL at the ``enter Id``
prompt during import::

    Enter search, enter Id, aBort, eDit, edit Candidates, plaY? i
    Enter release ID: https://tidal.com/browse/album/20638857?u OR https://tidal.com/browse/track/20638859?u

Using a browse link works, as well as putting in the numerical ID directly like so::

    Enter search, enter Id, aBort, eDit, edit Candidates, plaY? i
    Enter release ID: 20638857 OR 20638859

Other than that, the plugin has no interface outside of the standard beets interface.

Lyrics are obtained automatically depending on configuration and metadata is either in the candidate list or 
entered in manually with ``enter Id``.

Configuration
-------------

This plugin can be configured like other metadata source plugins as described in :ref:`metadata-source-plugin-configuration`.

The defaults are reasonable but the plugin does NOT process any files by default.

The available options under the ``tidal:`` section are:

- **auto**: Process files upon import.
  Default: ``no``
- **lyrics**: Grab lyrics when processing files.
  Default: ``yes``
- **synced_lyrics**: Grab synced LRC lyrics.
  Default: ``yes``
- **overwrite_lyrics**: Overwrite existing lyrics.
  Default: ``no``
- **metadata_search_limit**: How many items to query the API for when searching for metadata, ie. on candidate search.
  Default: ``25``
- **lyrics_search_limit**: How many items to query the API for when searching for lyrics.
  The lyrics API is heavily rate limited by TIDAL and the plugin does around 5-10 metadata searches per track when searching for lyrics, 
  so it is best to keep this number as low as possible. The plugin will slow down if rate limited.
  Default: ``10``
- **lyrics_no_duration_valid**: If tracks with no duration are valid candidates when searching for lyrics.
  Default: ``no``
- **search_max_altartists**: Maximum number of non-primary artists to add to searches.
  Each additional artist uses 1-2 metadata API calls and tracks can have near infinite alternative artists,
  so it is best to keep this as low as possible.

  Can be set to 0 to disable searching with alternative artists.
  Default: ``5``
- **max_lyrics_time_difference**: How far off the duration of tracks can be and still be suitable for lyrics.
  This is so technically valid search results don't cause incorrect lyrics to be applied to tracks.

  Can be set to 0 to consider all tracks valid.
  Default: ``5``
- **tokenfile**: What filename in the beets configuration directory to use for storing the login session.
  This should never need to be changed, but it is technically user configurable.
  Default: ``tidal_token.json``
- **write_sidecar**: Write lyrics to an accompanying LRC file with the track.
  This is useful for certain music players that cannot use embedded lyrics.
  Default: ``False``