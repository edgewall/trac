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

import os
import sys
import time
import StringIO
import mimetypes

import svn

import perm
import util
from Module import Module

class FileCommon(Module):
    CHUNK_SIZE = 4096
    
    def render (self):
        self.perm.assert_permission (perm.FILE_VIEW)

    def send_file(self, read_func, mime_type, length, last_modified):
        self.req.send_response(200)
        self.req.send_header('Content-Type', mime_type)
        self.req.send_header('Conten-Length', str(length))
        self.req.send_header('Last-Modified', last_modified)
        self.req.end_headers()
        while 1:
            data = read_func(self.CHUNK_SIZE)
            if not data:
                break
            self.req.write(data)

    
class Attachment(FileCommon):
    def display(self):
        type = self.args.get('type', None)
        id = self.args.get('id', None)
        filename = os.path.basename(self.args.get('filename', None))

        path = os.path.join(self.env.get_attachments_dir(), type, id, filename)
        try:
            f = open(path, 'rb')
        except IOError:
            raise util.TracError('Attachment not found')
        
        mime_type, enc = mimetypes.guess_type(filename)
        stat = os.fstat(f.fileno())
        length = stat[6]
        last_modified = time.strftime("%a, %d %b %Y %H:%M:%S GMT",
                                      time.gmtime(stat[8]))
        read_func = lambda x: f.read(x)
        self.send_file(read_func, mime_type, length, last_modified)


class File(FileCommon):
    def display (self):
        rev = self.args.get('rev', None)
        path = self.args.get('path', '/')
        if not rev:
            rev = svn.fs.youngest_rev(self.fs_ptr, self.pool)
        else:
            rev = int(rev)
        root = svn.fs.revision_root(self.fs_ptr, rev, self.pool)
        mime_type = svn.fs.node_prop (root, path, svn.util.SVN_PROP_MIME_TYPE,
                                      self.pool) or 'text/plain'
        length = svn.fs.file_length(root, path, self.pool)
        date = svn.fs.revision_prop(self.fs_ptr, rev,
                                svn.util.SVN_PROP_REVISION_DATE, self.pool)
        date_seconds = svn.util.svn_time_from_cstring(date, self.pool) / 1000000
        last_modified = time.strftime("%a, %d %b %Y %H:%M:%S GMT",
                                      time.gmtime(date_seconds))
        f = svn.fs.file_contents(root, path, self.pool)
        read_func = lambda x: svn.util.svn_stream_read(f, x)
        self.send_file(read_func, mime_type, length, last_modified)
