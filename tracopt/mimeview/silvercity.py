# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2009 Edgewall Software
# Copyright (C) 2004 Daniel Lundin <daniel@edgewall.com>
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

"""Syntax highlighting module, based on the SilverCity module.

Get it at: http://silvercity.sourceforge.net/
"""

import re
from StringIO import StringIO

from genshi.core import Markup

from trac.core import *
from trac.config import ListOption
from trac.env import ISystemInfoProvider
from trac.mimeview.api import IHTMLPreviewRenderer, Mimeview
from trac.util import get_pkginfo

try:
    import SilverCity
    have_silvercity = True
except ImportError:
    have_silvercity = False


__all__ = ['SilverCityRenderer']

types = {
    'text/css':                 ('CSS', 3),
    'text/html':                ('HyperText', 3, {'asp.default.language':1}),
    'application/xml':          ('XML', 3),
    'application/xhtml+xml':    ('HyperText', 3, {'asp.default.language':1}),
    'application/rss+xml':      ('HyperText', 3, {'asp.default.language':1}),
    'application/x-yaml':       ('YAML', 3),
    'text/x-yaml':              ('YAML', 3),
    'application/x-javascript': ('CPP', 3), # Kludgy.
    'text/x-asp':               ('HyperText', 3, {'asp.default.language':2}),
    'text/x-c++hdr':            ('CPP', 3),
    'text/x-c++src':            ('CPP', 3),
    'text/x-chdr':              ('CPP', 3),
    'text/x-csrc':              ('CPP', 3),
    'text/x-perl':              ('Perl', 3),
    'text/x-php':               ('HyperText', 3, {'asp.default.language': 4}),
    'application/x-httpd-php':  ('HyperText', 3, {'asp.default.language': 4}),
    'application/x-httpd-php4': ('HyperText', 3, {'asp.default.language': 4}),
    'application/x-httpd-php3': ('HyperText', 3, {'asp.default.language': 4}),
    'text/x-java':              ('Java', 3),
    'text/x-javascript':        ('CPP', 3), # Kludgy.
    'text/x-psp':               ('HyperText', 3, {'asp.default.language': 3}),
    'text/x-python':            ('Python', 3),
    'text/x-ruby':              ('Ruby', 3),
    'text/x-sql':               ('SQL', 3),
    'text/x-verilog':           ('Verilog', 3),
    'text/xml':                 ('XML', 3),
    'text/xslt':                ('XSLT', 3),
    'image/svg+xml':            ('XML', 3)
}

CRLF_RE = re.compile('\r$', re.MULTILINE)


class SilverCityRenderer(Component):
    """Syntax highlighting based on SilverCity."""

    implements(ISystemInfoProvider, IHTMLPreviewRenderer)

    silvercity_modes = ListOption('mimeviewer', 'silvercity_modes',
        '', doc=
        """List of additional MIME types known by SilverCity.
        For each, a tuple `mimetype:mode:quality` has to be
        specified, where `mimetype` is the MIME type,
        `mode` is the corresponding SilverCity mode to be used
        for the conversion and `quality` is the quality ratio
        associated to this conversion.
        That can also be used to override the default
        quality ratio used by the SilverCity render, which is 3
        (''since 0.10'').""")

    expand_tabs = True
    returns_source = True

    def __init__(self):
        self._types = None

    # ISystemInfoProvider methods
    
    def get_system_info(self):
        if have_silvercity:
            yield 'SilverCity', get_pkginfo(SilverCity).get('version', '?')
            # TODO: the above works only if setuptools was used to build
            # SilverCity, which is not yet the case by default for 0.9.7.
            # I've not been able to find an alternative way to get version.
    
    # IHTMLPreviewRenderer methods

    def get_quality_ratio(self, mimetype):
        # Extend default MIME type to mode mappings with configured ones
        if not have_silvercity:
            return 0
        if not self._types:
            self._types = {}
            self._types.update(types)
            self._types.update(
                Mimeview(self.env).configured_modes_mapping('silvercity'))
        return self._types.get(mimetype, (None, 0))[1]

    def render(self, context, mimetype, content, filename=None, rev=None):
        try:
            mimetype = mimetype.split(';', 1)[0]
            typelang = self._types[mimetype]
            lang = typelang[0]
            module = getattr(SilverCity, lang)
            generator = getattr(module, lang + "HTMLGenerator")
            try:
                allprops = typelang[2]
                propset = SilverCity.PropertySet()
                for p in allprops.keys():
                    propset[p] = allprops[p]
            except IndexError:
                pass
        except (KeyError, AttributeError):
            err = "No SilverCity lexer found for mime-type '%s'." % mimetype
            raise Exception, err

        # SilverCity does not like unicode strings
        content = content.encode('utf-8')
        
        # SilverCity generates extra empty line against some types of
        # the line such as comment or #include with CRLF. So we
        # standardize to LF end-of-line style before call.
        content = CRLF_RE.sub('', content)

        buf = StringIO()
        generator().generate_html(buf, content)

        br_re = re.compile(r'<br\s*/?>$', re.MULTILINE)
        span_default_re = re.compile(r'<span class="\w+_default">(.*?)</span>',
                                     re.DOTALL)
        html = span_default_re.sub(r'\1', br_re.sub('', buf.getvalue()))
        
        # Convert the output back to a unicode string
        html = html.decode('utf-8')

        # SilverCity generates _way_ too many non-breaking spaces...
        # We don't need them anyway, so replace them by normal spaces
        return [Markup(line)
                for line in html.replace('&nbsp;', ' ').splitlines()]
