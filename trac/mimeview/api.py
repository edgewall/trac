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
#         Christian Boos <cboos@neuf.fr>

"""
The `trac.mimeview` module centralize the intelligence related to
file metadata, principally concerning the `type` (MIME type) of the content
and, if relevant, concerning the text encoding (charset) used by the content.

There are primarily two approaches for getting the MIME type of a given file:
 * taking advantage of existing conventions for the file name
 * examining the file content and applying various heuristics

The module also knows how to convert the file content from one type
to another type.

In some cases, only the `url` pointing to the file's content is actually
needed, that's why we avoid to read the file's content when it's not needed.

The actual `content` to be converted might be a `unicode` object,
but it can also be the raw byte string (`str`) object, or simply
an object that can be `read()`.
"""

import re
from StringIO import StringIO

from trac.config import IntOption, ListOption, Option
from trac.core import *
from trac.util import sorted
from trac.util.text import to_utf8, to_unicode
from trac.util.markup import escape, Markup, Fragment, html


__all__ = ['get_mimetype', 'is_binary', 'detect_unicode', 'Mimeview',
           'content_to_unicode']


# Some common MIME types and their associated keywords and/or file extensions

KNOWN_MIME_TYPES = {
    'application/pdf':        ['pdf'],
    'application/postscript': ['ps'],
    'application/rtf':        ['rtf'],
    'application/x-sh':       ['sh'],
    'application/x-csh':      ['csh'],
    'application/x-troff':    ['nroff', 'roff', 'troff'],

    'image/x-icon':           ['ico'],
    'image/svg+xml':          ['svg'],
    
    'model/vrml':             ['vrml', 'wrl'],
    
    'text/css':               ['css'],
    'text/html':              ['html'],
    'text/plain':             ['txt', 'TXT', 'text', 'README', 'INSTALL',
                               'AUTHORS', 'COPYING', 'ChangeLog', 'RELEASE'],
    'text/xml':               ['xml'],
    'text/xsl':               ['xsl'],
    'text/x-csrc':            ['c', 'xs'],
    'text/x-chdr':            ['h'],
    'text/x-c++src':          ['cc', 'CC', 'cpp', 'C'],
    'text/x-c++hdr':          ['hh', 'HH', 'hpp', 'H'],
    'text/x-diff':            ['diff', 'patch'],
    'text/x-eiffel':          ['e'],
    'text/x-elisp':           ['el'],
    'text/x-fortran':         ['f'],
    'text/x-haskell':         ['hs'],
    'text/x-javascript':      ['js'],
    'text/x-objc':            ['m', 'mm'],
    'text/x-makefile':        ['make', 'mk',
                               'Makefile', 'makefile', 'GNUMakefile'],
    'text/x-pascal':          ['pas'],
    'text/x-perl':            ['pl', 'pm', 'PL', 'perl'],
    'text/x-php':             ['php', 'php3', 'php4'],
    'text/x-python':          ['py', 'python'],
    'text/x-pyrex':           ['pyx'],
    'text/x-ruby':            ['rb', 'ruby'],
    'text/x-scheme':          ['scm'],
    'text/x-textile':         ['txtl', 'textile'],
    'text/x-vba':             ['vb', 'vba', 'bas'],
    'text/x-verilog':         ['v', 'verilog'],
    'text/x-vhdl':            ['vhd'],
}

# extend the above with simple (text/x-<something>: <something>) mappings

for x in ['ada', 'asm', 'asp', 'awk', 'idl', 'inf', 'java', 'ksh', 'lua',
          'm4', 'mail', 'psp', 'rfc', 'rst', 'sql', 'tcl', 'tex', 'zsh']:
    KNOWN_MIME_TYPES.setdefault('text/x-%s' % x, []).append(x)


# Default mapping from keywords/extensions to known MIME types:

MIME_MAP = {}
for t, exts in KNOWN_MIME_TYPES.items():
    MIME_MAP[t] = t
    for e in exts:
        MIME_MAP[e] = t

