# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2019 Edgewall Software
# Copyright (C) 2007 Christian Boos <cboos@edgewall.org>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.

"""Inserts the current time (in seconds) into the wiki page."""

from trac.util.datefmt import datetime_now, format_datetime, utc
from trac.util.html import tag
from trac.wiki.macros import WikiMacroBase

revision = "$Rev$"
url = "$URL$"


class TimestampMacro(WikiMacroBase):
    _description = "Inserts the current time (in seconds) into the wiki page."

    def expand_macro(self, formatter, name, content, args=None):
        t = datetime_now(utc)
        return tag.strong(format_datetime(t, '%c'))
