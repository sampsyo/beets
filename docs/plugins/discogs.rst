Discogs Plugin
==============

The ``discogs`` plugin extends the autotagger's search capabilities to
include matches from the `Discogs`_ database.

Files can be imported as albums or as singletons. Since `Discogs`_ matches are
always based on `Discogs`_ releases, the album tag is written even to
singletons.  This enhances the importers results when reimporting as (full or
partial) albums later on.

.. _Discogs: https://discogs.com

Installation
------------

To use the ``discogs`` plugin, first enable it in your configuration (see
:ref:`using-plugins`). Then, install ``beets`` with ``discogs`` extra

.. code-block:: bash

    pip install "beets[discogs]"

You will also need to register for a `Discogs`_ account, and provide
authentication credentials via a personal access token or an OAuth2
authorization.

Matches from Discogs will now show up during import alongside matches from
MusicBrainz. The search terms sent to the Discogs API are based on the artist
and album tags of your tracks. If those are empty no query will be issued.

If you have a Discogs ID for an album you want to tag, you can also enter it
at the "enter Id" prompt in the importer.

OAuth Authorization
```````````````````

The first time you run the :ref:`import-cmd` command after enabling the plugin,
it will ask you to authorize with Discogs by visiting the site in a browser.
Subsequent runs will not require re-authorization.

Authentication via Personal Access Token
````````````````````````````````````````

As an alternative to OAuth, you can get a token from Discogs and add it to
your configuration.
To get a personal access token (called a "user token" in the `python3-discogs-client`_
documentation):

#. login to `Discogs`_;
#. visit the `Developer settings page <https://www.discogs.com/settings/developers>`_;
#. press the *Generate new token* button;
#. copy the generated token;
#. place it in your configuration in the ``discogs`` section as the ``user_token`` option:

   .. code-block:: yaml

      discogs:
          user_token: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"


Configuration
-------------

This plugin can be configured like other metadata source plugins as described in :ref:`metadata-source-plugin-configuration`.

There is one additional option in the ``discogs:`` section, ``index_tracks``.
Index tracks (see the `Discogs guidelines
<https://support.discogs.com/hc/en-us/articles/360005055373-Database-Guidelines-12-Tracklisting#Index_Tracks_And_Headings>`_),
along with headers, mark divisions between distinct works on the same release
or within works. When ``index_tracks`` is enabled:

.. code-block:: yaml

    discogs:
        index_tracks: yes

beets will incorporate the names of the divisions containing each track into
the imported track's title.

For example, importing
`this album
<https://www.discogs.com/Handel-Sutherland-Kirkby-Kwella-Nelson-Watkinson-Bowman-Rolfe-Johnson-Elliott-Partridge-Thomas-The-A/release/2026070>`_
would result in track names like:

.. code-block:: text

    Messiah, Part I: No.1: Sinfony
    Messiah, Part II: No.22: Chorus- Behold The Lamb Of God
    Athalia, Act I, Scene I: Sinfonia

whereas with ``index_tracks`` disabled you'd get:

.. code-block:: text

    No.1: Sinfony
    No.22: Chorus- Behold The Lamb Of God
    Sinfonia

This option is useful when importing classical music.

Other configurations available under ``discogs:`` are:

- **append_style_genre**: Appends the Discogs style (if found) to the genre tag. This can be useful if you want more granular genres to categorize your music.
  For example, a release in Discogs might have a genre of "Electronic" and a style of "Techno": enabling this setting would set the genre to be "Electronic, Techno" (assuming default separator of ``", "``) instead of just "Electronic".
  Default: ``False``
- **separator**: How to join multiple genre and style values from Discogs into a string.
  Default: ``", "``


Troubleshooting
---------------

Several issues have been encountered with the Discogs API. If you have one,
please start by searching for `a similar issue on the repo
<https://github.com/beetbox/beets/issues?utf8=%E2%9C%93&q=is%3Aissue+discogs>`_.

Here are two things you can try:

* Try deleting the token file (``~/.config/beets/discogs_token.json`` by
  default) to force re-authorization.
* Make sure that your system clock is accurate. The Discogs servers can reject
  your request if your clock is too out of sync.

Matching tracks by Discogs ID is not yet supported. The ``--group-albums``
option in album import mode provides an alternative to singleton mode for autotagging tracks that are not in album-related folders.

.. _python3-discogs-client: https://github.com/joalla/discogs_client
