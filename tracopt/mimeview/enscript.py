# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2009 Edgewall Software
# Copyright (C) 2004 Daniel Lundin <daniel@edgewall.com>
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
# Author: Daniel Lundin <daniel@edgewall.com>

from genshi.core import Markup

from trac.config import Option, ListOption
from trac.core import *
from trac.mimeview.api import IHTMLPreviewRenderer, Mimeview
from trac.util import NaivePopen
from trac.util.html import Deuglifier

__all__ = ['EnscriptRenderer']

types = {
    'application/xhtml+xml':    ('html', 2),
    'application/postscript':   ('postscript', 2),
    'application/x-csh':        ('csh', 2),
    'application/x-javascript': ('javascript', 2),
    'application/x-troff':      ('nroff', 2),
    'text/html':                ('html', 2),
    'text/x-ada':               ('ada', 2),
    'text/x-asm':               ('asm', 2),
    'text/x-awk':               ('awk', 2),
    'text/x-c++src':            ('cpp', 2),
    'text/x-c++hdr':            ('cpp', 2),
    'text/x-chdr':              ('c', 2),
    'text/x-csh':               ('csh', 2),
    'text/x-csrc':              ('c', 2),
    'text/x-diff':              ('diffu', 2), # Assume unified diff (works otherwise)
    'text/x-eiffel':            ('eiffel', 2),
    'text/x-elisp':             ('elisp', 2),
    'text/x-fortran':           ('fortran', 2),
    'text/x-haskell':           ('haskell', 2),
    'text/x-idl':               ('idl', 2),
    'text/x-inf':               ('inf', 2),
    'text/x-java':              ('java', 2),
    'text/x-javascript':        ('javascript', 2),
    'text/x-ksh':               ('ksh', 2),
    'text/x-lua':               ('lua', 2),
    'text/x-m4':                ('m4', 2),
    'text/x-makefile':          ('makefile', 2),
    'text/x-mail':              ('mail', 2),
    'text/x-matlab':            ('matlab', 2),
    'text/x-objc':              ('objc', 2),
    'text/x-pascal':            ('pascal', 2),
    'text/x-perl':              ('perl', 2),
    'text/x-pyrex':             ('pyrex', 2),
    'text/x-python':            ('python', 2),
    'text/x-rfc':               ('rfc', 2),
    'text/x-ruby':              ('ruby', 2),
    'text/x-sh':                ('sh', 2),
    'text/x-scheme':            ('scheme', 2),
    'text/x-sql':               ('sql', 2),
    'text/x-tcl':               ('tcl', 2),
    'text/x-tex':               ('tex', 2),
    'text/x-vba':               ('vba', 2),
    'text/x-verilog':           ('verilog', 2),
    'text/x-vhdl':              ('vhdl', 2),
    'model/vrml':               ('vrml', 2),
    'application/x-sh':         ('sh', 2),
    'text/x-zsh':               ('zsh', 2),
    'text/vnd.wap.wmlscript':   ('wmlscript', 2),
}


class EnscriptDeuglifier(Deuglifier):
    @classmethod
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


class EnscriptRenderer(Component):
    """Syntax highlighter using GNU Enscript."""

    implements(IHTMLPreviewRenderer)

    expand_tabs = True
    returns_source = True

    path = Option('mimeviewer', 'enscript_path', 'enscript',
        """Path to the Enscript executable.""")

    enscript_modes = ListOption('mimeviewer', 'enscript_modes',
        'text/x-dylan:dylan:4', doc=
        """List of additional MIME types known by Enscript.
        For each, a tuple `mimetype:mode:quality` has to be
        specified, where `mimetype` is the MIME type,
        `mode` is the corresponding Enscript mode to be used
        for the conversion and `quality` is the quality ratio
        associated to this conversion.
        That can also be used to override the default
        quality ratio used by the Enscript render, which is 2
        (''since 0.10'').""")

    def __init__(self):
        self._types = None

    # IHTMLPreviewRenderer methods

    def get_quality_ratio(self, mimetype):
        # Extend default MIME type to mode mappings with configured ones
        if not self._types:
            self._types = {}
            self._types.update(types)
            self._types.update(
                Mimeview(self.env).configured_modes_mapping('enscript'))
        return self._types.get(mimetype, (None, 0))[1]

    def render(self, context, mimetype, content, filename=None, rev=None):
        cmdline = self.path
        mimetype = mimetype.split(';', 1)[0] # strip off charset
        mode = self._types[mimetype][0]
        cmdline += ' --color -h -q --language=html -p - -E%s' % mode
        self.env.log.debug("Enscript command line: %s" % cmdline)

        np = NaivePopen(cmdline, content.encode('utf-8'), capturestderr=1)
        if np.errorlevel or np.err:
            self.env.disable_component(self)
            err = "Running enscript failed with (%s, %s), disabling " \
                  "EnscriptRenderer (command: '%s')" \
                  % (np.errorlevel, np.err.strip(), cmdline)
            raise Exception(err)
        odata = np.out

        # Strip header and footer
        i = odata.find('<PRE>')
        beg = i > 0 and i + 6
        i = odata.rfind('</PRE>')
        end = i > 0 and i or len(odata)

        odata = EnscriptDeuglifier().format(odata[beg:end].decode('utf-8'))
        return [Markup(line) for line in odata.splitlines()]
