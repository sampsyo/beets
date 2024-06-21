MusicBrainz Submit Plugin
=========================

The ``mbsubmit`` plugin provides extra prompt choices when an import session
fails to find a good enough match for a release. Additionally, it provides an
``mbsubmit`` command that prints the tracks of the current album in a format
that is parseable by MusicBrainz's `track parser`_. The prompt choices are:

- Print the tracks to stdout in a format suitable for MusicBrainz's `track
  parser`_.

- Create a new release on MusicBrainz, opens
  https://musicbrainz.org/release/add in a new browser window with
  fields pre-populated using existing metadata.

- Open the program `Picard`_ with the unmatched folder as an input, allowing
  you to start submitting the unmatched release to MusicBrainz with many input
  fields already filled in, thanks to Picard reading the preexisting tags of
  the files.

To create new releases on MusicBrainz with this plugin you need to install the
`PyJWT`_ library with:

.. code-block:: console

   $ pip install "beets[mbsubmit]"

.. _PyJWT: https://pyjwt.readthedocs.io/en/stable/

For the last option, `Picard`_ is assumed to be installed and available on the
machine including a ``picard`` executable. Picard developers list `download
options`_. `other GNU/Linux distributions`_ may distribute Picard via their
package manager as well.

.. _track parser: https://wiki.musicbrainz.org/History:How_To_Parse_Track_Listings
.. _Picard: https://picard.musicbrainz.org/
.. _download options: https://picard.musicbrainz.org/downloads/
.. _other GNU/Linux distributions: https://repology.org/project/picard-tagger/versions

Usage
-----

Enable the ``mbsubmit`` plugin in your configuration (see :ref:`using-plugins`)
and select one of the options mentioned above. Here the option ``Print tracks``
choice is demonstrated::

    No matching release found for 3 tracks.
    For help, see: https://beets.readthedocs.org/en/latest/faq.html#nomatch
    [U]se as-is, as Tracks, Group albums, Skip, Enter search, enter Id, aBort,
    Print tracks, Open files with Picard, Create release on musicbrainz? p
    01. An Obscure Track - An Obscure Artist (3:37)
    02. Another Obscure Track - An Obscure Artist (2:05)
    03. The Third Track - Another Obscure Artist (3:02)

    No matching release found for 3 tracks.
    For help, see: https://beets.readthedocs.org/en/latest/faq.html#nomatch
    [U]se as-is, as Tracks, Group albums, Skip, Enter search, enter Id, aBort,
    Print tracks?

You can also run ``beet mbsubmit QUERY`` to print the track information for any album::

    $ beet mbsubmit album:"An Obscure Album"
    01. An Obscure Track - An Obscure Artist (3:37)
    02. Another Obscure Track - An Obscure Artist (2:05)
    03. The Third Track - Another Obscure Artist (3:02)

As MusicBrainz currently does not support submitting albums programmatically,
the recommended workflow is to copy the output of the ``Print tracks`` choice
and paste it into the parser that can be found by clicking on the
"Track Parser" button on MusicBrainz "Tracklist" tab.

Create release on MusicBrainz
-----------------------------

The https://musicbrainz.org/release/add page can be seeded with existing
metadata, as described here: https://musicbrainz.org/doc/Development/Seeding/Release_Editor.
This works in the following way:

1. When you select the option to create a release, a local web server is started.
2. You point your web browser to that web server, either by clicking a link
   displayed in the console, or by having beets open the link automatically.
3. The opened web page will redirect you to MusicBrainz, and the form fields
   will be prepopulated with metadata found in the files. MusicBrainz may
   ask you to confirm the action.
4. You edit the release on MusicBrainz and click "Enter edit" to finish.
5. MusicBrainz will redirect you to the local web server, submitting the ID
   of the newly created release.
6. beets will add the release using the release ID returned by MusicBrainz.

Configuration
-------------

To configure the plugin, make a ``mbsubmit:`` section in your configuration
file. The following options are available:

- **format**: The format used for printing the tracks, defined using the
  same template syntax as beets’ :doc:`path formats </reference/pathformat>`.
  Default: ``$track. $title - $artist ($length)``.
- **threshold**: The minimum strength of the autotagger recommendation that
  will cause the ``Print tracks`` choice to be displayed on the prompt.
  Default: ``medium`` (causing the choice to be displayed for all albums that
  have a recommendation of medium strength or lower). Valid values: ``none``,
  ``low``, ``medium``, ``strong``.
- **create_release_server_hostname**: The host name of the local web server used for the
  'Create release on musicbrainz' functionality. The default is '127.0.0.1'.
  Adjust this if beets is running on a different host in your local network.
  Be aware that this web server is not secured in any way.
- **create_release_server_port**: The port for the local web server. By default,
  beets will choose a random available port for you.
- **create_release_method**: Either 'open_browser' to automatically open a new
  window/tab in your local browser or 'show_link' to simply show the link on
  the console.
- **create_release_await_mbid**: Whether or not to wait for you to create the
  release on MusicBrainz. If true, waits for a callback from MusicBrainz with
  the new release ID and proceeds to add the unmatched album using that Id.
  If false, simply shows the select action prompt again. Default: true.
- **create_release_default_type**: The default release type when none can be
  identified from the unmatched files.
  See https://musicbrainz.org/doc/Release_Group/Type
- **create_release_default_language**: The default language as an `ISO 639-3`_
  code (eng, deu, jpn).
- **create_release_default_script**: The default script as an `ISO 15924`_ code
  (Latn, Cyrl).
- **create_release_default_status**: The default status. Possible values:
  official, promotion, bootleg, pseudo-release.
- **create_release_default_packaging**: The default packaging.
  See https://musicbrainz.org/doc/Release/Packaging
- **create_release_default_edit_note**: The default edit note when submitting
  new releases.
- **picard_path**: The path to the ``picard`` executable. Could be an absolute
  path, and if not, ``$PATH`` is consulted. The default value is simply
  ``picard``. Windows users will have to find and specify the absolute path to
  their ``picard.exe``. That would probably be:
  ``C:\Program Files\MusicBrainz Picard\picard.exe``.

.. _ISO 639-3: https://en.wikipedia.org/wiki/List_of_ISO_639-3_codes
.. _ISO 15924: https://en.wikipedia.org/wiki/ISO_15924

Please note that some values of the ``threshold`` configuration option might
require other ``beets`` command line switches to be enabled in order to work as
intended. In particular, setting a threshold of ``strong`` will only display
the prompt if ``timid`` mode is enabled. You can find more information about
how the recommendation system works at :ref:`match-config`.
