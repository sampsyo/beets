# This file is part of beets.
# Copyright 2016, Heinz Wiesinger.
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

"""Synchronize information from amarok's library via dbus"""

from datetime import datetime
from os.path import basename
from time import mktime
from xml.sax.saxutils import quoteattr

from beets.dbcore import types
from beets.library import DateType
from beets.util import displayable_path
from beetsplug.metasync import MetaSource


def import_dbus():
    try:
        return __import__("dbus")
    except ImportError:
        return None


dbus = import_dbus()


class Amarok(MetaSource):
    item_types = {
        "amarok_rating": types.INTEGER,
        "amarok_score": types.FLOAT,
        "amarok_uid": types.STRING,
        "amarok_playcount": types.INTEGER,
        "amarok_firstplayed": DateType(),
        "amarok_lastplayed": DateType(),
    }

    query_xml = '<query version="1.0"> \
                    <filters> \
                        <and><include field="filename" value=%s /></and> \
                    </filters> \
                </query>'

    def __init__(self, config, log):
        super().__init__(config, log)

        if not dbus:
            raise ImportError("failed to import dbus")

        self.collection = dbus.SessionBus().get_object(
            "org.kde.amarok", "/Collection"
        )

    def sync_from_source(self, item):
        path = displayable_path(item.path)

        # amarok unfortunately doesn't allow searching for the full path, only
        # for the patch relative to the mount point. But the full path is part
        # of the result set. So query for the filename and then try to match
        # the correct item from the results we get back
        results = self.collection.Query(
            self.query_xml % quoteattr(basename(path))
        )
        for result in results:
            if result["xesam:url"] != path:
                continue

            item.amarok_rating = result["xesam:userRating"]
            item.amarok_score = result["xesam:autoRating"]
            item.amarok_playcount = result["xesam:useCount"]
            item.amarok_uid = result["xesam:id"].replace(
                "amarok-sqltrackuid://", ""
            )

            if result["xesam:firstUsed"][0][0] != 0:
                # These dates are stored as timestamps in amarok's db, but
                # exposed over dbus as fixed integers in the current timezone.
                first_played = datetime(
                    result["xesam:firstUsed"][0][0],
                    result["xesam:firstUsed"][0][1],
                    result["xesam:firstUsed"][0][2],
                    result["xesam:firstUsed"][1][0],
                    result["xesam:firstUsed"][1][1],
                    result["xesam:firstUsed"][1][2],
                )

                if result["xesam:lastUsed"][0][0] != 0:
                    last_played = datetime(
                        result["xesam:lastUsed"][0][0],
                        result["xesam:lastUsed"][0][1],
                        result["xesam:lastUsed"][0][2],
                        result["xesam:lastUsed"][1][0],
                        result["xesam:lastUsed"][1][1],
                        result["xesam:lastUsed"][1][2],
                    )
                else:
                    last_played = first_played

                item.amarok_firstplayed = mktime(first_played.timetuple())
                item.amarok_lastplayed = mktime(last_played.timetuple())
