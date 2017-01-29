# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2014 Edgewall Software
# Copyright (C) 2004 Daniel Lundin <daniel@edgewall.com>
# Copyright (C) 2005-2006 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2006-2007 Christian Boos <cboos@edgewall.org>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Daniel Lundin <daniel@edgewall.com>
#         Christopher Lenz <cmlenz@gmx.de>
#         Christian Boos <cboos@edgewall.org>

"""
File metadata management
------------------------

The `trac.mimeview` package centralizes the intelligence related to
file metadata, principally concerning the `type` (MIME type) of the
content and, if relevant, concerning the text encoding (charset) used
by the content.

There are primarily two approaches for getting the MIME type of a
given file, either taking advantage of existing conventions for the
file name, or examining the file content and applying various
heuristics.

The module also knows how to convert the file content from one type to
another type.

In some cases, only the `url` pointing to the file's content is
actually needed, that's why we avoid to read the file's content when
it's not needed.

The actual `content` to be converted might be a `unicode` object, but
it can also be the raw byte string (`str`) object, or simply an object
that can be `read()`.

.. note:: (for plugin developers)

  The Mimeview API is quite complex and many things there are
  currently a bit difficult to work with (e.g. what an actual
  `content` might be, see the last paragraph of this description).

  So this area is mainly in a ''work in progress'' state, which will
  be improved along the lines described in :teo:`#3332`.

  In particular, if you are interested in writing `IContentConverter`
  and `IHTMLPreviewRenderer` components, note that those interfaces
  will be merged into a new style `IContentConverter`.  Feel free to
  contribute remarks and suggestions for improvements to the
  corresponding ticket (#3332 as well).
"""

import re
from StringIO import StringIO
from collections import namedtuple

from genshi import Markup, Stream
from genshi.core import TEXT, START, END, START_NS, END_NS
from genshi.builder import Fragment, tag
from genshi.input import HTMLParser

from trac.config import IntOption, ListOption, Option
from trac.core import Component, ExtensionPoint, Interface, TracError, \
                      implements
from trac.resource import Resource
from trac.util import Ranges, content_disposition
from trac.util.text import exception_to_unicode, to_unicode
from trac.util.translation import _, tag_


__all__ = ['Context', 'Mimeview', 'RenderingContext', 'get_mimetype',
           'is_binary', 'detect_unicode', 'content_to_unicode', 'ct_mimetype']


