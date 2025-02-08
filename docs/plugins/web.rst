Web Plugin
==========

The ``web`` plugin is a very basic alternative interface to beets that
supplements the CLI. It can't do much right now, and the interface is a little
clunky, but you can use it to query and browse your music and---in browsers that
support HTML5 Audio---you can even play music.

While it's not meant to replace the CLI, a graphical interface has a number of
advantages in certain situations. For example, when editing a tag, a natural CLI
makes you retype the whole thing---common GUI conventions can be used to just
edit the part of the tag you want to change. A graphical interface could also
drastically increase the number of people who can use beets.

Install
-------

To use the ``web`` plugin, first enable it in your configuration (see
:ref:`using-plugins`). Then, install ``beets`` with ``web`` extra

.. code-block:: bash

    pip install "beets[web]"

Run the Server
--------------

Then just type ``beet web`` to start the server and go to
http://localhost:8337/. This is what it looks like:

.. image:: beetsweb.png

You can also specify the hostname and port number used by the Web server. These
can be specified on the command line or in the ``[web]`` section of your
:doc:`configuration file </reference/config>`.

On the command line, use ``beet web [HOSTNAME] [PORT]``. Or the configuration
options below.

Usage
-----

Type queries into the little search box. Double-click a track to play it with
HTML5 Audio.

Configuration
-------------

To configure the plugin, make a ``web:`` section in your
configuration file. The available options are:

- **host**: The server hostname. Set this to 0.0.0.0 to bind to all interfaces.
  Default: Bind to 127.0.0.1.
- **port**: The server port.
  Default: 8337.
- **cors**: The CORS allowed origin (see :ref:`web-cors`, below).
  Default: CORS is disabled.
- **cors_supports_credentials**: Support credentials when using CORS (see :ref:`web-cors`, below).
  Default: CORS_SUPPORTS_CREDENTIALS is disabled.
- **reverse_proxy**: If true, enable reverse proxy support (see
  :ref:`reverse-proxy`, below).
  Default: false.
- **include_paths**: If true, includes paths in item objects.
  Default: false.
- **readonly**: If true, DELETE and PATCH operations are not allowed. Only GET is permitted.
  Default: true.

Implementation
--------------

The Web backend is built using a simple REST+JSON API with the excellent
`Flask`_ library. The frontend is a single-page application written with
`Backbone.js`_. This allows future non-Web clients to use the same backend API.


.. _Backbone.js: https://backbonejs.org

Eventually, to make the Web player really viable, we should use a Flash fallback
for unsupported formats/browsers. There are a number of options for this:

* `audio.js`_
* `html5media`_
* `MediaElement.js`_

.. _audio.js: https://kolber.github.io/audiojs/
.. _html5media: https://html5media.info/
.. _MediaElement.js: https://www.mediaelementjs.com/

.. _web-cors:

Cross-Origin Resource Sharing (CORS)
------------------------------------

The ``web`` plugin's API can be used as a backend for an in-browser client. By
default, browsers will only allow access from clients running on the same
server as the API. (You will get an arcane error about ``XMLHttpRequest``
otherwise.) A technology called `CORS`_ lets you relax this restriction.

If you want to use an in-browser client hosted elsewhere (or running from a
different server on your machine), set the ``cors`` configuration option to
the "origin" (protocol, host, and optional port number) where the client is
served. Or set it to ``'*'`` to enable access from all origins. Note that there
are security implications if you set the origin to ``'*'``, so please research
this before using it.

If the ``web`` server is behind a proxy that uses credentials, you might want
to set the ``cors_supports_credentials`` configuration option to true to let
in-browser clients log in.

For example::

    web:
        host: 0.0.0.0
        cors: 'http://example.com'

.. _CORS: https://en.wikipedia.org/wiki/Cross-origin_resource_sharing
.. _reverse-proxy:

Reverse Proxy Support
---------------------

When the server is running behind a reverse proxy, you can tell the plugin to
respect forwarded headers. Specifically, this can help when you host the
plugin at a base URL other than the root ``/`` or when you use the proxy to
handle secure connections. Enable the ``reverse_proxy`` configuration option
if you do this.

