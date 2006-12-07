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
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Jonas Borgström <jonas@edgewall.com>
#         Christopher Lenz <cmlenz@gmx.de>

import re

from genshi import Markup
from genshi.builder import tag

from trac.core import *
from trac.perm import IPermissionRequestor
from trac.web import IRequestHandler
from trac.web.chrome import INavigationContributor


class AboutModule(Component):
    """Provides various about pages."""

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'about'

    def get_navigation_items(self, req):
        yield ('metanav', 'about',
               tag.a('About Trac', href=req.href.about()))

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
        if page == 'config':
            data = self._render_config(req)
        elif page == 'systeminfo':
            data = self._render_systeminfo(req)
        else:
            data = {}

        return 'about.html', {'about': data}, None

    # Internal methods

    def _render_config(self, req):
        req.perm.assert_permission('CONFIG_VIEW')
        data = {'page': 'config'}
        
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
        data['config'] = sections
        return data

    def _render_systeminfo(self, req):
        req.perm.assert_permission('CONFIG_VIEW')
        data = {'page': 'systeminfo', 'systeminfo': self.env.systeminfo}
        return data
