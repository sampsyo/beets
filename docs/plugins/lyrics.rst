Lyrics Plugin
=============

The ``lyrics`` plugin fetches and stores song lyrics from databases on the Web.
Namely, the current version of the plugin uses `Genius.com`_, `Tekstowo.pl`_,
`LRCLIB`_ and, optionally, the Google Custom Search API.

.. _Genius.com: https://genius.com/
.. _Tekstowo.pl: https://www.tekstowo.pl/
.. _LRCLIB: https://lrclib.net/


Install
-------

Firstly, enable ``lyrics`` plugin in your configuration (see
:ref:`using-plugins`). Then, install ``beets`` with ``lyrics`` extra

.. code-block:: bash

    pip install "beets[lyrics]"

Fetch Lyrics During Import
--------------------------

When importing new files, beets will now fetch lyrics for files that don't
already have them. The lyrics will be stored in the beets database. If the
``import.write`` config option is on, then the lyrics will also be written to
the files' tags.

Configuration
-------------

To configure the plugin, make a ``lyrics:`` section in your configuration file.
Default configuration:

.. code-block:: yaml

    lyrics:
        auto: yes
        bing_client_secret: null
        bing_lang_from: []
        bing_lang_to: null
        dist_thresh: 0.11
        fallback: null
        force: no
        google_API_key: null
        google_engine_ID: 009217259823014548361:lndtuqkycfu
        sources: [lrclib, google, genius, tekstowo]
        synced: no

The available options are:

- **auto**: Fetch lyrics automatically during import.
- **bing_client_secret**: Your Bing Translation application password
  (see :ref:`lyrics-translation`)
- **bing_lang_from**: By default all lyrics with a language other than
  ``bing_lang_to`` are translated. Use a list of lang codes to restrict the set
  of source languages to translate.
- **bing_lang_to**: Language to translate lyrics into.
- **dist_thresh**: The maximum distance between the artist and title
  combination of the music file and lyrics candidate to consider them a match.
  Lower values will make the plugin more strict, higher values will make it
  more lenient. This does not apply to the ``lrclib`` backend as it matches
  durations.
- **fallback**: By default, the file will be left unchanged when no lyrics are
  found. Use the empty string ``''`` to reset the lyrics in such a case.
- **force**: By default, beets won't fetch lyrics if the files already have
  ones. To instead always fetch lyrics, set the ``force`` option to ``yes``.
- **google_API_key**: Your Google API key (to enable the Google Custom Search
  backend).
- **google_engine_ID**: The custom search engine to use.
  Default: The `beets custom search engine`_, which gathers an updated list of
  sources known to be scrapeable.
- **sources**: List of sources to search for lyrics. An asterisk ``*`` expands
  to all available sources. The ``google`` source will be automatically
  deactivated if no ``google_API_key`` is setup.
- **synced**: Prefer synced lyrics over plain lyrics if a source offers them.
  Currently ``lrclib`` is the only source that provides them.

.. _beets custom search engine: https://www.google.com:443/cse/publicurl?cx=009217259823014548361:lndtuqkycfu

Fetching Lyrics Manually
------------------------

The ``lyrics`` command provided by this plugin fetches lyrics for items that
match a query (see :doc:`/reference/query`). For example, ``beet lyrics magnetic
fields absolutely cuckoo`` will get the lyrics for the appropriate Magnetic
Fields song, ``beet lyrics magnetic fields`` will get lyrics for all my tracks
by that band, and ``beet lyrics`` will get lyrics for my entire library. The
lyrics will be added to the beets database and, if ``import.write`` is on,
embedded into files' metadata.

The ``-p, --print`` option to the ``lyrics`` command makes it print lyrics out
to the console so you can view the fetched (or previously-stored) lyrics.

The ``-f, --force`` option forces the command to fetch lyrics, even for tracks
that already have lyrics.

Inversely, the ``-l, --local`` option restricts operations to lyrics that are
locally available, which show lyrics faster without using the network at all.

Rendering Lyrics into Other Formats
-----------------------------------

The ``-r directory, --write-rest directory`` option renders all lyrics as
`reStructuredText`_ (ReST) documents in ``directory`` (by default, the current
directory). That directory, in turn, can be parsed by tools like `Sphinx`_ to
generate HTML, ePUB, or PDF documents.

Minimal ``conf.py`` and ``index.rst`` files are created the first time the
command is run. They are not overwritten on subsequent runs, so you can safely
modify these files to customize the output.

Sphinx supports various `builders`_, see a few suggestions:


.. admonition:: Build an HTML version

  ::

      sphinx-build -b html . _build/html

.. admonition:: Build an ePUB3 formatted file, usable on ebook readers

  ::

      sphinx-build -b epub3 . _build/epub

.. admonition:: Build a PDF file, which incidentally also builds a LaTeX file

  ::

      sphinx-build -b latex %s _build/latex && make -C _build/latex all-pdf


.. _Sphinx: https://www.sphinx-doc.org/
.. _reStructuredText: http://docutils.sourceforge.net/rst.html
.. _builders: https://www.sphinx-doc.org/en/stable/builders.html

Activate Google Custom Search
------------------------------

You need to `register for a Google API key`_. Set the ``google_API_key``
configuration option to your key.

Then add ``google`` to the list of sources in your configuration (or use
default list, which includes it as long as you have an API key).
If you use default ``google_engine_ID``, we recommend limiting the sources to
``google`` as the other sources are already included in the Google results.

Optionally, you can `define a custom search engine`_. Get your search engine's
token and use it for your ``google_engine_ID`` configuration option. By
default, beets use a list of sources known to be scrapeable.

Note that the Google custom search API is limited to 100 queries per day.
After that, the lyrics plugin will fall back on other declared data sources.

.. _register for a Google API key: https://console.developers.google.com/
.. _define a custom search engine: https://www.google.com/cse/all


.. _lyrics-translation:

Activate On-the-Fly Translation
-------------------------------

You need to register for a Microsoft Azure Marketplace free account and
to the `Microsoft Translator API`_. Follow the four steps process, specifically
at step 3 enter ``beets`` as *Client ID* and copy/paste the generated
*Client secret* into your ``bing_client_secret`` configuration, alongside
``bing_lang_to`` target ``language code``.

.. _Microsoft Translator API: https://docs.microsoft.com/en-us/azure/cognitive-services/translator/translator-how-to-signup
