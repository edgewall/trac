# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 Edgewall Software
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

from trac.test import EnvironmentStub, Mock, MockPerm, locale_en
from trac.ticket.model import Ticket
from trac.ticket.web_ui import TicketModule
from trac.web.chrome import Chrome
from trac.util.datefmt import utc


class TicketModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.ticket_module = TicketModule(self.env)

    def tearDown(self):
        self.env.reset_db()

    def create_request(self, authname='anonymous', **kwargs):
        kw = {'path_info': '/', 'perm': MockPerm(), 'args': {},
              'href': self.env.href, 'abs_href': self.env.abs_href,
              'tz': utc, 'locale': None, 'lc_time': locale_en,
              'session': {}, 'authname': authname,
              'chrome': {'notices': [], 'warnings': []},
              'method': None, 'get_header': lambda v: None, 'is_xhr': False,
              'form_token': None}
        kw.update(kwargs)
        return Mock(add_redirect_listener=lambda x: [].append(x), **kw)

    def _create_ticket_with_change(self, old_props, new_props):
        """Create a ticket with `old_props` and apply properties
        in `new_props`.
        """
        t = Ticket(self.env)
        t.populate(old_props)
        t.insert()
        t.populate(new_props)
        t.save_changes('actor')
        return t

    def test_ticket_module_as_default_handler(self):
        """The New Ticket mainnav entry is active when TicketModule is the
        `default_handler` and navigating to the base url. Test for regression
        of http://trac.edgewall.org/ticket/8791.
        """
        req = self.create_request()
        chrome = Chrome(self.env).prepare_request(req, self.ticket_module)

        name = None
        for item in chrome['nav']['mainnav']:
            if item['active'] is True:
                name = item['name']
                break
        self.assertEqual('newticket', name)

    def test_ticket_property_diff_owner_change(self):
        """Property diff message when ticket owner is changed."""
        t = self._create_ticket_with_change({'owner': 'owner1'},
                                            {'owner': 'owner2'})

        req = self.create_request(args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['owner']

        self.assertEqual("changed from <em>owner1</em> to <em>owner2</em>",
                         str(field['rendered']))

    def test_ticket_property_diff_owner_add(self):
        """Property diff message when ticket owner is added."""
        t = self._create_ticket_with_change({'owner': ''},
                                            {'owner': 'owner2'})

        req = self.create_request(args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['owner']

        self.assertEqual("set to <em>owner2</em>", str(field['rendered']))

    def test_ticket_property_diff_owner_remove(self):
        """Property diff message when ticket owner is removed."""
        t = self._create_ticket_with_change({'owner': 'owner1'},
                                            {'owner': ''})

        req = self.create_request(args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['owner']

        self.assertEqual("<em>owner1</em> deleted", str(field['rendered']))

    def test_ticket_property_diff_reporter_change(self):
        """Property diff message when ticket reporter is changed."""
        t = self._create_ticket_with_change({'reporter': 'reporter1'},
                                            {'reporter': 'reporter2'})

        req = self.create_request(args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['reporter']

        self.assertEqual("changed from <em>reporter1</em> to "
                         "<em>reporter2</em>", str(field['rendered']))

    def test_ticket_property_diff_reporter_add(self):
        """Property diff message when ticket reporter is added."""
        t = self._create_ticket_with_change({'reporter': ''},
                                            {'reporter': 'reporter2'})

        req = self.create_request(args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['reporter']

        self.assertEqual("set to <em>reporter2</em>", str(field['rendered']))

    def test_ticket_property_diff_reporter_remove(self):
        """Property diff message when ticket reporter is removed."""
        t = self._create_ticket_with_change({'reporter': 'reporter1'},
                                            {'reporter': ''})

        req = self.create_request(args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['reporter']

        self.assertEqual("<em>reporter1</em> deleted", str(field['rendered']))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TicketModuleTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
