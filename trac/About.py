# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004, 2005 Edgewall Software
# Copyright (C) 2004, 2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004, 2005 Daniel Lundin <daniel@edgewall.com>
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
#         Christopher Lenz <cmlenz@gmx.de>

from __future__ import generators
import re

from trac import perm
from trac.core import *
from trac.web.chrome import add_stylesheet, INavigationContributor
from trac.web.main import IRequestHandler


class AboutModule(Component):
    """
    Provides various about pages.
    """

    implements(INavigationContributor, IRequestHandler)

    about_cs = """
<?cs include "header.cs"?>
<div id="ctxtnav" class="nav">
 <h2>About Navigation</h2>
 <ul>
  <li class="first<?cs if:!about.config_href ?> last<?cs /if ?>"><a href="<?cs
    var:trac.href.about ?>">Overview</a></li><?cs
  if:about.config_href ?>
   <li><a href="<?cs var:about.config_href ?>">Configuration</a></li><?cs
  /if ?><?cs
  if:about.plugins_href ?>
   <li class="last"><a href="<?cs var:about.plugins_href ?>">Plugins</a></li><?cs
  /if ?>
 </ul>
</div>
<div id="content" class="about<?cs if:about.page ?>_<?cs var:about.page ?><?cs /if ?>">

 <?cs if:about.page == "config"?>
  <h1>Configuration</h1>
  <table><thead><tr><th class="section">Section</th>
   <th class="name">Name</th><th class="value">Value</th></tr></thead><?cs
  each:section = about.config ?>
   <tr><th rowspan="<?cs var:len(section.options) ?>"><?cs var:section.name ?></th><?cs
   each:option = section.options ?><?cs if:name(option) != 0 ?><tr><?cs /if ?>
    <td><?cs var:option.name ?></td>
    <td><?cs var:option.value ?></td>
   </tr><?cs /each ?><?cs
  /each ?></table>
  <div id="help">
   See <a href="<?cs var:trac.href.wiki ?>/TracIni">TracIni</a> for information about
   the configuration.
  </div>

 <?cs elif:about.page == "plugins" ?>
  <h1>Plugins</h1>
  <dl id="plugins"><?cs
   each:plugin = about.plugins ?>
    <h2 id="<?cs var:plugin.module ?>.<?cs var:plugin.name ?>"><?cs var:plugin.name ?></h2>
    <table>
     <tr>
      <th class="module" scope="row">Module</th>
      <td class="module"><?cs var:plugin.module ?><br />
      <span class="path"><?cs var:plugin.path ?></span></td>
     </tr><?cs
     if:plugin.description ?><tr>
      <th class="description" scope="row">Description</th>
      <td class="description"><?cs var:plugin.description ?></td>
     </tr><?cs /if ?><?cs
     if:len(plugin.extension_points) ?><tr>
      <th class="xtnpts">Extension points:</th>
      <td class="xtnpts"><ul><?cs each:extension_point = plugin.extension_points ?>
       <li>
        <code><?cs var:extension_point.module ?>.<?cs var:extension_point.interface ?></code><?cs
         if:len(extension_point.extensions) ?> (<?cs
          var:len(extension_point.extensions) ?> extensions)<ul><?cs
          each:extension = extension_point.extensions ?>
           <li><a href="#<?cs var:extension.module ?>.<?cs
             var:extension.name ?>"><?cs var:extension.name ?></a></li><?cs
          /each ?></ul><?cs
         /if ?>
       </li><?cs
      /each ?></ul></td></tr><?cs
     /if ?>
    </table><?cs
   /each ?>
  </dl>

 <?cs else ?>
  <a href="http://trac.edgewall.com" style="border: none; float: right; margin-left: 2em">
   <img style="display: block" src="<?cs var:htdocs_location ?>trac_banner.png"
     alt="Trac: Integrated SCM &amp; Project Management"/>
  </a>
<h1>About Trac <?cs var:trac.version ?></h1>
<p>
Trac is a web-based software project management and bug/issue
tracking system emphasizing ease of use and low ceremony. 
It provides an interface to the Subversion revision control systems, integrated Wiki and convenient report facilities. 
</p>
  <p>Trac is distributed under the GNU General Public License (GPL).<br />
  The entire text of the license should be found in the COPYING file,
  included in the package.</p>
  <p>Please visit the Trac open source project: 
  <a href="http://projects.edgewall.com/trac/">http://projects.edgewall.com/trac/</a></p>
  <p>Trac is a product of <a href="http://www.edgewall.com/">Edgewall
  Software</a>, provider of professional Linux and software development
  services.</p>
  <p>Copyright &copy; 2003-2005 <a href="http://www.edgewall.com/">Edgewall
  Software</a></p>
  <a href="http://www.edgewall.com/">
   <img style="display: block; margin: 30px" src="<?cs var:htdocs_location ?>edgewall.png"
     alt="Edgewall Software"/></a>
 <?cs /if ?>
</div>
<?cs include "footer.cs"?>
""" # about_cs

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'about'

    def get_navigation_items(self, req):
        yield 'metanav', 'about', '<a href="%s" accesskey="9">About Trac</a>' \
              % self.env.href.about()

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'/about(?:_trac)?(?:/(.*))?$', req.path_info)
        if match:
            if match.group(1):
                req.args['page'] = match.group(1)
            return 1

    def process_request(self, req):
        page = req.args.get('page', 'default')
        req.hdf['title'] = 'About Trac'
        if req.perm.has_permission(perm.CONFIG_VIEW):
            req.hdf['about.config_href'] = self.env.href.about('config')
            req.hdf['about.plugins_href'] = self.env.href.about('plugins')
        if page == 'config':
            self._render_config(req)
        elif page == 'plugins':
            self._render_plugins(req)

        add_stylesheet(req, 'about.css')
        template = req.hdf.parse(self.about_cs)
        return template, None

    # Internal methods

    def _render_config(self, req):
        req.perm.assert_permission(perm.CONFIG_VIEW)
        req.hdf['about.page'] = 'config'
        # Export the config table to hdf
        sections = []
        for section in self.config.sections():
            options = []
            for name,value in self.config.options(section):
                options.append({'name': name, 'value': value})
            options.sort(lambda x,y: cmp(x['name'], y['name']))
            sections.append({'name': section, 'options': options})
        sections.sort(lambda x,y: cmp(x['name'], y['name']))
        req.hdf['about.config'] = sections
        # TODO:
        # We should probably export more info here like:
        # permissions, components...

    def _render_plugins(self, req):
        req.perm.assert_permission(perm.CONFIG_VIEW)
        import sys
        req.hdf['about.page'] = 'plugins'
        from trac.core import ComponentMeta
        plugins = []
        for component in ComponentMeta._components:
            if not self.env.is_component_enabled(component):
                continue
            plugin = {'name': component.__name__}
            if component.__doc__:
                plugin['description'] = component.__doc__

            module = sys.modules[component.__module__]
            plugin['module'] = module.__name__
            if hasattr(module, '__file__'):
                plugin['path'] = module.__file__

            xtnpts = []
            for name, xtnpt in component._extension_points.items():
                xtnpts.append({'name': name,
                               'interface': xtnpt.interface.__name__,
                               'module': xtnpt.interface.__module__})
                if xtnpt.interface.__doc__:
                    xtnpts[-1]['description'] = xtnpt.interface.__doc__
                extensions = []
                for extension in ComponentMeta._registry.get(xtnpt.interface, []):
                    extensions.append({'name': extension.__name__,
                                       'module': extension.__module__})
                xtnpts[-1]['extensions'] = extensions
            xtnpts.sort(lambda x,y: cmp(x['name'], y['name']))
            plugin['extension_points'] = xtnpts

            plugins.append(plugin)

        def plugincmp(x, y):
            c = cmp(len(x['module'].split('.')), len(y['module'].split('.')))
            if c == 0:
                c = cmp(x['module'].lower(), y['module'].lower())
                if c == 0:
                    c = cmp(x['name'].lower(), y['name'].lower())
            return c
        plugins.sort(plugincmp)

        req.hdf['about.plugins'] = plugins
