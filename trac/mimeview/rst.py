# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2005 Edgewall Software
# Copyright (C) 2004 Oliver Rutherfurd
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Daniel Lundin
#         Oliver Rutherfurd (initial implementation)
#         Nuutti Kotivuori (role support)
#
# Trac support for reStructured Text, including a custom 'trac' directive
#
# 'trac' directive code by Oliver Rutherfurd.
#
# Inserts `reference` nodes for TracLinks into the document tree.

__docformat__ = 'reStructuredText'

from distutils.version import StrictVersion
import re

from trac.core import *
from trac.mimeview.api import IHTMLPreviewRenderer, content_to_unicode
from trac.web.href import Href
from trac.wiki.formatter import WikiProcessor
from trac.wiki import WikiSystem

WIKI_LINK = re.compile(r'(?:wiki:)?(.+)')
TICKET_LINK = re.compile(r'(?:#(\d+))|(?:ticket:(\d+))')
REPORT_LINK = re.compile(r'(?:{(\d+)})|(?:report:(\d+))')
CHANGESET_LINK = re.compile(r'(?:\[(\d+)\])|(?:changeset:(\d+))')
FILE_LINK = re.compile(r'(?:browser|repos|source):([^#]+)#?(.*)')

def _wikipage(href, args):
    return href.wiki(args[0])

def _ticket(href, args):
    return href.ticket(args[0])

def _report(href, args):
    return href.report(args[0])

def _changeset(href, args):
    return href.changeset(int(args[0]))

def _browser(href, args):
    path = args[0]
    rev = len(args) == 2 and args[1] or ''
    return href.browser(path, rev=rev)

# TracLink REs and callback functions
LINKS = [(TICKET_LINK, _ticket),
         (REPORT_LINK, _report),
         (CHANGESET_LINK, _changeset),
         (FILE_LINK, _browser),
         (WIKI_LINK, _wikipage)]

class ReStructuredTextRenderer(Component):
    """
    Renders plain text in reStructuredText format as HTML.
    """
    implements(IHTMLPreviewRenderer)

    def get_quality_ratio(self, mimetype):
        if mimetype == 'text/x-rst':
            return 8
        return 0

    def render(self, req, mimetype, content, filename=None, rev=None):
        try:
            from docutils import nodes
            from docutils.core import publish_string
            from docutils.parsers import rst
            from docutils import __version__
        except ImportError:
            raise TracError, 'Docutils not found'
        if StrictVersion(__version__) < StrictVersion('0.3.3'):
            raise TracError, 'Docutils version >= %s required, %s found' \
                             % ('0.3.3', __version__)

        def trac_get_reference(rawtext, link, text):
            for (pattern, function) in LINKS:
                m = pattern.match(link)
                if m:
                    g = filter(None, m.groups())
                    missing = 0
                    if not text:
                        text = g[0]
                    if pattern == WIKI_LINK:
                        pagename = re.search(r'^[^\#]+',g[0])
                        if not WikiSystem(self.env).has_page(pagename.group()):
                            missing = 1
                            text = text + "?"
                    uri = function(req.href, g)
                    reference = nodes.reference(rawtext, text)
                    reference['refuri']= uri
                    if missing:
                        reference.set_class('missing')
                    return reference
            return None

        def trac(name, arguments, options, content, lineno,
                 content_offset, block_text, state, state_machine):
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
            link = arguments[0]
            if len(arguments) == 2:
                text = arguments[1]
            else:
                text = None
            reference = trac_get_reference(block_text, link, text)
            if reference:
                p = nodes.paragraph()
                p += reference
                return p
            # didn't find a match (invalid TracLink),
            # report a warning
            warning = state_machine.reporter.warning(
                    '%s is not a valid TracLink' % (arguments[0]),
                    nodes.literal_block(block_text, block_text),
                    line=lineno)
            return [warning]

        def trac_role(name, rawtext, text, lineno, inliner, options={},
                      content=[]):
            args  = text.split(" ",1)
            link = args[0]
            if len(args)==2:
                text = args[1]
            else:
                text = None
            reference = trac_get_reference(rawtext, link, text)
            if reference:
                return [reference], []
            warning = nodes.warning(None, nodes.literal_block(text,
                'WARNING: %s is not a valid TracLink' % rawtext))
            return warning, []

        # 1 required arg, 1 optional arg, spaces allowed in last arg
        trac.arguments = (1,1,1)
        trac.options = None
        trac.content = None
        rst.directives.register_directive('trac', trac)
        rst.roles.register_local_role('trac', trac_role)

        # The code_block could is taken from the leo plugin rst2
        def code_formatter(language, text):
            processor = WikiProcessor(self.env, language)
            html = processor.process(req, text)
            raw = nodes.raw('', html, format='html')
            return raw
        
        def code_role(name, rawtext, text, lineno, inliner, options={},
                      content=[]):
            language = options.get('language')
            if not language:
                args  = text.split(':', 1)
                language = args[0]
                if len(args) == 2:
                    text = args[1]
                else:
                    text = ''
            reference = code_formatter(language, text)
            return [reference], []
        
        def code_block(name, arguments, options, content, lineno,
                       content_offset, block_text, state, state_machine):
            """
            Create a code-block directive for docutils.

            Usage: .. code-block:: language

            If the language can be syntax highlighted it will be.
            """
            language = arguments[0]
            text = '\n'.join(content)        
            reference = code_formatter(language, text)
            return [reference]

        # These are documented
        # at http://docutils.sourceforge.net/spec/howto/rst-directives.html.
        code_block.arguments = (
            1, # Number of required arguments.
            0, # Number of optional arguments.
            0) # True if final argument may contain whitespace.
    
        # A mapping from option name to conversion function.
        code_role.options = code_block.options = {
            'language' :
            rst.directives.unchanged # Return the text argument, unchanged
        }
        code_block.content = 1 # True if content is allowed.
        # Register the directive with docutils.
        rst.directives.register_directive('code-block', code_block)
        rst.roles.register_local_role('code-block', code_role)

        _inliner = rst.states.Inliner()
        _parser = rst.Parser(inliner=_inliner)
        content = content_to_unicode(self.env, content, mimetype)
        content = content.encode('utf-8')
        html = publish_string(content, writer_name='html', parser=_parser,
                              settings_overrides={'halt_level': 6})
        html = html.decode('utf-8')
        return html[html.find('<body>') + 6:html.find('</body>')].strip()
