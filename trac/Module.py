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
import time
from util import *
from Href import href
from __init__ import __version__

class Module:
    def __init__(self, config, args):
        self.config = config
        self.args = args

    def run(self):
        self.req.hdf.setValue('cgi_location', self.cgi_location)
        self.render_global()
        self.render()
        try:
            disp = getattr(self, 'display_' + self.args['format'])
        except (KeyError,AttributeError):
            disp = self.display
        disp()
        
    def render (self):
        """
        Override this function to add data the template requires
        to self.req.hdf.
        """
        pass
    
    def render_global (self):
        sql_to_hdf(self.db, "SELECT name FROM enum WHERE type='priority' ORDER BY value",
                   self.req.hdf, 'enums.priority')
        sql_to_hdf(self.db, "SELECT name FROM enum WHERE type='severity' ORDER BY value",
                   self.req.hdf, 'enums.severity')
        
        self.req.hdf.setValue('htdocs_location', self.config['general']['htdocs_location'])
        self.req.hdf.setValue('project.name', self.config['project']['name'])
        self.req.hdf.setValue('project.descr', self.config['project']['descr'])
        self.req.hdf.setValue('trac.active_module', self._name)
        self.req.hdf.setValue('trac.authname', self.authname)
        self.req.hdf.setValue('trac.href.wiki', href.wiki())
        self.req.hdf.setValue('trac.href.browser', href.browser('/'))
        self.req.hdf.setValue('trac.href.timeline', href.timeline())
        self.req.hdf.setValue('trac.href.report', href.report())
        self.req.hdf.setValue('trac.href.newticket', href.newticket())
        self.req.hdf.setValue('trac.href.search', href.search())
        self.req.hdf.setValue('trac.href.about', href.about())
        self.req.hdf.setValue('trac.href.about_config', href.about('config/'))
        self.req.hdf.setValue('trac.href.login', href.login())
        self.req.hdf.setValue('trac.href.logout', href.logout())
        self.req.hdf.setValue('trac.href.homepage', 'http://trac.edgewall.com/')
        self.req.hdf.setValue('trac.version', __version__)
        self.req.hdf.setValue('trac.time',
                              time.strftime('%c', time.localtime()))
        self.req.hdf.setValue('trac.time.gmt',
                              time.strftime('%a, %d %b %Y %H:%M:%S GMT',
                                            time.gmtime()))

        
        self.req.hdf.setValue('header_logo.link',
                              self.config['header_logo']['link'])
        self.req.hdf.setValue('header_logo.alt',
                              self.config['header_logo']['alt'])
        if self.config['header_logo']['src'][0] == '/':
            self.req.hdf.setValue('header_logo.src',
                                  self.config['header_logo']['src'])
        else:
            self.req.hdf.setValue('header_logo.src',
                                  self.config['general']['htdocs_location']
                                  + '/' + self.config['header_logo']['src'])
        self.req.hdf.setValue('header_logo.width',
                              self.config['header_logo']['width'])
        self.req.hdf.setValue('header_logo.height',
                              self.config['header_logo']['height'])
        self.req.hdf.setValue('trac.href.logout', href.logout())

        templates_dir = self.config['general']['templates_dir']
        self.req.hdf.setValue('hdf.loadpaths.0', templates_dir)

    def display(self):
        self.req.display(self.template_name)

    def display_hdf(self):
        def hdf_tree_walk(node,prefix=''):
            while node: 
                np = (prefix and prefix+'.' or '') + (node.name() or '')
                nvalue = node.value()
                if nvalue: result.append((np, nvalue))
                hdf_tree_walk(node.child(), np)
                node = node.next()
        self.req.send_response(200)
        self.req.send_header('Content-Type', 'text/plain')
        self.req.end_headers()
        result = []
        hdf_tree_walk (self.req.hdf)
        result.sort()
        for (name,value) in result:
            self.req.write(name)
            if value.find('\n') == -1:
                self.req.write('= %s\r\n' % value)
            else:
                self.req.write('<< EOM\r\n%s\r\nEOM\r\n' % value)
        
