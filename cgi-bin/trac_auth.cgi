#!/usr/bin/env python
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

import trac.db
from trac.util import *
from trac.auth import authenticate_user
from trac import Href
        
if __name__ == '__main__':
    if not os.getenv('REMOTE_USER'):
        print 'Content-Type: text/html\r\n\r\n',
        print ('<html><body><pre>'
               'svntrac missconfigured, please enable apache auth on this url'
               '</pre></body></html>')
    else:
        trac.db.init()
        config = trac.db.load_config()
        Href.initialize(config)
        authenticate_user()
        # Try to redirect the user to the same page he came from
        uri = os.getenv('HTTP_REFERER')
        if not uri:
            uri = Href.href.wiki()
        redirect (uri)

