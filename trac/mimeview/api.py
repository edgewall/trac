# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2006 Edgewall Software
# Copyright (C) 2004 Daniel Lundin <daniel@edgewall.com>
# Copyright (C) 2005-2006 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2006 Christian Boos <cboos@neuf.fr>
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

import re
from StringIO import StringIO

from trac.config import IntOption, Option
from trac.core import *
from trac.util import to_utf8, to_unicode
from trac.util.markup import escape, Markup, Fragment, html


__all__ = ['get_mimetype', 'is_binary', 'detect_unicode', 'Mimeview',
           'content_to_unicode']

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
    'm':'text/x-objc', 'mm':'text/x-objc',
    'm4':'text/x-m4',
    'make':'text/x-makefile', 'mk':'text/x-makefile',
    'Makefile':'text/x-makefile',
    'makefile':'text/x-makefile', 'GNUMakefile':'text/x-makefile',
    'mail':'text/x-mail',
    'pas':'text/x-pascal',
    'pdf':'application/pdf',
    'pl':'text/x-perl', 'pm':'text/x-perl', 'PL':'text/x-perl',
    'perl':'text/x-perl',
    'php':'text/x-php', 'php4':'text/x-php', 'php3':'text/x-php',
    'ps':'application/postscript',
    'psp':'text/x-psp',
    'py':'text/x-python', 'python':'text/x-python',
    'pyx':'text/x-pyrex',
    'nroff':'application/x-troff', 'roff':'application/x-troff',
    'troff':'application/x-troff',
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
    'vb':'text/x-vba', 'vba':'text/x-vba', 'bas':'text/x-vba',
    'v':'text/x-verilog', 'verilog':'text/x-verilog',
    'vhd':'text/x-vhdl',
    'vrml':'model/vrml',
    'wrl':'model/vrml',
    'xml':'text/xml',
    'xs':'text/x-csrc',
    'xsl':'text/xsl',
    'zsh':'text/x-zsh'
}


MODE_RE = re.compile(
    r"#!(?:[/\w.-_]+/)?(\w+)|"               # look for shebang
    r"-\*-\s*(?:mode:\s*)?([\w+-]+)\s*-\*-"  # look for Emacs' -*- mode -*-
    )

def get_mimetype(filename, content=None):
    """Guess the most probable MIME type of a file with the given name.

    `content` is either a `str` or an `unicode` string.
    """
    suffix = filename.split('.')[-1]
    if MIME_MAP.has_key(suffix):
        return MIME_MAP[suffix]
    elif content:
        match = re.search(MODE_RE, content[:1000])
        if match:
            mode = match.group(1) or match.group(2).lower()
            if MIME_MAP.has_key(mode):
                return MIME_MAP[mode]
    try:
        import mimetypes
        return mimetypes.guess_type(filename)[0]
    except:
        if content and is_binary(content):
            return 'application/octet-stream'
        else:
            return None

def is_binary(data):
    """Detect binary content by checking the first thousand bytes for zeroes.

    Operate on either `str` or `unicode` strings.
    """
    if isinstance(data, str) and detect_unicode(data):
        return False
    return '\0' in data[:1000]

def detect_unicode(data):
    """Detect different unicode charsets by looking for BOMs (Byte Order Marks).

    Operate obviously only on `str` objects.
    """
    if data.startswith('\xff\xfe'):
        return 'utf-16-le'
    elif data.startswith('\xfe\xff'):
        return 'utf-16-be'
    elif data.startswith('\xef\xbb\xbf'):
        return 'utf-8'
    else:
        return None

def content_to_unicode(env, content, mimetype):
    """Utility for transforming an `IHTMLPreviewRenderer.render`'s `content`
    argument to an unicode string.
    """
    mimeview = Mimeview(env)
    if hasattr(content, 'read'):
        content = content.read(mimeview.get_max_preview_size())
    return mimeview.to_unicode(content, mimetype)


