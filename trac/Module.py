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
from util import *
from Href import href
from __init__ import __version__
import neo_cgi

class Module:
    def __init__(self, config, args):
        self.config = config
        self.args = args
        self.cgi = neo_cgi.CGI()

    def run(self):
        self.cgi.hdf.setValue('cgi_location', self.cgi_location)
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
        to self.cgi.hdf.
        """
        pass
    
    def render_global (self):
        sql_to_hdf(self.db, "SELECT name FROM enum WHERE type='priority' ORDER BY value",
                   self.cgi.hdf, 'enums.priority')
        sql_to_hdf(self.db, "SELECT name FROM enum WHERE type='severity' ORDER BY value",
                   self.cgi.hdf, 'enums.severity')
        
        self.cgi.hdf.setValue('htdocs_location', self.config['general']['htdocs_location'])
        self.cgi.hdf.setValue('project.name', self.config['project']['name'])
        self.cgi.hdf.setValue('project.descr', self.config['project']['descr'])
        self.cgi.hdf.setValue('trac.active_module', self._name)
        self.cgi.hdf.setValue('trac.authname', self.authname)
        self.cgi.hdf.setValue('trac.href.wiki', href.wiki())
        self.cgi.hdf.setValue('trac.href.browser', href.browser('/'))
        self.cgi.hdf.setValue('trac.href.timeline', href.timeline())
        self.cgi.hdf.setValue('trac.href.report', href.report())
        self.cgi.hdf.setValue('trac.href.newticket', href.newticket())
        self.cgi.hdf.setValue('trac.href.search', href.search())
        self.cgi.hdf.setValue('trac.href.about', href.about())
        self.cgi.hdf.setValue('trac.href.about_config', href.about('config/'))
        self.cgi.hdf.setValue('trac.href.login', href.login())
        self.cgi.hdf.setValue('trac.href.logout', href.logout())
        self.cgi.hdf.setValue('trac.href.homepage', 'http://trac.edgewall.com/')
        self.cgi.hdf.setValue('trac.version', __version__)

        
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
        self.cgi.hdf.setValue('trac.href.logout', href.logout())



    def display(self):
        templates_dir = self.config['general']['templates_dir']
        self.cgi.hdf.setValue('hdf.loadpaths.0', templates_dir)
        tmpl_filename = os.path.join (templates_dir, self.template_name)
        self.cgi.display(tmpl_filename)


    def display_hdf(self):
        def hdf_tree_walk(node,prefix=''):
            while node: 
                nname = node.name()
                nvalue = node.value()
                np = (prefix and prefix+'.' or '') + (nname or '')
                if nvalue:
                    result.append("%s = %s" % (np,nvalue))
                hdf_tree_walk(node.child(), np)
                node = node.next()
        print "Content-type: text/plain\r\n"
        result = []
        hdf_tree_walk (self.cgi.hdf)
        result.sort()
        for r in result:
            print r
        
