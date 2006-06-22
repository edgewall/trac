# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2006 Edgewall Software
# Copyright (C) 2004-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004-2005 Daniel Lundin <daniel@edgewall.com>
# Copyright (C) 2005-2006 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Jonas Borgström <jonas@edgewall.com>
#         Christopher Lenz <cmlenz@gmx.de>

import re

from trac.core import *
from trac.perm import IPermissionRequestor
from trac.web import IRequestHandler
from trac.util.markup import html
from trac.web.chrome import add_stylesheet, INavigationContributor


class AboutModule(Component):
    """Provides various about pages."""

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'about'

    def get_navigation_items(self, req):
        yield ('metanav', 'about',
               html.a('About Trac', href=req.href.about()))

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['CONFIG_VIEW']

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'/about(?:_trac)?(?:/(.*))?$', req.path_info)
        if match:
            if match.group(1):
                req.args['page'] = match.group(1)
            return True

    def process_request(self, req):
        page = req.args.get('page', 'default')
        req.hdf['title'] = 'About Trac'
        if req.perm.has_permission('CONFIG_VIEW'):
            req.hdf['about.config_href'] = req.href.about('config')
            req.hdf['about.plugins_href'] = req.href.about('plugins')
        if page == 'config':
            self._render_config(req)
        elif page == 'plugins':
            self._render_plugins(req)

        add_stylesheet(req, 'common/css/about.css')
        return 'about.cs', None

    # Internal methods

    def _render_config(self, req):
        req.perm.assert_permission('CONFIG_VIEW')
        req.hdf['about.page'] = 'config'
        
        # Export the config table to hdf
        sections = []
        for section in self.config.sections():
            options = []
            default_options = self.config.defaults().get(section)
            for name,value in self.config.options(section):
                default = default_options and default_options.get(name) or ''
                options.append({
                    'name': name, 'value': value,
                    'valueclass': (unicode(value) == unicode(default) 
                                   and 'defaultvalue' or 'value')})
            options.sort(lambda x,y: cmp(x['name'], y['name']))
            sections.append({'name': section, 'options': options})
        sections.sort(lambda x,y: cmp(x['name'], y['name']))
        req.hdf['about.config'] = sections
        # TODO:
        # We should probably export more info here like:
        # permissions, components...

    def _render_plugins(self, req):
        try:
            from trac.wiki.formatter import wiki_to_html
            import inspect
            def getdoc(obj):
                return wiki_to_html(inspect.getdoc(obj), self.env, req)
        except:
            def getdoc(obj):
                return obj.__doc__
        req.perm.assert_permission('CONFIG_VIEW')
        import sys
        req.hdf['about.page'] = 'plugins'
        from trac.core import ComponentMeta
        plugins = []
        for component in ComponentMeta._components:
            if not self.env.is_component_enabled(component):
                continue
            plugin = {'name': component.__name__}
            if component.__doc__:
                plugin['description'] = getdoc(component)

            module = sys.modules[component.__module__]
            plugin['module'] = module.__name__
            if hasattr(module, '__file__'):
                plugin['path'] = module.__file__

            xtnpts = []
            for name, xtnpt in [(attr, getattr(component, attr)) for attr
                                in dir(component)]:
                if not isinstance(xtnpt, ExtensionPoint):
                    continue
                xtnpts.append({'name': name,
                               'interface': xtnpt.interface.__name__,
                               'module': xtnpt.interface.__module__})
                if xtnpt.interface.__doc__:
                    xtnpts[-1]['description'] = getdoc(xtnpt.interface)
                extensions = []
                for extension in ComponentMeta._registry.get(xtnpt.interface, []):
                    if self.env.is_component_enabled(extension):
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