class RenderingContext(object):
    """A rendering context specifies ''how'' the content should be rendered.

    It holds together all the needed contextual information that will be
    needed by individual renderer components.

    To that end, a context keeps track of the Href instance
    (``.href``) which should be used as a base for building URLs.

    It also provides a `PermissionCache` (``.perm``) which can be used
    to restrict the output so that only the authorized information is
    shown.

    A rendering context may also be associated to some Trac resource which
    will be used as the implicit reference when rendering relative links
    or for retrieving relative content and can be used to retrieve related
    metadata.

    Rendering contexts can be nested, and a new context can be created from
    an existing context using the call syntax. The previous context can be
    retrieved using the ``.parent`` attribute.

    For example, when rendering a wiki text of a wiki page, the context will
    be associated to a resource identifying that wiki page.

    If that wiki text contains a `[[TicketQuery]]` wiki macro, the macro will
    set up nested contexts for each matching ticket that will be used for
    rendering the ticket descriptions.

    :since: version 1.0

    """

    def __init__(self, resource, href=None, perm=None):
        """Directly create a `RenderingContext`.

        :param resource: the associated resource
        :type resource: `Resource`
        :param href: an `Href` object suitable for creating URLs
        :param perm: a `PermissionCache` object used for restricting the
                     generated output to "authorized" information only.

        The actual `.perm` attribute of the rendering context will be bound
        to the given `resource` so that fine-grained permission checks will
        apply to that.
        """
        self.parent = None  #: The parent context, if any
        self.resource = resource
        self.href = href
        self.perm = perm(resource) if perm and resource else perm
        self._hints = None

    @staticmethod
    def from_request(*args, **kwargs):
        """
        :deprecated: since 1.0, use `web_context` instead. Will be removed
                     in release 1.3.1.
        """
        from trac.web.chrome import web_context
        return web_context(*args, **kwargs)

    def __repr__(self):
        path = []
        context = self
        while context:
            if context.resource.realm:  # skip toplevel resource
                path.append(repr(context.resource))
            context = context.parent
        return '<%s %s>' % (type(self).__name__, ' - '.join(reversed(path)))

    def child(self, resource=None, id=False, version=False, parent=False):
        """Create a nested rendering context.

        `self` will be the parent for the new nested context.

        :param resource: either a `Resource` object or the realm string for a
                         resource specification to be associated to the new
                         context. If `None`, the resource will be the same
                         as the resource of the parent context.
        :param id: the identifier part of the resource specification
        :param version: the version of the resource specification
        :return: the new context object
        :rtype: `RenderingContext`

        >>> context = RenderingContext('wiki', 'WikiStart')
        >>> ticket1 = Resource('ticket', 1)
        >>> context.child('ticket', 1).resource == ticket1
        True
        >>> context.child(ticket1).resource is ticket1
        True
        >>> context.child(ticket1)().resource is ticket1
        True
        """
        if resource:
            resource = Resource(resource, id=id, version=version,
                                parent=parent)
        else:
            resource = self.resource
        context = RenderingContext(resource, href=self.href, perm=self.perm)
        context.parent = self

        # hack for context instances created by from_request()
        # this is needed because various parts of the code rely on a request
        # object being available, but that will hopefully improve in the
        # future
        if hasattr(self, 'req'):
            context.req = self.req

        return context

    __call__ = child

    def __contains__(self, resource):
        """Check whether a resource is in the rendering path.

        The primary use for this check is to avoid to render the content of a
        resource if we're already embedded in a context associated to that
        resource.

        :param resource: a `Resource` specification which will be checked for
        """
        context = self
        while context:
            if context.resource and \
                   context.resource.realm == resource.realm and \
                   context.resource.id == resource.id:
                # we don't care about version here
                return True
            context = context.parent

    # Rendering hints
    #
    # A rendering hint is a key/value pairs that can influence renderers,
    # wiki formatters and processors in the way they produce their output.
    # The keys are strings, but the values could be anything.
    #
    # In nested contexts, the hints are inherited from their parent context,
    # unless overridden locally.

    def set_hints(self, **keyvalues):
        """Set rendering hints for this rendering context.

        >>> ctx = RenderingContext('timeline')
        >>> ctx.set_hints(wiki_flavor='oneliner', shorten_lines=True)
        >>> t_ctx = ctx('ticket', 1)
        >>> t_ctx.set_hints(wiki_flavor='html', preserve_newlines=True)
        >>> (t_ctx.get_hint('wiki_flavor'), t_ctx.get_hint('shorten_lines'), \
             t_ctx.get_hint('preserve_newlines'))
        ('html', True, True)
        >>> (ctx.get_hint('wiki_flavor'), ctx.get_hint('shorten_lines'), \
             ctx.get_hint('preserve_newlines'))
        ('oneliner', True, None)
        """
        if self._hints is None:
            self._hints = {}
            hints = self._parent_hints()
            if hints is not None:
                self._hints.update(hints)
        self._hints.update(keyvalues)

    def get_hint(self, hint, default=None):
        """Retrieve a rendering hint from this context or an ancestor context.

        >>> ctx = RenderingContext('timeline')
        >>> ctx.set_hints(wiki_flavor='oneliner')
        >>> t_ctx = ctx('ticket', 1)
        >>> t_ctx.get_hint('wiki_flavor')
        'oneliner'
        >>> t_ctx.get_hint('preserve_newlines', True)
        True
        """
        hints = self._hints
        if hints is None:
            hints = self._parent_hints()
            if hints is None:
                return default
        return hints.get(hint, default)

    def has_hint(self, hint):
        """Test whether a rendering hint is defined in this context or in some
        ancestor context.

        >>> ctx = RenderingContext('timeline')
        >>> ctx.set_hints(wiki_flavor='oneliner')
        >>> t_ctx = ctx('ticket', 1)
        >>> t_ctx.has_hint('wiki_flavor')
        True
        >>> t_ctx.has_hint('preserve_newlines')
        False
        """
        hints = self._hints
        if hints is None:
            hints = self._parent_hints()
            if hints is None:
                return False
        return hint in hints

    def _parent_hints(self):
        p = self.parent
        while p and p._hints is None:
            p = p.parent
        return p and p._hints


class Context(RenderingContext):
    """
    :deprecated: since 1.0, use `RenderingContext` instead. `Context` is
                 kept for compatibility and will be removed release 1.3.1.
    """


# Some common MIME types and their associated keywords and/or file extensions

