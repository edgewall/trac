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

from util import *

class Href:
    def __init__(self, base):
        self.base = base

    def log(self, path):
        return '%ssvntrac.cgi?mode=log&path=%s' % (self.base, path)
        
    def file(self, path, rev):
        return '%ssvntrac.cgi?mode=file&path=%s&rev=%s' % (self.base, path, rev)

    def browser(self, path):
        return '%ssvntrac.cgi?mode=browser&path=%s' % (self.base, path)

    def login(self):
        return '%ssvntrac_auth.cgi' % self.base

    def logout(self):
        return '%ssvntrac.cgi?logout=now' % self.base

    def timeline(self):
        return '%ssvntrac.cgi?mode=timeline' % self.base

    def changeset(self, rev):
        return '%ssvntrac.cgi?mode=changeset&rev=%s' % (self.base, rev)

    def ticket(self, ticket):
        return '%ssvntrac.cgi?mode=ticket&id=%s' % (self.base, ticket)

    def newticket(self):
        return '%ssvntrac.cgi?mode=newticket' % self.base

    def search(self):
        return '%ssvntrac.cgi?mode=search' % self.base

    def wiki(self, page = None, version=None):
        if page and version:
            return '%ssvntrac.cgi?mode=wiki&page=%s&version=%s' % \
                   (self.base, page, version)
        elif page:
            return '%ssvntrac.cgi?mode=wiki&page=%s' % (self.base, page)
        else:
            return '%ssvntrac.cgi?mode=wiki' % self.base

    def report(self, report=None, action=None):
        if report and action:
            return '%ssvntrac.cgi?mode=report&id=%s&action=%s' % \
                   (self.base, report, action)
        elif report:
            return '%ssvntrac.cgi?mode=report&id=%s' % (self.base, report)
        elif action:
            return '%ssvntrac.cgi?mode=report&action=%s' % (self.base,
                                                            action)
        else:
            return '%ssvntrac.cgi?mode=report' % self.base


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
        if report and action:
            return href_join(self.base, 'report', str(report), action)
        elif report:
            return href_join(self.base, 'report', str(report))
        elif action:
            return href_join(self.base, 'report', action)
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
