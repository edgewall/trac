# -*- coding: utf-8 -*-
#
# Copyright (C) 2016 Edgewall Software
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

import trac.tests.compat
from trac.perm import DefaultPermissionStore, PermissionCache
from trac.test import EnvironmentStub, Mock, MockPerm, locale_en
from trac.util.datefmt import utc
from trac.web.api import _RequestArgs, HTTPBadRequest, RequestDone
from trac.wiki.model import WikiPage
from trac.wiki.web_ui import ReadonlyWikiPolicy, WikiModule


class ReadonlyWikiPolicyTestCase(unittest.TestCase):

    def setUp(self):
        self.env = \
            EnvironmentStub(enable=['trac.attachment.LegacyAttachmentPolicy',
                                    'trac.perm.*',
                                    'trac.wiki.web_ui.ReadonlyWikiPolicy'])
        self.policy = ReadonlyWikiPolicy(self.env)
        store = DefaultPermissionStore(self.env)
        store.grant_permission('user1', 'WIKI_ADMIN')
        store.grant_permission('user2', 'WIKI_DELETE')
        store.grant_permission('user2', 'WIKI_MODIFY')
        store.grant_permission('user2', 'WIKI_RENAME')
        self.page = WikiPage(self.env, 'SomePage')
        self.page.text = 'This is a readonly page.'
        self.page.readonly = 1
        self.page.save('user', 'readonly page added', '127.0.0.1')

    def test_check_permission_returns_none(self):
        perm_cache = PermissionCache(self.env, 'user1')
        self.assertIn('WIKI_ADMIN', perm_cache)
        for perm in ('WIKI_DELETE', 'WIKI_MODIFY', 'WIKI_RENAME'):
            self.assertNotIn(perm, perm_cache)
            self.assertIsNone(
                self.policy.check_permission(perm, perm_cache.username,
                                             self.page.resource, perm_cache))

    def test_check_permission_returns_false(self):
        perm_cache = PermissionCache(self.env, 'user2')
        self.assertNotIn('WIKI_ADMIN', perm_cache)
        for perm in ('WIKI_DELETE', 'WIKI_MODIFY', 'WIKI_RENAME'):
            self.assertIn(perm, perm_cache)
            self.assertIs(False,
                          self.policy.check_permission(perm,
                                                       perm_cache.username,
                                                       self.page.resource,
                                                       perm_cache))


class WikiModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def _create_request(self, authname='anonymous', **kwargs):
        kw = {'path_info': '/', 'perm': MockPerm(), 'args': _RequestArgs(),
              'href': self.env.href, 'abs_href': self.env.abs_href,
              'tz': utc, 'locale': None, 'lc_time': locale_en,
              'session': {}, 'authname': authname,
              'chrome': {'notices': [], 'warnings': []},
              'method': None, 'get_header': lambda v: None, 'is_xhr': False,
              'form_token': None}
        if 'args' in kwargs:
            kw['args'].update(kwargs.pop('args'))
        kw.update(kwargs)
        def redirect(url, permanent=False):
            raise RequestDone
        return Mock(add_redirect_listener=lambda x: [].append(x),
                    redirect=redirect, **kw)

    def test_invalid_post_request_raises_exception(self):
        req = self._create_request(method='POST', action=None)

        self.assertRaises(HTTPBadRequest,
                          WikiModule(self.env).process_request, req)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ReadonlyWikiPolicyTestCase))
    suite.addTest(unittest.makeSuite(WikiModuleTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
