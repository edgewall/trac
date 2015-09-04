# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import unittest

from trac.resource import ResourceNotFound
from trac.test import EnvironmentStub, Mock, MockPerm, locale_en
from trac.ticket.admin import ComponentAdminPanel
from trac.ticket.model import Component
from trac.util.datefmt import utc
from trac.web.api import RequestDone, _RequestArgs


class ComponentAdminPanelTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)

    def tearDown(self):
        self.env.reset_db()

    def _create_request(self, authname='anonymous', **kwargs):
        kw = {'path_info': '/', 'perm': MockPerm(), 'args': _RequestArgs(),
              'href': self.env.href, 'abs_href': self.env.abs_href,
              'tz': utc, 'locale': None, 'lc_time': locale_en,
              'session': {}, 'authname': authname,
              'chrome': {'notices': [], 'warnings': []},
              'method': None, 'get_header': lambda v: None, 'is_xhr': False,
              'form_token': None, }
        if 'args' in kwargs:
            kw['args'].update(kwargs.pop('args'))
        kw.update(kwargs)
        def redirect(url, permanent=False):
            raise RequestDone
        return Mock(add_redirect_listener=lambda x: [].append(x),
                    redirect=redirect, **kw)

    def test_add_component(self):
        cap = ComponentAdminPanel(self.env)
        name, owner = 'component3', 'user3'
        req = self._create_request(method='POST',
                                   args={'name': name, 'owner': owner,
                                         'add': True})

        self.assertRaises(ResourceNotFound, Component, self.env, name)
        self.assertRaises(RequestDone, cap.render_admin_panel, req,
                          'ticket', 'component', None)
        component = Component(self.env, name)
        self.assertEqual(name, component.name)
        self.assertEqual(owner, component.owner)

    def test_remove_component(self):
        cap = ComponentAdminPanel(self.env)
        name = 'component2'
        req = self._create_request(method='POST',
                                   args={'sel': name, 'remove': True})

        component = Component(self.env, name)
        self.assertEqual(name, component.name)
        self.assertEqual('somebody', component.owner)
        self.assertRaises(RequestDone, cap.render_admin_panel, req,
                          'ticket', 'component', None)
        self.assertRaises(ResourceNotFound, Component, self.env, name)

    def test_remove_multiple_components(self):
        cap = ComponentAdminPanel(self.env)
        names = ['component1', 'component2']
        req = self._create_request(method='POST',
                                   args={'sel': names, 'remove': True})

        for name in names:
            component = Component(self.env, name)
            self.assertEqual(name, component.name)
            self.assertEqual('somebody', component.owner)
        self.assertRaises(RequestDone, cap.render_admin_panel, req,
                          'ticket', 'component', None)
        for name in names:
            self.assertRaises(ResourceNotFound, Component, self.env, name)


def suite():
    return unittest.makeSuite(ComponentAdminPanelTestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
