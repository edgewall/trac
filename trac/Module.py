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
from perm import PermissionError
import auth
import neo_cgi

class Module:
    def __init__(self, config, args, pool):
        self.config = config
        self.args = args
        self.pool = pool
        self.cgi = neo_cgi.CGI()

    def run(self):
        self.cgi.hdf.setValue('cgi_location', os.getenv('SCRIPT_NAME'))
        try:
            self.render()
            self.apply_template()
        except PermissionError, e:
            self.cgi.hdf.setValue('title', 'Permission Denied')
            self.cgi.hdf.setValue('error.type', 'permission')
            self.cgi.hdf.setValue('error.action', e.action)
            self.cgi.hdf.setValue('error.message', str(e))
            self.template_name = 'error.cs'
            Module.apply_template(self)
        except Exception, e:
            # Catch exceptions and let error.cs display
            # a pretty error message + traceback.
            import traceback, StringIO
            tb = StringIO.StringIO()
	    try:
		traceback.print_exc(file=tb)
		self.cgi.hdf.setValue('title', 'Oups')
		self.cgi.hdf.setValue('error.type', 'internal')
		self.cgi.hdf.setValue('error.message', str(e))
		self.cgi.hdf.setValue('error.traceback',tb.getvalue())
		self.template_name = 'error.cs'
		Module.apply_template(self)
	    except:
		print 'Content-Type: text/plain\r\n\r\n',
		print 'Error Message:'
		print str(e)
		print
		print 'Tracebac:'
		print tb.getvalue()
        
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
        
        self.cgi.hdf.setValue('htdocs_location',
                              self.config['general']['htdocs_location'])
        self.cgi.hdf.setValue('trac.active_module', self._name)
        self.cgi.hdf.setValue('trac.authname', auth.get_authname())
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
        self.cgi.hdf.setValue('trac.version', '0.1')

        
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
        
        templates_dir = self.config['general']['templates_dir']
        self.cgi.hdf.setValue('hdf.loadpaths.0', templates_dir)
        tmpl_filename = os.path.join (templates_dir, self.template_name)

        self.cgi.display(tmpl_filename)

        
