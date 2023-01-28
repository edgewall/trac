# -*- coding: utf-8 -*-
#
# Copyright (C) 2021-2023 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import unittest

from trac.test import EnvironmentStub, MockRequest, makeSuite
from trac.util.html import Markup
from trac.web.api import RequestDone
from trac.wiki.intertrac import InterTracDispatcher
from trac.wiki.model import WikiPage


class InterTracDispatcherTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.dispatcher = InterTracDispatcher(self.env)

    def tearDown(self):
        self.env.reset_db()

    def _assert_dispatch(self, wikitext, redirected):
        req = MockRequest(self.env, path_info='/intertrac/' + wikitext)
        results = []
        def listener(*args):
            results.append(args)
        req.add_redirect_listener(listener)
        self.assertTrue(self.dispatcher.match_request(req))
        try:
            self.dispatcher.process_request(req)
            self.fail('RequestDone not raised')
        except RequestDone:
            self.assertEqual(1, len(results))
            url = results[0][1]
            self.assertNotIsInstance(url, Markup)
            self.assertIsInstance(url, str)
            self.assertEqual(redirected, url)

    def _save_wikipage(self, name, text='content\r\n'):
        page = WikiPage(self.env, name)
        page.text = text
        page.save('john', '')
        return page

    def test_normal(self):
        with self.env.db_transaction:
            self._save_wikipage('WikiStart', 'content\r\n')
            self._save_wikipage('WikiStart', 'content\r\n' * 2)
        self._assert_dispatch('WikiStart@1',
                              '/trac.cgi/wiki/WikiStart?version=1')

    def test_with_ampersand_character(self):
        with self.env.db_transaction:
            self._save_wikipage('Page&Name')
            self._save_wikipage('Page&mp;Name')
        self._assert_dispatch('wiki:Page&Name', '/trac.cgi/wiki/Page%26Name')
        self._assert_dispatch('wiki:Page&amp;Name',
                              '/trac.cgi/wiki/Page%26amp%3BName')


def test_suite():
    return makeSuite(InterTracDispatcherTestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
