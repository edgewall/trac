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
import urllib
from types import ListType
from util import href_join

class Href:
    def __init__(self, base):
        self.base = base

    def log(self, path, rev=None):
        path = urllib.quote(path)
        if rev:
            return href_join(self.base, 'log', path) + '?rev=' + str(rev)
        else:
            return href_join(self.base, 'log', path)
        
    def file(self, path, rev=None, format=None):
        path = urllib.quote(path)
        if rev and format:
            return href_join(self.base, 'file', path) + \
                   '?rev=%s&format=%s' % (str(rev), format)
        elif rev:
            return href_join(self.base, 'file', path) + '?rev=' + str(rev)
        elif format:
            return href_join(self.base, 'file', path) + '?format=' + format
        else:
            return href_join(self.base, 'file', path)

    def browser(self, path, rev=None):
        path = urllib.quote(path)
        if rev:
            return href_join(self.base, 'browser', path) + '?rev=' + str(rev)
        else:
            return href_join(self.base, 'browser', path)

    def login(self):
        return href_join(self.base, 'login')

    def logout(self):
        return href_join(self.base, 'logout')

    def timeline(self):
        return href_join(self.base, 'timeline')

    def changeset(self, rev):
        return href_join(self.base, 'changeset', str(rev))

    def ticket(self, ticket):
        return href_join(self.base, 'ticket', str(ticket))

    def newticket(self):
        return href_join(self.base, 'newticket')

    def query(self, constraints={}, order=None, desc=0, action=None):
        href = href_join(self.base, 'query')
        params = []
        if action:
            params.append('action=' + urllib.quote(action))
        for field in constraints.keys():
            values = constraints[field]
            if type(values) is not ListType:
                values = [values]
            for value in values:
                params.append(field + '=' + urllib.quote(value))
        if order:
            params.append('order=' + urllib.quote(order))
        if desc:
            params.append('desc=1')
        if params:
            href += '?' + ('&').join(params)
        return href

    def roadmap(self, show=None):
        href = href_join(self.base, 'roadmap')
        if show:
            href = href + '?show=' + show
        return href

    def milestone(self, milestone, action=None):
        params = []
        if milestone:
            if milestone.find('/') >= 0:
                # pass the milestone ID as query-string parameter, so the slash
                # doesn't get interpreted as path separator
                href = href_join(self.base, 'milestone')
                params.append(('id', milestone))
            else:
                href = href_join(self.base, 'milestone',
                                 urllib.quote_plus(milestone))
        else:
            href = href_join(self.base, 'milestone')
        if action:
            params.append(('action', action))
        if params:
            href += '?' + urllib.urlencode(params)
        return href

    def settings(self):
        return href_join(self.base, 'settings')

    def search(self, query=None, page=0, include=[]):
        uri = 'search'
        if query:
            uri += '?q=' + urllib.quote(query)
            if page:
                uri += '&page=%d' % int(page)
            if include:
                uri += '&' + '&'.join([i + '=on' for i in include])
        return href_join(self.base, uri)

    def about(self, page=None):
        if page:
            return href_join(self.base, 'about_trac', page)
        else:
            return href_join(self.base, 'about_trac')

    def wiki(self, page=None, version=None, diff=0, history=0):
        if page and version and diff:
            return href_join(self.base, 'wiki', page) + '?version=' + str(version) + '&diff=yes'
        elif page and version:
            return href_join(self.base, 'wiki', page) + '?version=' + str(version)
        elif page and history:
            return href_join(self.base, 'wiki', page) + '?history=yes'
        elif page:
            return href_join(self.base, 'wiki', page)
        else:
            return href_join(self.base, 'wiki')

    def report(self, report=None, action=None):
        if report:
            href = href_join(self.base, 'report', str(report))
        else:
            href = href_join(self.base, 'report')
        if action:
            href = href + '?action=' + action
        return href

    def attachment(self, module, id, filename, format=None):
        id = urllib.quote(urllib.quote(id, ''))
        filename = urllib.quote(filename)
        if format:
            return href_join(self.base, 'attachment', module, id, filename) + \
                   '?format='+format
        else:
            return href_join(self.base, 'attachment', module, id, filename)

