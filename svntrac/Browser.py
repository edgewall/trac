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

from Module import Module
from util import *
import perm

import StringIO
import string
from svn import fs, util, delta

class Browser (Module):
    template_name = 'browser.template'

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
    
    def get_info (self, path, revision):
        """
        Extracts information for a given path and revision
        """
        root = fs.revision_root(self.fs_ptr, revision, self.pool)
        entries = fs.dir_entries (root, path, self.pool)
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
                date = format_date (date, self.pool)
            else:
                date = ""

            item = {
                'name'       : name,
                'fullpath'   : fullpath,
                'created_rev': created_rev,
                'date'       : date,
                'is_dir'     : is_dir,
                'size'       : size
                }
            info.append(item)
        return info
            
    def pretty_size (self, size):
        if size < 1024:
            return '%d bytes' % size
        elif size < 1024 * 1024:
            return '%d kb' % (size / 1024)
        else:
            return '%d MB' % (size / 1024 / 1024)
        
    def print_item (self, out, item, idx):
        if idx % 2:
            out.write ('<tr class="item-row-even">\n')
        else:
            out.write ('<tr class="item-row-odd">\n')
        if item['is_dir']:
            out.write ('<td class="name-column"><a href="%s">%s</a></td>'
                       % (browser_href (item['fullpath']), item['name']))
            out.write ('<td class="size-column">&nbsp;</td>')
            out.write ('<td class="rev-column">%s</td>' %
                       item['created_rev'])
        else:
            out.write ('<td class="name-column"><a href="%s">%s</a></td>'
                       % (log_href (item['fullpath']), item['name']))
            out.write ('<td class="size-column">%s</td>' %
                       self.pretty_size(item['size']))
            out.write ('<td class="rev-column"><a href="%s">%s</a></td>'
                       % (file_href(item['fullpath'],
                                                item['created_rev']),
                          item['created_rev']))
        out.write ('<td class="date-column">%s</td>' % item['date'])
        out.write ('\n</tr>\n')

    def get_path_links (self):
        list = self.path[1:].split('/')
        path = '/'
        str  = '<a href="%s">/</a>' % browser_href('/')
        for part in list:
            if part == '':
                return str
            path = path + part + '/'
            str = str + '<a href="%s">%s/</a>' % (browser_href(path), part)
        return str
    
    def render (self):
        perm.assert_permission (perm.BROWSER_VIEW)
        
        if not self.rev:
            rev = fs.youngest_rev(self.fs_ptr, self.pool)
        else:
            rev = int(self.rev)
            
        info = self.get_info (self.path, rev)
        info.sort (lambda x, y: cmp(x['name'], y['name']))
        info.sort (lambda x, y: cmp(y['is_dir'], x['is_dir']))

        out = StringIO.StringIO()
        idx = 0
        # print a '..' list item
        if self.path != '/':
            parent = string.join(self.path.split('/')[:-2], '/') + '/'
            out.write ('<tr class="item-row-odd">\n')
            out.write ('<td><a href="%s">..</a></td><td class="size-column">&nbsp;</td><td class="rev-column">&nbsp;</td><td class="date-column">&nbsp;</td>' %
                       browser_href(parent))
            out.write ('</tr>')
            idx = 1
        # print the "ordinary" items
        for item in info:
            self.print_item (out, item, idx)
            idx = idx + 1

        self.namespace['path']        = self.path
        self.namespace['path_links']  = self.get_path_links ()
        self.namespace['revision']    = rev
        self.namespace['dir_entries'] = out.getvalue()