KNOWN_MIME_TYPES = {
    'application/javascript':  'js',
    'application/msword':      'doc dot',
    'application/pdf':         'pdf',
    'application/postscript':  'ps',
    'application/rtf':         'rtf',
    'application/x-dos-batch': 'bat batch cmd dos',
    'application/x-sh':        'sh',
    'application/x-csh':       'csh',
    'application/x-genshi':    'genshi',
    'application/x-troff':     'nroff roff troff',
    'application/x-yaml':      'yml yaml',

    'application/rss+xml':     'rss',
    'application/xsl+xml':     'xsl',
    'application/xslt+xml':    'xslt',

    'image/x-icon':            'ico',
    'image/svg+xml':           'svg',

    'model/vrml':              'vrml wrl',

    'text/css':                'css',
    'text/html':               'html htm',
    'text/plain':              'txt TXT text README INSTALL '
                               'AUTHORS COPYING ChangeLog RELEASE',
    'text/xml':                'xml',

    # see also TEXT_X_TYPES below
    'text/x-apacheconf':       'apache',
    'text/x-csrc':             'c xs',
    'text/x-chdr':             'h',
    'text/x-c++src':           'cc CC cpp C c++ C++',
    'text/x-c++hdr':           'hh HH hpp H',
    'text/x-csharp':           'cs c# C#',
    'text/x-diff':             'patch',
    'text/x-eiffel':           'e',
    'text/x-elisp':            'el',
    'text/x-fortran':          'f',
    'text/x-haskell':          'hs',
    'text/x-ini':              'ini cfg',
    'text/x-nginx-conf':       'nginx',
    'text/x-objc':             'm mm',
    'text/x-ocaml':            'ml mli',
    'text/x-makefile':         'make mk Makefile GNUMakefile',
    'text/x-pascal':           'pas',
    'text/x-perl':             'pl pm PL',
    'text/x-php':              'php3 php4',
    'text/x-python':           'py',
    'text/x-python-doctest':   'pycon',
    'text/x-pyrex':            'pyx',
    'text/x-ruby':             'rb',
    'text/x-scheme':           'scm',
    'text/x-textile':          'txtl',
    'text/x-vba':              'vb vba bas',
    'text/x-verilog':          'v',
    'text/x-vhdl':             'vhd',
}
for t in KNOWN_MIME_TYPES.keys():
    types = KNOWN_MIME_TYPES[t].split()
    if t.startswith('text/x-'):
        types.append(t[len('text/x-'):])
    KNOWN_MIME_TYPES[t] = types

# extend the above with simple (text/x-<something>: <something>) mappings

TEXT_X_TYPES = """
    ada asm asp awk idl inf java ksh lua m4 mail psp rfc rst sql tcl tex zsh
"""
for x in TEXT_X_TYPES.split():
    KNOWN_MIME_TYPES.setdefault('text/x-%s' % x, []).append(x)


# Default mapping from keywords/extensions to known MIME types:

MIME_MAP = {}
for t, exts in KNOWN_MIME_TYPES.items():
    MIME_MAP[t] = t
    for e in exts:
        MIME_MAP[e] = t

# Simple builtin autodetection from the content using a regexp
MODE_RE = re.compile(r"""
      \#!.+?env\s+(\w+)                     # 1. look for shebang with env
    | \#!(?:[/\w.-_]+/)?(\w+)               # 2. look for regular shebang
    | -\*-\s*(?:mode:\s*)?([\w+-]+)\s*-\*-  # 3. look for Emacs' -*- mode -*-
    | vim:.*?(?:syntax|filetype|ft)=(\w+)   # 4. look for VIM's syntax=<n>
    """, re.VERBOSE)


def get_mimetype(filename, content=None, mime_map=MIME_MAP,
                 mime_map_patterns={}):
    """Guess the most probable MIME type of a file with the given name.

    `filename` is either a filename (the lookup will then use the suffix)
    or some arbitrary keyword.

    `content` is either a `str` or an `unicode` string.
    """
    # 0) mimetype from filename pattern (most specific)
    for mimetype, regexp in mime_map_patterns.iteritems():
        if regexp.match(filename):
            return mimetype
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
        except Exception:
            pass
        if not mimetype and content:
            match = re.search(MODE_RE, content[:1000] + content[-1000:])
            if match:
                mode = match.group(1) or match.group(2) or match.group(4) or \
                    match.group(3).lower()
                if mode in mime_map:
                    # 3) mimetype from the content, using the `MODE_RE`
                    return mime_map[mode]
            else:
                if is_binary(content):
                    # 4) mimetype from the content, using`is_binary`
                    return 'application/octet-stream'
        return mimetype


def ct_mimetype(content_type):
    """Return the mimetype part of a content type."""
    return (content_type or '').split(';')[0].strip()