# Simple builtin autodetection from the content using a regexp
MODE_RE = re.compile(
    r"#!(?:[/\w.-_]+/)?(\w+)|"               # look for shebang
    r"-\*-\s*(?:mode:\s*)?([\w+-]+)\s*-\*-|" # look for Emacs' -*- mode -*-
    r"vim:.*?syntax=(\w+)"                   # look for VIM's syntax=<n>
    )

def get_mimetype(filename, content=None, mime_map=MIME_MAP):
    """Guess the most probable MIME type of a file with the given name.

    `filename` is either a filename (the lookup will then use the suffix)
    or some arbitrary keyword.
    
    `content` is either a `str` or an `unicode` string.
    """
    suffix = filename.split('.')[-1]
    if suffix in mime_map:
        # 1) mimetype from the suffix, using the `mime_map`
        return mime_map[suffix]
    else:
        mimetype = None
        try:
            import mimetypes
            # 2) mimetype from the suffix, using the `mimetypes` module
            mimetype = mimetypes.guess_type(filename)[0]
        except:
            pass
        if not mimetype and content:
            match = re.search(MODE_RE, content[:1000])
            if match:
                mode = match.group(1) or match.group(3) or \
                    match.group(2).lower()
                if mode in mime_map:
                    # 3) mimetype from the content, using the `MODE_RE`
                    return mime_map[mode]
            else:
                if is_binary(content):
                    # 4) mimetype from the content, using`is_binary`
                    return 'application/octet-stream'
        return mimetype

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
    """Retrieve an `unicode` object from a `content` to be previewed"""
    mimeview = Mimeview(env)
    if hasattr(content, 'read'):
        content = content.read(mimeview.max_preview_size)
    return mimeview.to_unicode(content, mimetype)


