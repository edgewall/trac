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
# Syntax highlighting module, using GNU enscript.
# 

import re
import sys
import os

from trac.util import NaivePopen, escape

supported_types = [               
    (1, 'application/postscript', 'postscript'),
    (1, 'application/x-csh', 'csh'),
    (1, 'application/x-troff', 'nroff'),
    (1, 'text/html',         'html'),
    (1, 'text/x-ada',        'ada'),
    (1, 'text/x-asm',        'asm'),
    (1, 'text/x-awk',        'awk'),
    (1, 'text/x-c++src',     'cpp'),
    (1, 'text/x-c++hdr',     'cpp'),
    (1, 'text/x-chdr',       'c'),
    (1, 'text/x-csrc',       'c'),
    (1, 'text/x-diff',       None),
    (1, 'text/x-eiffel',     'eiffel'),
    (1, 'text/x-elisp',      'elisp'),
    (1, 'text/x-fortran',    'fortran'),
    (1, 'text/x-haskell',    'haskell'),
    (1, 'text/x-idl',        'idl'),
    (1, 'text/x-inf',        'inf'),
    (1, 'text/x-java',       'java'),
    (1, 'text/x-javascript', 'javacsript'),
    (1, 'text/x-ksh',        'ksh'),
    (1, 'text/x-m4',         'm4'),
    (1, 'text/x-makefile',   'makefile'),
    (1, 'text/x-mail',       'mail'),
    (1, 'text/x-matlab',     'matlab'),
    (1, 'text/x-objc',       'objc'),
    (1, 'text/x-pascal',     None),
    (1, 'text/x-perl',       'perl'),
    (1, 'text/x-pyrex',      'pyrex'),
    (1, 'text/x-python',     'python'),
    (1, 'text/x-rfc',        'rfc'),
    (1, 'text/x-scheme',     'scheme'),
    (1, 'text/x-sql',        'sql'),
    (1, 'text/x-tcl',        'tcl'),
    (1, 'text/x-tex',        'tex'),
    (1, 'text/x-vba',        'vba'),
    (1, 'text/x-verilog',    'verilog'),
    (1, 'text/x-vhdl',       'vhdl'),
    (1, 'model/vrml',        None),
    (1, 'application/x-sh',  'sh'),
    (1, 'text/x-zsh',        'zsh'),
    ]

# Build type-enscript_suffix map
types = {}
for p,t,s in supported_types:
    types[t] = s


class Deuglifier:

    _rules = [r'(?P<comment><FONT COLOR="#B22222">)',
              r'(?P<keyword><FONT COLOR="#5F9EA0">)',
              r'(?P<type><FONT COLOR="#228B22">)',
              r'(?P<string><FONT COLOR="#BC8F8F">)',
              r'(?P<func><FONT COLOR="#0000FF">)',
              r'(?P<prep><FONT COLOR="#B8860B">)',
              r'(?P<lang><FONT COLOR="#A020F0">)',
              r'(?P<var><FONT COLOR="#DA70D6">)',
              r'(?P<font><FONT.*?>)',
              r'(?P<endfont></FONT>)']

    _compiled_rules = re.compile('(?:' + '|'.join(_rules) + ')')
    _open_tags = []

    def format(self, indata):
        return re.sub(self._compiled_rules, self.replace, indata)

    def replace(self, fullmatch):
        for mtype, match in fullmatch.groupdict().items():
            if match:
                if mtype == 'font':
                    return '<span>'
                elif mtype == 'endfont':
                    return '</span>'
                return '<span class="code-%s">' % mtype


def display(data, mimetype, filename, env):    
    try:
        lang = types[mimetype]
    except KeyError:
        raise Exception, "Enscript doesn't support %s" % mimetype
    env.log.debug("type: %s enscript-suffix: %s" % (mimetype, lang))
    enscript_path = '/usr/bin/enscript --color -h -q --language=html '\
                    '--pretty-print=%s ' \
                    '-p -' % lang
    np = NaivePopen(enscript_path, data)
    odata = np.out
    # Strip header and footer
    i = odata.find('</H1>')
    beg = i > 0 and i + 7
    i = odata.rfind('</PRE>')
    end = i > 0 and i or len(odata)

    odata = Deuglifier().format(odata[beg:end])
    return '<div class="code-block">' + odata + '</div>'
