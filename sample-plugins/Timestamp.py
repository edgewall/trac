"""Inserts the current time (in seconds) into the wiki page."""

import time

#
# The following shows the code for macro, old-style.
#
# The `execute` function serves no purpose other than to illustrate
# the example, it will not be used anymore.
#
# ---- (ignore in your own macro) ----
# --
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
from genshi.builder import tag

from trac.wiki.macros import WikiMacroBase

class TimestampMacro(WikiMacroBase):
    """Inserts the current time (in seconds) into the wiki page."""

    def render_macro(self, formatter, name, args):
        t = time.localtime()
        return tag.b(time.strftime('%c', t))
# --
# ---- (reuse for your own macro) ----