class IHTMLPreviewRenderer(Interface):
    """Extension point interface for components that add HTML renderers of
    specific content types to the `Mimeview` component.

    (Deprecated)
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


class IContentConverter(Interface):
    """An extension point interface for generic MIME based content
    conversion."""

    def get_supported_conversions():
        """Return an iterable of tuples in the form (key, name, extension,
        in_mimetype, out_mimetype, quality) representing the MIME conversions
        supported and
        the quality ratio of the conversion in the range 0 to 9, where 0 means
        no support and 9 means "perfect" support. eg. ('latex', 'LaTeX', 'tex',
        'text/x-trac-wiki', 'text/plain', 8)"""

    def convert_content(req, mimetype, content, key):
        """Convert the given content from mimetype to the output MIME type
        represented by key. Returns a tuple in the form (content,
        output_mime_type) or None if conversion is not possible."""


class Mimeview(Component):
    """A generic class to prettify data, typically source code."""

    renderers = ExtensionPoint(IHTMLPreviewRenderer)
    annotators = ExtensionPoint(IHTMLPreviewAnnotator)
    converters = ExtensionPoint(IContentConverter)

    default_charset = Option('trac', 'default_charset', 'iso-8859-15',
        """Charset to be used when in doubt.""")

    tab_width = IntOption('mimeviewer', 'tab_width', 8,
        """Displayed tab width in file preview (''since 0.9'').""")

    max_preview_size = IntOption('mimeviewer', 'max_preview_size', 262144,
        """Maximum file size for HTML preview. (''since 0.9'').""")

    mime_map = ListOption('mimeviewer', 'mime_map',
        'text/x-dylan:dylan,text/x-idl:ice,text/x-ada:ads:adb',
        """List of additional MIME types and keyword mappings.
        Mappings are comma-separated, and for each MIME type,
        there's a colon (":") separated list of associated keywords
        or file extensions. (''since 0.10'').""")

    def __init__(self):
        self._mime_map = None
        
    # Public API

    def get_supported_conversions(self, mimetype):
        """Return a list of target MIME types in same form as
        `IContentConverter.get_supported_conversions()`, but with the converter
        component appended. Output is ordered from best to worst quality."""
        converters = []
        for converter in self.converters:
            for k, n, e, im, om, q in converter.get_supported_conversions():
                if im == mimetype and q > 0:
                    converters.append((k, n, e, im, om, q, converter))
        converters = sorted(converters, key=lambda i: i[-1], reverse=True)
        return converters

    def convert_content(self, req, mimetype, content, key, filename=None,
                        url=None):
        """Convert the given content to the target MIME type represented by
        `key`, which can be either a MIME type or a key. Returns a tuple of
        (content, output_mime_type, extension)."""
        if not content:
            return ('', 'text/plain;charset=utf-8')

        # Ensure we have a MIME type for this content
        full_mimetype = mimetype
        if not full_mimetype:
            if hasattr(content, 'read'):
                content = content.read(self.max_preview_size)
            full_mimetype = self.get_mimetype(filename, content)
        if full_mimetype:
            mimetype = full_mimetype.split(';')[0].strip() # split off charset
        else:
            mimetype = full_mimetype = 'text/plain' # fallback if not binary

        # Choose best converter
        candidates = list(self.get_supported_conversions(mimetype))
        candidates = [c for c in candidates if key in (c[0], c[4])]
        if not candidates:
            raise TracError('No available MIME conversions from %s to %s' %
                            (mimetype, key))

        # First successful conversion wins
        for ck, name, ext, input_mimettype, output_mimetype, quality, \
                converter in candidates:
            output = converter.convert_content(req, mimetype, content, ck)
            if not output:
                continue
            return (output[0], output[1], ext)
        raise TracError('No available MIME conversions from %s to %s' %
                        (mimetype, key))

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
                content = content.read(self.max_preview_size)
            full_mimetype = self.get_mimetype(filename, content)
        if full_mimetype:
            mimetype = full_mimetype.split(';')[0].strip() # split off charset
        else:
            mimetype = full_mimetype = 'text/plain' # fallback if not binary

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
        """Deprecated: use `max_preview_size` attribute directly."""
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

    def get_mimetype(self, filename, content=None):
        """Infer the MIME type from the `filename` or the `content`.

        `content` is either a `str` or an `unicode` object.

        Return the detected MIME type, augmented by the
        charset information (i.e. "<mimetype>; charset=..."),
        or `None` if detection failed.
        """
        # Extend default extension to MIME type mappings with configured ones
        if not self._mime_map:
            self._mime_map = MIME_MAP
            for mapping in self.config['mimeviewer'].getlist('mime_map'):
                if ':' in mapping:
                    assocations = mapping.split(':')
                    for keyword in assocations: # Note: [0] kept on purpose
                        self._mime_map[keyword] = assocations[0]

        mimetype = get_mimetype(filename, content, self._mime_map)
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

    def configured_modes_mapping(self, renderer):
        """Return a MIME type to `(mode,quality)` mapping for given `option`"""
        types, option = {}, '%s_modes' % renderer
        for mapping in self.config['mimeviewer'].getlist(option):
            if not mapping:
                continue
            try:
                mimetype, mode, quality = mapping.split(':')
                types[mimetype] = (mode, int(quality))
            except (TypeError, ValueError):
                self.log.warning("Invalid mapping '%s' specified in '%s' "
                                 "option." % (mapping, option))
        return types
    
    def preview_to_hdf(self, req, content, length, mimetype, filename,
                       url=None, annotations=None):
        """Prepares a rendered preview of the given `content`.

        Note: `content` will usually be an object with a `read` method.
        """        
        if length >= self.max_preview_size:
            return {'max_file_size_reached': True,
                    'max_file_size': self.max_preview_size,
                    'raw_href': url}
        else:
            return {'preview': self.render(req, mimetype, content, filename,
                                           url, annotations),
                    'raw_href': url}

    def send_converted(self, req, in_type, content, selector, filename='file'):
        """Helper method for converting `content` and sending it directly.

        `selector` can be either a key or a MIME Type."""
        from trac.web import RequestDone
        content, output_type, ext = self.convert_content(req, in_type,
                                                         content, selector)
        req.send_response(200)
        req.send_header('Content-Type', output_type)
        req.send_header('Content-Disposition', 'filename=%s.%s' % (filename,
                                                                   ext))
        req.end_headers()
        req.write(content)
        raise RequestDone        
        

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
