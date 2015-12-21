# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2009 Edgewall Software
# Copyright (C) 2004 Daniel Lundin
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

"""Trac support for Textile
See also: https://github.com/textile/python-textile
"""

import textile

from trac.core import *
from trac.env import ISystemInfoProvider
from trac.mimeview.api import IHTMLPreviewRenderer
from trac.util import get_pkginfo


class TextileRenderer(Component):
    """Renders plain text in Textile format as HTML."""

    implements(IHTMLPreviewRenderer, ISystemInfoProvider)

    # IHTMLPreviewRenderer methods

    def get_quality_ratio(self, mimetype):
        if mimetype == 'text/x-textile':
            return 8
        return 0

    def render(self, context, mimetype, content, filename=None, rev=None):
        return textile.textile(content.encode('utf-8'), encoding='utf-8')

    # ISystemInfoProvider methods

    def get_system_info(self):
        version = get_pkginfo(textile).get('version')
        yield 'Textile', version
