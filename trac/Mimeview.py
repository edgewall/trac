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
    'asp':'text/x-asp',
    'c':'text/x-csrc',
    'h':'text/x-chdr',
    'cc':'text/x-c++src', 'cpp':'text/x-c++src', 'CC':'text/x-c++src',
    'hh':'text/x-c++hdr', 'HH':'text/x-c++hdr',  'hpp':'text/x-c++hdr',
    'js':'application/x-javascript',
    'pl':'text/x-perl',
    'php':'text/x-php', 'php4':'text/x-php', 'php3':'text/x-php',
    'psp':'text/x-psp',
    'py':'text/x-python',
    'rb':'text/x-ruby',
    'sql':'text/x-sql',
    'xml':'text/xml',
    'xsl':'text/xsl',
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

            for prio, mimetype in viewer.supported_types:
                self.add_viewer (mimetype, viewer, prio)
                
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
        
    def display(self, data, mimetype=None, filename=None):
        if not data:
            return ''
        if not mimetype and filename:
            mimetype = self.get_mimetype(filename)
        idx = 0
        while not idx == -1:
            viewer,idx = self.get_viewer (mimetype, idx)
            try:
                return viewer.display(data, mimetype, filename, self.env)
            except Exception, e:
                if self.env:
                    self.env.log.error('Display failed: %s' % e)
                idx += 1
