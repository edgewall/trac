# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2013 Edgewall Software
# Copyright (C) 2005 Christian Boos <cboos@bct-technology.com>
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
# Author: Christian Boos <cboos@bct-technology.com>
#         Christopher Lenz <cmlenz@gmx.de>

import os
import re

from genshi.core import Markup

from trac.core import *
from trac.config import Option
from trac.mimeview.api import IHTMLPreviewRenderer, content_to_unicode
from trac.util import NaivePopen
from trac.util.html import Deuglifier
from trac.util.translation import _

__all__ = ['PHPRenderer']

php_types = ('text/x-php', 'application/x-httpd-php',
             'application/x-httpd-php4', 'application/x-httpd-php1')


class PhpDeuglifier(Deuglifier):

    def format(self, indata):
        # The PHP highlighter produces the end-span tags on the next line
        # instead of the line they actually apply to, which causes
        # Trac to produce lots of (useless) open-and-immediately-close
        # spans beginning each line.  This tries to curtail by bubbling
        # the first span after a set of 1+ "<br />" to before them.
        r_fixeol = re.compile(r"((?:<br />)+)(</(?:font|span)>)")
        indata = r_fixeol.sub(lambda m: m.group(2) + m.group(1), indata)

        # Now call superclass implementation that handles the dirty work
        # of applying css classes.
        return Deuglifier.format(self, indata)

    @classmethod
    def rules(cls):
        colors = dict(comment='FF8000', lang='0000BB', keyword='007700',
                      string='DD0000')
        # rules check for <font> for PHP 4 or <span> for PHP 5
        return [r'(?P<%s><(?:font color="|span style="color: )#%s">)' % c
                for c in colors.items()
                ] + [r'(?P<font><font.*?>)', r'(?P<endfont></font>)']


class PHPRenderer(Component):
    """Syntax highlighter using the PHP executable."""

    implements(IHTMLPreviewRenderer)

    path = Option('mimeviewer', 'php_path', 'php',
        """Path to the PHP executable (''since 0.9'').""")

    returns_source = True

    # IHTMLPreviewRenderer methods

    def get_quality_ratio(self, mimetype):
        if mimetype in php_types:
            return 5
        return 0

    def render(self, context, mimetype, content, filename=None, rev=None):
        # -n to ignore php.ini so we're using default colors
        cmdline = '%s -sn' % self.path
        self.log.debug("PHP command line: %s", cmdline)

        content = content_to_unicode(self.env, content, mimetype)
        content = content.encode('utf-8')
        np = NaivePopen(cmdline, content, capturestderr=1)
        if (os.name != 'nt' and np.errorlevel) or np.err:
            msg = 'Running (%s) failed: %s, %s.' % (cmdline,
                                                    np.errorlevel,
                                                    np.err)
            raise Exception(msg)

        odata = ''.join(np.out.splitlines()[1:-1])
        if odata.startswith('X-Powered-By:') or \
                odata.startswith('Content-type:'):
            raise TracError(_('You appear to be using the PHP CGI '
                              'binary. Trac requires the CLI version '
                              'for syntax highlighting.'))

        epilogues = ["</span>", "</font>"]
        for e in epilogues:
            if odata.endswith(e):
                odata = odata[:-len(e)]
                break

        html = PhpDeuglifier().format(odata.decode('utf-8'))

        # PHP generates _way_ too many non-breaking spaces...
        # We don't need them anyway, so replace them by normal spaces
        return [Markup(line.replace('&nbsp;', ' '))
                for line in html.split('<br />')]