Technically, this option lets the proxy provide ``X-Script-Name`` and
``X-Scheme`` HTTP headers to control the plugin's the ``SCRIPT_NAME`` and its
``wsgi.url_scheme`` parameter.

Here's a sample `Nginx`_ configuration that serves the web plugin under the
/beets directory::

    location /beets {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Scheme $scheme;
        proxy_set_header X-Script-Name /beets;
    }

.. _Nginx: https://www.nginx.com

JSON API
--------

``GET /item/``
++++++++++++++

Responds with a list of all tracks in the beets library. ::

    {
      "items": [
        {
          "id": 6,
          "title": "A Song",
          ...
        }, {
          "id": 12,
          "title": "Another Song",
          ...
        }
        ...
      ]
    }


``GET /item/6``
+++++++++++++++

Looks for an item with id *6* in the beets library and responds with its JSON
representation. ::

    {
      "id": 6,
      "title": "A Song",
      ...
    }

If there is no item with that id responds with a *404* status
code.

``DELETE /item/6``
++++++++++++++++++

Removes the item with id *6* from the beets library. If the *?delete* query string is included,
the matching file will be deleted from disk.

Only allowed if ``readonly`` configuration option is set to ``no``.

``PATCH /item/6``
++++++++++++++++++

Updates the item with id *6* and write the changes to the music file. The body should be a JSON object
containing the changes to the object.

Returns the updated JSON representation. ::

    {
      "id": 6,
      "title": "A Song",
      ...
    }

Only allowed if ``readonly`` configuration option is set to ``no``.

``GET /item/6,12,13``
+++++++++++++++++++++

Response with a list of tracks with the ids *6*, *12* and *13*.  The format of
the response is the same as for `GET /item/`_. It is *not guaranteed* that the
response includes all the items requested. If a track is not found it is silently
dropped from the response.

This endpoint also supports *DELETE* and *PATCH* methods as above, to operate on all
items of the list.

``GET /item/path/...``
++++++++++++++++++++++

Look for an item at the given absolute path on the server. If it corresponds to
a track, return the track in the same format as ``/item/*``.

If the server runs UNIX, you'll need to include an extra leading slash:
``http://localhost:8337/item/path//Users/beets/Music/Foo/Bar/Baz.mp3``


``GET /item/query/querystring``
+++++++++++++++++++++++++++++++

Returns a list of tracks matching the query. The *querystring* must be a
valid query as described in :doc:`/reference/query`. ::

    {
      "results": [
        { "id" : 6,  "title": "A Song" },
        { "id" : 12, "title": "Another Song" }
      ]
    }

Path elements are joined as parts of a query. For example,
``/item/query/foo/bar`` will be converted to the query ``foo,bar``.
To specify literal path separators in a query, use a backslash instead of a
slash.

This endpoint also supports *DELETE* and *PATCH* methods as above, to operate on all
items returned by the query.

``GET /item/6/file``
++++++++++++++++++++

Sends the  media file for the track. If the item or its corresponding file do
not exist a *404* status code is returned.


Albums
++++++

For albums, the following endpoints are provided:

* ``GET /album/``

* ``GET /album/5``

* ``GET /album/5/art``

* ``DELETE /album/5``

* ``GET /album/5,7``

* ``DELETE /album/5,7``

* ``GET /album/query/querystring``

* ``DELETE /album/query/querystring``

The interface and response format is similar to the item API, except replacing
the encapsulation key ``"items"`` with ``"albums"`` when requesting ``/album/``
or ``/album/5,7``. In addition we can request the cover art of an album with
``GET /album/5/art``.
You can also add the '?expand' flag to get the individual items of an album.

``DELETE`` is only allowed if ``readonly`` configuration option is set to ``no``.

``GET /stats``
++++++++++++++

Responds with the number of tracks and albums in the database. ::

    {
      "items": 5,
      "albums": 3
    }

.. _Flask: https://flask.palletsprojects.com/en/1.1.x/
