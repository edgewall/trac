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

import sys
import StringIO
from time import gmtime, strftime
from svn import fs, util, delta

from Module import Module
import perm

class File (Module):
    CHUNK_SIZE = 4096

    def render (self):
        self.perm.assert_permission (perm.FILE_VIEW)

    def get_mime_type (self, root, path):
        """
        Try to use the mime-type stored in subversion. text/plain is default.
        """
        type = fs.node_prop (root, path, util.SVN_PROP_MIME_TYPE, self.pool)
        if not type:
            type = 'text/plain'
        return type

    def display (self):
        rev = self.args.get('rev', None)
        path = self.args.get('path', '/')
        
        if not rev:
            rev = fs.youngest_rev(self.fs_ptr, self.pool)
        else:
            rev = int(rev)
            
        root = fs.revision_root(self.fs_ptr, rev, self.pool)

        mime_type = self.get_mime_type (root, path)
        size = fs.file_length(root, path, self.pool)
        date = fs.revision_prop(self.fs_ptr, rev,
                                util.SVN_PROP_REVISION_DATE, self.pool)
        date_seconds = util.svn_time_from_cstring(date, self.pool) / 1000000
        date = strftime("%a, %d %b %Y %H:%M:%S GMT", gmtime(date_seconds))

        self.req.send_response(200)
        self.req.send_header('Last-Modified', date)
        self.req.send_header('Content-Length', str(size))
        self.req.send_header('Content-Type', mime_type)
        self.req.end_headers()
       
        file = fs.file_contents(root, path, self.pool)
        while 1:
            data = util.svn_stream_read(file, self.CHUNK_SIZE)
            if not data:
                break
            self.req.write(data)
