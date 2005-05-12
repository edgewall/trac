# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004-2005 Edgewall Software
# Copyright (C) 2004 Daniel Lundin <daniel@edgewall.com>
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
# Author: Daniel Lundin <daniel@edgewall.com>
#         Christopher Lenz <cmlenz@gmx.de>
#

from trac.core import *

__all__ = ['get_mimetype', 'is_binary', 'Mimeview']

MIME_MAP = {
    'css':'text/css',
    'html':'text/html',
    'txt':'text/plain', 'TXT':'text/plain', 'text':'text/plain',
    'README':'text/plain', 'INSTALL':'text/plain', 
    'AUTHORS':'text/plain', 'COPYING':'text/plain', 
    'ChangeLog':'text/plain', 'RELEASE':'text/plain', 
    'ada':'text/x-ada',
    'asm':'text/x-asm',
    'asp':'text/x-asp',
    'awk':'text/x-awk',
    'c':'text/x-csrc',
    'csh':'application/x-csh',
    'diff':'text/x-diff', 'patch':'text/x-diff',
    'e':'text/x-eiffel',
    'el':'text/x-elisp',
    'f':'text/x-fortran',
    'h':'text/x-chdr',
    'cc':'text/x-c++src', 'cpp':'text/x-c++src', 'CC':'text/x-c++src',
    'hh':'text/x-c++hdr', 'HH':'text/x-c++hdr',  'hpp':'text/x-c++hdr',
    'hs':'text/x-haskell',
    'ico':'image/x-icon',
    'idl':'text/x-idl',
    'inf':'text/x-inf',
    'java':'text/x-java',
    'js':'text/x-javascript',
    'ksh':'text/x-ksh',
    'm':'text/x-objc',
    'm4':'text/x-m4',
    'make':'text/x-makefile', 'mk':'text/x-makefile', 'Makefile':'text/x-makefile',
    'mail':'text/x-mail',
    'pas':'text/x-pascal',
    'pl':'text/x-perl', 'pm':'text/x-perl', 'PL':'text/x-perl', 'perl':'text/x-perl',
    'php':'text/x-php', 'php4':'text/x-php', 'php3':'text/x-php',
    'ps':'application/postscript',
    'psp':'text/x-psp',
    'py':'text/x-python', 'python':'text/x-python',
    'pyx':'text/x-pyrex',
    'nroff':'application/x-troff', 'roff':'application/x-troff', 'troff':'application/x-troff',
    'rb':'text/x-ruby', 'ruby':'text/x-ruby',
    'rfc':'text/x-rfc',
    'rst': 'text/x-rst',
    'scm':'text/x-scheme',
    'sh':'application/x-sh',
    'sql':'text/x-sql',
    'svg':'image/svg+xml',
    'tcl':'text/x-tcl',
    'tex':'text/x-tex',
    'txtl': 'text/x-textile', 'textile': 'text/x-textile',
    'vba':'text/x-vba',
    'bas':'text/x-vba',
    'v':'text/x-verilog', 'verilog':'text/x-verilog',
    'vhd':'text/x-vhdl',
    'vrml':'model/vrml',
    'wrl':'model/vrml',
    'xml':'text/xml',
    'xs':'text/x-csrc',
    'xsl':'text/xsl',
    'zsh':'text/x-zsh',
    'barf':'application/x-test',
}

def get_mimetype(filename):
    try:
        i = filename.rfind('.')
        suffix = filename[i+1:]
        return MIME_MAP[suffix]
    except KeyError:
        import mimetypes
        return mimetypes.guess_type(filename)[0]
    except:
        return None

def is_binary(str):
    """
    Try to detect content by checking the first thousand bytes for zeroes.
    """
    for i in range(0, min(len(str), 1000)):
        if str[i] == '\0':
            return True
    return False


class IHTMLPreviewRenderer(Interface):
    """
    Extension point interface for components that add HTML renderers of specific
    content types to the `Mimeview` component.
    """

    def get_quality_ratio(mimetype):
        """
        Return the level of support this renderer provides for the content of
        the specified MIME type. The return value must be a number between 0
        and 9, where 0 means no support and 9 means "perfect" support.
        """

    def render(req, mimetype, content, filename=None, rev=None):
        """
        Render an XHTML preview of the given content of the specified MIME type,
        and return the generated XHTML text as a string.

        The `filename` and `rev` parameters are provided for renderers that
        embed objects (using <object> or <img>) instead of included the content
        inline.
        """


class Mimeview(Component):
    """A generic class to prettify data, typically source code."""

    renderers = ExtensionPoint(IHTMLPreviewRenderer)

    def render(self, req, mimetype, content, filename=None, rev=None):
        if not content:
            return ''

        if filename and not mimetype:
            mimetype = get_mimetype(filename)

        candidates = []
        for renderer in self.renderers:
            qr = renderer.get_quality_ratio(mimetype)
            if qr > 0:
                candidates.append((qr, renderer))
        candidates.sort(lambda x,y: cmp(y[0], x[0]))

        for qr, renderer in candidates:
            try:
                self.log.debug('Trying to render HTML preview using %s'
                               % renderer.__class__.__name__)
                return renderer.render(req, mimetype, content, filename, rev)
            except Exception, e:
                self.log.warning('HTML preview using %s failed (%s)'
                                 % (renderer, e))

        return None


class PlainTextRenderer(Component):
    """
    HTML preview renderer for plain text, and fallback for any kind of text for
    which no more specific renderer is available.
    """

    implements(IHTMLPreviewRenderer)

    def get_quality_ratio(self, mimetype):
        return 1

    def render(self, req, mimetype, content, filename=None, rev=None):
        if is_binary(content):
            self.env.log.debug("Binary data; no preview available")
            return ''

        self.env.log.debug("Using default plain text mimeviewer")
        from trac.util import escape
        return '<pre class="code-block">' + escape(content) + '</pre>'


class ImageRenderer(Component):
    """
    Inline image display.
    """

    implements(IHTMLPreviewRenderer)

    def get_quality_ratio(self, mimetype):
        if mimetype.startswith('image/'):
            return 8
        return 0

    def render(self, req, mimetype, content, filename=None, rev=None):
        src = '?'
        if rev:
            src += 'rev=%d&' % rev
        src += 'format=raw'
        return '<div class="image-file"><img src="%s" alt="" /></div>' % src


class WikiTextRenderer(Component):
    """
    Render files containing Trac's own Wiki formatting markup.
    """

    implements(IHTMLPreviewRenderer)

    def get_quality_ratio(self, mimetype):
        if mimetype in ('text/x-trac-wiki', 'application/x-trac-wiki'):
            return 8
        return 0

    def render(self, req, mimetype, content, filename=None, rev=None):
        from trac.wiki import wiki_to_html
        return wiki_to_html(content, self.env, req)
