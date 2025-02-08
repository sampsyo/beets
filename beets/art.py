# This file is part of beets.
# Copyright 2016, Adrian Sampson.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

"""High-level utilities for manipulating image files associated with
music and items' embedded album art.
"""

import os
from tempfile import NamedTemporaryFile

import mediafile

from beets.util import bytestring_path, displayable_path, syspath
from beets.util.artresizer import ArtResizer


def mediafile_image(image_path, maxwidth=None):
    """Return a `mediafile.Image` object for the path."""

    with open(syspath(image_path), "rb") as f:
        data = f.read()
    return mediafile.Image(data, type=mediafile.ImageType.front)


def get_art(log, item):
    # Extract the art.
    try:
        mf = mediafile.MediaFile(syspath(item.path))
    except mediafile.UnreadableFileError as exc:
        log.warning(
            "Could not extract art from {0}: {1}",
            displayable_path(item.path),
            exc,
        )
        return

    return mf.art


def embed_item(
    log,
    item,
    imagepath,
    maxwidth=None,
    itempath=None,
    compare_threshold=0,
    ifempty=False,
    as_album=False,
    id3v23=None,
    quality=0,
):
    """Embed an image into the item's media file."""
    # Conditions.
    if compare_threshold:
        is_similar = check_art_similarity(
            log, item, imagepath, compare_threshold
        )
        if is_similar is None:
            log.warning("Error while checking art similarity; skipping.")
            return
        elif not is_similar:
            log.info("Image not similar; skipping.")
            return

    if ifempty and get_art(log, item):
        log.info("media file already contained art")
        return

    # Filters.
    if maxwidth and not as_album:
        imagepath = resize_image(log, imagepath, maxwidth, quality)

    # Get the `Image` object from the file.
    try:
        log.debug("embedding {0}", displayable_path(imagepath))
        image = mediafile_image(imagepath, maxwidth)
    except OSError as exc:
        log.warning("could not read image file: {0}", exc)
        return

    # Make sure the image kind is safe (some formats only support PNG
    # and JPEG).
    if image.mime_type not in ("image/jpeg", "image/png"):
        log.info("not embedding image of unsupported type: {}", image.mime_type)
        return

    item.try_write(path=itempath, tags={"images": [image]}, id3v23=id3v23)


def embed_album(
    log,
    album,
    maxwidth=None,
    quiet=False,
    compare_threshold=0,
    ifempty=False,
    quality=0,
):
    """Embed album art into all of the album's items."""
    imagepath = album.artpath
    if not imagepath:
        log.info("No album art present for {0}", album)
        return
    if not os.path.isfile(syspath(imagepath)):
        log.info(
            "Album art not found at {0} for {1}",
            displayable_path(imagepath),
            album,
        )
        return
    if maxwidth:
        imagepath = resize_image(log, imagepath, maxwidth, quality)

    log.info("Embedding album art into {0}", album)

    for item in album.items():
        embed_item(
            log,
            item,
            imagepath,
            maxwidth,
            None,
            compare_threshold,
            ifempty,
            as_album=True,
            quality=quality,
        )


def resize_image(log, imagepath, maxwidth, quality):
    """Returns path to an image resized to maxwidth and encoded with the
    specified quality level.
    """
    log.debug(
        "Resizing album art to {0} pixels wide and encoding at quality \
              level {1}",
        maxwidth,
        quality,
    )
    imagepath = ArtResizer.shared.resize(
        maxwidth, syspath(imagepath), quality=quality
    )
    return imagepath


def check_art_similarity(
    log,
    item,
    imagepath,
    compare_threshold,
    artresizer=None,
):
    """A boolean indicating if an image is similar to embedded item art.

    If no embedded art exists, always return `True`. If the comparison fails
    for some reason, the return value is `None`.

    This must only be called if `ArtResizer.shared.can_compare` is `True`.
    """
    with NamedTemporaryFile(delete=True) as f:
        art = extract(log, f.name, item)

        if not art:
            return True

        if artresizer is None:
            artresizer = ArtResizer.shared

        return artresizer.compare(art, imagepath, compare_threshold)


def extract(log, outpath, item):
    art = get_art(log, item)
    outpath = bytestring_path(outpath)
    if not art:
        log.info("No album art present in {0}, skipping.", item)
        return

    # Add an extension to the filename.
    ext = mediafile.image_extension(art)
    if not ext:
        log.warning("Unknown image type in {0}.", displayable_path(item.path))
        return
    outpath += bytestring_path("." + ext)

    log.info(
        "Extracting album art from: {0} to: {1}",
        item,
        displayable_path(outpath),
    )
    with open(syspath(outpath), "wb") as f:
        f.write(art)
    return outpath


def extract_first(log, outpath, items):
    for item in items:
        real_path = extract(log, outpath, item)
        if real_path:
            return real_path


def clear(log, lib, query):
    items = lib.items(query)
    log.info("Clearing album art from {0} items", len(items))
    for item in items:
        log.debug("Clearing art for {0}", item)
        item.try_write(tags={"images": None})
