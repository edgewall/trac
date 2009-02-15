# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2009 Edgewall Software
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

from genshi.builder import tag

from trac.core import *
from trac.perm import IPermissionRequestor
from trac.util.translation import _
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
               tag.a(_('About Trac'), href=req.href.about()))

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['CONFIG_VIEW']

    # IRequestHandler methods

    def match_request(self, req):
        return re.match(r'/about(?:_trac)?(?:/.+)?$', req.path_info)

    def process_request(self, req):
        data = {}

        if 'CONFIG_VIEW' in req.perm('config', 'systeminfo'):
            # Collect system information
            data['systeminfo'] = self.env.systeminfo

        if 'CONFIG_VIEW' in req.perm('config', 'ini'):
            # Collect config information
            sections = []
            for section in self.config.sections():
                options = []
                default_options = self.config.defaults().get(section)
                for name,value in self.config.options(section):
                    default = default_options and default_options.get(name) or ''
                    options.append({
                        'name': name, 'value': value,
                        'modified': unicode(value) != unicode(default)
                    })
                options.sort(lambda x,y: cmp(x['name'], y['name']))
                sections.append({'name': section, 'options': options})
            sections.sort(lambda x,y: cmp(x['name'], y['name']))
            data['config'] = sections

        return 'about.html', data, None
