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

from trac.search.web_ui import SearchModule
from trac.test import EnvironmentStub, MockRequest
from trac.ticket.model import Ticket
from trac.ticket.web_ui import TicketModule


class SearchModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.search_module = SearchModule(self.env)

    def tearDown(self):
        self.env.reset_db()

    def _insert_ticket(self, **kw):
        """Helper for inserting a ticket into the database"""
        ticket = Ticket(self.env)
        for k, v in kw.items():
            ticket[k] = v
        return ticket.insert()

    def test_process_request_page_in_range(self):
        for _ in range(0, 21):
            self._insert_ticket(summary="Trac")
        req = MockRequest(self.env,
                          args={'page': '3', 'q': 'Trac', 'ticket': 'on'})

        data = self.search_module.process_request(req)[1]

        self.assertEqual([], req.chrome['warnings'])
        self.assertEqual(2, data['results'].page)

    def test_process_request_page_out_of_range(self):
        """Out of range value for page defaults to page 1."""
        for _ in range(0, 20):
            self._insert_ticket(summary="Trac")
        req = MockRequest(self.env,
                          args={'page': '3', 'q': 'Trac', 'ticket': 'on'})

        data = self.search_module.process_request(req)[1]

        self.assertIn("Page 3 is out of range.", req.chrome['warnings'])
        self.assertEqual(0, data['results'].page)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(SearchModuleTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
