# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004 Edgewall Software
# Copyright (C) 2004 Daniel Lundin <daniel@edgewall.com>
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
#
# Syntax highlighting module, based on the SilverCity module.
# Get it at: http://silvercity.sourceforge.net/
#

from __future__ import generators

import re
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from trac.core import *
from trac.mimeview.api import IHTMLPreviewRenderer

__all__ = ['SilverCityRenderer']

types = {
    'text/css':['CSS'],
    'text/html':['HyperText', {'asp.default.language':1}],
    'application/xml':['XML'],
    'application/xhtml+xml':['HyperText', {'asp.default.language':1}],
    'application/x-javascript':['CPP'], # Kludgy.
    'text/x-asp':['HyperText', {'asp.default.language':2}],
    'text/x-c++hdr':['CPP'],
    'text/x-c++src':['CPP'],
    'text/x-chdr':['CPP'],
    'text/x-csrc':['CPP'],
    'text/x-perl':['Perl'],
    'text/x-php':['HyperText', {'asp.default.language':4}],
    'application/x-httpd-php':['HyperText', {'asp.default.language':4}],
    'application/x-httpd-php4':['HyperText', {'asp.default.language':4}],
    'application/x-httpd-php3':['HyperText', {'asp.default.language':4}],
    'text/x-psp':['HyperText', {'asp.default.language':3}],
    'text/x-python':['Python'],
    'text/x-ruby':['Ruby'],
    'text/x-sql':['SQL'],
    'text/xml':['XML'],
    'text/xslt':['XSLT'],
    'image/svg+xml':['XML']
}

CRLF_RE = re.compile('\r$', re.MULTILINE)


class SilverCityRenderer(Component):
    """Syntax highlighting based on SilverCity."""

    implements(IHTMLPreviewRenderer)

    def get_quality_ratio(self, mimetype):
        if mimetype in types.keys():
            return 3
        return 0

    def render(self, req, mimetype, content, filename=None, rev=None):
        import SilverCity
        try:
            typelang = types[mimetype]
            lang = typelang[0]
            module = getattr(SilverCity, lang)
            generator = getattr(module, lang + "HTMLGenerator")
            try:
                allprops = typelang[1]
                propset = SilverCity.PropertySet()
                for p in allprops.keys():
                    propset[p] = allprops[p]
            except IndexError:
                pass
        except (KeyError, AttributeError):
            err = "No SilverCity lexer found for mime-type '%s'." % mimetype
            raise Exception, err

        # SilverCity generates extra empty line against some types of
        # the line such as comment or #include with CRLF. So we
        # standardize to LF end-of-line style before call.
        content = CRLF_RE.sub('', content)

        buf = StringIO()
        generator().generate_html(buf, content)

        br_re = re.compile(r'<br\s*/?>$', re.MULTILINE)
        span_default_re = re.compile(r'<span class="p_default">(.*?)</span>',
                                     re.DOTALL)
        html = span_default_re.sub(r'\1', br_re.sub('', buf.getvalue()))

        for line in html.splitlines():
            # SilverCity generates _way_ too many non-breaking spaces...
            # We don't need them anyway, so replace them by normal spaces
            yield line.replace('&nbsp;', ' ')
