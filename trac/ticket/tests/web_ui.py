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

from __future__ import with_statement

import unittest

from trac.core import TracError
from trac.resource import ResourceNotFound
from trac.test import EnvironmentStub, MockRequest
from trac.ticket.api import TicketSystem
from trac.ticket.model import Ticket
from trac.ticket.web_ui import TicketModule
from trac.web.chrome import Chrome


class TicketModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.ticket_module = TicketModule(self.env)

    def _insert_ticket(self, **kw):
        """Helper for inserting a ticket into the database"""
        ticket = Ticket(self.env)
        for k, v in kw.items():
            ticket[k] = v
        return ticket.insert()

    def test_ticket_module_as_default_handler(self):
        """The New Ticket mainnav entry is active when TicketModule is the
        `default_handler` and navigating to the base url. Test for regression
        of http://trac.edgewall.org/ticket/8791.
        """
        req = MockRequest(self.env)
        chrome = Chrome(self.env).prepare_request(req, self.ticket_module)

        name = None
        for item in chrome['nav']['mainnav']:
            if item['active'] is True:
                name = item['name']
                break
        self.assertEqual('newticket', name)

    def _test_invalid_cnum_raises(self, action, cnum=None):
        self._insert_ticket()
        req = MockRequest(self.env, args={'action': action, 'id': '1'})
        if cnum is not None:
            req.args.update({'cnum': cnum})

        self.assertRaises(TracError, self.ticket_module.process_request, req)

    def test_comment_history_cnum_missing_raises(self):
        self._test_invalid_cnum_raises('comment-history')

    def test_comment_history_cnum_invalid_type_raises(self):
        self._test_invalid_cnum_raises('comment-history', 'a')

    def test_comment_history_cnum_empty_raises(self):
        self._test_invalid_cnum_raises('comment-history', '')

    def test_comment_history_cnum_out_of_range(self):
        """Out of range cnum returns an empty history."""
        self._insert_ticket()
        req = MockRequest(self.env, args={'action': 'comment-history',
                                          'id': '1', 'cnum': '1'})

        resp = self.ticket_module.process_request(req)
        self.assertEqual([], resp[1]['history'])

    def test_comment_diff_cnum_missing_raises(self):
        self._test_invalid_cnum_raises('comment-diff')

    def test_comment_diff_cnum_invalid_type_raises(self):
        self._test_invalid_cnum_raises('comment-diff', 'a')

    def test_comment_diff_cnum_empty_raises(self):
        self._test_invalid_cnum_raises('comment-diff', '')

    def test_comment_diff_cnum_out_of_range_raises(self):
        self._insert_ticket()
        req = MockRequest(self.env, args={'action': 'comment-diff',
                                          'id': '1', 'cnum': '1'})

        self.assertRaises(ResourceNotFound,
                          self.ticket_module.process_request, req)

    def test_edit_comment_cnum_missing_raises(self):
        id_ = self._insert_ticket()
        req = MockRequest(
            self.env, method='POST', path_info='/ticket/%d' % id_,
            args={'edit_comment': 'Submit changes', 'cnum_edit': '42'})
        self.assertTrue(self.ticket_module.match_request(req))
        self.assertRaises(TracError, self.ticket_module.process_request, req)

    def _test_newticket_with_enum_as_custom_field(self, field_name):
        self.env.config.set('ticket-custom', field_name, 'text')
        self.env.config.set('ticket-custom', '%s.label' % field_name,
                            '(%s)' % field_name)
        with self.env.db_transaction as db:
            if field_name in ('milestone', 'component', 'version'):
                db("DELETE FROM %s" % field_name)
            elif field_name == 'type':
                db("DELETE FROM enum WHERE type='ticket_type'")
            else:
                db("DELETE FROM enum WHERE type=%s", (field_name,))
        tktsys = TicketSystem(self.env)
        tktsys.reset_ticket_fields()
        del tktsys.custom_fields

        req = MockRequest(self.env, path_info='/newticket')
        self.assertEqual(True, self.ticket_module.match_request(req))
        resp = self.ticket_module.process_request(req)
        for field in resp[1]['fields']:
            if field['name'] == field_name:
                self.assertEqual('(%s)' % field_name, field['label'])
                self.assertTrue(field['custom'])
                self.assertFalse(field['options'])
                self.assertFalse(field.get('optgroups'))
                break
        else:
            self.fail('Missing %s in fields' % field_name)

    def test_newticket_with_component_as_custom_field(self):
        self._test_newticket_with_enum_as_custom_field('component')

    def test_newticket_with_milestone_as_custom_field(self):
        self._test_newticket_with_enum_as_custom_field('milestone')

    def test_newticket_with_priority_as_custom_field(self):
        self._test_newticket_with_enum_as_custom_field('priority')

    def test_newticket_with_resolution_as_custom_field(self):
        self._test_newticket_with_enum_as_custom_field('resolution')

    def test_newticket_with_severity_as_custom_field(self):
        self._test_newticket_with_enum_as_custom_field('severity')

    def test_newticket_with_type_as_custom_field(self):
        self._test_newticket_with_enum_as_custom_field('type')

    def test_newticket_with_version_as_custom_field(self):
        self._test_newticket_with_enum_as_custom_field('version')


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TicketModuleTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
