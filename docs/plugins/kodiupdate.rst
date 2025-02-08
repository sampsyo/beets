KodiUpdate Plugin
=================

The ``kodiupdate`` plugin lets you automatically update `Kodi`_'s music
library whenever you change your beets library.

To use ``kodiupdate`` plugin, enable it in your configuration
(see :ref:`using-plugins`).
Then, you'll want to configure the specifics of your Kodi host.
You can do that using a ``kodi:`` section in your ``config.yaml``,
which looks like this::

    kodi:
        host: localhost
        port: 8080
        user: kodi
        pwd: kodi

To update multiple Kodi instances, specify them as an array::

    kodi:
      - host: x.x.x.x
        port: 8080
        user: kodi
        pwd: kodi
      - host: y.y.y.y
        port: 8081
        user: kodi2
        pwd: kodi2


To use the ``kodiupdate`` plugin, first enable it in your configuration (see
:ref:`using-plugins`). Then, install ``beets`` with ``kodiupdate`` extra

.. code-block:: bash

    pip install "beets[kodiupdate]"

You'll also need to enable JSON-RPC in Kodi.

In Kodi's interface, navigate to System/Settings/Network/Services and choose "Allow control of Kodi via HTTP."

With that all in place, you'll see beets send the "update" command to your Kodi
host every time you change your beets library.

.. _Kodi: https://kodi.tv/

Configuration
-------------

The available options under the ``kodi:`` section are:

- **host**: The Kodi host name.
  Default: ``localhost``
- **port**: The Kodi host port.
  Default: 8080
- **user**: The Kodi host user.
  Default: ``kodi``
- **pwd**: The Kodi host password.
  Default: ``kodi``
