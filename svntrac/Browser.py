# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003 Edgewall Software
# Copyright (C) 2003 Jonas Borgström <jonas@edgewall.com>
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
# Author: Jonas Borgström <jonas@edgewall.com>

import StringIO
import string

from svn import fs, util, delta

from Module import Module
from util import *
from Href import href
import perm

class Browser(Module):
    template_name = 'browser.cs'

    def __init__(self, config, args, pool):
        Module.__init__(self, config, args, pool)

        self.rev = dict_get_with_default(args, 'rev', None)
        self.path = dict_get_with_default(args, 'path', '/')
    
    def get_info(self, path, revision):
        """
        Extracts information for a given path and revision
        """
        root = fs.revision_root(self.fs_ptr, revision, self.pool)
        entries = fs.dir_entries(root, path, self.pool)
        info = []
        for item in entries.keys():
            fullpath = path + item

            is_dir = fs.is_dir(root, fullpath, self.pool)
            if is_dir:
                name = item + '/'
                fullpath = fullpath + '/'
                size = 0
            else:
                size = fs.file_length(root, fullpath, self.pool)
                name = item

            created_rev = fs.node_created_rev(root, fullpath, self.pool)
            date = fs.revision_prop(self.fs_ptr, created_rev,
                                    util.SVN_PROP_REVISION_DATE,
                                    self.pool)
            if date:
                date = format_date(date, self.pool)
            else:
                date = ""

            item = {
                'name'       : name,
                'fullpath'   : fullpath,
                'created_rev': created_rev,
                'date'       : date,
                'is_dir'     : is_dir,
                'size'       : self.pretty_size(size) }
            if is_dir:
                item['browser_href'] = href.browser(fullpath)
            else:
                item['log_href'] = href.log(fullpath)
                item['rev_href'] = href.file(fullpath, created_rev)
                
            info.append(item)
        return info
            
    def pretty_size(self, size):
        if size < 1024:
            return '%d bytes' % size
        elif size < 1024 * 1024:
            return '%d kb' % (size / 1024)
        else:
            return '%d MB' % (size / 1024 / 1024)
        
    def get_path_links(self):
        list = self.path[1:].split('/')
        path = '/'
        str  = '<a href="%s">/</a>' % href.browser('/')
        for part in list:
            if part == '':
                return str
            path = path + part + '/'
            str = str + '<a href="%s">%s/</a>' % (href.browser(path), part)
        return str

    def render(self):
        perm.assert_permission (perm.BROWSER_VIEW)
        
        if not self.rev:
            rev = fs.youngest_rev(self.fs_ptr, self.pool)
        else:
            rev = int(self.rev)
            
        info = self.get_info(self.path, rev)
        info.sort(lambda x, y: cmp(x['name'], y['name']))
        info.sort(lambda x, y: cmp(y['is_dir'], x['is_dir']))

        add_dictlist_to_hdf(info, self.cgi.hdf, 'browser.items')

        if self.path != '/':
            parent = string.join(self.path.split('/')[:-2], '/') + '/'
            self.cgi.hdf.setValue('browser.parent_href', href.browser(parent))

        self.cgi.hdf.setValue('browser.path', self.path)
        self.cgi.hdf.setValue('browser.revision', str(rev))
        self.cgi.hdf.setValue('browser.path_links', self.get_path_links ())
