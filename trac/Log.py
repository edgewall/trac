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

from util import *
from Href import href
from Module import Module
import perm

from svn import util, repos

class Log (Module):
    template_name = 'log.cs'

    def __init__(self, config, args, pool):
        Module.__init__(self, config, args, pool)
        
        self.path = dict_get_with_default(args, 'path', '/')

    def log_receiver (self, baton, rev, author, date, log, pool):
        item = {
            'rev'    : rev,
            'author' : author,
            'date'   : format_date (date, pool),
            'log'    : log,
            'file_href': href.file(self.path, rev),
            'changeset_href': href.changeset(rev)
            }
        self.log_info.insert (0, item)

    def get_info (self, path):
        self.log_info = []
        repos.svn_repos_get_logs (self.repos, [path],
                                   0, -1, 0, 1, self.log_receiver,
                                   self.pool)
        return self.log_info

    def generate_path_links(self):
        list = self.path.split('/')
        path = '/'
        self.cgi.hdf.setValue('log.filename', list[-1])
        self.cgi.hdf.setValue('log.path.0', '[root]')
        self.cgi.hdf.setValue('log.path.0.url' , href.browser(path))
        i = 0
        for part in list[:-1]:
            i = i + 1
            if part == '':
                break
            path = path + part + '/'
            self.cgi.hdf.setValue('log.path.%d' % i, part)
            self.cgi.hdf.setValue('log.path.%d.url' % i,
                                  href.browser(path))

    def render (self):
        perm.assert_permission (perm.LOG_VIEW)

        info = self.get_info (self.path)

        self.generate_path_links()
        self.cgi.hdf.setValue('log.path', self.path)
        add_dictlist_to_hdf(info, self.cgi.hdf, 'log.items')
