# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christian Boos <cboos@bct-technology.com>
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
# Author: Christian Boos <cboos@bct-technology.com>
#         Christopher Lenz <cmlenz@gmx.de>
#

from trac.core import *
from trac.mimeview.api import IHTMLPreviewRenderer
from trac.util import Deuglifier, NaivePopen

__all__ = ['PHPRenderer']

php_types = ('text/x-php', 'application/x-httpd-php',
             'application/x-httpd-php4', 'application/x-httpd-php1')


class PhpDeuglifier(Deuglifier):

    def rules(cls):
        return [
            r'(?P<comment><font color="#FF8000">)',
            r'(?P<keyword><font color="#5F9EA0">)',
            r'(?P<string><font color="#DD0000">)',
            r'(?P<func><font color="#007700">)',
            r'(?P<lang><font color="#0000BB">)',
            r'(?P<font><font.*?>)',
            r'(?P<endfont></font>)',
        ]
    rules = classmethod(rules)


class PHPRenderer(Component):
    """
    Syntax highlighting using the PHP executable if available.
    """

    implements(IHTMLPreviewRenderer)

    def get_quality_ratio(self, mimetype):
        if mimetype in php_types:
            return 4
        return 0

    def render(self, req, mimetype, content, filename=None, rev=None):
        cmdline = self.config.get('mimeviewer', 'php_path')
        cmdline += ' -s'
        self.env.log.debug("PHP command line: %s" % cmdline)

        np = NaivePopen(cmdline, content, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % (cmdline, np.errorlevel, np.err)
            raise Exception, err
        odata = np.out

        # Strip header
        beg = odata.find('<code>')
        odata = PhpDeuglifier().format(odata[beg:])
        return '<div class="code-block">' + odata + '</div>'
