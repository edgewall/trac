# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2005 Edgewall Software
# Copyright (C) 2004-2005 Daniel Lundin <daniel@edgewall.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Daniel Lundin <daniel@edgewall.com>

from trac.core import *
from trac.util.markup import html
from trac.web import IRequestHandler
from trac.web.chrome import INavigationContributor


class SettingsModule(Component):

    implements(INavigationContributor, IRequestHandler)

    _form_fields = ['newsid','name', 'email']

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'settings'

    def get_navigation_items(self, req):
        yield ('metanav', 'settings',
               html.A('Settings', href=req.href.settings()))

    # IRequestHandler methods

    def match_request(self, req):
        return req.path_info == '/settings'

    def process_request(self, req):
        action = req.args.get('action')

        if req.method == 'POST':
            if action == 'save':
                self._do_save(req)
            elif action == 'load':
                self._do_load(req)

        req.hdf['title'] = 'Settings'
        req.hdf['settings'] = req.session
        if req.authname == 'anonymous':
            req.hdf['settings.session_id'] = req.session.sid

        return 'settings.cs', None

    # Internal methods

    def _do_save(self, req):
        for field in self._form_fields:
            val = req.args.get(field)
            if val:
                if field == 'newsid' and val:
                    req.session.change_sid(val)
                else:
                    req.session[field] = val
        req.redirect(req.href.settings())

    def _do_load(self, req):
        if req.authname == 'anonymous':
            oldsid = req.args.get('loadsid')
            req.session.get_session(oldsid)
        req.redirect(req.href.settings())
