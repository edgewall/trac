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

import os
import StringIO
from Toolbar import Toolbar
from util import *
import neo_cgi

class Module:
    def __init__(self, config, args, pool):
        self.config = config
        self.args = args
        self.pool = pool
        self.cgi = neo_cgi.CGI()
        
        self.toolbar = Toolbar()
        self.cgi.hdf.setValue('title', '')
        self.cgi.hdf.setValue('svntrac_url', 'http://svntrac.edgewall.com/')
        self.cgi.hdf.setValue('htdocs_location',
                              config['general']['htdocs_location'])
        self.cgi.hdf.setValue('cgi_name', get_cgi_name())

    def render (self):
        """
        this function can be overridden to fill self.namespace with
        useful content.
        """
        pass

    def apply_template (self):
        theme_dir = self.config['general']['theme_dir']
        tmpl_filename = os.path.join (theme_dir, self.template_name)

        self.cgi.hdf.setValue('toolbar', self.toolbar.render (self._name))
        self.cgi.display(tmpl_filename)

        
