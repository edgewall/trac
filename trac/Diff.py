# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004 Edgewall Software
# Copyright (C) 2003, 2004 Jonas Borgström <jonas@edgewall.com>
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
# Author: Jonas Borgström <jonas@edgewall.com>

import re

line_re = re.compile('@@ [+-]([0-9]+),([0-9]+) [+-]([0-9]+),([0-9]+) @@')
header_re = re.compile('header ([^\|]+) ([^\|]+) \| ([^\|]+) ([^\|]+) redaeh')
space_re = re.compile(' ( +)|^ ')

class HDFBuilder:
    def __init__(self, hdf, prefix, tabwidth=8):
        self.block = []
        self.ttype  = None
        self.p_block = []
        self.p_type  = None
        self.hdf = hdf
        self.prefix = prefix
        self.tabwidth = tabwidth
        self.changeno = -1
        self.blockno = 0
        self.offset_base = 0
        self.offset_changed = 0

    def _write_block (self, prefix, dtype, old = None, new = None):
        self.hdf.setValue(prefix + '.type', dtype);
        self.hdf.setValue(prefix + '.base.offset', str(self.offset_base))
        self.hdf.setValue(prefix + '.changed.offset',
                          str(self.offset_changed))
        if old:
            lineno = 1
            for line in old:
                self.hdf.setValue(prefix + '.base.lines.%d' % lineno, line)
                lineno += 1
            self.offset_base += lineno - 1
        if new:
            lineno = 1
            for line in new:
                self.hdf.setValue(prefix + '.changed.lines.%d' % lineno, line)
                lineno += 1
            self.offset_changed += lineno - 1

    def print_block (self):
        prefix = '%s.changes.%d.blocks.%d' % (self.prefix, self.changeno,
                                              self.blockno)
        if self.p_type == '-' and self.ttype == '+':
            self._write_block(prefix, 'mod', old=self.p_block, new=self.block)
        elif self.ttype == '+':
            self._write_block(prefix, 'add', new=self.block)
        elif self.ttype == '-':
            self._write_block(prefix, 'rem', old=self.block)
        elif self.ttype == ' ':
            self._write_block(prefix, 'unmod', old=self.block, new=self.block)
        self.block = self.p_block = []
        self.blockno += 1

    def writeline(self, text):
        match = header_re.search(text)
        if match:
            self.hdf.setValue('%s.name.old' % self.prefix, match.group(1))
            self.hdf.setValue('%s.rev.old' % self.prefix, match.group(2))
            self.hdf.setValue('%s.name.new' % self.prefix, match.group(3))
            self.hdf.setValue('%s.rev.new' % self.prefix, match.group(4))
            return
        if text[0:2] in ['++', '--']:
            return
        match = line_re.search(text)
        if match:
            self.print_block()
            self.changeno += 1
            self.blockno = 0
            self.offset_base = int(match.group(1)) - 1
            self.offset_changed = int(match.group(3)) - 1
            return
        ttype = text[0]
        text = text[1:]
        text = space_re.sub(lambda m:
            len(m.group(0)) / 2 * '&nbsp; ' + len(m.group(0)) % 2 * '&nbsp;',
            text.expandtabs(self.tabwidth))
        if ttype == self.ttype:
            self.block.append(text)
        else:
            if ttype == '+' and self.ttype == '-':
                self.p_block = self.block
                self.p_type = self.ttype
            else:
                self.print_block()
            self.block = [text]
            self.ttype = ttype

    def close(self):
        self.print_block()


def get_options(env, req, args, advanced=0):
    from Session import Session
    session = Session(env, req)

    def get_bool_option(name, default=0):
        pref = int(session.get('diff_' + name, default))
        arg = args.has_key(name)
        if args.has_key('update') and arg != pref:
            session.set_var('diff_' + name, arg)
        else:
            arg = pref
        return arg

    pref = session.get('diff_style', 'inline')
    arg = args.get('style', pref)
    if args.has_key('update') and arg != pref:
        session.set_var('diff_style', arg)
    req.hdf.setValue('diff.style', arg)

    if advanced:

        pref = int(session.get('diff_contextlines', 2))
        arg = int(args.get('contextlines', pref))
        if args.has_key('update') and arg != pref:
            session.set_var('diff_contextlines', arg)
        options = ['-u%d' % arg]
        req.hdf.setValue('diff.options.contextlines', str(arg))

        arg = get_bool_option('ignoreblanklines')
        if arg:
            options.append('-B')
        req.hdf.setValue('diff.options.ignoreblanklines', str(arg))

        arg = get_bool_option('ignorecase')
        if arg:
            options.append('-i')
        req.hdf.setValue('diff.options.ignorecase', str(arg))

        arg = get_bool_option('ignorewhitespace')
        if arg:
            options.append('-b')
        req.hdf.setValue('diff.options.ignorewhitespace', str(arg))

        return options

    return []
