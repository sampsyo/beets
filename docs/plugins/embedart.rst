EmbedArt Plugin
===============

Typically, beets stores album art in a "file on the side": along with each
album, there is a file (named "cover.jpg" by default) that stores the album art.
You might want to embed the album art directly into each file's metadata. While
this will take more space than the external-file approach, it is necessary for
displaying album art in some media players (iPods, for example).

Embedding Art Automatically
---------------------------

To use the ``embedart`` plugin, first enable it in your configuration (see
:ref:`using-plugins`). Then, install ``beets`` with ``embedart`` extra

.. code-block:: bash

    pip install "beets[embedart]"

You'll also want to enable the :doc:`/plugins/fetchart` to obtain the images to
be embedded. Art will be embedded after each album has its cover art set.

This behavior can be disabled with the ``auto`` config option (see below).

.. _image-similarity-check:

Image Similarity
''''''''''''''''

When importing a lot of files with the ``auto`` option, one may be reluctant to
overwrite existing embedded art for all of them.

You can tell beets to avoid embedding images that are too different from the
existing ones.
This works by computing the perceptual hashes (`PHASH`_) of the two images and
checking that the difference between the two does not exceed a
threshold. You can set the threshold with the ``compare_threshold`` option.

A threshold of 0 (the default) disables similarity checking and always embeds
new images. Set the threshold to another number---we recommend between 10 and
100---to adjust the sensitivity of the comparison. The smaller the threshold
number, the more similar the images must be.

This feature requires `ImageMagick`_.

Configuration
-------------

To configure the plugin, make an ``embedart:`` section in your configuration
file. The available options are:

- **auto**: Enable automatic album art embedding.
  Default: ``yes``.
- **compare_threshold**: How similar candidate art must be to
  existing art to be written to the file (see :ref:`image-similarity-check`).
  Default: 0 (disabled).
- **ifempty**: Avoid embedding album art for files that already have art
  embedded.
  Default: ``no``.
- **maxwidth**: A maximum width to downscale images before embedding
  them (the original image file is not altered). The resize operation reduces
  image width to at most ``maxwidth`` pixels. The height is recomputed so that
  the aspect ratio is preserved. See also :ref:`image-resizing` for further
  caveats about image resizing.
  Default: 0 (disabled).
- **quality**: The JPEG quality level to use when compressing images (when
  ``maxwidth`` is set). This should be either a number from 1 to 100 or 0 to
  use the default quality. 65–75 is usually a good starting point. The default
  behavior depends on the imaging tool used for scaling: ImageMagick tries to
  estimate the input image quality and uses 92 if it cannot be determined, and
  PIL defaults to 75.
  Default: 0 (disabled)
- **remove_art_file**: Automatically remove the album art file for the album
  after it has been embedded. This option is best used alongside the
  :doc:`FetchArt </plugins/fetchart>` plugin to download art with the purpose of
  directly embedding it into the file's metadata without an "intermediate"
  album art file.
  Default: ``no``.

Note: ``compare_threshold`` option requires `ImageMagick`_, and ``maxwidth``
requires either `ImageMagick`_ or `Pillow`_.

.. _Pillow: https://github.com/python-pillow/Pillow
.. _ImageMagick: https://www.imagemagick.org/
.. _PHASH: http://www.fmwconcepts.com/misc_tests/perceptual_hash_test_results_510/

Manually Embedding and Extracting Art
-------------------------------------

The ``embedart`` plugin provides a couple of commands for manually managing
embedded album art:

* ``beet embedart [-f IMAGE] QUERY``: embed images in every track of the
  albums matching the query. If the ``-f`` (``--file``) option is given, then
  use a specific image file from the filesystem; otherwise, each album embeds
  its own currently associated album art. The command prompts for confirmation
  before making the change unless you specify the ``-y`` (``--yes``) option.

* ``beet embedart [-u IMAGE_URL] QUERY``: embed image specified in the URL
  into every track of the albums matching the query. The ``-u`` (``--url``) option can be used to specify the URL of the image to be used. The command prompts for confirmation before making the change unless you specify the ``-y`` (``--yes``) option.

* ``beet extractart [-a] [-n FILE] QUERY``: extracts the images for all albums
  matching the query. The images are placed inside the album folder. You can
  specify the destination file name using the ``-n`` option, but leave off the
  extension: it will be chosen automatically. The destination filename is
  specified using the ``art_filename`` configuration option. It defaults to
  ``cover`` if it's not specified via ``-o`` nor the config.
  Using ``-a``, the extracted image files are automatically associated with the
  corresponding album.

* ``beet extractart -o FILE QUERY``: extracts the image from an item matching
  the query and stores it in a file. You have to specify the destination file
  using the ``-o`` option, but leave off the extension: it will be chosen
  automatically.

* ``beet clearart QUERY``: removes all embedded images from all items matching
  the query. The command prompts for confirmation before making the change
  unless you specify the ``-y`` (``--yes``) option.
