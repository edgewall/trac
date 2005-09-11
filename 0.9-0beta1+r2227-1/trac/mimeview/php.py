# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christian Boos <cboos@bct-technology.com>
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
# Author: Christian Boos <cboos@bct-technology.com>
#         Christopher Lenz <cmlenz@gmx.de>

from __future__ import generators

from trac.core import *
from trac.mimeview.api import IHTMLPreviewRenderer
from trac.util import Deuglifier, NaivePopen

__all__ = ['PHPRenderer']

php_types = ('text/x-php', 'application/x-httpd-php',
             'application/x-httpd-php4', 'application/x-httpd-php1')


class PhpDeuglifier(Deuglifier):

    def rules(cls):
        colors = dict(comment='FF8000', lang='0000BB', keyword='007700',
                      string='DD0000')
        # rules check for <font> for PHP 4 or <span> for PHP 5
        color_rules = [
                r'(?P<%s><(?:font color="|span style="color: )#%s">)' % c
                for c in colors.items()
                ]
        return color_rules + [ r'(?P<font><font.*?>)', r'(?P<endfont></font>)' ]
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
        # -n to ignore php.ini so we're using default colors
        cmdline += ' -sn'
        self.env.log.debug("PHP command line: %s" % cmdline)

        np = NaivePopen(cmdline, content, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % (cmdline, np.errorlevel,
                                                    np.err)
            raise Exception, err
        odata = ''.join(np.out.splitlines()[1:-1])
        if odata.startswith('X-Powered-By'):
            raise TracError, 'You appear to be using the PHP CGI binary.  ' \
                             'Trac requires the CLI version for syntax ' \
                             'highlighting.'

        html = PhpDeuglifier().format(odata)
        for line in html.split('<br />'):
            # PHP generates _way_ too many non-breaking spaces...
            # We don't need them anyway, so replace them by normal spaces
            yield line.replace('&nbsp;', ' ')
