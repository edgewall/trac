# -*- coding: utf-8 -*-
#
# Copyright (C) 2016-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import re
import unittest

from trac.perm import DefaultPermissionStore, PermissionCache
from trac.test import EnvironmentStub, MockRequest
from trac.web.api import HTTPBadRequest
from trac.web.chrome import Chrome
from trac.wiki.model import WikiPage
from trac.wiki.web_ui import DefaultWikiPolicy, WikiModule


class DefaultWikiPolicyTestCase(unittest.TestCase):

    def setUp(self):
        self.env = \
            EnvironmentStub(enable=['trac.attachment.LegacyAttachmentPolicy',
                                    'trac.perm.*',
                                    'trac.wiki.web_ui.*'])
        self.env.config.set('trac', 'permission_policies',
                            'DefaultWikiPolicy,DefaultPermissionPolicy')
        self.policy = DefaultWikiPolicy(self.env)
        store = DefaultPermissionStore(self.env)
        store.grant_permission('user1', 'WIKI_ADMIN')
        store.grant_permission('user2', 'WIKI_DELETE')
        store.grant_permission('user2', 'WIKI_MODIFY')
        store.grant_permission('user2', 'WIKI_RENAME')
        self.page = WikiPage(self.env, 'SomePage')
        self.page.text = 'This is a readonly page.'
        self.page.readonly = 1
        self.page.save('user', 'readonly page added')

    def test_user_with_wiki_admin_can_modify_readonly_page(self):
        """User with WIKI_ADMIN cannot modify a readonly page."""
        perm_cache = PermissionCache(self.env, 'user1', self.page.resource)
        self.assertIn('WIKI_ADMIN', perm_cache)
        for perm in ('WIKI_DELETE', 'WIKI_MODIFY', 'WIKI_RENAME'):
            self.assertIn(perm, perm_cache)
            self.assertIsNone(
                self.policy.check_permission(perm, perm_cache.username,
                                             self.page.resource, perm_cache))

    def test_user_without_wiki_admin_cannot_modify_readonly_page(self):
        """User without WIKI_ADMIN cannot modify a readonly page."""
        perm_cache = PermissionCache(self.env, 'user2', self.page.resource)
        self.assertNotIn('WIKI_ADMIN', perm_cache)
        for perm in ('WIKI_DELETE', 'WIKI_MODIFY', 'WIKI_RENAME'):
            self.assertNotIn(perm, perm_cache)
            self.assertFalse(
                self.policy.check_permission(perm, perm_cache.username,
                                             self.page.resource, perm_cache))


class WikiModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def _insert_templates(self):
        page = WikiPage(self.env)
        page.name = 'PageTemplates/TheTemplate'
        page.text = 'The template below /PageTemplates'
        page.save('trac', 'create page')
        page = WikiPage(self.env)
        page.name = 'TheTemplate'
        page.text = 'The template below /'
        page.save('trac', 'create page')

    def tearDown(self):
        self.env.reset_db()

    def test_invalid_post_request_raises_exception(self):
        req = MockRequest(self.env, method='POST', action=None)

        self.assertRaises(HTTPBadRequest,
                          WikiModule(self.env).process_request, req)

    def test_invalid_get_request_raises_exception(self):
        req = MockRequest(self.env, method='GET', action=None,
                          args=dict(version='a', old_version='1'))

        with self.assertRaises(HTTPBadRequest) as cm:
            WikiModule(self.env).process_request(req)
        self.assertEqual("400 Bad Request (Invalid value for request argument "
                         "<em>version</em>.)", unicode(cm.exception))

        req = MockRequest(self.env, method='GET', action=None,
                          args=dict(version='2', old_version='a'))

        with self.assertRaises(HTTPBadRequest) as cm:
            WikiModule(self.env).process_request(req)
        self.assertEqual("400 Bad Request (Invalid value for request argument "
                         "<em>old_version</em>.)", unicode(cm.exception))

    def test_wiki_template_relative_path(self):
        self._insert_templates()
        req = MockRequest(self.env, path_info='/wiki/NewPage', method='GET',
                          args={'action': 'edit', 'page': 'NewPage',
                                'template': 'TheTemplate'})

        resp = WikiModule(self.env).process_request(req)

        self.assertEqual('The template below /PageTemplates',
                         resp[1]['page'].text)

    def test_wiki_template_absolute_path(self):
        self._insert_templates()
        req = MockRequest(self.env, path_info='/wiki/NewPage', method='GET',
                          args={'action': 'edit', 'page': 'NewPage',
                                'template': '/TheTemplate'})

        resp = WikiModule(self.env).process_request(req)

        self.assertEqual('The template below /', resp[1]['page'].text)

    def test_edit_action_with_empty_verion(self):
        """Universal edit button requires request with parameters string
        ?action=edit&version= and ?action=view&version= (#12937)
        """
        req = MockRequest(self.env, path_info='/wiki/NewPage', method='GET',
                          args={'action': 'view', 'version': '',
                                'page': 'NewPage'})

        resp = WikiModule(self.env).process_request(req)

        self.assertEqual('wiki_view.html', resp[0])
        self.assertIsNone(resp[1]['version'])
        self.assertEqual('NewPage', resp[1]['page'].name)

        req = MockRequest(self.env, path_info='/wiki/NewPage', method='GET',
                          args={'action': 'edit', 'version': '',
                                'page': 'NewPage'})

        resp = WikiModule(self.env).process_request(req)

        self.assertEqual('wiki_edit.html', resp[0])
        self.assertNotIn('version', resp[1])
        self.assertEqual('NewPage', resp[1]['page'].name)

    def test_wiki_page_path(self):
        for name in ('WikiStart', 'Page', 'Page/SubPage'):
            page = WikiPage(self.env)
            page.name = name
            page.text = 'Contents for %s\n' % name
            page.save('trac', 'create page')

        def get_pagepath(path_info):
            content = self._render_wiki_page(path_info)
            match = re.search(r'<div\s+id="pagepath"[^>]*>.*?</div>', content,
                              re.DOTALL)
            return match and match.group(0)

        pagepath = get_pagepath('/wiki')
        self.assertIn(' href="/trac.cgi/wiki">wiki:</a>', pagepath)
        self.assertIn(' href="/trac.cgi/wiki/WikiStart"', pagepath)
        pagepath = get_pagepath('/wiki/Page')
        self.assertIn(' href="/trac.cgi/wiki">wiki:</a>', pagepath)
        self.assertIn(' href="/trac.cgi/wiki/Page"', pagepath)
        pagepath = get_pagepath('/wiki/Page/SubPage')
        self.assertIn(' href="/trac.cgi/wiki">wiki:</a>', pagepath)
        self.assertIn(' href="/trac.cgi/wiki/Page"', pagepath)
        self.assertIn(' href="/trac.cgi/wiki/Page/SubPage"', pagepath)

    def _render_wiki_page(self, path_info):
        req = MockRequest(self.env, path_info=path_info, method='GET')
        mod = WikiModule(self.env)
        self.assertTrue(mod.match_request(req))
        resp = mod.process_request(req)
        self.assertEqual(2, len(resp))
        content = Chrome(self.env).render_template(req, resp[0], resp[1],
                                                   {'iterable': False,
                                                    'fragment': False})
        return content.decode('utf-8')


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(DefaultWikiPolicyTestCase))
    suite.addTest(unittest.makeSuite(WikiModuleTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
