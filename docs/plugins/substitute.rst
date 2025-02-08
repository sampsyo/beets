Substitute Plugin
=================

The ``substitute`` plugin lets you easily substitute values in your templates and
path formats. Specifically, it is intended to let you *canonicalize* names
such as artists: For example, perhaps you want albums from The Jimi Hendrix
Experience to be sorted into the same folder as solo Hendrix albums.

This plugin is intended as a replacement for the ``rewrite`` plugin. While
the ``rewrite`` plugin modifies the metadata, this plugin does not.

Enable the ``substitute`` plugin (see :ref:`using-plugins`), then make a ``substitute:`` section in your config file to contain your rules.
Each rule consists of a case-insensitive regular expression pattern, and a
replacement string. For example, you might use:

.. code-block:: yaml

    substitute:
      .*jimi hendrix.*: Jimi Hendrix

The replacement can be an expression utilising the matched regex, allowing us
to create more general rules. Say for example, we want to sort all albums by
multiple artists into the directory of the first artist. We can thus capture
everything before the first ``,``, `` &`` or `` and``, and use this capture
group in the output, discarding the rest of the string.

.. code-block:: yaml

    substitute:
      ^(.*?)(,| &| and).*: \1

This would handle all the below cases in a single rule:

    Bob Dylan and The Band -> Bob Dylan
    Neil Young & Crazy Horse -> Neil Young
    James Yorkston, Nina Persson & The Second Hand Orchestra -> James Yorkston


To apply the substitution, you have to call the function ``%substitute{}`` in the paths section. For example:

.. code-block:: yaml

    paths:
        default: \%substitute{$albumartist}/$year - $album\%aunique{}/$track - $title
