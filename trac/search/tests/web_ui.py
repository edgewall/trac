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
from trac.test import EnvironmentStub, Mock, MockPerm, locale_en
from trac.ticket.model import Ticket
from trac.ticket.web_ui import TicketModule
from trac.util.datefmt import utc
from trac.web.api import _RequestArgs


class SearchModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.search_module = SearchModule(self.env)

    def tearDown(self):
        self.env.reset_db()

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

    def _insert_ticket(self, **kw):
        """Helper for inserting a ticket into the database"""
        ticket = Ticket(self.env)
        for k, v in kw.items():
            ticket[k] = v
        return ticket.insert()

    def test_process_request_page_in_range(self):
        for _ in range(0, 21):
            self._insert_ticket(summary="Trac")
        req = self._create_request(args={'page': '3', 'q': 'Trac',
                                         'ticket': 'on'})

        data = self.search_module.process_request(req)[1]

        self.assertEqual([], req.chrome['warnings'])
        self.assertEqual(2, data['results'].page)

    def test_process_request_page_out_of_range(self):
        """Out of range value for page defaults to page 1."""
        for _ in range(0, 20):
            self._insert_ticket(summary="Trac")
        req = self._create_request(args={'page': '3', 'q': 'Trac',
                                         'ticket': 'on'})

        data = self.search_module.process_request(req)[1]

        self.assertIn("Page 3 is out of range.", req.chrome['warnings'])
        self.assertEqual(0, data['results'].page)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(SearchModuleTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