def is_binary(data):
    """Detect binary content by checking the first thousand bytes for zeroes.

    Operate on either `str` or `unicode` strings.
    """
    if isinstance(data, str) and detect_unicode(data):
        return False
    return '\0' in data[:1000]


def detect_unicode(data):
    """Detect different unicode charsets by looking for BOMs (Byte Order Mark).

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
    """Retrieve an `unicode` object from a `content` to be previewed.

    In case the raw content had an unicode BOM, we remove it.

    >>> from trac.test import EnvironmentStub
    >>> env = EnvironmentStub()
    >>> content_to_unicode(env, u"\ufeffNo BOM! h\u00e9 !", '')
    u'No BOM! h\\xe9 !'
    >>> content_to_unicode(env, "\xef\xbb\xbfNo BOM! h\xc3\xa9 !", '')
    u'No BOM! h\\xe9 !'

    """
    mimeview = Mimeview(env)
    if hasattr(content, 'read'):
        content = content.read(mimeview.max_preview_size)
    u = mimeview.to_unicode(content, mimetype)
    if u and u[0] == u'\ufeff':
        u = u[1:]
    return u


class IHTMLPreviewRenderer(Interface):
    """Extension point interface for components that add HTML renderers of
    specific content types to the `Mimeview` component.

    .. note::

      This interface will be merged with IContentConverter, as
      conversion to text/html will simply be a particular content
      conversion.

      Note however that the IHTMLPreviewRenderer will still be
      supported for a while through an adapter, whereas the
      IContentConverter interface itself will be changed.

      So if all you want to do is convert to HTML and don't feel like
      following the API changes, you should rather implement this
      interface for the time being.
    """

    #: implementing classes should set this property to True if they
    #: support text content where Trac should expand tabs into spaces
    expand_tabs = False

    #: indicate whether the output of this renderer is source code that can
    #: be decorated with annotations
    returns_source = False

    def get_extra_mimetypes():
        """Augment the Mimeview system with new mimetypes associations.

        This is an optional method. Not implementing the method or
        returning nothing is fine, the component will still be asked
        via `get_quality_ratio` if it supports a known mimetype.  But
        implementing it can be useful when the component knows about
        additional mimetypes which may augment the list of already
        mimetype to keywords associations.

        Generate ``(mimetype, keywords)`` pairs for each additional
        mimetype, with ``keywords`` being a list of keywords or
        extensions that can be used as aliases for the mimetype
        (typically file suffixes or Wiki processor keys).

        .. versionadded:: 1.0
        """

    def get_quality_ratio(mimetype):
        """Return the level of support this renderer provides for the `content`
        of the specified MIME type. The return value must be a number between
        0 and 9, where 0 means no support and 9 means "perfect" support.
        """

    def render(context, mimetype, content, filename=None, url=None):
        """Render an XHTML preview of the raw ``content`` in a
        `RenderingContext`.

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
        """Return a (type, label, description) tuple
        that defines the type of annotation and provides human readable names.
        The `type` element should be unique to the annotator.
        The `label` element is used as column heading for the table,
        while `description` is used as a display name to let the user
        toggle the appearance of the annotation type.
        """

    def get_annotation_data(context):
        """Return some metadata to be used by the `annotate_row` method below.

        This will be called only once, before lines are processed.
        If this raises an error, that annotator won't be used.
        """

    def annotate_row(context, row, number, line, data):
        """Return the XHTML markup for the table cell that contains the
        annotation data.

        `context` is the context corresponding to the content being annotated,
        `row` is the tr Element being built, `number` is the line number being
        processed and `line` is the line's actual content.
        `data` is whatever additional data the `get_annotation_data` method
        decided to provide.
        """


