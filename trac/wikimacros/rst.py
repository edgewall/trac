# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004 Edgewall Software
# Copyright (C) 2004 Oliver Rutherford
#
# Trac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Trac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Daniel Lundin
#         Oliver Rutherford
#
# Trac support for reStructured Text, including a custom 'trac' directive
#
# 'trac' directive code by Oliver Rutherford.
#
# Inserts `reference` nodes for TracLinks into the document tree.

import re

from docutils import nodes
from docutils.core import publish_string
from docutils.parsers.rst import directives

__docformat__ = 'reStructuredText'

TICKET_LINK = re.compile(r'(?:#(\d+))|(?:ticket:(\d+))')
REPORT_LINK = re.compile(r'(?:{(\d+)})|(?:report:(\d+))')
CHANGESET_LINK = re.compile(r'(?:\[(\d+)\])|(?:changeset:(\d+))')
FILE_LINK = re.compile(r'(?:browser|repos|source):([^#]+)#?(.*)')

def _ticket(match,arguments):
    """_ticket(match,arguments) -> (uri,text)"""
    template = 'ticket/%s'
    ticket = int(filter(None,match.groups())[0])
    text = arguments[int(len(arguments) == 2)]
    return (template % (ticket,), text)

def _report(match,arguments):
    """_report(match,arguments) -> (uri,text)"""
    template = 'report/%d'
    report = int(filter(None,match.groups())[0])
    text = arguments[int(len(arguments) == 2)]
    return (template % (report,), text)

def _changeset(match,arguments):
    """_changeset(match,arguments) -> (uri,text)"""
    template = 'changeset/%d'
    changeset = int(filter(None,match.groups())[0])
    text = arguments[int(len(arguments) == 2)]
    return (template % (changeset,), text)

def _browser(match,arguments):
    """_browser(match,arguments) -> (uri,text)"""
    template = 'browser/%s'
    matches = filter(None,match.groups())
    if len(matches) == 2:
        path,revision = matches
    else:
        path,revision = matches[0],''
    uri = template % path
    if revision:
        uri += '?rev=%s' % revision
    text = arguments[int(len(arguments) == 2)]
    return (uri, text)

# TracLink REs and callback functions
LINKS = [
    (TICKET_LINK, _ticket),
    (REPORT_LINK, _report),
    (CHANGESET_LINK, _changeset),
    (FILE_LINK, _browser),
]

def trac(name,arguments,options,content,lineno,
         content_offset,block_text,state,state_machine):
    """Inserts a `reference` node into the document 
    for a given `TracLink`_, based on the content 
    of the arguments.

    Usage::

      .. trac:: target [text]

    ``target`` may be one of the following:

      * For tickets: ``#1`` or ``ticket:1``
      * For reports: ``{1}`` or ``report:1``
      * For changesets: ``[1]`` or ``changeset:1``
      * For files: ``source:trunk/COPYING``

    ``[text]`` is optional.  If not given, ``target`` is
    used as the reference text.

    .. _TracLink: http://projects.edgewall.com/trac/wiki/TracLinks
    """

    for (pattern, function) in LINKS:
        m = pattern.match(arguments[0])
        if m:
            uri,text = function(m,arguments)
            reference = nodes.reference(block_text,text)
            reference['refuri']= uri
            return reference

    # didn't find a match (invalid TracLink), 
    # report a warning
    warning = state_machine.reporter.warning(
            '%s is not a valid TracLink' % (arguments[0]),
            nodes.literal_block(block_text, block_text),
            line=lineno)
    return [warning]

trac.arguments = (1,1,1)    # 1 required arg, 1 optional arg, spaces allowed in last arg
trac.options = None
trac.content = None
directives.register_directive('trac', trac)

def execute(hdf, text):
    html = publish_string(text, writer_name = 'html')
    return html[html.find('<body>')+6:html.find('</body>')].strip()

# A naive test
if __name__ == '__main__':
    __test = """
===============
Trac Link Tests
===============

This document is for testing the ``..trac::`` directive.

tickets
=======

``.. trac:: #1``:
	.. trac:: #1
``.. trac:: #1 ticket one``:
	.. trac:: #1 ticket one
``.. trac:: ticket:1``:
	.. trac:: ticket:1
``.. trac:: ticket:1 ticket one``:
	.. trac:: ticket:1 ticket one

reports
=======

``.. trac:: {1}``:
	.. trac:: {1}
``.. trac:: {1} report one``:
	.. trac:: {1} report one
``.. trac:: report:1``:
	.. trac:: report:1
``.. trac:: report:1 report one``:
	.. trac:: report:1 report one

changesets
==========

``.. trac:: [42]``: 
	.. trac:: [42]
``.. trac:: [42] changeset 42``: 
	.. trac:: [42] changeset 42
``.. trac:: changeset:42``: 
	.. trac:: changeset:42
``.. trac:: changeset:42 changeset 42``: 
	.. trac:: changeset:42 changeset 42
``.. trac:: foo``: 
	.. trac:: foo

files
=====

``.. trac:: browser:foo/hoo``:
	.. trac:: browser:foo/hoo
``.. trac:: repos:foo/hoo foo/hoo``:
	.. trac:: repos:foo/hoo foo/hoo
``.. trac:: source:foo/hoo hoo in foo``:
	.. trac:: source:foo/hoo hoo in foo
``.. trac:: browser:foo/hoo#latest latest of foo/hoo``:
	.. trac:: browser:foo/hoo#latest latest of foo/hoo
``.. trac:: repos:foo/hoo#42 foo/hoo in rev 42``:
	.. trac:: repos:foo/hoo#42 foo/hoo in rev 42
"""

    html = publish_string(__test, writer_name = 'html')
    print html
    

