# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2014 Edgewall Software
# Copyright (C) 2007 Christian Boos <cboos@edgewall.org>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

"""Inserts the current time (in seconds) into the wiki page."""

revision = "$Rev$"
url = "$URL$"

from datetime import datetime

from genshi.builder import tag
from trac.util.datefmt import format_datetime, utc
from trac.wiki.macros import WikiMacroBase


class TimestampMacro(WikiMacroBase):
    _description = "Inserts the current time (in seconds) into the wiki page."

    def expand_macro(self, formatter, name, content, args=None):
        t = datetime.now(utc)
        return tag.strong(format_datetime(t, '%c'))
