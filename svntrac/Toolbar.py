# svntrac
#
# Copyright (C) 2003 Xyche Software
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

import StringIO
from util import *
from auth import get_authname
import perm

class Toolbar:
    def __init__(self):
        self.log = 0
        self.browser = 1
        self.timeline = 1
        self.changeset = 0
        self.log_path = '/'
        self.browser_path = '/'

    def enable_log (self, path = '/', enable=1):
        self.log      = enable
        self.log_path = path
    
    def enable_browser(self, path = '/', enable=1):
        self.browser      = enable
        self.browser_path = path
    
    def enable_timeline (self, enable=1):
        self.timeline = enable
    
    def enable_changeset (self, rev, enable=1):
        self.changeset     = enable
        self.changeset_rev = rev
    
    def enable_timeline (self, enable=1):
        self.timeline = enable
    
    def render (self):
        out = StringIO.StringIO()
        out.write ('<table width="100%" cellspacing="0" cellpadding="0"><tr><td class="navbar" bgcolor="black">')

        out.write ('<a href="%s" class="navbar-link">menu</a> |' % menu_href ())
        
        if perm.has_permission (perm.BROWSER_VIEW):
            out.write ('<a href="%s" class="navbar-link">browse</a> |'
                       % browser_href (self.browser_path))
        if perm.has_permission (perm.TIMELINE_VIEW):
            out.write ('<a href="%s" class="navbar-link">timeline</a> | '
                       % timeline_href ())
            
        if perm.has_permission (perm.REPORT_VIEW):
            out.write ('<a href="%s" class="navbar-link">reports</a> |' % report_href ())
        
        if perm.has_permission (perm.WIKI_VIEW):
            out.write ('<a href="%s" class="navbar-link">wiki</a> |' % wiki_href ())
        
        if perm.has_permission (perm.TICKET_CREATE):
            out.write ('<a href="%s" class="navbar-link">new ticket</a> |' % newticket_href ())

        if self.log:
            out.write ('<a href="%s" class="navbar-link">log</a> |'
                       % log_href (self.log_path))
        if self.changeset:
            out.write ('<a href="%s" class="navbar-link">change set</a> |'
                       % changeset_href (self.changeset_rev))
            
        out.write ('</td><td align="right" class="navbar" bgcolor="black">')
        authname = get_authname ()        
        if authname == 'anonymous':
            out.write ('<a href="%s" class="navbar-link">login</a>' % login_href())
        else:
            out.write ('logged in as %s | <a href="svntrac.cgi?logout=now" class="navbar-link">logout</a>' % authname)
        out.write ('</td>')
        out.write ('</td></tr></table>')
        return out.getvalue()
