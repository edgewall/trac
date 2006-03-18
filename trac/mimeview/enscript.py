# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2005 Edgewall Software
# Copyright (C) 2004 Daniel Lundin <daniel@edgewall.com>
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
# Author: Daniel Lundin <daniel@edgewall.com>

from trac.core import *
from trac.mimeview.api import IHTMLPreviewRenderer
from trac.util import escape, NaivePopen, Deuglifier

__all__ = ['EnscriptRenderer']

types = {
    'application/xhtml+xml':    'html',
    'application/postscript':   'postscript',
    'application/x-csh':        'csh',
    'application/x-troff':      'nroff',
    'text/html':                'html',
    'text/x-ada':               'ada',
    'text/x-asm':               'asm',
    'text/x-awk':               'awk',
    'text/x-c++src':            'cpp',
    'text/x-c++hdr':            'cpp',
    'text/x-chdr':              'c',
    'text/x-csh':               'csh',
    'text/x-csrc':              'c',
    'text/x-diff':              'diffu', # Assume unified diff (works otherwise)
    'text/x-eiffel':            'eiffel',
    'text/x-elisp':             'elisp',
    'text/x-fortran':           'fortran',
    'text/x-haskell':           'haskell',
    'text/x-idl':               'idl',
    'text/x-inf':               'inf',
    'text/x-java':              'java',
    'text/x-javascript':        'javascript',
    'text/x-ksh':               'ksh',
    'text/x-lua':               'lua',
    'text/x-m4':                'm4',
    'text/x-makefile':          'makefile',
    'text/x-mail':              'mail',
    'text/x-matlab':            'matlab',
    'text/x-objc':              'objc',
    'text/x-pascal':            'pascal',
    'text/x-perl':              'perl',
    'text/x-pyrex':             'pyrex',
    'text/x-python':            'python',
    'text/x-rfc':               'rfc',
    'text/x-ruby':              'ruby',
    'text/x-sh':                'sh',
    'text/x-scheme':            'scheme',
    'text/x-sql':               'sql',
    'text/x-tcl':               'tcl',
    'text/x-tex':               'tex',
    'text/x-vba':               'vba',
    'text/x-verilog':           'verilog',
    'text/x-vhdl':              'vhdl',
    'model/vrml':               'vrml',
    'application/x-sh':         'sh',
    'text/x-zsh':               'zsh',
    'text/vnd.wap.wmlscript':   'wmlscript',
}


class EnscriptDeuglifier(Deuglifier):
    def rules(cls):
        return [
            r'(?P<comment><FONT COLOR="#B22222">)',
            r'(?P<keyword><FONT COLOR="#5F9EA0">)',
            r'(?P<type><FONT COLOR="#228B22">)',
            r'(?P<string><FONT COLOR="#BC8F8F">)',
            r'(?P<func><FONT COLOR="#0000FF">)',
            r'(?P<prep><FONT COLOR="#B8860B">)',
            r'(?P<lang><FONT COLOR="#A020F0">)',
            r'(?P<var><FONT COLOR="#DA70D6">)',
            r'(?P<font><FONT.*?>)',
            r'(?P<endfont></FONT>)'
        ]
    rules = classmethod(rules)


class EnscriptRenderer(Component):
    """Syntax highlighting using GNU Enscript."""

    implements(IHTMLPreviewRenderer)

    expand_tabs = True

    def get_quality_ratio(self, mimetype):
        if mimetype in types:
            return 2
        return 0

    def render(self, req, mimetype, content, filename=None, rev=None):
        cmdline = self.config.get('mimeviewer', 'enscript_path')
        cmdline += ' --color -h -q --language=html -p - -E' + types[mimetype]
        self.env.log.debug("Enscript command line: %s" % cmdline)

        np = NaivePopen(cmdline, content, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % (cmdline, np.errorlevel,
                                                    np.err)
            raise Exception, err
        odata = np.out

        # Strip header and footer
        i = odata.find('<PRE>')
        beg = i > 0 and i + 6
        i = odata.rfind('</PRE>')
        end = i > 0 and i or len(odata)

        odata = EnscriptDeuglifier().format(odata[beg:end])
        return odata.splitlines()
