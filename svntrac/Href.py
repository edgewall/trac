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

from util import *

class Href:
    def __init__(self, cgi_name, authcgi_name):
        self.cgi_name = cgi_name
        self.authcgi_name = authcgi_name

    def log(self, path):
        return '%s?mode=log&path=%s' % (self.cgi_name, path)
        
    def file(self, path, rev):
        return '%s?mode=file&path=%s&rev=%s' % (self.cgi_name, path, rev)

    def browser(self, path):
        return '%s?mode=browser&path=%s' % (self.cgi_name, path)

    def login(self):
        return self.authcgi_name

    def logout(self):
        return '%s?logout=now' % self.cgi_name

    def timeline(self):
        return '%s?mode=timeline' % self.cgi_name

    def changeset(self, rev):
        return '%s?mode=changeset&rev=%s' % (self.cgi_name, rev)

    def ticket(self, ticket):
        return '%s?mode=ticket&id=%s' % (self.cgi_name, ticket)

    def newticket(self):
        return '%s?mode=newticket' % self.cgi_name

    def wiki(self, page = None, version=None):
        if page and version:
            return '%s?mode=wiki&page=%s&version=%s' % \
                   (self.cgi_name, page, version)
        elif page:
            return '%s?mode=wiki&page=%s' % (self.cgi_name, page)
        else:
            return '%s?mode=wiki' % self.cgi_name

    def report(self, report=None, action=None):
        if report and action:
            return '%s?mode=report&id=%s&action=%s' % \
                   (self.cgi_name, report, action)
        elif report:
            return '%s?mode=report&id=%s' % (self.cgi_name, report)
        else:
            return '%s?mode=report' % self.cgi_name


class RewriteHref(Href):
    """
    Alternative href scheme using mod_rewrite

    This scheme produces more 'attractive' links but need
    server side configuration to work correctly
    """
    def log(self, path):
        return href_join(self.cgi_name, 'log', path)
        
    def file(self, path, rev):
        return href_join(self.cgi_name, 'file', path, str(rev))

    def browser(self, path):
        return href_join(self.cgi_name, 'browser', path)

    def timeline(self):
        return href_join(self.cgi_name, 'timeline/')

    def changeset(self, rev):
        return href_join(self.cgi_name, 'changeset', str(rev))

    def ticket(self, ticket):
        return href_join(self.cgi_name, 'ticket', str(ticket))

    def newticket(self):
        return href_join(self.cgi_name, 'newticket/')

    def wiki(self, page = None, version=None):
        if page and version:
            return href_join(self.cgi_name, 'wiki', page, str(version))
        elif page:
            return href_join(self.cgi_name, 'wiki', page)
        else:
            return href_join(self.cgi_name, 'wiki/')

    def report(self, report=None, action=None):
        if report and action:
            return href_join(self.cgi_name, 'report', str(report), action)
        elif report:
            return href_join(self.cgi_name, 'report', str(report))
        else:
            return href_join(self.cgi_name, 'report/')




href = None

def initialize(config):
    global href
    
    href_scheme = config['general']['href_scheme']
    cgi_name = config['general']['cgi_name']
    authcgi_name = config['general']['authcgi_name']
    
    if href_scheme == 'rewrite':
        href = RewriteHref(cgi_name, authcgi_name)
    else:
        href = Href(cgi_name, authcgi_name)
