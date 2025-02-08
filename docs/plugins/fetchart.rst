FetchArt Plugin
===============

The ``fetchart`` plugin retrieves album art images from various sources on the
Web and stores them as image files.

To use the ``fetchart`` plugin, first enable it in your configuration (see
:ref:`using-plugins`). Then, install ``beets`` with ``fetchart`` extra

.. code-block:: bash

    pip install "beets[fetchart]"

Fetching Album Art During Import
--------------------------------

When the plugin is enabled, it automatically tries to get album art for every
album you import.

By default, beets stores album art image files alongside the music files for an
album in a file called ``cover.jpg``. To customize the name of this file, use
the :ref:`art-filename` config option. To embed the art into the files' tags,
use the :doc:`/plugins/embedart`. (You'll want to have both plugins enabled.)

Configuration
-------------

To configure the plugin, make a ``fetchart:`` section in your configuration
file. The available options are:

- **auto**: Enable automatic album art fetching during import.
  Default: ``yes``.
- **cautious**: Pick only trusted album art by ignoring filenames that do not
  contain one of the keywords in ``cover_names``.
  Default: ``no``.
- **cover_names**: Prioritize images containing words in this list.
  Default: ``cover front art album folder``.
- **minwidth**: Only images with a width bigger or equal to ``minwidth`` are
  considered as valid album art candidates. Default: 0.
- **maxwidth**: A maximum image width to downscale fetched images if they are
  too big. The resize operation reduces image width to at most ``maxwidth``
  pixels. The height is recomputed so that the aspect ratio is preserved. See
  the section on :ref:`cover-art-archive-maxwidth` below for additional
  information regarding the Cover Art Archive source.
  Default: 0 (no maximum is enforced).
- **quality**: The JPEG quality level to use when compressing images (when
  ``maxwidth`` is set). This should be either a number from 1 to 100 or 0 to
  use the default quality. 65–75 is usually a good starting point. The default
  behavior depends on the imaging tool used for scaling: ImageMagick tries to
  estimate the input image quality and uses 92 if it cannot be determined, and
  PIL defaults to 75.
  Default: 0 (disabled)
- **max_filesize**: The maximum size of a target piece of cover art in bytes.
  When using an ImageMagick backend this sets
  ``-define jpeg:extent=max_filesize``. Using PIL this will reduce JPG quality
  by up to 50% to attempt to reach the target filesize. Neither method is
  *guaranteed* to reach the target size, however in most cases it should
  succeed.
  Default: 0 (disabled)
- **enforce_ratio**: Only images with a width:height ratio of 1:1 are
  considered as valid album art candidates if set to ``yes``.
  It is also possible to specify a certain deviation to the exact ratio to
  still be considered valid. This can be done either in pixels
  (``enforce_ratio: 10px``) or as a percentage of the longer edge
  (``enforce_ratio: 0.5%``). Default: ``no``.
- **sources**: List of sources to search for images. An asterisk `*` expands
  to all available sources.
  Default: ``filesystem coverart itunes amazon albumart``, i.e., everything but
  ``wikipedia``, ``google``, ``fanarttv`` and ``lastfm``. Enable those sources
  for more matches at the cost of some speed. They are searched in the given
  order, thus in the default config, no remote (Web) art source are queried if
  local art is found in the filesystem. To use a local image as fallback,
  move it to the end of the list. For even more fine-grained control over
  the search order, see the section on :ref:`album-art-sources` below.
- **google_key**: Your Google API key (to enable the Google Custom Search
  backend).
  Default: None.
- **google_engine**: The custom search engine to use.
  Default: The `beets custom search engine`_, which searches the entire web.
- **fanarttv_key**: The personal API key for requesting art from
  fanart.tv. See below.
- **lastfm_key**: The personal API key for requesting art from Last.fm. See
  below.
- **store_source**: If enabled, fetchart stores the artwork's source in a
  flexible tag named ``art_source``. See below for the rationale behind this.
  Default: ``no``.
- **high_resolution**: If enabled, fetchart retrieves artwork in the highest
  resolution it can find (warning: image files can sometimes reach >20MB).
  Default: ``no``.
- **deinterlace**: If enabled, `Pillow`_ or `ImageMagick`_ backends are
  instructed to store cover art as non-progressive JPEG. You might need this if
  you use DAPs that don't support progressive images.
  Default: ``no``.
- **cover_format**: If enabled, forced the cover image into the specified
  format. Most often, this will be either ``JPEG`` or ``PNG`` [#imgformats]_.
  Also respects ``deinterlace``.
  Default: None (leave unchanged).

Note: ``maxwidth`` and ``enforce_ratio`` options require either `ImageMagick`_
or `Pillow`_.

.. note::

    Previously, there was a ``remote_priority`` option to specify when to
    look for art on the filesystem. This is
    still respected, but a deprecation message will be shown until you
    replace this configuration with the new ``filesystem`` value in the
    ``sources`` array.

.. _beets custom search engine: https://cse.google.com.au:443/cse/publicurl?cx=001442825323518660753:hrh5ch1gjzm
.. _Pillow: https://github.com/python-pillow/Pillow
.. _ImageMagick: https://www.imagemagick.org/
.. [#imgformats] Other image formats are available, though the full list
   depends on your system and what backend you are using. If you're using the
   ImageMagick backend, you can use ``magick identify -list format`` to get a
   full list of all supported formats, and you can use the Python function
   PIL.features.pilinfo() to print a list of all supported formats in Pillow
   (``python3 -c 'import PIL.features as f; f.pilinfo()'``).

Here's an example that makes plugin select only images that contain ``front`` or
``back`` keywords in their filenames and prioritizes the iTunes source over
others::

    fetchart:
        cautious: true
        cover_names: front back
        sources: itunes *


Manually Fetching Album Art
---------------------------

Use the ``fetchart`` command to download album art after albums have already
been imported::

    $ beet fetchart [-f] [query]

By default, the command will only look for album art when the album doesn't
already have it; the ``-f`` or ``--force`` switch makes it search for art
in Web databases regardless. If you specify a query, only matching albums will
be processed; otherwise, the command processes every album in your library.

Display Only Missing Album Art
------------------------------

Use the ``fetchart`` command with the ``-q`` switch in order to display only missing
art::

    $ beet fetchart [-q] [query]

By default the command will display all albums matching the ``query``. When the
``-q`` or ``--quiet`` switch is given, only albums for which artwork has been
fetched, or for which artwork could not be found will be printed.

.. _image-resizing:

Image Resizing
--------------

Beets can resize images using `Pillow`_, `ImageMagick`_, or a server-side resizing
proxy. If either Pillow or ImageMagick is installed, beets will use those;
otherwise, it falls back to the resizing proxy. If the resizing proxy is used,
no resizing is performed for album art found on the filesystem---only downloaded
art is resized. Server-side resizing can also be slower than local resizing, so
consider installing one of the two backends for better performance.

When using ImageMagick, beets looks for the ``convert`` executable in your path.
On some versions of Windows, the program can be shadowed by a system-provided
``convert.exe``. On these systems, you may need to modify your ``%PATH%``
environment variable so that ImageMagick comes first or use Pillow instead.

.. _Pillow: https://github.com/python-pillow/Pillow
.. _ImageMagick: https://www.imagemagick.org/

.. _album-art-sources:

Album Art Sources
-----------------

By default, this plugin searches for art in the local filesystem as well as on
the Cover Art Archive, the iTunes Store, Amazon, and AlbumArt.org, in that
order.
You can reorder the sources or remove
some to speed up the process using the ``sources`` configuration option.

When looking for local album art, beets checks for image files located in the
same folder as the music files you're importing. Beets prefers to use an image
file whose name contains "cover", "front", "art", "album" or "folder", but in
the absence of well-known names, it will use any image file in the same folder
as your music files.

For some of the art sources, the backend service can match artwork by various
criteria. If you want finer control over the search order in such cases, you
can use this alternative syntax for the ``sources`` option::

    fetchart:
        sources:
            - filesystem
            - coverart: release
            - itunes
            - coverart: releasegroup
            - '*'

where listing a source without matching criteria will default to trying all
available strategies. Entries of the forms ``coverart: release releasegroup``
and ``coverart: *`` are also valid.
Currently, only the ``coverart`` source supports multiple criteria:
namely, ``release`` and ``releasegroup``, which refer to the
respective MusicBrainz IDs.

When you choose to apply changes during an import, beets will search for art as
described above.  For "as-is" imports (and non-autotagged imports using the
``-A`` flag), beets only looks for art on the local filesystem.

Google custom search
''''''''''''''''''''

To use the google image search backend you need to
`register for a Google API key`_. Set the ``google_key`` configuration
option to your key, then add ``google`` to the list of sources in your
configuration.

.. _register for a Google API key: https://console.developers.google.com.

Optionally, you can `define a custom search engine`_. Get your search engine's
token and use it for your ``google_engine`` configuration option. The
default engine searches the entire web for cover art.

.. _define a custom search engine: https://www.google.com/cse/all

Note that the Google custom search API is limited to 100 queries per day.
After that, the fetchart plugin will fall back on other declared data sources.

Fanart.tv
'''''''''

Although not strictly necessary right now, you might think about
`registering a personal fanart.tv API key`_. Set the ``fanarttv_key``
configuration option to your key, then add ``fanarttv`` to the list of sources
in your configuration.

.. _registering a personal fanart.tv API key: https://fanart.tv/get-an-api-key/

More detailed information can be found `on their Wiki`_. Specifically, the
personal key will give you earlier access to new art.

.. _on their Wiki: https://wiki.fanart.tv/General/personal%20api/

Last.fm
'''''''

To use the Last.fm backend, you need to `register for a Last.fm API key`_. Set
the ``lastfm_key`` configuration option to your API key, then add ``lastfm`` to
the list of sources in your configuration.

.. _register for a Last.fm API key: https://www.last.fm/api/account/create

Spotify
'''''''

Spotify backend is enabled by default and will update album art if a valid Spotify album id is found.

.. _pip: https://pip.pypa.io
.. _BeautifulSoup: https://www.crummy.com/software/BeautifulSoup/bs4/doc/

Cover Art URL
'''''''''''''

The `fetchart` plugin can also use a flexible attribute field ``cover_art_url``
where you can manually specify the image URL to be used as cover art. Any custom
plugin can use this field to provide the cover art and ``fetchart`` will use it
as a source.

.. _cover-art-archive-maxwidth:

Cover Art Archive Pre-sized Thumbnails
--------------------------------------

The CAA provides pre-sized thumbnails of width 250, 500, and 1200 pixels. If you
set the `maxwidth` option to one of these values, the corresponding image will
be downloaded, saving `beets` the need to scale down the image. It can also
speed up the downloading process, as some cover arts can sometimes be very
large.

Storing the Artwork's Source
----------------------------

Storing the current artwork's source might be used to narrow down
``fetchart`` commands. For example, if some albums have artwork placed
manually in their directories that should not be replaced by a forced
album art fetch, you could do

``beet fetchart -f ^art_source:filesystem``

The values written to ``art_source`` are the same names used in the ``sources``
configuration value.
