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

import time
import string
import posixpath

import svn

import util
import perm
import authzperm
import Module
from Wiki import wiki_to_oneliner

class Browser(Module.Module):
    template_name = 'browser.cs'

    def get_info(self, path, revision, rev_specified):
        """
        Extracts information for a given path and revision
        """
        # We need to really make sure it's an ordinary string. The FieldStorage
        # class provided by modpython might give us some strange string-like object
        # that svn doesn't like.
        path = str(path)
        try:
            root = svn.fs.revision_root(self.fs_ptr, revision, self.pool)
        except svn.core.SubversionException:
            raise util.TracError('Invalid revision number: %d' % revision)

        node_type = svn.fs.check_path(root, path, self.pool)
        if not node_type in [svn.core.svn_node_dir, svn.core.svn_node_file]:
            raise util.TracError('"%s": no such file or directory in revision %d' \
                            % (path, revision), 'No such file or directory')

        date = svn.fs.revision_prop(self.fs_ptr, revision,
                                    svn.util.SVN_PROP_REVISION_DATE,
                                    self.pool)
        if date:
            date_seconds = svn.util.svn_time_from_cstring(date, self.pool) / 1000000
            self.req.check_modified(date_seconds)

        # Redirect to the file module if the requested path happens
        # to point to a regular file
        if svn.fs.is_file(root, path, self.pool):
            if rev_specified:
                self.req.redirect(self.env.href.file(path, revision))
            else:
                self.req.redirect(self.env.href.log(path))

        entries = svn.fs.dir_entries(root, path, self.pool)
        info = []
        for item in entries.keys():
            fullpath = posixpath.join(path, item)

            is_dir = svn.fs.is_dir(root, fullpath, self.pool)
            if is_dir:
                name = item + '/'
                fullpath = fullpath + '/'
            else:
                name = item

            created_rev = svn.fs.node_created_rev(root, fullpath, self.pool)
            date = svn.fs.revision_prop(self.fs_ptr, created_rev,
                                        svn.util.SVN_PROP_REVISION_DATE,
                                        self.pool)
            if date:
                date_seconds = svn.util.svn_time_from_cstring(date,
                                                          self.pool) / 1000000
                date = time.strftime('%x %X', time.localtime(date_seconds))
            else:
                date_seconds = 0
                date = ''
            author = svn.fs.revision_prop(self.fs_ptr, created_rev,
                                          svn.util.SVN_PROP_REVISION_AUTHOR,
                                          self.pool)
            change = svn.fs.revision_prop(self.fs_ptr, created_rev,
                                          svn.util.SVN_PROP_REVISION_LOG,
                                          self.pool)
            item = {
                'name'         : name,
                'fullpath'     : fullpath,
                'created_rev'  : created_rev,
                'date'         : date,
                'date_seconds' : date_seconds,
                'age'          : util.pretty_timedelta(date_seconds),
                'is_dir'       : is_dir,
                'author'       : author,
                'change'       : wiki_to_oneliner(util.shorten_line(util.wiki_escape_newline(change)),
                                                  self.req.hdf, self.env,self.db),
                'permission'   : self.authzperm.has_permission(fullpath)
            }
            if rev_specified:
                item['log_href'] = self.env.href.log(fullpath, revision)
                if is_dir:
                    item['browser_href'] = self.env.href.browser(fullpath,
                                                                 revision)
                else:
                    item['browser_href'] = self.env.href.file(fullpath, revision)
            else:
                item['log_href'] = self.env.href.log(fullpath)
                if is_dir:
                    item['browser_href'] = self.env.href.browser(fullpath)
                else:
                    item['browser_href'] = self.env.href.file(fullpath)

            info.append(item)
        return info

    def generate_path_links(self, path, rev, rev_specified):
        list = path.split('/')
        path = '/'
        self.req.hdf.setValue('browser.path.0', 'root')
        if rev_specified:
            self.req.hdf.setValue('browser.path.0.url',
                                  self.env.href.browser(path, rev))
        else:
            self.req.hdf.setValue('browser.path.0.url',
                                  self.env.href.browser(path))
        i = 0
        for part in list:
            i = i + 1
            if part == '':
                continue
            path = path + part + '/'
            self.req.hdf.setValue('browser.path.%d' % i, part)
            url = ''
            if rev_specified:
                url = self.env.href.browser(path, rev)
            else:
                url = self.env.href.browser(path)
            self.req.hdf.setValue('browser.path.%d.url' % i, url)
            if i == len(list) - 1:
                self.add_link('up', url, 'Parent directory')

        self.req.hdf.setValue('browser.path.%d.last' % (len(list) - 1), '1')


    def render(self):
        self.perm.assert_permission (perm.BROWSER_VIEW)
        
        rev = self.args.get('rev', None)
        path = self.args.get('path', '/')
        order = self.args.get('order', 'name').lower()
        desc = self.args.has_key('desc')
        
        self.authzperm.assert_permission (path)
        
        if not rev:
            rev_specified = 0
            rev = svn.fs.youngest_rev(self.fs_ptr, self.pool)
        else:
            try:
                rev = int(rev)
                rev_specified = 1
            except:
                rev_specified = rev.lower() in ['head', 'latest', 'trunk']
                rev = svn.fs.youngest_rev(self.fs_ptr, self.pool)

        info = self.get_info(path, rev, rev_specified)
        if order == 'date':
            if desc:
                info.sort(lambda y, x: cmp(x['date_seconds'],
                                           y['date_seconds']))
            else:
                info.sort(lambda x, y: cmp(x['date_seconds'],
                                           y['date_seconds']))
        else:
            if desc:
                info.sort(lambda y, x: cmp(util.rstrip(x['name'], '/'),
                                           util.rstrip(y['name'], '/')))
            else:
                info.sort(lambda x, y: cmp(util.rstrip(x['name'], '/'),
                                           util.rstrip(y['name'], '/')))

        # Always put directories before files
        info.sort(lambda x, y: cmp(y['is_dir'], x['is_dir']))

        util.add_dictlist_to_hdf(info, self.req.hdf, 'browser.items')

        self.generate_path_links(path, rev, rev_specified)

        if path != '/':
            parent = string.join(path.split('/')[:-2], '/') + '/'
            if rev_specified:
                self.req.hdf.setValue('browser.parent_href',
                                      self.env.href.browser(parent, rev))
            else:
                self.req.hdf.setValue('browser.parent_href',
                                      self.env.href.browser(parent))

        self.req.hdf.setValue('title', path)
        self.req.hdf.setValue('browser.path', path)
        self.req.hdf.setValue('browser.revision', str(rev))
        self.req.hdf.setValue('browser.order', order)
        self.req.hdf.setValue('browser.order_dir', desc and 'desc' or 'asc')
        self.req.hdf.setValue('browser.current_href', self.env.href.browser(path))
        self.req.hdf.setValue('browser.log_href', self.env.href.log(path))
