EmbyUpdate Plugin
=================

``embyupdate`` is a plugin that lets you automatically update `Emby`_'s library
whenever you change your beets library.

To use it, first enable the your configuration (see :ref:`using-plugins`).
Then, install ``beets`` with ``embyupdate`` extra

.. code-block:: bash

    pip install "beets[embyupdate]"

Then, you'll want to configure the specifics of your Emby server. You can do
that using an ``emby`` section in your ``config.yaml``

.. code-block:: yaml

    emby:
        host: localhost
        port: 8096
        username: user
        apikey: apikey

With that all in place, you'll see beets send the "update" command to your Emby server every time you change your beets library.

.. _Emby: https://emby.media/

Configuration
-------------

The available options under the ``emby:`` section are:

- **host**: The Emby server host. You also can include ``http://`` or ``https://``.
  Default: ``localhost``
- **port**: The Emby server port.
  Default: 8096
- **username**: A username of an Emby user that is allowed to refresh the library.
- **userid**: A user ID of an Emby user that is allowed to refresh the library.
  (This is only necessary for private users i.e. when the user is hidden from
  login screens)
- **apikey**: An Emby API key for the user.
- **password**: The password for the user. (This is only necessary if no API
  key is provided.)

You can choose to authenticate either with ``apikey`` or ``password``, but only
one of those two is required.
