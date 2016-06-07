# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2009 Edgewall Software
# Copyright (C) 2006 Matthew Good <matt@matt-good.net>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# Author: Matthew Good <matt@matt-good.net>

from __future__ import absolute_import

import os
import pygments
import re
from datetime import datetime
from pkg_resources import resource_filename
from pygments.formatters.html import HtmlFormatter
from pygments.lexers import get_all_lexers, get_lexer_by_name
from pygments.styles import get_all_styles, get_style_by_name

from trac.core import *
from trac.config import ListOption, Option
from trac.env import ISystemInfoProvider
from trac.mimeview.api import IHTMLPreviewRenderer, Mimeview
from trac.prefs import IPreferencePanelProvider
from trac.util import get_pkginfo
from trac.util.datefmt import http_date, localtz
from trac.util.translation import _
from trac.web.api import IRequestHandler, HTTPNotFound
from trac.web.chrome import add_notice, add_stylesheet

from genshi import QName, Stream
from genshi.core import Attrs, START, END, TEXT

__all__ = ['PygmentsRenderer']


class PygmentsRenderer(Component):
    """HTML renderer for syntax highlighting based on Pygments."""

    implements(ISystemInfoProvider, IHTMLPreviewRenderer,
               IPreferencePanelProvider, IRequestHandler)

    default_style = Option('mimeviewer', 'pygments_default_style', 'trac',
        """The default style to use for Pygments syntax highlighting.""")

    pygments_modes = ListOption('mimeviewer', 'pygments_modes',
        '', doc=
        """List of additional MIME types known by Pygments.

        For each, a tuple `mimetype:mode:quality` has to be
        specified, where `mimetype` is the MIME type,
        `mode` is the corresponding Pygments mode to be used
        for the conversion and `quality` is the quality ratio
        associated to this conversion. That can also be used
        to override the default quality ratio used by the
        Pygments render.""")

    expand_tabs = True
    returns_source = True

    QUALITY_RATIO = 7

    EXAMPLE = """<!DOCTYPE html>
<html lang="en">
  <head>
    <title>Hello, world!</title>
    <script>
      jQuery(document).ready(function($) {
        $("h1").fadeIn("slow");
      });
    </script>
  </head>
  <body>
    <h1>Hello, world!</h1>
  </body>
</html>"""

    def __init__(self):
        self._types = None

    # ISystemInfoProvider methods

    def get_system_info(self):
        version = get_pkginfo(pygments).get('version')
        # if installed from source, fallback to the hardcoded version info
        if not version and hasattr(pygments, '__version__'):
            version = pygments.__version__
        yield 'Pygments', version

    # IHTMLPreviewRenderer methods

    def get_extra_mimetypes(self):
        for lexname, aliases, _, mimetypes in get_all_lexers():
            for mimetype in mimetypes:
                yield mimetype, aliases

    def get_quality_ratio(self, mimetype):
        # Extend default MIME type to mode mappings with configured ones
        if self._types is None:
            self._init_types()
        try:
            return self._types[mimetype][1]
        except KeyError:
            return 0

    def render(self, context, mimetype, content, filename=None, rev=None):
        req = context.req
        if self._types is None:
            self._init_types()
        add_stylesheet(req, '/pygments/%s.css' %
                       req.session.get('pygments_style', self.default_style))
        try:
            if len(content) > 0:
                mimetype = mimetype.split(';', 1)[0]
                language = self._types[mimetype][0]
                return self._generate(language, content)
        except (KeyError, ValueError):
            raise Exception("No Pygments lexer found for mime-type '%s'."
                            % mimetype)

    # IPreferencePanelProvider methods

    def get_preference_panels(self, req):
        yield ('pygments', _('Syntax Highlighting'))

    def render_preference_panel(self, req, panel):
        styles = list(get_all_styles())

        if req.method == 'POST':
            style = req.args.get('style')
            if style and style in styles:
                req.session['pygments_style'] = style
                add_notice(req, _('Your preferences have been saved.'))
            req.redirect(req.href.prefs(panel or None))

        output = self._generate('html', self.EXAMPLE)
        return 'prefs_pygments.html', {
            'output': output,
            'selection': req.session.get('pygments_style', self.default_style),
            'styles': styles
        }

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'/pygments/([-\w]+)\.css', req.path_info)
        if match:
            req.args['style'] = match.group(1)
            return True

    def process_request(self, req):
        style = req.args['style']
        try:
            style_cls = get_style_by_name(style)
        except ValueError, e:
            raise HTTPNotFound(e)

        parts = style_cls.__module__.split('.')
        filename = resource_filename('.'.join(parts[:-1]), parts[-1] + '.py')
        mtime = datetime.fromtimestamp(os.path.getmtime(filename), localtz)
        last_modified = http_date(mtime)
        if last_modified == req.get_header('If-Modified-Since'):
            req.send_response(304)
            req.end_headers()
            return

        formatter = HtmlFormatter(style=style_cls)
        content = u'\n\n'.join([
            formatter.get_style_defs('div.code pre'),
            formatter.get_style_defs('table.code td')
        ]).encode('utf-8')

        req.send_response(200)
        req.send_header('Content-Type', 'text/css; charset=utf-8')
        req.send_header('Last-Modified', last_modified)
        req.send_header('Content-Length', len(content))
        req.write(content)

    # Internal methods

    def _init_types(self):
        self._types = {}
        for lexname, aliases, _, mimetypes in get_all_lexers():
            name = aliases[0] if aliases else lexname
            for mimetype in mimetypes:
                self._types[mimetype] = (name, self.QUALITY_RATIO)

        # Pygments < 1.4 doesn't know application/javascript
        if 'application/javascript' not in self._types:
            js_entry = self._types.get('text/javascript')
            if js_entry:
                self._types['application/javascript'] = js_entry

        self._types.update(
            Mimeview(self.env).configured_modes_mapping('pygments')
        )

    def _generate(self, language, content):
        lexer = get_lexer_by_name(language, stripnl=False)
        return GenshiHtmlFormatter().generate(lexer.get_tokens(content))


class GenshiHtmlFormatter(HtmlFormatter):
    """A Pygments formatter subclass that generates a Python stream instead
    of writing markup as strings to an output file.
    """

    def _chunk(self, tokens):
        """Groups tokens with the same CSS class in the token stream
        and yields them one by one, along with the CSS class, with the
        values chunked together."""

        last_class = None
        text = []
        for ttype, value in tokens:
            c = self._get_css_class(ttype)
            if c == 'n':
                c = ''
            if c == last_class:
                text.append(value)
                continue

            # If no value, leave the old <span> open.
            if value:
                yield last_class, u''.join(text)
                text = [value]
                last_class = c

        if text:
            yield last_class, u''.join(text)

    def generate(self, tokens):
        pos = (None, -1, -1)
        span = QName('span')
        class_ = QName('class')

        def _generate():
            for c, text in self._chunk(tokens):
                if c:
                    attrs = Attrs([(class_, c)])
                    yield START, (span, attrs), pos
                    yield TEXT, text, pos
                    yield END, span, pos
                else:
                    yield TEXT, text, pos
        return Stream(_generate())
