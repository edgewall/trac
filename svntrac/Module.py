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
import StringIO
from Toolbar import Toolbar

class Module:
    def __init__(self, config, args, pool):
        self.config = config
        self.args   = args
        self.pool   = pool
        
        self.toolbar = Toolbar()

        self.namespace = {}
        self.namespace['title'] = ''
        self.namespace['svntrac_url'] = 'http://svntrac.xyche.com/'
        self.namespace['htdocs_location'] = config.get('general',
                                                       'htdocs_location')

    def render (self):
        """
        this function can be overridden to fill self.namespace with
        useful content.
        """
        pass

    def apply_template (self):
        svntrac_home = self.config.get('general', 'svntrac_home')
        tmpl_filename = self.config.get('templates', self.template_key)
        tmpl_filename = os.path.join (svntrac_home, tmpl_filename)

        self.namespace['toolbar'] = self.toolbar.render ()

        header_tmpl = self.config.get('templates', 'header_template')
        footer_tmpl = self.config.get('templates', 'footer_template')
        header_tmpl = os.path.join (svntrac_home, header_tmpl)
        footer_tmpl = os.path.join (svntrac_home, footer_tmpl)
        
        header = open(header_tmpl).read()
        footer = open(footer_tmpl).read()
        
        self.namespace['header'] = header % self.namespace
        self.namespace['footer'] = footer % self.namespace
        template = open(tmpl_filename).read ()
        # Apply the template
        out = template % self.namespace
        print 'Content-type: text/html\r\n\r\n'
        print out
        
