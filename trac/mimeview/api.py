# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004-2005 Edgewall Software
# Copyright (C) 2004 Daniel Lundin <daniel@edgewall.com>
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
# Author: Daniel Lundin <daniel@edgewall.com>
#         Christopher Lenz <cmlenz@gmx.de>
#

from __future__ import generators
import re
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from trac.core import *
from trac.util import enum, escape

__all__ = ['get_charset', 'get_mimetype', 'is_binary', 'detect_unicode',
           'Mimeview']

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
    'cc':'text/x-c++src', 'CC':'text/x-c++src',
    'cpp':'text/x-c++src', 'C':'text/x-c++src',
    'hh':'text/x-c++hdr', 'HH':'text/x-c++hdr',
    'hpp':'text/x-c++hdr', 'H':'text/x-c++hdr',
    'hs':'text/x-haskell',
    'ico':'image/x-icon',
    'idl':'text/x-idl',
    'inf':'text/x-inf',
    'java':'text/x-java',
    'js':'text/x-javascript',
    'ksh':'text/x-ksh',
    'lua':'text/x-lua',
    'm':'text/x-objc',
    'm4':'text/x-m4',
    'make':'text/x-makefile', 'mk':'text/x-makefile', 'Makefile':'text/x-makefile',
    'mail':'text/x-mail',
    'pas':'text/x-pascal',
    'pdf':'application/pdf',
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
    'rtf':'application/rtf',
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
    'zsh':'text/x-zsh'
}

def get_charset(mimetype):
    """Return the character encoding included in the given content type string,
    or `None` if `mimetype` is `None` or empty or if no charset information is
    available.
    """
    if mimetype:
        ctpos = mimetype.find('charset=')
        if ctpos >= 0:
            return mimetype[ctpos + 8:]

def get_mimetype(filename):
    """Guess the most probable MIME type of a file with the given name."""
    try:
        suffix = filename.split('.')[-1]
        return MIME_MAP[suffix]
    except KeyError:
        import mimetypes
        return mimetypes.guess_type(filename)[0]
    except:
        return None

def is_binary(str):
    """Detect binary content by checking the first thousand bytes for zeroes."""
    if detect_unicode(str):
        return False
    for i in range(0, min(len(str), 1000)):
        if str[i] == '\0':
            return True
    return False

def detect_unicode(data):
    """Detect different unicode charsets by looking for BOMs (Byte Order
    Marks)."""
    if data.startswith('\xff\xfe'):
        return 'utf-16-le'
    elif data.startswith('\xfe\xff'):
        return 'utf-16-be'
    elif data.startswith('\xef\xbb\xbf'):
        return 'utf-8'
    else:
        return None


class IHTMLPreviewRenderer(Interface):
    """Extension point interface for components that add HTML renderers of
    specific content types to the `Mimeview` component.
    """

    # implementing classes should set this property to True if they
    # support text content where Trac should expand tabs into spaces
    expand_tabs = False

    def get_quality_ratio(mimetype):
        """Return the level of support this renderer provides for the content of
        the specified MIME type. The return value must be a number between 0
        and 9, where 0 means no support and 9 means "perfect" support.
        """

    def render(req, mimetype, content, filename=None, rev=None):
        """Render an XHTML preview of the given content of the specified MIME
        type.
        
        Can return the generated XHTML text as a single string or as an iterable
        that yields strings. In the latter case, the list will be considered to
        correspond to lines of text in the original content.

        The `filename` and `rev` parameters are provided for renderers that
        embed objects (using <object> or <img>) instead of included the content
        inline.
        """

class IHTMLPreviewAnnotator(Interface):
    """Extension point interface for components that can annotate an XHTML
    representation of file contents with additional information."""

    def get_annotation_type():
        """Return a (type, label, description) tuple that defines the type of
        annotation and provides human readable names. The `type` element should
        be unique to the annotator. The `label` element is used as column
        heading for the table, while `description` is used as a display name to
        let the user toggle the appearance of the annotation type.
        """

    def annotate_line(number, content):
        """Return the XHTML markup for the table cell that contains the
        annotation data."""


