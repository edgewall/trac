# -*- coding: iso8859-1 -*-
"""
Displays a list of all installed Wiki macros, including documentation if
available.
"""

from trac.util import escape
from trac.WikiFormatter import wiki_to_html

import os
import inspect
import imp
import StringIO

def execute(hdf, args, env):

    def get_macros(dir):
        macros = []
        for file in [f for f in os.listdir(dir)
                     if f.lower().endswith('.py') and not f.startswith('__')]:
            try:
                module = imp.load_source(file[:-3], os.path.join(dir, file))
                macros.append(module)
            except Exception:
                pass
        return macros

    macros = []
    import trac.wikimacros
    macros += get_macros(os.path.dirname(inspect.getfile(trac.wikimacros)))
    macros += get_macros(os.path.join(env.path, 'wiki-macros'))
    macros.sort(lambda a, b: cmp(a.__name__, b.__name__))

    buf = StringIO.StringIO()
    buf.write("<dl>")
    for macro in macros:
        buf.write("<dt><code>[[%s]]</code></dt>" % escape(macro.__name__))
        if macro.__doc__:
            buf.write("<dd><p style='white-space: pre'>%s</p></dd>"
                      % escape(inspect.getdoc(macro)))
    buf.write("</dl>")
    return buf.getvalue()

