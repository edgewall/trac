# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2020 Edgewall Software
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

"""Example macro."""

from trac.util.translation import cleandoc_
from trac.wiki.macros import WikiMacroBase

revision = "$Rev$"
url = "$URL$"


class HelloWorldMacro(WikiMacroBase):
    _description = cleandoc_(
    """Simple HelloWorld macro.

    Note that the name of the class is meaningful:
     - it must end with "Macro"
     - what comes before "Macro" ends up being the macro name

    The documentation of the class (i.e. what you're reading)
    will become the documentation of the macro, as shown by
    the !MacroList macro (usually used in the WikiMacros page).
    """)

    def expand_macro(self, formatter, name, content, args=None):
        """Return some output that will be displayed in the Wiki content.

        `name` is the actual name of the macro (no surprise, here it'll be
        `'HelloWorld'`),
        `content` is the text enclosed in parenthesis at the call of the
          macro. Note that if there are ''no'' parenthesis (like in, e.g.
          [[HelloWorld]]), then `content` is `None`.
        `args` will contain a dictionary of arguments when called using the
          Wiki processor syntax and will be `None` if called using the
          macro syntax.
        """
        return 'Hello World, content = ' + str(content)

    # Note that there's no need to HTML escape the returned data, as
    # the template engine (Jinja2) will do it for us.  To prevent
    # escaping, return a Markup instance or use the tag builder API
    # from trac.util.html.
