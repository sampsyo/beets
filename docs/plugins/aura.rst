AURA Plugin
===========

This plugin is a server implementation of the `AURA`_ specification using the
`Flask`_ framework. AURA is still a work in progress and doesn't yet have a
stable version, but this server should be kept up to date. You are advised to
read the :ref:`aura-issues` section.

.. _AURA: https://auraspec.readthedocs.io
.. _Flask: https://palletsprojects.com/p/flask/

Install
-------

To use the ``aura`` plugin, first enable it in your configuration (see
:ref:`using-plugins`). Then, install ``beets`` with ``aura`` extra

    pip install "beets[aura]"


Usage
-----

Use ``beet aura`` to start the AURA server.
By default Flask's built-in server is used, which will give a warning about
using it in a production environment. It is safe to ignore this warning if the
server will have only a few users.

Alternatively, you can use ``beet aura -d`` to start the server in
`development mode`_, which will reload the server every time the AURA plugin
file is changed.

You can specify the hostname and port number used by the server in your
:doc:`configuration file </reference/config>`. For more detail see the
:ref:`configuration` section below.

If you would prefer to use a different WSGI server, such as gunicorn or uWSGI,
then see :ref:`aura-external-server`.

AURA is designed to separate the client and server functionality. This plugin
provides the server but not the client, so unless you like looking at JSON you
will need a separate client. Currently the only client is `AURA Web Client`_.
In order to use a local browser client with ``file:///`` see :ref:`aura-cors`.

By default the API is served under http://127.0.0.1:8337/aura/. For example
information about the track with an id of 3 can be obtained at
http://127.0.0.1:8337/aura/tracks/3.

**Note the absence of a trailing slash**:
http://127.0.0.1:8337/aura/tracks/3/ returns a ``404 Not Found`` error.

.. _development mode: https://flask.palletsprojects.com/en/1.1.x/server
.. _AURA Web Client: https://sr.ht/~callum/aura-web-client/


.. _configuration:

Configuration
-------------

To configure the plugin, make an ``aura:`` section in your
configuration file. The available options are:

- **host**: The server hostname. Set this to ``0.0.0.0`` to bind to all
  interfaces. Default: ``127.0.0.1``.
- **port**: The server port.
  Default: ``8337``.
- **cors**: A YAML list of origins to allow CORS requests from (see
  :ref:`aura-cors`, below).
  Default: disabled.
- **cors_supports_credentials**: Allow authenticated requests when using CORS.
  Default: disabled.
- **page_limit**: The number of items responses should be truncated to if the
  client does not specify. Default ``500``.


.. _aura-cors:

Cross-Origin Resource Sharing (CORS)
------------------------------------

`CORS`_ allows browser clients to make requests to the AURA server. You should
set the ``cors`` configuration option to a YAML list of allowed origins.

For example::

    aura:
        cors:
            - http://www.example.com
            - https://aura.example.org

In order to use the plugin with a local browser client accessed using
``file:///`` you must include ``'null'`` in the list of allowed origins
(including quote marks)::

    aura:
        cors:
            - 'null'

Alternatively you use ``'*'`` to enable access from all origins.
Note that there are security implications if you set the origin to ``'*'``,
so please research this before using it. Note the use of quote marks when
allowing all origins.

If the server is behind a proxy that uses credentials, you might want to set
the ``cors_supports_credentials`` configuration option to true to let
in-browser clients log in. Note that this option has not been tested, so it
may not work.

.. _CORS: https://en.wikipedia.org/wiki/Cross-origin_resource_sharing


.. _aura-external-server:

Using an External WSGI Server
-----------------------------

If you would like to use a different WSGI server (not Flask's built-in one),
then you can! The ``beetsplug.aura`` module provides a WSGI callable called
``create_app()`` which can be used by many WSGI servers.

For example to run the AURA server using `gunicorn`_ use
``gunicorn 'beetsplug.aura:create_app()'``, or for `uWSGI`_ use
``uwsgi --http :8337 --module 'beetsplug.aura:create_app()'``.
Note that these commands just show how to use the AURA app and you would
probably use something a bit different in a production environment. Read the
relevant server's documentation to figure out what you need.

.. _gunicorn: https://gunicorn.org
.. _uWSGI: https://uwsgi-docs.readthedocs.io


Reverse Proxy Support
---------------------

The plugin should work behind a reverse proxy without further configuration,
however this has not been tested extensively. For details of what headers must
be rewritten and a sample NGINX configuration see `Flask proxy setups`_.

It is (reportedly) possible to run the application under a URL prefix (for
example so you could have ``/foo/aura/server`` rather than ``/aura/server``),
but you'll have to work it out for yourself :-)

If using NGINX, do **not** add a trailing slash (``/``) to the URL where the
application is running, otherwise you will get a 404. However if you are using
Apache then you **should** add a trailing slash.

.. _Flask proxy setups: https://flask.palletsprojects.com/en/1.1.x/deploying/wsgi-standalone/#proxy-setups


.. _aura-issues:

Issues
------

As of writing there are some differences between the specification and this
implementation:

- Compound filters are not specified in AURA, but this server interprets
  multiple ``filter`` parameters as AND. See `issue #19`_ for discussion.
- The ``bitrate`` parameter used for content negotiation is not supported.
  Adding support for this is doable, but the way Flask handles acceptable MIME
  types means it's a lot easier not to bother with it. This means an error
  could be returned even if no transcoding was required.

It is possible that some attributes required by AURA could be absent from the
server's response if beets does not have a saved value for them. However, this
has not happened so far.

Beets fields (including flexible fields) that do not have an AURA equivalent
are not provided in any resource's attributes section, however these fields may
be used for filtering.

The ``mimetype`` and ``framecount`` attributes for track resources are not
supported. The first is due to beets storing the file type (e.g. ``MP3``), so
it is hard to filter by MIME type. The second is because there is no
corresponding beets field.

Artists are defined by the ``artist`` field on beets Items, which means some
albums have no ``artists`` relationship. Albums only have related artists
when their beets ``albumartist`` field is the same as the ``artist`` field on
at least one of it's constituent tracks.

The only art tracked by beets is a single cover image, so only albums have
related images at the moment. This could be expanded to looking in the same
directory for other images, and relating tracks to their album's image.

There are likely to be some performance issues, especially with larger
libraries. Sorting, pagination and inclusion (most notably of images) are
probably the main offenders. On a related note, the program attempts to import
Pillow every time it constructs an image resource object, which is not good.

The beets library is accessed using a so called private function (with a single
leading underscore) ``beets.ui.__init__._open_library()``. This shouldn't cause
any issues but it is probably not best practice.

.. _issue #19: https://github.com/beetbox/aura/issues/19
