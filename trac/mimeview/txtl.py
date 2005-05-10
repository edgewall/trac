# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004 Edgewall Software
# Copyright (C) 2004 Daniel Lundin
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
# Trac support for Textile
# See also: http://dealmeida.net/projects/textile/ for
#
__docformat__ = 'reStructuredText'

from trac.core import *
from trac.mimeview.api import IHTMLPreviewRenderer


class TextileRenderer(Component):
    """
    Renders plain text in Textile format as HTML.
    """
    implements(IHTMLPreviewRenderer)

    def get_quality_ratio(self, mimetype):
        if mimetype == 'text/x-textile':
            return 8
        return 0

    def render(self, req, mimetype, content, filename=None, rev=None):
        import textile
        return textile.textile(content)
