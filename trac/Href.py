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

class Href:
    def __init__(self, base):
        self.base = base

    def log(self, path):
        return '%strac.cgi?mode=log&path=%s' % (self.base, path)
        
    def file(self, path, rev):
        return '%strac.cgi?mode=file&path=%s&rev=%s' % (self.base, path, rev)

    def browser(self, path):
        return '%strac.cgi?mode=browser&path=%s' % (self.base, path)

    def login(self):
        return '%strac_auth.cgi' % self.base

    def logout(self):
        return '%strac.cgi?logout=now' % self.base

    def timeline(self):
        return '%strac.cgi?mode=timeline' % self.base

    def changeset(self, rev):
        return '%strac.cgi?mode=changeset&rev=%s' % (self.base, rev)

    def ticket(self, ticket):
        return '%strac.cgi?mode=ticket&id=%s' % (self.base, ticket)

    def newticket(self):
        return '%strac.cgi?mode=newticket' % self.base

    def search(self):
        return '%strac.cgi?mode=search' % self.base

    def wiki(self, page = None, version=None):
        if page and version:
            return '%strac.cgi?mode=wiki&page=%s&version=%s' % \
                   (self.base, page, version)
        elif page:
            return '%strac.cgi?mode=wiki&page=%s' % (self.base, page)
        else:
            return '%strac.cgi?mode=wiki' % self.base

    def report(self, report=None, action=None):
        if report and action:
            return '%strac.cgi?mode=report&id=%s&action=%s' % \
                   (self.base, report, action)
        elif report:
            return '%strac.cgi?mode=report&id=%s' % (self.base, report)
        elif action:
            return '%strac.cgi?mode=report&action=%s' % (self.base,
                                                            action)
        else:
            return '%strac.cgi?mode=report' % self.base


class RewriteHref(Href):
    """
    Alternative href scheme using mod_rewrite

    This scheme produces more 'attractive' links but need
    server side configuration to work correctly
    """
    def log(self, path):
        return href_join(self.base, 'log', path)
        
    def file(self, path, rev):
        return href_join(self.base, 'file', path, str(rev))

    def browser(self, path):
        return href_join(self.base, 'browser', path)

    def timeline(self):
        return href_join(self.base, 'timeline/')

    def changeset(self, rev):
        return href_join(self.base, 'changeset', str(rev))

    def ticket(self, ticket):
        return href_join(self.base, 'ticket', str(ticket))

    def newticket(self):
        return href_join(self.base, 'newticket/')

    def search(self):
        return href_join(self.base, 'search/')

    def wiki(self, page = None, version=None):
        if page and version:
            return href_join(self.base, 'wiki', page, str(version))
        elif page:
            return href_join(self.base, 'wiki', page)
        else:
            return href_join(self.base, 'wiki/')

    def report(self, report=None, action=None):
        if action:
	    return Href.report(self, report, action)
        elif report:
            return href_join(self.base, 'report', str(report))
        else:
            return href_join(self.base, 'report/')




href = None

def initialize(config):
    global href
    
    href_scheme = config['general']['href_scheme']
    cgi_location = config['general']['cgi_location']
    
    if href_scheme == 'rewrite':
        href = RewriteHref(cgi_location)
    else:
        href = Href(cgi_location)