class Mimeview(Component):
    """A generic class to prettify data, typically source code."""

    renderers = ExtensionPoint(IHTMLPreviewRenderer)
    annotators = ExtensionPoint(IHTMLPreviewAnnotator)

    # Public API

    def get_annotation_types(self):
        """Generator that returns all available annotation types."""
        for annotator in self.annotators:
            yield annotator.get_annotation_type()

    def render(self, req, mimetype, content, filename=None, rev=None,
               annotations=None):
        """Render an XHTML preview of the given content of the specified MIME
        type, selecting the most appropriate `IHTMLPreviewRenderer`
        implementation available for the given MIME type.

        Return a string containing the XHTML text.
        """
        if not content:
            return ''

        if filename and not mimetype:
            mimetype = get_mimetype(filename)
        mimetype = mimetype.split(';')[0].strip() # split off charset

        expanded_content = None

        candidates = []
        for renderer in self.renderers:
            qr = renderer.get_quality_ratio(mimetype)
            if qr > 0:
                expand_tabs = getattr(renderer, 'expand_tabs', False)
                self.log.debug('Renderer %s expand_tabs = %s' % (renderer.__class__.__name__, expand_tabs))
                if expand_tabs and expanded_content is None:
                    tab_width = int(self.config.get('mimeviewer', 'tab_width'))
                    expanded_content = content.expandtabs(tab_width)

                if expand_tabs:
                    candidates.append((qr, renderer, expanded_content))
                else:
                    candidates.append((qr, renderer, content))
        candidates.sort(lambda x,y: cmp(y[0], x[0]))

        for qr, renderer, content in candidates:
            try:
                self.log.debug('Trying to render HTML preview using %s'
                               % renderer.__class__.__name__)
                result = renderer.render(req, mimetype, content, filename, rev)

                if not result:
                    continue
                elif isinstance(result, (str, unicode)):
                    return result
                elif annotations:
                    return self._annotate(result, annotations)
                else:
                    buf = StringIO()
                    buf.write('<div class="code-block"><pre>')
                    for line in result:
                        buf.write(line + '\n')
                    buf.write('</pre></div>')
                    return buf.getvalue()
            except Exception, e:
                self.log.warning('HTML preview using %s failed (%s)'
                                 % (renderer, e), exc_info=True)

    def _annotate(self, lines, annotations):
        buf = StringIO()
        buf.write('<table class="code-block listing"><thead><tr>')
        annotators = []
        for annotator in self.annotators:
            atype, alabel, adesc = annotator.get_annotation_type()
            if atype in annotations:
                buf.write('<th class="%s">%s</th>' % (atype, alabel))
                annotators.append(annotator)
        buf.write('<th class="content">&nbsp;</th>')
        buf.write('</tr></thead><tbody>')

        space_re = re.compile('(?P<spaces> (?: +))|'
                              '^(?P<tag><\w+.*?>)?( )')
        def htmlify(match):
            m = match.group('spaces')
            if m:
                div, mod = divmod(len(m), 2)
                return div * '&nbsp; ' + mod * '&nbsp;'
            return (match.group('tag') or '') + '&nbsp;'

        for num, line in enum(_html_splitlines(lines)):
            cells = []
            for annotator in annotators:
                cells.append(annotator.annotate_line(num + 1, line))
            cells.append('<td>%s</td>\n' % space_re.sub(htmlify, line))
            buf.write('<tr>' + '\n'.join(cells) + '</tr>')
        buf.write('</tbody></table>')
        return buf.getvalue()


def _html_splitlines(lines):
    """Tracks open and close tags in lines of HTML text and yields lines that
    have no tags spanning more than one line."""
    open_tag_re = re.compile(r'<(\w+)\s.*?[^/]?>')
    close_tag_re = re.compile(r'</(\w+)>')
    open_tags = []
    for line in lines:
        # Reopen tags still open from the previous line
        for tag in open_tags:
            line = tag.group(0) + line
        open_tags = []

        # Find all tags opened on this line
        for tag in open_tag_re.finditer(line):
            open_tags.append(tag)

        # Find all tags closed on this line
        for ctag in close_tag_re.finditer(line):
            for otag in open_tags:
                if otag.group(1) == ctag.group(1):
                    open_tags.remove(otag)
                    break

        # Close all tags still open at the end of line, they'll get reopened at
        # the beginning of the next line
        for tag in open_tags:
            line += '</%s>' % tag.group(1)

        yield line


class LineNumberAnnotator(Component):
    """Text annotator that adds a column with line numbers."""
    implements(IHTMLPreviewAnnotator)

    # ITextAnnotator methods

    def get_annotation_type(self):
        return 'lineno', 'Line', 'Line numbers'

    def annotate_line(self, number, content):
        return '<th id="l%s"><a href="#l%s">%s</a></th>' % (number, number,
                                                            number)


class PlainTextRenderer(Component):
    """HTML preview renderer for plain text, and fallback for any kind of text
    for which no more specific renderer is available.
    """
    implements(IHTMLPreviewRenderer)

    expand_tabs = True

    def get_quality_ratio(self, mimetype):
        if mimetype.startswith('text/'):
            return 1
        return 0

    def render(self, req, mimetype, content, filename=None, rev=None):
        if is_binary(content):
            self.env.log.debug("Binary data; no preview available")
            return

        self.env.log.debug("Using default plain text mimeviewer")
        from trac.util import escape
        for line in content.splitlines():
            yield escape(line)


class ImageRenderer(Component):
    """Inline image display."""
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
    """Render files containing Trac's own Wiki formatting markup."""
    implements(IHTMLPreviewRenderer)

    def get_quality_ratio(self, mimetype):
        if mimetype in ('text/x-trac-wiki', 'application/x-trac-wiki'):
            return 8
        return 0

    def render(self, req, mimetype, content, filename=None, rev=None):
        from trac.wiki import wiki_to_html
        return wiki_to_html(content, self.env, req)