class IHTMLPreviewRenderer(Interface):
    """Extension point interface for components that add HTML renderers of
    specific content types to the `Mimeview` component.
    """

    # implementing classes should set this property to True if they
    # support text content where Trac should expand tabs into spaces
    expand_tabs = False

    def get_quality_ratio(mimetype):
        """Return the level of support this renderer provides for the `content`
        of the specified MIME type. The return value must be a number between
        0 and 9, where 0 means no support and 9 means "perfect" support.
        """

    def render(req, mimetype, content, filename=None, url=None):
        """Render an XHTML preview of the raw `content`.

        The `content` might be:
         * a `str` object
         * an `unicode` string
         * any object with a `read` method, returning one of the above

        It is assumed that the content will correspond to the given `mimetype`.

        Besides the `content` value, the same content may eventually
        be available through the `filename` or `url` parameters.
        This is useful for renderers that embed objects, using <object> or
        <img> instead of including the content inline.
        
        Can return the generated XHTML text as a single string or as an
        iterable that yields strings. In the latter case, the list will
        be considered to correspond to lines of text in the original content.
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

    default_charset = Option('trac', 'default_charset', 'iso-8859-15',
        """Charset to be used when in doubt.""")

    tab_width = IntOption('mimeviewer', 'tab_width', 8,
        """Displayed tab width in file preview (''since 0.9'').""")

    max_preview_size = IntOption('mimeviewer', 'max_preview_size', 262144,
        """Maximum file size for HTML preview. (''since 0.9'').""")

    # Public API

    def get_annotation_types(self):
        """Generator that returns all available annotation types."""
        for annotator in self.annotators:
            yield annotator.get_annotation_type()

    def render(self, req, mimetype, content, filename=None, url=None,
               annotations=None):
        """Render an XHTML preview of the given `content`.

        `content` is the same as an `IHTMLPreviewRenderer.render`'s
        `content` argument.

        The specified `mimetype` will be used to select the most appropriate
        `IHTMLPreviewRenderer` implementation available for this MIME type.
        If not given, the MIME type will be infered from the filename or the
        content.

        Return a string containing the XHTML text.
        """
        if not content:
            return ''

        # Ensure we have a MIME type for this content
        full_mimetype = mimetype
        if not full_mimetype:
            if hasattr(content, 'read'):
                content = content.read(mimeview.get_max_preview_size())
            full_mimetype = self.get_mimetype(filename, content)
        mimetype = full_mimetype.split(';')[0].strip() # split off charset

        # Determine candidate `IHTMLPreviewRenderer`s
        candidates = []
        for renderer in self.renderers:
            qr = renderer.get_quality_ratio(mimetype)
            if qr > 0:
                candidates.append((qr, renderer))
        candidates.sort(lambda x,y: cmp(y[0], x[0]))

        # First candidate which renders successfully wins.
        # Also, we don't want to expand tabs more than once.
        expanded_content = None
        for qr, renderer in candidates:
            try:
                self.log.debug('Trying to render HTML preview using %s'
                               % renderer.__class__.__name__)
                # check if we need to perform a tab expansion
                rendered_content = content
                if getattr(renderer, 'expand_tabs', False):
                    if expanded_content is None:
                        content = content_to_unicode(self.env, content,
                                                     full_mimetype)
                        expanded_content = content.expandtabs(self.tab_width)
                    rendered_content = expanded_content
                result = renderer.render(req, full_mimetype, rendered_content,
                                         filename, url)
                if not result:
                    continue
                elif isinstance(result, Fragment):
                    return result
                elif isinstance(result, basestring):
                    return Markup(to_unicode(result))
                elif annotations:
                    return Markup(self._annotate(result, annotations))
                else:
                    buf = StringIO()
                    buf.write('<div class="code"><pre>')
                    for line in result:
                        buf.write(line + '\n')
                    buf.write('</pre></div>')
                    return Markup(buf.getvalue())
            except Exception, e:
                self.log.warning('HTML preview using %s failed (%s)'
                                 % (renderer, e), exc_info=True)

    def _annotate(self, lines, annotations):
        buf = StringIO()
        buf.write('<table class="code"><thead><tr>')
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

        num = -1
        for num, line in enumerate(_html_splitlines(lines)):
            cells = []
            for annotator in annotators:
                cells.append(annotator.annotate_line(num + 1, line))
            cells.append('<td>%s</td>\n' % space_re.sub(htmlify, line))
            buf.write('<tr>' + '\n'.join(cells) + '</tr>')
        else:
            if num < 0:
                return ''
        buf.write('</tbody></table>')
        return buf.getvalue()

    def get_max_preview_size(self):
        return self.max_preview_size

    def get_charset(self, content='', mimetype=None):
        """Infer the character encoding from the `content` or the `mimetype`.

        `content` is either a `str` or an `unicode` object.
        
        The charset will be determined using this order:
         * from the charset information present in the `mimetype` argument
         * auto-detection of the charset from the `content`
         * the configured `default_charset` 
        """
        if mimetype:
            ctpos = mimetype.find('charset=')
            if ctpos >= 0:
                return mimetype[ctpos + 8:].strip()
        if isinstance(content, str):
            utf = detect_unicode(content)
            if utf is not None:
                return utf
        return self.default_charset

    def get_mimetype(self, filename, content):
        """Infer the MIME type from the `filename` or the `content`.

        `content` is either a `str` or an `unicode` object.
        """
        mimetype = get_mimetype(filename, content)
        charset = None
        if mimetype:
            charset = self.get_charset(content, mimetype)
        if mimetype and charset and not 'charset' in mimetype:
            mimetype += '; charset=' + charset
        return mimetype

    def to_utf8(self, content, mimetype=None):
        """Convert an encoded `content` to utf-8.

        ''Deprecated in 0.10. You should use `unicode` strings only.''
        """
        return to_utf8(content, self.get_charset(content, mimetype))

    def to_unicode(self, content, mimetype=None, charset=None):
        """Convert `content` (an encoded `str` object) to an `unicode` object.

        This calls `trac.util.to_unicode` with the `charset` provided,
        or the one obtained by `Mimeview.get_charset()`.
        """
        if not charset:
            charset = self.get_charset(content, mimetype)
        return to_unicode(content, charset)

    def preview_to_hdf(self, req, content, length, mimetype, filename,
                       url=None, annotations=None):
        """Prepares a rendered preview of the given `content`.

        Note: `content` will usually be an object with a `read` method.
        """        
        max_preview_size = self.get_max_preview_size()
        if length >= max_preview_size:
            return {'max_file_size_reached': True,
                    'max_file_size': max_preview_size,
                    'raw_href': url}
        else:
            return {'preview': self.render(req, mimetype, content, filename,
                                           url, annotations),
                    'raw_href': url}


def _html_splitlines(lines):
    """Tracks open and close tags in lines of HTML text and yields lines that
    have no tags spanning more than one line."""
    open_tag_re = re.compile(r'<(\w+)(\s.*?)?[^/]?>')
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

        open_tags.reverse()

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


# -- Default annotators

class LineNumberAnnotator(Component):
    """Text annotator that adds a column with line numbers."""
    implements(IHTMLPreviewAnnotator)

    # ITextAnnotator methods

    def get_annotation_type(self):
        return 'lineno', 'Line', 'Line numbers'

    def annotate_line(self, number, content):
        return '<th id="L%s"><a href="#L%s">%s</a></th>' % (number, number,
                                                            number)


# -- Default renderers

class PlainTextRenderer(Component):
    """HTML preview renderer for plain text, and fallback for any kind of text
    for which no more specific renderer is available.
    """
    implements(IHTMLPreviewRenderer)

    expand_tabs = True

    TREAT_AS_BINARY = [
        'application/pdf',
        'application/postscript',
        'application/rtf'
    ]

    def get_quality_ratio(self, mimetype):
        if mimetype in self.TREAT_AS_BINARY:
            return 0
        return 1

    def render(self, req, mimetype, content, filename=None, url=None):
        if is_binary(content):
            self.env.log.debug("Binary data; no preview available")
            return

        self.env.log.debug("Using default plain text mimeviewer")
        content = content_to_unicode(self.env, content, mimetype)
        for line in content.splitlines():
            yield escape(line)


class ImageRenderer(Component):
    """Inline image display. Here we don't need the `content` at all."""
    implements(IHTMLPreviewRenderer)

    def get_quality_ratio(self, mimetype):
        if mimetype.startswith('image/'):
            return 8
        return 0

    def render(self, req, mimetype, content, filename=None, url=None):
        if url:
            return html.DIV(html.IMG(src=url,alt=filename),
                            class_="image-file")


class WikiTextRenderer(Component):
    """Render files containing Trac's own Wiki formatting markup."""
    implements(IHTMLPreviewRenderer)

    def get_quality_ratio(self, mimetype):
        if mimetype in ('text/x-trac-wiki', 'application/x-trac-wiki'):
            return 8
        return 0

    def render(self, req, mimetype, content, filename=None, url=None):
        from trac.wiki import wiki_to_html
        return wiki_to_html(content_to_unicode(self.env, content, mimetype),
                            self.env, req)
