# svntrac
#
# Copyright (C) 2003 Xyche Software
# Copyright (C) 2003 Jonas Borgström <jonas@xyche.com>
#
# svntrac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# svntrac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Jonas Borgström <jonas@xyche.com>

import sys
import StringIO
from svn import fs, util, delta

from Module import Module
import perm

class File (Module):
    CHUNK_SIZE = 4096

    def __init__(self, config, args, pool):
        Module.__init__(self, config, args, pool)
        
        if args.has_key('rev'):
            self.rev = args['rev']
        else:
            self.rev = None
        
        if args.has_key('path'):
            self.path = args['path']
        else:
            self.path = '/'
        
    def render (self):
        perm.assert_permission (perm.FILE_VIEW)

    def get_mime_type (self, root, path):
        """
        Try to use the mime-type stored in subversion. text/plain is default.
        """
        type = fs.node_prop (root, path, util.SVN_PROP_MIME_TYPE, self.pool)
        if not type:
            type = 'text/plain'
        return type

    def apply_template (self):
        if not self.rev:
            rev = fs.youngest_rev(self.fs_ptr, self.pool)
        else:
            rev = int(self.rev)
            
        root = fs.revision_root(self.fs_ptr, rev, self.pool)

        mime_type = self.get_mime_type (root, self.path)

        print 'Content-type: %s\n\r\n\r' % mime_type
        file = fs.file_contents(root, self.path, self.pool)
        while 1:
            data = util.svn_stream_read(file, self.CHUNK_SIZE)
            if not data:
                break
            sys.stdout.write(data)
