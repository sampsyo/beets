AcousticBrainz Submit Plugin
============================

The ``absubmit`` plugin lets you submit acoustic analysis results to an
`AcousticBrainz`_ server. This plugin is now deprecated since the
AcousicBrainz project has been shut down.

As an alternative the `beets-xtractor`_ plugin can be used.

Warning
-------

The AcousticBrainz project has shut down. To use this plugin you must set the
``base_url`` configuration option to a server offering the AcousticBrainz API.

Installation
------------

The ``absubmit`` plugin requires the `streaming_extractor_music`_ program
to run. Its source can be found on `GitHub`_, and while it is possible to
compile the extractor from source, AcousticBrainz would prefer if you used
their binary (see the AcousticBrainz `FAQ`_).

Then, install ``beets`` with ``absubmit`` extra

    pip install "beets[absubmit]"

Lastly, enable the plugin in your configuration (see :ref:`using-plugins`). 


Submitting Data
---------------

To run the analysis program and upload its results, type::

    beet absubmit [-f] [-d] [QUERY]

By default, the command will only look for AcousticBrainz data when the tracks
don't already have it; the ``-f`` or ``--force`` switch makes it refetch
data even when it already exists. You can use the ``-d`` or ``--dry`` switch
to check which files will be analyzed, before you start a longer period
of processing.

The plugin works on music with a MusicBrainz track ID attached. The plugin
will also skip music that the analysis tool doesn't support.
`streaming_extractor_music`_ currently supports files with the extensions
``mp3``, ``ogg``, ``oga``, ``flac``, ``mp4``, ``m4a``, ``m4r``, ``m4b``,
``m4p``, ``aac``, ``wma``, ``asf``, ``mpc``, ``wv``, ``spx``, ``tta``,
``3g2``, ``aif``, ``aiff`` and ``ape``.

Configuration
-------------

To configure the plugin, make a ``absubmit:`` section in your configuration
file. The available options are:

- **auto**: Analyze every file on import. Otherwise, you need to use the
  ``beet absubmit`` command explicitly.
  Default: ``no``
- **extractor**: The absolute path to the `streaming_extractor_music`_ binary.
  Default: search for the program in your ``$PATH``
- **force**: Analyze items and submit of AcousticBrainz data even for tracks
  that already have it.
  Default: ``no``.
- **pretend**: Do not analyze and submit of AcousticBrainz data but print out
  the items which would be processed.
  Default: ``no``.
- **base_url**: The base URL of the AcousticBrainz server. The plugin has no
  function if this option is not set.
  Default: None

.. _streaming_extractor_music: https://essentia.upf.edu/
.. _FAQ: https://acousticbrainz.org/faq
.. _pip: https://pip.pypa.io
.. _requests: https://requests.readthedocs.io/en/master/
.. _github: https://github.com/MTG/essentia
.. _AcousticBrainz: https://acousticbrainz.org
.. _beets-xtractor: https://github.com/adamjakab/BeetsPluginXtractor