class IContentConverter(Interface):
    """An extension point interface for generic MIME based content
    conversion.

    .. note:: This api will likely change in the future (see :teo:`#3332`)

    """

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
        output_mime_type) or None if conversion is not possible.

        content must be a `str` instance or an iterable instance which
        iterates `str` instances."""


class Content(object):
    """A lazy file-like object that only reads `input` if necessary."""
    def __init__(self, input, max_size):
        self.input = input
        self.max_size = max_size
        self.content = None

    def read(self, size=-1):
        if size == 0:
            return ''
        if self.content is None:
            self.content = StringIO(self.input.read(self.max_size))
        return self.content.read(size)

    def reset(self):
        if self.content is not None:
            self.content.seek(0)


class Mimeview(Component):
    """Generic HTML renderer for data, typically source code."""

    required = True

    renderers = ExtensionPoint(IHTMLPreviewRenderer)
    annotators = ExtensionPoint(IHTMLPreviewAnnotator)
    converters = ExtensionPoint(IContentConverter)

    default_charset = Option('trac', 'default_charset', 'utf-8',
        """Charset to be used when in doubt.""")

    tab_width = IntOption('mimeviewer', 'tab_width', 8,
        """Displayed tab width in file preview.""")

    max_preview_size = IntOption('mimeviewer', 'max_preview_size', 262144,
        """Maximum file size for HTML preview.""")

    mime_map = ListOption('mimeviewer', 'mime_map',
        'text/x-dylan:dylan, text/x-idl:ice, text/x-ada:ads:adb',
        doc="""List of additional MIME types and keyword mappings.
        Mappings are comma-separated, and for each MIME type,
        there's a colon (":") separated list of associated keywords
        or file extensions.
        """)

    mime_map_patterns = ListOption('mimeviewer', 'mime_map_patterns',
        'text/plain:README(?!\.rst)|INSTALL(?!\.rst)|COPYING.*',
        doc="""List of additional MIME types associated to filename patterns.
        Mappings are comma-separated, and each mapping consists of a MIME type
        and a Python regexp used for matching filenames, separated by a colon
        (":"). (''since 1.0'')
        """)

    treat_as_binary = ListOption('mimeviewer', 'treat_as_binary',
        'application/octet-stream, application/pdf, application/postscript, '
        'application/msword, application/rtf',
        doc="""Comma-separated list of MIME types that should be treated as
        binary data.
        """)

    def __init__(self):
        self._mime_map = None
        self._mime_map_patterns = None

    # Public API

    def get_supported_conversions(self, mimetype):
        """Return a list of target MIME types as instances of the `namedtuple`
        `MimeConversion`. Output is ordered from best to worst quality.

        The `MimeConversion` `namedtuple` has fields: key, name, extension,
        in_mimetype, out_mimetype, quality, converter.
        """
        fields = ('key', 'name', 'extension', 'in_mimetype',
                  'out_mimetype', 'quality', 'converter')
        _MimeConversion = namedtuple('MimeConversion', fields)
        converters = []
        for c in self.converters:
            for k, n, e, im, om, q in c.get_supported_conversions() or []:
                if im == mimetype and q > 0:
                    converters.append(_MimeConversion(k, n, e, im, om, q, c))
        converters = sorted(converters, key=lambda i: i.quality, reverse=True)
        return converters

    def convert_content(self, req, mimetype, content, key, filename=None,
                        url=None, iterable=False):
        """Convert the given content to the target MIME type represented by
        `key`, which can be either a MIME type or a key. Returns a tuple of
        (content, output_mime_type, extension)."""
        if not content:
            return '', 'text/plain;charset=utf-8', '.txt'

        # Ensure we have a MIME type for this content
        full_mimetype = mimetype
        if not full_mimetype:
            if hasattr(content, 'read'):
                content = content.read(self.max_preview_size)
            full_mimetype = self.get_mimetype(filename, content)
        if full_mimetype:
            mimetype = ct_mimetype(full_mimetype)  # split off charset
        else:
            mimetype = full_mimetype = 'text/plain'  # fallback if not binary

        # Choose best converter
        candidates = [c for c in self.get_supported_conversions(mimetype)
                        if key in (c.key, c.out_mimetype)]
        if not candidates:
            raise TracError(
                _("No available MIME conversions from %(old)s to %(new)s",
                  old=mimetype, new=key))

        # First successful conversion wins
        for conversion in candidates:
            output = conversion.converter.convert_content(req, mimetype,
                                                          content,
                                                          conversion.key)
            if output:
                content, content_type = output
                if iterable:
                    if isinstance(content, basestring):
                        content = (content,)
                else:
                    if not isinstance(content, basestring):
                        content = ''.join(content)
                return content, content_type, conversion.extension
        raise TracError(
            _("No available MIME conversions from %(old)s to %(new)s",
              old=mimetype, new=key))

    def get_annotation_types(self):
        """Generator that returns all available annotation types."""
        for annotator in self.annotators:
            yield annotator.get_annotation_type()

    def render(self, context, mimetype, content, filename=None, url=None,
               annotations=None, force_source=False):
        """Render an XHTML preview of the given `content`.

        `content` is the same as an `IHTMLPreviewRenderer.render`'s
        `content` argument.

        The specified `mimetype` will be used to select the most appropriate
        `IHTMLPreviewRenderer` implementation available for this MIME type.
        If not given, the MIME type will be infered from the filename or the
        content.

        Return a string containing the XHTML text.

        When rendering with an `IHTMLPreviewRenderer` fails, a warning is added
        to the request associated with the context (if any), unless the
        `disable_warnings` hint is set to `True`.
        """
        if not content:
            return ''
        if not isinstance(context, RenderingContext):
            raise TypeError("RenderingContext expected (since 0.11)")

        # Ensure we have a MIME type for this content
        full_mimetype = mimetype
        if not full_mimetype:
            if hasattr(content, 'read'):
                content = content.read(self.max_preview_size)
            full_mimetype = self.get_mimetype(filename, content)
        if full_mimetype:
            mimetype = ct_mimetype(full_mimetype)   # split off charset
        else:
            mimetype = full_mimetype = 'text/plain' # fallback if not binary

        # Determine candidate `IHTMLPreviewRenderer`s
        candidates = []
        for renderer in self.renderers:
            qr = renderer.get_quality_ratio(mimetype)
            if qr > 0:
                candidates.append((qr, renderer))
        candidates.sort(lambda x, y: cmp(y[0], x[0]))

        # Wrap file-like object so that it can be read multiple times
        if hasattr(content, 'read'):
            content = Content(content, self.max_preview_size)

        # First candidate which renders successfully wins.
        # Also, we don't want to expand tabs more than once.
        expanded_content = None
        for qr, renderer in candidates:
            if force_source and not getattr(renderer, 'returns_source', False):
                continue  # skip non-source renderers in force_source mode
            if isinstance(content, Content):
                content.reset()
            try:
                ann_names = ', '.join(annotations) if annotations else \
                           'no annotations'
                self.log.debug('Trying to render HTML preview using %s [%s]',
                               renderer.__class__.__name__, ann_names)

                # check if we need to perform a tab expansion
                rendered_content = content
                if getattr(renderer, 'expand_tabs', False):
                    if expanded_content is None:
                        content = content_to_unicode(self.env, content,
                                                     full_mimetype)
                        expanded_content = content.expandtabs(self.tab_width)
                    rendered_content = expanded_content

                result = renderer.render(context, full_mimetype,
                                         rendered_content, filename, url)
                if not result:
                    continue

                if not (force_source or getattr(renderer, 'returns_source',
                                                False)):
                    # Direct rendering of content
                    if isinstance(result, basestring):
                        if not isinstance(result, unicode):
                            result = to_unicode(result)
                        return Markup(to_unicode(result))
                    elif isinstance(result, Fragment):
                        return result.generate()
                    else:
                        return result

                # Render content as source code
                if annotations:
                    marks = context.req.args.get('marks') if context.req \
                            else None
                    if marks:
                        context.set_hints(marks=marks)
                    return self._render_source(context, result, annotations)
                else:
                    if isinstance(result, list):
                        result = Markup('\n').join(result)
                    return tag.div(class_='code')(tag.pre(result)).generate()

            except Exception as e:
                self.log.warning('HTML preview using %s with %r failed: %s',
                                 renderer.__class__.__name__, context,
                                 exception_to_unicode(e, traceback=True))
                if context.req and not context.get_hint('disable_warnings'):
                    from trac.web.chrome import add_warning
                    add_warning(context.req,
                        _("HTML preview using %(renderer)s failed (%(err)s)",
                          renderer=renderer.__class__.__name__,
                          err=exception_to_unicode(e)))

    def _render_source(self, context, stream, annotations):
        from trac.web.chrome import add_warning
        annotators, labels, titles = {}, {}, {}
        for annotator in self.annotators:
            atype, alabel, atitle = annotator.get_annotation_type()
            if atype in annotations:
                labels[atype] = alabel
                titles[atype] = atitle
                annotators[atype] = annotator
        annotations = [a for a in annotations if a in annotators]

        if isinstance(stream, list):
            stream = HTMLParser(StringIO(u'\n'.join(stream)))
        elif isinstance(stream, unicode):
            text = stream
            def linesplitter():
                for line in text.splitlines(True):
                    yield TEXT, line, (None, -1, -1)
            stream = linesplitter()

        annotator_datas = []
        for a in annotations:
            annotator = annotators[a]
            try:
                data = (annotator, annotator.get_annotation_data(context))
            except TracError as e:
                self.log.warning("Can't use annotator '%s': %s", a, e)
                add_warning(context.req, tag.strong(
                    tag_("Can't use %(annotator)s annotator: %(error)s",
                         annotator=tag.em(a), error=tag.pre(e))))
                data = None, None
            annotator_datas.append(data)

        def _head_row():
            return tag.tr(
                [tag.th(labels[a], class_=a, title=titles[a])
                 for a in annotations] +
                [tag.th(u'\xa0', class_='content')]
            )

        def _body_rows():
            for idx, line in enumerate(_group_lines(stream)):
                row = tag.tr()
                for annotator, data in annotator_datas:
                    if annotator:
                        annotator.annotate_row(context, row, idx+1, line, data)
                    else:
                        row.append(tag.td())
                row.append(tag.td(line))
                yield row

        return tag.table(class_='code')(
            tag.thead(_head_row()),
            tag.tbody(_body_rows())
        )

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

    @property
    def mime_map(self):
        # Extend default extension to MIME type mappings with configured ones
        if not self._mime_map:
            self._mime_map = MIME_MAP.copy()
            # augment mime_map from `IHTMLPreviewRenderer`s
            for renderer in self.renderers:
                if hasattr(renderer, 'get_extra_mimetypes'):
                    for mimetype, kwds in renderer.get_extra_mimetypes() or []:
                        self._mime_map[mimetype] = mimetype
                        for keyword in kwds:
                            self._mime_map[keyword] = mimetype
            # augment/override mime_map from trac.ini
            for mapping in self.config['mimeviewer'].getlist('mime_map'):
                if ':' in mapping:
                    assocations = mapping.split(':')
                    for keyword in assocations: # Note: [0] kept on purpose
                        self._mime_map[keyword] = assocations[0]
        return self._mime_map

    def get_mimetype(self, filename, content=None):
        """Infer the MIME type from the `filename` or the `content`.

        `content` is either a `str` or an `unicode` object.

        Return the detected MIME type, augmented by the
        charset information (i.e. "<mimetype>; charset=..."),
        or `None` if detection failed.
        """

        mimetype = get_mimetype(filename, content, self.mime_map,
                                self.mime_map_patterns)
        charset = None
        if mimetype:
            charset = self.get_charset(content, mimetype)
        if mimetype and charset and not 'charset' in mimetype:
            mimetype += '; charset=' + charset
        return mimetype

    @property
    def mime_map_patterns(self):
        if not self._mime_map_patterns:
            self._mime_map_patterns = {}
            for mapping in self.config['mimeviewer'] \
                    .getlist('mime_map_patterns'):
                if ':' in mapping:
                    mimetype, regexp = mapping.split(':', 1)
                try:
                    self._mime_map_patterns[mimetype] = re.compile(regexp)
                except re.error as e:
                    self.log.warning("mime_map_patterns contains invalid "
                                     "regexp '%s' for mimetype '%s' (%s)",
                                     regexp, mimetype, exception_to_unicode(e))
        return self._mime_map_patterns

    def is_binary(self, mimetype=None, filename=None, content=None):
        """Check if a file must be considered as binary."""
        if not mimetype and filename:
            mimetype = self.get_mimetype(filename, content)
        if mimetype:
            mimetype = ct_mimetype(mimetype)
            if mimetype in self.treat_as_binary:
                return True
        if content is not None and is_binary(content):
            return True
        return False

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
                                 "option.", mapping, option)
        return types

    def preview_data(self, context, content, length, mimetype, filename,
                     url=None, annotations=None, force_source=False):
        """Prepares a rendered preview of the given `content`.

        Note: `content` will usually be an object with a `read` method.
        """
        data = {'raw_href': url, 'size': length,
                'max_file_size': self.max_preview_size,
                'max_file_size_reached': False,
                'rendered': None,
                }
        if length >= self.max_preview_size:
            data['max_file_size_reached'] = True
        else:
            result = self.render(context, mimetype, content, filename, url,
                                 annotations, force_source=force_source)
            data['rendered'] = result
        return data

    def send_converted(self, req, in_type, content, selector, filename='file'):
        """Helper method for converting `content` and sending it directly.

        `selector` can be either a key or a MIME Type."""
        from trac.web.chrome import Chrome
        from trac.web.api import RequestDone
        iterable = Chrome(self.env).use_chunked_encoding
        content, output_type, ext = self.convert_content(req, in_type, content,
                                                         selector,
                                                         iterable=iterable)
        if iterable:
            def encoder(content):
                for chunk in content:
                    if isinstance(chunk, unicode):
                        chunk = chunk.encode('utf-8')
                    yield chunk
            content = encoder(content)
            length = None
        else:
            if isinstance(content, unicode):
                content = content.encode('utf-8')
            length = len(content)
        req.send_response(200)
        req.send_header('Content-Type', output_type)
        if length is not None:
            req.send_header('Content-Length', length)
        if filename:
            req.send_header('Content-Disposition',
                            content_disposition('attachment',
                                                '%s.%s' % (filename, ext)))
        req.end_headers()
        req.write(content)
        raise RequestDone


def _group_lines(stream):
    space_re = re.compile('(?P<spaces> (?: +))|^(?P<tag><\w+.*?>)?( )')

    def pad_spaces(match):
        m = match.group('spaces')
        if m:
            div, mod = divmod(len(m), 2)
            return div * u'\xa0 ' + mod * u'\xa0'
        return (match.group('tag') or '') + u'\xa0'

    def _generate():
        stack = []
        def _reverse():
            for event in reversed(stack):
                if event[0] is START:
                    yield END, event[1][0], event[2]
                else:
                    yield END_NS, event[1][0], event[2]

        for kind, data, pos in stream:
            if kind is TEXT:
                lines = data.split('\n')
                if lines:
                    # First element
                    for e in stack:
                        yield e
                    yield kind, lines.pop(0), pos
                    for e in _reverse():
                        yield e
                    # Subsequent ones, prefix with \n
                    for line in lines:
                        yield TEXT, '\n', pos
                        for e in stack:
                            yield e
                        yield kind, line, pos
                        for e in _reverse():
                            yield e
            else:
                if kind is START or kind is START_NS:
                    stack.append((kind, data, pos))
                elif kind is END or kind is END_NS:
                    stack.pop()
                else:
                    yield kind, data, pos

    buf = []

    # Fix the \n at EOF.
    if not isinstance(stream, list):
        stream = list(stream)
    found_text = False

    for i in range(len(stream)-1, -1, -1):
        if stream[i][0] is TEXT:
            e = stream[i]
            # One chance to strip a \n
            if not found_text and e[1].endswith('\n'):
                stream[i] = (e[0], e[1][:-1], e[2])
            if len(e[1]):
                found_text = True
                break
    if not found_text:
        raise StopIteration

    for kind, data, pos in _generate():
        if kind is TEXT and data == '\n':
            yield Stream(buf[:])
            del buf[:]
        else:
            if kind is TEXT:
                data = space_re.sub(pad_spaces, data)
            buf.append((kind, data, pos))
    if buf:
        yield Stream(buf[:])


# -- Default annotators

class LineNumberAnnotator(Component):
    """Text annotator that adds a column with line numbers."""
    implements(IHTMLPreviewAnnotator)

    # IHTMLPreviewAnnotator methods

    def get_annotation_type(self):
        return 'lineno', _('Line'), _('Line numbers')

    def get_annotation_data(self, context):
        try:
            marks = Ranges(context.get_hint('marks'))
        except ValueError:
            marks = None
        return {
            'id': context.get_hint('id', '') + 'L%s',
            'marks': marks,
            'offset': context.get_hint('lineno', 1) - 1
        }

    def annotate_row(self, context, row, lineno, line, data):
        lineno += data['offset']
        id = data['id'] % lineno
        if data['marks'] and lineno in data['marks']:
            row(class_='hilite')
        row.append(tag.th(id=id)(tag.a(lineno, href='#' + id)))


# -- Default renderers

class PlainTextRenderer(Component):
    """HTML preview renderer for plain text, and fallback for any kind of text
    for which no more specific renderer is available.
    """
    implements(IHTMLPreviewRenderer)

    expand_tabs = True
    returns_source = True

    def get_quality_ratio(self, mimetype):
        if mimetype in Mimeview(self.env).treat_as_binary:
            return 0
        return 1

    def render(self, context, mimetype, content, filename=None, url=None):
        if is_binary(content):
            self.log.debug("Binary data; no preview available")
            return

        self.log.debug("Using default plain text mimeviewer")
        return content_to_unicode(self.env, content, mimetype)


class ImageRenderer(Component):
    """Inline image display.

    This component doesn't need the `content` at all.
    """
    implements(IHTMLPreviewRenderer)

    def get_quality_ratio(self, mimetype):
        if mimetype.startswith('image/'):
            return 8
        return 0

    def render(self, context, mimetype, content, filename=None, url=None):
        if url:
            return tag.div(tag.img(src=url, alt=filename),
                           class_='image-file')


class WikiTextRenderer(Component):
    """HTML renderer for files containing Trac's own Wiki formatting markup."""
    implements(IHTMLPreviewRenderer)

    def get_quality_ratio(self, mimetype):
        if mimetype in ('text/x-trac-wiki', 'application/x-trac-wiki'):
            return 8
        return 0

    def render(self, context, mimetype, content, filename=None, url=None):
        from trac.wiki.formatter import format_to_html
        return format_to_html(self.env, context,
                              content_to_unicode(self.env, content, mimetype))
