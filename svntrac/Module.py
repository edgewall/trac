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
from util import *
from Href import href
import auth
import neo_cgi

class Module:
    def __init__(self, config, args, pool):
        self.config = config
        self.args = args
        self.pool = pool
        self.cgi = neo_cgi.CGI()
        
    def render (self):
        """
        Override this function to add data the template requires
        to self.cgi.hdf.
        """
        pass

    def apply_template (self):
        sql_to_hdf("SELECT name FROM enum WHERE type='priority' ORDER BY name",
                   self.cgi.hdf, 'enums.priority')
        sql_to_hdf("SELECT name FROM enum WHERE type='severity' ORDER BY name",
                   self.cgi.hdf, 'enums.severity')
        
        self.cgi.hdf.setValue('title', '')
        self.cgi.hdf.setValue('htdocs_location',
                              self.config['general']['htdocs_location'])
        self.cgi.hdf.setValue('cgi_location',
                              self.config['general']['cgi_location'])
        self.cgi.hdf.setValue('svntrac.active_module', self._name)
        self.cgi.hdf.setValue('svntrac.authname', auth.get_authname())
        self.cgi.hdf.setValue('svntrac.href.wiki', href.wiki())
        self.cgi.hdf.setValue('svntrac.href.browser', href.browser('/'))
        self.cgi.hdf.setValue('svntrac.href.timeline', href.timeline())
        self.cgi.hdf.setValue('svntrac.href.report', href.report())
        self.cgi.hdf.setValue('svntrac.href.newticket', href.newticket())
        self.cgi.hdf.setValue('svntrac.href.search', href.search())
        self.cgi.hdf.setValue('svntrac.href.login', href.login())
        self.cgi.hdf.setValue('svntrac.href.logout', href.logout())
        self.cgi.hdf.setValue('svntrac.version', '0.0.1')

        
        self.cgi.hdf.setValue('header_logo.link',
                              self.config['header_logo']['link'])
        self.cgi.hdf.setValue('header_logo.alt',
                              self.config['header_logo']['alt'])
        if self.config['header_logo']['src'][0] == '/':
            self.cgi.hdf.setValue('header_logo.src',
                                  self.config['header_logo']['src'])
        else:
            self.cgi.hdf.setValue('header_logo.src',
                                  self.config['general']['htdocs_location']
                                  + '/' + self.config['header_logo']['src'])
        self.cgi.hdf.setValue('header_logo.width',
                              self.config['header_logo']['width'])
        self.cgi.hdf.setValue('header_logo.height',
                              self.config['header_logo']['height'])
        self.cgi.hdf.setValue('svntrac.href.logout', href.logout())
        
        templates_dir = self.config['general']['templates_dir']
        self.cgi.hdf.setValue('hdf.loadpaths.0', templates_dir)
        tmpl_filename = os.path.join (templates_dir, self.template_name)

        self.cgi.display(tmpl_filename)

        
