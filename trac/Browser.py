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

import string

from svn import core, fs, util, delta

from Module import Module
from util import *
import perm

class Browser(Module):
    template_name = 'browser.cs'

    def get_info(self, path, revision, rev_specified):
        """
        Extracts information for a given path and revision
        """
        root = fs.revision_root(self.fs_ptr, revision, self.pool)

        node_type = fs.check_path(root, path, self.pool)
        if not node_type in [core.svn_node_dir, core.svn_node_file]:
            raise TracError('"%s": no such file or directory in revision %d' \
                            % (path, revision), 'Not such file or directory')

        # Redirect to the file module if the requested path happens
        # to point to a regular file
        if fs.is_file(root, path, self.pool):
            if rev_specified:
                self.req.redirect(self.env.href.file(path, revision))
            else:
                self.req.redirect(self.env.href.log(path))
            
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
                date_seconds = util.svn_time_from_cstring(date,
                                                          self.pool) / 1000000
                date = time.asctime(time.localtime(date_seconds))[4:-8]
            else:
                date_seconds = 0
                date = ''

            item = {
                'name'       : name,
                'fullpath'   : fullpath,
                'created_rev': created_rev,
                'date'       : date,
                'date_seconds' : date_seconds,
                'is_dir'     : is_dir,
                'size'       : self.pretty_size(size),
                'size_bytes' : size }
            if is_dir:
                item['browser_href'] = self.env.href.browser(fullpath)
            else:
                item['log_href'] = self.env.href.log(fullpath)
                item['rev_href'] = self.env.href.file(fullpath, revision)
                
            info.append(item)
        return info
            
    def pretty_size(self, size):
        if size < 1024:
            return '%d bytes' % size
        elif size < 1024 * 1024:
            return '%d kb' % (size / 1024)
        else:
            return '%d MB' % (size / 1024 / 1024)
        
    def generate_path_links(self, path):
        list = path[1:].split('/')
        path = '/'
        self.req.hdf.setValue('browser.path.0', 'root')
        self.req.hdf.setValue('browser.path.0.url' , self.env.href.browser(path))
        i = 0
        for part in list:
            i = i + 1
            if part == '':
                break
            path = path + part + '/'
            self.req.hdf.setValue('browser.path.%d' % i, part)
            self.req.hdf.setValue('browser.path.%d.url' % i,
                                  self.env.href.browser(path))
        self.req.hdf.setValue('browser.path.%d.last' % (len(list) - 1), '1')
                

    def render(self):
        self.perm.assert_permission (perm.BROWSER_VIEW)

        rev = self.args.get('rev', None)
        path = self.args.get('path', '/')
        order = self.args.get('order', 'name')
        
        if rev in ['head', 'latest', 'trunk']:
            rev = fs.youngest_rev(self.fs_ptr, self.pool)
            rev_specified = 1
        elif not rev:
            rev_specified = 0
            rev = fs.youngest_rev(self.fs_ptr, self.pool)
        else:
            rev_specified = 1
            rev = int(rev)
            
        info = self.get_info(path, rev, rev_specified)
        if order == 'size':
            info.sort(lambda x, y: cmp(x['size_bytes'], y['size_bytes']))
        elif order == 'Size':
            info.sort(lambda y, x: cmp(x['size_bytes'], y['size_bytes']))
        elif order == 'date':
            info.sort(lambda x, y: cmp(x['date_seconds'], y['date_seconds']))
        elif order == 'Date':
            info.sort(lambda y, x: cmp(x['date_seconds'], y['date_seconds']))
        elif order == 'Name':
            info.sort(lambda y, x: cmp(x['name'], y['name']))
        else:
            info.sort(lambda x, y: cmp(x['name'], y['name']))
            
        # Always put directories before files
        info.sort(lambda x, y: cmp(y['is_dir'], x['is_dir']))

        add_dictlist_to_hdf(info, self.req.hdf, 'browser.items')

        self.generate_path_links(path)

        if path != '/':
            parent = string.join(path.split('/')[:-2], '/') + '/'
            self.req.hdf.setValue('browser.parent_href',
                                  self.env.href.browser(parent))

        self.req.hdf.setValue('title', path + ' (browser)')
        self.req.hdf.setValue('browser.path', path)
        self.req.hdf.setValue('browser.revision', str(rev))
        self.req.hdf.setValue('browser.sort_order', order)
        self.req.hdf.setValue('browser.current_href', self.env.href.browser(path))
