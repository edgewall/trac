# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2020 Edgewall Software
# Copyright (C) 2004 Daniel Lundin
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.
#
# Author: Daniel Lundin <daniel@edgewall.com>

"""Trac support for Textile
See also: https://github.com/textile/python-textile
"""

try:
    import textile
except ImportError:
    textile = None
has_textile = textile is not None

from trac.api import ISystemInfoProvider
from trac.core import Component, implements
from trac.mimeview.api import IHTMLPreviewRenderer
from trac.util import get_pkginfo, lazy
from trac.util.html import Markup, TracHTMLSanitizer
from trac.wiki.api import WikiSystem


if not has_textile:
    def render_textile(text):
        return None
elif hasattr(textile, 'Textile') and hasattr(textile.Textile, 'parse'):
    def render_textile(text):  # 2.2.0 and later
        return textile.textile(text)
else:
    def render_textile(text):
        text = text.encode('utf-8')
        rv = textile.textile(text)
        return rv.decode('utf-8')


class TextileRenderer(Component):
    """Renders plain text in Textile format as HTML."""

    implements(IHTMLPreviewRenderer, ISystemInfoProvider)

    # IHTMLPreviewRenderer methods

    def get_quality_ratio(self, mimetype):
        if has_textile and mimetype == 'text/x-textile':
            return 8
        return 0

    @lazy
    def _sanitizer(self):
        wikisys = WikiSystem(self.env)
        return TracHTMLSanitizer(safe_schemes=wikisys.safe_schemes,
                                 safe_origins=wikisys.safe_origins)

    def render(self, context, mimetype, content, filename=None, rev=None):
        output = render_textile(content)
        if WikiSystem(self.env).render_unsafe_content:
            return Markup(output)
        return self._sanitizer.sanitize(output)

    # ISystemInfoProvider methods

    def get_system_info(self):
        if has_textile:
            # textile.__version__ is available since 2.1.6
            version = get_pkginfo(textile).get('version') or \
                      getattr(textile, '__version__', 'n/a')
            yield 'Textile', version
