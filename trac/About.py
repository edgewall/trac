# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004 Edgewall Software
# Copyright (C) 2004 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004 Daniel Lundin <daniel@edgewall.com>
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

import util
import perm
from Module import Module
import neo_cgi
import neo_cs

class About (Module):
    template_name = ''

    about_cs = """
<?cs include "header.cs"?>
<div id="page-content">
<div id="subheader-links">
 <a href="<?cs var:trac.href.about ?>">About Trac</a>&nbsp;
 | <a href="<?cs var:trac.href.about_config ?>">View Config</a>&nbsp;
</div>
 <div id="main">
  <div id="main-content">
<?cs if about.page == "config"?>
  <h3>Configuration</h3>
  <table>
  <tr><th>Section</th><th>Name</th><th>Value</th></tr>
  <?cs each:item = about.config ?>
    <tr>
      <td><?cs var:item.section ?></td>
      <td><?cs var:item.name ?></td>
      <td><?cs var:item.value ?></td>
    </tr>
  <?cs /each ?>
  </table>
<?cs else ?>
  <a class="noline" href="http://trac.edgewall.com"
      style="float: right"><img src="<?cs var:htdocs_location ?>trac_banner.png" alt=""/></a>
<h1>About Trac <?cs var:trac.version ?></h1>
<p>
Trac is a web-based software project management and bug/issue
tracking system emphasizing ease of use and low ceremony. 
It provides an interface to the Subversion revision control systems, integrated Wiki and convenient report facilities. 
</p>
  <p>
  Trac is distributed under the GNU General Public License (GPL).<br />
  The entire text of the license should be found in the COPYING file,
  included in the package.
    </p>
  <p>
  Please visit the Trac open source project: 
  <a href="http://projects.edgewall.com/trac/">http://projects.edgewall.com/trac/</a>
  </p>
  <p>
  Trac is a product of <a href="http:/www.edgewall.com/">Edgewall Software</a>, provider of professional Linux and software development services.
  </p>
<p>
Copyright &copy; 2003,2004 <a href="http://www.edgewall.com/">Edgewall Software</a>
</p>
  <a class="noline" href="http://www.edgewall.com/">
   <img style="display: block; margin: 30px" src="<?cs var:htdocs_location ?>edgewall_logo_left-226x43.png"
     alt="Edgewall Software"/></a>
<?cs /if ?>
 </div>
</div>
</div>
<?cs include "footer.cs"?>
""" # about_cs
    
    def render (self):
        page = self.args.get('page', 'default')
        self.cgi.hdf.setValue('title', 'About Trac')
        if page[0:7] == '/config':
            self.perm.assert_permission(perm.CONFIG_VIEW)
            self.cgi.hdf.setValue('about.page', 'config')
            # Export the config table to hdf
            i = 0
            for section in self.config.keys():
                for name in self.config[section].keys():
                    value = self.config[section][name]
                    self.cgi.hdf.setValue('about.config.%d.section' % i, section)
                    self.cgi.hdf.setValue('about.config.%d.name' % i, name)
                    self.cgi.hdf.setValue('about.config.%d.value' % i, value)
                    i = i + 1
            # TODO:
            # We should probably export more info here like:
            # permissions, components...


    def display (self):
        cs = neo_cs.CS(self.cgi.hdf)
        cs.parseStr(self.about_cs)
        print "Content-type: text/html\r\n"
        print cs.render()
