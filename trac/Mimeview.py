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

MIME_MAP = {
    'css':'text/css',
    'html':'text/html',
    'txt':'text/plain', 'TXT':'text/plain', 'text':'text/plain',
    'README':'text/plain', 'INSTALL':'text/plain', 
    'AUTHORS':'text/plain', 'COPYING':'text/plain', 
    'ChangeLog':'text/plain', 'RELEASE':'text/plain', 
    'ada':'text/x-ada',
    'asm':'text/x-asm',
    'asp':'text/x-asp',
    'awk':'text/x-awk',
    'c':'text/x-csrc',
    'csh':'application/x-csh',
    'diff':'text/x-diff', 'patch':'text/x-diff',
    'e':'text/x-eiffel',
    'el':'text/x-elisp',
    'f':'text/x-fortran',
    'h':'text/x-chdr',
    'cc':'text/x-c++src', 'cpp':'text/x-c++src', 'CC':'text/x-c++src',
    'hh':'text/x-c++hdr', 'HH':'text/x-c++hdr',  'hpp':'text/x-c++hdr',
    'hs':'text/x-haskell',
    'ico':'image/x-icon',
    'idl':'text/x-idl',
    'inf':'text/x-inf',
    'java':'text/x-java',
    'js':'text/x-javascript',
    'ksh':'text/x-ksh',
    'm':'text/x-objc',
    'm4':'text/x-m4',
    'make':'text/x-makefile', 'mk':'text/x-makefile', 'Makefile':'text/x-makefile',
    'mail':'text/x-mail',
    'pas':'text/x-pascal',
    'pl':'text/x-perl', 'pm':'text/x-perl', 'PL':'text/x-perl', 'perl':'text/x-perl',
    'php':'text/x-php', 'php4':'text/x-php', 'php3':'text/x-php',
    'ps':'application/postscript',
    'psp':'text/x-psp',
    'py':'text/x-python', 'python':'text/x-python',
    'pyx':'text/x-pyrex',
    'nroff':'application/x-troff', 'roff':'application/x-troff', 'troff':'application/x-troff',
    'rb':'text/x-ruby', 'ruby':'text/x-ruby',
    'rfc':'text/x-rfc',
    'scm':'text/x-scheme',
    'sh':'application/x-sh',
    'sql':'text/x-sql',
    'svg':'image/svg+xml',
    'tcl':'text/x-tcl',
    'tex':'text/x-tex',
    'vba':'text/x-vba',
    'bas':'text/x-vba',
    'v':'text/x-verilog', 'verilog':'text/x-verilog',
    'vhd':'text/x-vhdl',
    'vrml':'model/vrml',
    'wrl':'model/vrml',
    'xml':'text/xml',
    'xs':'text/x-csrc',
    'xsl':'text/xsl',
    'zsh':'text/x-zsh',
    'barf':'application/x-test',
 }

class Mimeview:
    """A generic class to prettify data, typically source code."""

    viewers = {}

    def __init__(self, env=None):
        self.env = env
        self.load_viewers()

    def load_viewers(self):
        import mimeviewers
        for name in mimeviewers.__all__:
            v = __import__('mimeviewers.' + name, globals(),  locals(), [])
            viewer = getattr(mimeviewers, name)
            for st in viewer.supported_types:
                self.add_viewer (st[1], viewer, st[0])

    def add_viewer(self, type, viewer, prio=0):
        if not self.viewers.has_key(type):
            self.viewers[type] = []
        if not viewer in self.viewers[type]:
            self.viewers[type].append([prio, viewer])
        self.viewers[type].sort()

    def get_viewer(self, mimetype, _idx=0):
        try:
            if mimetype:
                i = _idx
            else:
                i = -1
            return self.viewers[mimetype][_idx][1], i
        except (KeyError, IndexError):
            return self.get_viewer(None)

    def get_mimetype(self, filename):
        try:
            i = filename.rfind('.')
            suffix = filename[i+1:]
            return MIME_MAP[suffix]
        except KeyError:
            import mimetypes
            return mimetypes.guess_type(filename)[0]
        except:
            return None

    def is_binary(self, str):
        """
        Try to detect content by checking the first thousand bytes for zeroes.
        """
        for i in range(0, min(len(str), 1000)):
            if str[i] == '\0':
                return 1
        return 0

    def display(self, data, mimetype=None, filename=None, rev=None):
        if not data:
            return ''
        if filename:
            if not mimetype:
                mimetype = self.get_mimetype(filename)
        idx = 0
        while not idx == -1:
            viewer,idx = self.get_viewer (mimetype, idx)
            try:
                return viewer.display(data, mimetype, filename, rev, self.env)
            except Exception, e:
                if self.env:
                    self.env.log.warning('Display failed: %s' % e)
                idx += 1
