# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2020 Edgewall Software
# Copyright (C) 2007 Christian Boos <cboos@edgewall.org>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.

"""Inserts the current time (in seconds) into the wiki page."""

revision = "$Rev$"
url = "$URL$"

#
# The following shows the code for macro, old-style.
#
# The `execute` function serves no purpose other than to illustrate
# the example, it will not be used anymore.
#
# ---- (ignore in your own macro) ----
# --
import time # Trac before version 0.11 was using `time` module

def execute(hdf, txt, env):
    t = time.localtime()
    return "<b>%s</b>" % time.strftime('%c', t)
# --
# ---- (ignore in your own macro) ----


#
# The following is the converted new-style macro
#
# ---- (reuse for your own macro) ----
# --
from datetime import datetime
# Note: since Trac 0.11, datetime objects are used internally

from genshi.builder import tag

from trac.util.datefmt import datetime_now, format_datetime, utc
from trac.wiki.macros import WikiMacroBase

class TimestampMacro(WikiMacroBase):
    _description = "Inserts the current time (in seconds) into the wiki page."

    def expand_macro(self, formatter, name, content, args=None):
        t = datetime_now(utc)
        return tag.strong(format_datetime(t, '%c'))
# --
# ---- (reuse for your own macro) ----
