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

import os
import pkg_resources
import unittest

from trac.search.web_ui import SearchModule
from trac.test import EnvironmentStub, MockRequest
from trac.ticket.model import Ticket
from trac.ticket.test import insert_ticket
from trac.ticket.web_ui import TicketModule
from trac.wiki.admin import WikiAdmin
from trac.wiki.web_ui import WikiModule
from trac.web.api import RequestDone


class SearchModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.search_module = SearchModule(self.env)
        pages_dir = pkg_resources.resource_filename('trac.wiki',
                                                    'default-pages')
        for page_name in ('WikiStart', 'TracModWSGI'):
            page = os.path.join(pages_dir, page_name)
            WikiAdmin(self.env).import_page(page, page_name)

    def tearDown(self):
        self.env.reset_db()

    def _insert_ticket(self, **kw):
        """Helper for inserting a ticket into the database"""
        return insert_ticket(self.env, **kw)

    def test_process_request_page_in_range(self):
        for _ in range(21):
            self._insert_ticket(summary="Trac")
        req = MockRequest(self.env,
                          args={'page': '3', 'q': 'Trac', 'ticket': 'on'})

        data = self.search_module.process_request(req)[1]

        self.assertEqual([], req.chrome['warnings'])
        self.assertEqual(2, data['results'].page)

    def test_process_request_page_out_of_range(self):
        """Out of range value for page defaults to page 1."""
        for _ in range(20):
            self._insert_ticket(summary="Trac")
        req = MockRequest(self.env,
                          args={'page': '3', 'q': 'Trac', 'ticket': 'on'})

        data = self.search_module.process_request(req)[1]

        self.assertIn("Page 3 is out of range.", req.chrome['warnings'])
        self.assertEqual(0, data['results'].page)

    def test_camelcase_quickjump(self):
        """CamelCase word does quick-jump."""
        req = MockRequest(self.env, args={'q': 'WikiStart'})

        self.assertRaises(RequestDone,
                          self.search_module.process_request, req)

        self.assertEqual('http://example.org/trac.cgi/wiki/WikiStart',
                         req.headers_sent['Location'])
        self.assertIn("You arrived here through", req.chrome['notices'][0])
        self.assertIn('<a href="/trac.cgi/search?'
                      'q=WikiStart&amp;noquickjump=1">here</a>',
                      req.chrome['notices'][0])

    def test_non_camelcase_no_quickjump(self):
        """Non-CamelCase word does not quick-jump."""
        req = MockRequest(self.env, args={'q': 'TracModWSGI'})

        data = self.search_module.process_request(req)[1]

        results = list(data['results'])
        self.assertIsNone(data['quickjump'])
        self.assertEqual('TracModWSGI', data['query'])
        self.assertEqual(1, len(results))
        self.assertEqual('/trac.cgi/wiki/TracModWSGI', results[0]['href'])
        self.assertEqual([], req.chrome['notices'])


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(SearchModuleTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
