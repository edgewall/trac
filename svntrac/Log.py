# svntrac
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

from util import *
from Href import href
from Module import Module
import perm

import StringIO
from svn import util, repos

class Log (Module):
    template_name = 'log.template'

    def __init__(self, config, args, pool):
        Module.__init__(self, config, args, pool)
        
        self.path = dict_get_with_default(args, 'path', '/')

    def log_receiver (self, baton, rev, author, date, log, pool):
        item = {
            'rev'    : rev,
            'author' : author,
            'date'   : format_date (date, pool),
            'log'    : log
            }
        self.log_info.insert (0, item)

    def get_info (self, path):
        self.log_info = []
        repos.svn_repos_get_logs (self.repos, [path],
                                   0, -1, 0, 1, self.log_receiver,
                                   self.pool)
        return self.log_info

    def print_item (self, out, item, idx):
        if idx % 2:
            out.write ('<tr class="item-row-even">\n')
        else:
            out.write ('<tr class="item-row-odd">\n')
            
        out.write ('<td class="date-column">%s</td>' % (item['date']))
        out.write ('<td class="rev-column"><a href="%s">%s</a></td>'
                   % (href.file(self.path, item['rev']), item['rev']))
        out.write ('<td class="rev-column"><a href="%s">%s</a></td>'
                   % (href.changeset(item['rev']), item['rev']))
        out.write ('<td class="summary-column">%s</td>' % (item['log']))
        out.write ('\n</tr>\n')
        
    def render (self):
        perm.assert_permission (perm.LOG_VIEW)
            
        info = self.get_info (self.path)

        out = StringIO.StringIO()
        idx = 0
        for item in info:
            self.print_item (out, item, idx)
            idx = idx + 1
            
        self.namespace['path']         = self.path
        self.namespace['log_entries']  = out.getvalue()
