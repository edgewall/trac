#!/usr/bin/env python
#
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

import os
import cgi
import cgitb; cgitb.enable()
import ConfigParser

import svntrac.db
from svntrac.util import *
from svntrac.auth import authenticate_user
        
if __name__ == '__main__':
    if not os.getenv('REMOTE_USER'):
        print 'Content-Type: text/html\r\n\r\n',
        print ('<html><body><pre>'
               'svntrac missconfigured, please enable apache auth on this url'
               '</pre></body></html>')
    else:
        config = svntrac.load_config()
        svntrac.db.init (config)
        authenticate_user ()
        redirect (wiki_href ())

