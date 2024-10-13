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
        translate:
            api_key:
            from_languages: []
            to_language:
        dist_thresh: 0.11
        fallback: null
        force: no
        google_API_key: null
        google_engine_ID: 009217259823014548361:lndtuqkycfu
        sources: [lrclib, google, genius, tekstowo]
        synced: no

The available options are:

- **auto**: Fetch lyrics automatically during import.
- **translate**:

  - **api_key**: Api key to access your Azure Translator resource. (see
    :ref:`lyrics-translation`)
  - **from_languages**: By default all lyrics with a language other than
    ``translate_to`` are translated. Use a list of language codes to restrict
    them.
  - **to_language**: Language code to translate lyrics to.
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

We use Azure to optionally translate your lyrics. To set up the integration,
follow these steps:

1. `Create a Translator resource`_ on Azure.
2. `Obtain its API key`_.
3. Add the API key to your configuration as ``translate.api_key``.
4. Configure your target language using the ``translate.to_language`` option.


For example, with the following configuration

.. code-block:: yaml

  lyrics:
    translate:
      api_key: YOUR_TRANSLATOR_API_KEY
      to_language: de

You should expect lyrics like this::

  Original verse / Ursprünglicher Vers
  Some other verse / Ein anderer Vers

.. _create a Translator resource: https://learn.microsoft.com/en-us/azure/ai-services/translator/create-translator-resource
.. _obtain its API key: https://learn.microsoft.com/en-us/python/api/overview/azure/ai-translation-text-readme?view=azure-python&preserve-view=true#get-an-api-key
