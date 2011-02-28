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

from trac.util.datefmt import format_datetime, utc
from trac.wiki.macros import WikiMacroBase

class TimestampMacro(WikiMacroBase):
    _description = "Inserts the current time (in seconds) into the wiki page."

    def expand_macro(self, formatter, name, args):
        t = datetime.now(utc)
        return tag.b(format_datetime(t, '%c'))
# --
# ---- (reuse for your own macro) ----
