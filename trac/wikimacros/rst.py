# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004 Edgewall Software
# Copyright (C) 2004 Oliver Rutherfurd
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
#         Oliver Rutherfurd
#
# Trac support for reStructured Text, including a custom 'trac' directive
#
# 'trac' directive code by Oliver Rutherfurd.
#
# Inserts `reference` nodes for TracLinks into the document tree.

import re

from docutils import nodes
from docutils.core import publish_string
from docutils.parsers.rst import directives

from trac.Href import Href

__docformat__ = 'reStructuredText'

WIKI_LINK = re.compile(r'(?:wiki:)?(?P<w>(^|(?<=[^A-Za-z]))[!]?[A-Z][a-z/]+(?:[A-Z][a-z/]+)+)')
TICKET_LINK = re.compile(r'(?:#(\d+))|(?:ticket:(\d+))')
REPORT_LINK = re.compile(r'(?:{(\d+)})|(?:report:(\d+))')
CHANGESET_LINK = re.compile(r'(?:\[(\d+)\])|(?:changeset:(\d+))')
FILE_LINK = re.compile(r'(?:browser|repos|source):([^#]+)#?(.*)')

def _wikipage(href, match, arguments):
    """_wiki(match,arguments) -> (uri,text)"""
    template = '../wiki/%s'
    page = filter(None,match.groups())[0]
    text = arguments[int(len(arguments) == 2)]
    uri = href.wiki(page)
    return (uri, text)

def _ticket(href, match, arguments):
    """_ticket(match,arguments) -> (uri,text)"""
    ticket = int(filter(None,match.groups())[0])
    text = arguments[int(len(arguments) == 2)]
    uri = href.ticket(ticket)
    return (uri, text)

def _report(href, match, arguments):
    """_report(match,arguments) -> (uri,text)"""
    report = int(filter(None,match.groups())[0])
    text = arguments[int(len(arguments) == 2)]
    uri = href.report(report)
    return (uri, text)

def _changeset(href, match, arguments):
    """_changeset(match,arguments) -> (uri,text)"""
    changeset = int(filter(None,match.groups())[0])
    text = arguments[int(len(arguments) == 2)]
    uri = href.changeset(changeset)
    return (uri, text)

def _browser(href, match, arguments):
    """_browser(match,arguments) -> (uri,text)"""
    matches = filter(None,match.groups())
    if len(matches) == 2:
        path,revision = matches
    else:
        path,revision = matches[0],''
    uri = href.browser(path, revision)
    text = arguments[int(len(arguments) == 2)]
    return (uri, text)

# TracLink REs and callback functions
LINKS = [(WIKI_LINK, _wikipage),
         (TICKET_LINK, _ticket),
         (REPORT_LINK, _report),
         (CHANGESET_LINK, _changeset),
         (FILE_LINK, _browser)]

def trac(href, name,arguments,options,content,lineno,
         content_offset,block_text,state,state_machine):
    """Inserts a `reference` node into the document 
    for a given `TracLink`_, based on the content 
    of the arguments.

    Usage::

      .. trac:: target [text]

    ``target`` may be one of the following:

      * For wiki: ``WikiName`` or ``wiki:WikiName``
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
            uri,text = function(href, m,arguments)
            reference = nodes.reference(block_text, text)
            reference['refuri']= uri
            return reference

    # didn't find a match (invalid TracLink), 
    # report a warning
    warning = state_machine.reporter.warning(
            '%s is not a valid TracLink' % (arguments[0]),
            nodes.literal_block(block_text, block_text),
            line=lineno)
    return [warning]

def execute(hdf, text, env, href): 
    def do_trac(name,arguments,options,content,lineno,
                content_offset,block_text,state,state_machine):
        return trac(href, name,arguments,options,content,lineno,
                    content_offset,block_text,state,state_machine)
    # 1 required arg, 1 optional arg, spaces allowed in last arg
    do_trac.arguments = (1,1,1)    
    do_trac.options = None
    do_trac.content = None
    directives.register_directive('trac', do_trac)

    html = publish_string(text, writer_name = 'html')
    return html[html.find('<body>')+6:html.find('</body>')].strip()
