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
from util import *

class Href:
    def __init__(self, base):
        self.base = base

    def log(self, path):
        return href_join(self.base, 'log', path)
        
    def file(self, path, rev=None):
        if rev:
            return href_join(self.base, 'file', path) + '?rev=' + str(rev)
        else:
            return href_join(self.base, 'file', path)

    def browser(self, path, rev=None):
        if rev:
            return href_join(self.base, 'browser', path) + '?rev=' + str(rev)
        else:
            return href_join(self.base, 'browser', path)

    def login(self):
        return '%s/login' % self.base

    def logout(self):
        return '%s/logout' % self.base

    def timeline(self):
        return href_join(self.base, 'timeline/')

    def changeset(self, rev):
        return href_join(self.base, 'changeset', str(rev))

    def ticket(self, ticket):
        return href_join(self.base, 'ticket', str(ticket))

    def newticket(self):
        return '%s?mode=newticket' % self.base

    def newticket(self):
        return href_join(self.base, 'newticket/')

    def search(self):
        return href_join(self.base, 'search/')

    def about(self, page=None):
        if page:
            return href_join(self.base, 'about_trac/', page)
        else:
            return href_join(self.base, 'about_trac/')

    def wiki(self, page = None, version=None, diff=0):
        if page and version and diff:
            return href_join(self.base, 'wiki', page) + '?version=' + str(version) + '&diff=yes'
        elif page and version:
            return href_join(self.base, 'wiki', page) + '?version=' + str(version)
        elif page:
            return href_join(self.base, 'wiki', page)
        else:
            return href_join(self.base, 'wiki/')

    def report(self, report=None, action=None):
        if report:
            href = href_join(self.base, 'report', str(report))
        else:
            href = href_join(self.base, 'report/')
        if action:
            href = href + '?action=' + action
        return href

href = None

def initialize(cgi_location):
    global href
    href = Href(cgi_location)
