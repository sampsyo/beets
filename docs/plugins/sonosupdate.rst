SonosUpdate Plugin
==================

The ``sonosupdate`` plugin lets you automatically update `Sonos`_'s music
library whenever you change your beets library.

To use ``sonosupdate`` plugin, enable it in your configuration
(see :ref:`using-plugins`).

To use the ``sonosupdate`` plugin, first enable it in your configuration (see
:ref:`using-plugins`). Then, install ``beets`` with ``sonosupdate`` extra

    pip install "beets[sonosupdate]"

With that all in place, you'll see beets send the "update" command to your Sonos
controller every time you change your beets library.

.. _Sonos: https://sonos.com/
