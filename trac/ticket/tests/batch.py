# -*- coding: utf-8 -*-
#
# Copyright (C) 2012-2019 Edgewall Software
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
from datetime import datetime, timedelta

from trac.core import Component, implements
from trac.perm import DefaultPermissionPolicy, DefaultPermissionStore, \
                      PermissionSystem
from trac.test import EnvironmentStub, MockRequest
from trac.ticket import api, default_workflow, model, web_ui
from trac.ticket.batch import BatchModifyModule
from trac.ticket.test import insert_ticket
from trac.util.datefmt import datetime_now, utc
from trac.web.api import HTTPBadRequest, RequestDone
from trac.web.chrome import web_context
from trac.web.session import DetachedSession


class ChangeListTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)

    def _change_list_test_helper(self, original, new, new2, mode):
        batch = BatchModifyModule(self.env)
        return batch._change_list(original, new, new2, mode)

    def _add_list_test_helper(self, original, to_add):
        return self._change_list_test_helper(original, to_add, '', '+')

    def _remove_list_test_helper(self, original, to_remove):
        return self._change_list_test_helper(original, to_remove, '', '-')

    def _add_remove_list_test_helper(self, original, to_add, to_remove):
        return self._change_list_test_helper(original, to_add, to_remove,
                                             '+-')

    def _assign_list_test_helper(self, original, new):
        return self._change_list_test_helper(original, new, '', '=')

    # Assign list items

    def test_replace_empty_with_single(self):
        """Replace empty field with single item."""
        changed = self._assign_list_test_helper('', 'alice')
        self.assertEqual(changed, 'alice')

    def test_replace_empty_with_items(self):
        """Replace empty field with items."""
        changed = self._assign_list_test_helper('', 'alice, bob')
        self.assertEqual(changed, 'alice, bob')

    def test_replace_item(self):
        """Replace item with a different item."""
        changed = self._assign_list_test_helper('alice', 'bob')
        self.assertEqual(changed, 'bob')

    def test_replace_item_with_items(self):
        """Replace item with different items."""
        changed = self._assign_list_test_helper('alice', 'bob, carol')
        self.assertEqual(changed, 'bob, carol')

    def test_replace_items_with_item(self):
        """Replace items with a different item."""
        changed = self._assign_list_test_helper('alice, bob', 'carol')
        self.assertEqual(changed, 'carol')

    def test_replace_items(self):
        """Replace items with different items."""
        changed = self._assign_list_test_helper('alice, bob', 'carol, dave')
        self.assertEqual(changed, 'carol, dave')

    def test_replace_items_partial(self):
        """Replace items with different (or not) items."""
        changed = self._assign_list_test_helper('alice, bob', 'bob, dave')
        self.assertEqual(changed, 'bob, dave')

    def test_clear(self):
        """Clear field."""
        changed = self._assign_list_test_helper('alice bob', '')
        self.assertEqual(changed, '')

    # Add / remove list items

    def test_add_item(self):
        """Append additional item."""
        changed = self._add_list_test_helper('alice', 'bob')
        self.assertEqual(changed, 'alice, bob')

    def test_add_items(self):
        """Append additional items."""
        changed = self._add_list_test_helper('alice, bob', 'carol, dave')
        self.assertEqual(changed, 'alice, bob, carol, dave')

    def test_remove_item(self):
        """Remove existing item."""
        changed = self._remove_list_test_helper('alice, bob', 'bob')
        self.assertEqual(changed, 'alice')

    def test_remove_items(self):
        """Remove existing items."""
        changed = self._remove_list_test_helper('alice, bob, carol',
                                                'alice, carol')
        self.assertEqual(changed, 'bob')

    def test_remove_idempotent(self):
        """Ignore missing item to be removed."""
        changed = self._remove_list_test_helper('alice', 'bob')
        self.assertEqual(changed, 'alice')

    def test_remove_mixed(self):
        """Ignore only missing item to be removed."""
        changed = self._remove_list_test_helper('alice, bob', 'bob, carol')
        self.assertEqual(changed, 'alice')

    def test_add_remove(self):
        """Remove existing item and append additional item."""
        changed = self._add_remove_list_test_helper('alice, bob', 'carol',
                                                    'alice')
        self.assertEqual(changed, 'bob, carol')

    def test_add_no_duplicates(self):
        """Existing items are not duplicated."""
        changed = self._add_list_test_helper('alice, bob', 'bob, carol')
        self.assertEqual(changed, 'alice, bob, carol')

    def test_remove_all_duplicates(self):
        """Remove all duplicates."""
        changed = self._remove_list_test_helper('alice, bob, alice', 'alice')
        self.assertEqual(changed, 'bob')


class BatchModifyTestCase(unittest.TestCase):

    ticket_manipulators = None

    @classmethod
    def setUpClass(cls):
        class TicketValidator1(Component):
            implements(api.ITicketManipulator)

            def prepare_ticket(self, req, ticket, fields, actions):
                pass

            def validate_ticket(self, req, ticket):
                errors = []
                if ticket['component'] == 'component3':
                    errors.append(('component', 'Invalid Component'))
                return errors

        class TicketValidator2(Component):
            implements(api.ITicketManipulator)

            def prepare_ticket(self, req, ticket, fields, actions):
                pass

            def validate_ticket(self, req, ticket):
                return []

            def validate_comment(self, req, comment):
                if 'badword' in comment:
                    yield "Word is not allowed in comment"

        cls.ticket_manipulators = [TicketValidator1, TicketValidator2]

    @classmethod
    def tearDownClass(cls):
        from trac.core import ComponentMeta
        for manipulator in cls.ticket_manipulators:
            ComponentMeta.deregister(manipulator)

    def setUp(self):
        self.env = EnvironmentStub(default_data=True, enable=[
            default_workflow.ConfigurableTicketWorkflow,
            DefaultPermissionPolicy, DefaultPermissionStore,
            BatchModifyModule, api.TicketSystem, web_ui.TicketModule
        ])
        self.env.config.set('trac', 'permission_policies',
                            'DefaultPermissionPolicy')
        self.env.config.set('ticket-custom', 'text1', 'text')
        self.env.config.set('ticket-custom', 'text1.max_size', 5)
        self.env.config.set('ticket-custom', 'time1', 'time')
        self.env.config.set('ticket-custom', 'time1.format', 'date')
        self.env.config.set('ticket-workflow',
                            'acknowledge', '* -> acknowledged')
        ps = PermissionSystem(self.env)
        ps.grant_permission('has_ta_&_bm', 'TICKET_ADMIN')
        ps.grant_permission('has_bm', 'TICKET_BATCH_MODIFY')
        ps.grant_permission('has_ta_&_bm', 'TICKET_BATCH_MODIFY')
        session = DetachedSession(self.env, 'has_ta_&_bm')
        session.set('query_href', '')
        session.save()
        session = DetachedSession(self.env, 'has_bm')
        session.set('query_href', '')
        session.save()
        self._insert_ticket('Ticket 1', reporter='user1',
                            component='component1', description='the desc',
                            keywords='foo one', status='new')
        self._insert_ticket('Ticket 2', reporter='user1',
                            component='component2', description='the desc',
                            keywords='baz two', status='new')

    def tearDown(self):
        self.env.reset_db()

    def assertCommentAdded(self, ticket_id, comment):
        ticket = model.Ticket(self.env, int(ticket_id))
        changes = ticket.get_changelog()
        comment_change = [c for c in changes if c[2] == 'comment'][-1]
        self.assertEqual(comment_change[4], comment)

    def assertFieldValue(self, ticket_id, field, new_value):
        ticket = model.Ticket(self.env, int(ticket_id))
        self.assertEqual(ticket[field], new_value)

    def _insert_ticket(self, summary, **kw):
        """Helper for inserting a ticket into the database"""
        ticket = insert_ticket(self.env, summary=summary, **kw)
        return ticket.id

    def _insert_component(self, name):
        component = model.Component(self.env)
        component.name = name
        component.insert()

    def test_require_post_method(self):
        """Request must use POST method."""
        module = BatchModifyModule(self.env)
        req = MockRequest(self.env, method='GET', path_info='/batchmodify')
        req.session['query_href'] = req.href.query()

        self.assertTrue(module.match_request(req))
        with self.assertRaises(HTTPBadRequest):
            module.process_request(req)

        req = MockRequest(self.env, method='POST', path_info='/batchmodify',
                          args={'selected_tickets': ''})
        req.session['query_href'] = req.href.query()

        self.assertTrue(module.match_request(req))
        with self.assertRaises(RequestDone):
            module.process_request(req)

    def test_redirect_to_query_href_in_req_args(self):
        redirect_listener_args = []
        def redirect_listener(req, url, permanent):
            redirect_listener_args[:] = (url, permanent)

        module = BatchModifyModule(self.env)
        req = MockRequest(self.env, method='POST', path_info='/batchmodify')
        query_opened_tickets = req.href.query(status='!closed')
        query_default = req.href.query()
        req.args = {'selected_tickets': '',
                    'query_href': query_opened_tickets}
        req.session['query_href'] = query_default
        req.add_redirect_listener(redirect_listener)

        self.assertTrue(module.match_request(req))
        self.assertRaises(RequestDone, module.process_request, req)
        self.assertEqual([query_opened_tickets, False],
                         redirect_listener_args)

    def test_save_comment(self):
        """Comments are saved to all selected tickets."""
        req = MockRequest(self.env, method='POST', authname='has_bm',
                          path_info='/batchmodify', args={
            'batchmod_value_comment': 'the comment',
            'action': 'leave',
            'selected_tickets': '1,2',
        })

        batch = BatchModifyModule(self.env)
        self.assertTrue(batch.match_request(req))
        with self.assertRaises(RequestDone):
            batch.process_request(req)

        self.assertCommentAdded(1, 'the comment')
        self.assertCommentAdded(2, 'the comment')

    def test_save_values(self):
        """Changed values are saved to all tickets."""
        req = MockRequest(self.env, method='POST', authname='has_bm',
                          path_info='/batchmodify', args={
            'batchmod_value_component': 'component1',
            'batchmod_value_comment': '',
            'action': 'leave',
            'selected_tickets': '1,2',
        })

        batch = BatchModifyModule(self.env)
        self.assertTrue(batch.match_request(req))
        with self.assertRaises(RequestDone):
            batch.process_request(req)

        self.assertFieldValue(1, 'component', 'component1')
        self.assertFieldValue(2, 'component', 'component1')

    def test_list_fields_add(self):
        req = MockRequest(self.env, method='POST', authname='has_bm',
                          path_info='/batchmodify', args={
            'batchmod_mode_keywords': '+',
            'batchmod_primary_keywords': 'baz new',
            'batchmod_secondary_keywords': '*****',
            'action': 'leave',
            'selected_tickets': '1,2',
        })

        batch = BatchModifyModule(self.env)
        self.assertTrue(batch.match_request(req))
        with self.assertRaises(RequestDone):
            batch.process_request(req)

        self.assertFieldValue(1, 'keywords', 'foo, one, baz, new')
        self.assertFieldValue(2, 'keywords', 'baz, two, new')

    def test_list_fields_addrem(self):
        req = MockRequest(self.env, method='POST', authname='has_bm',
                          path_info='/batchmodify', args={
            'batchmod_mode_keywords': '+-',
            'batchmod_primary_keywords': 'one three four',
            'batchmod_secondary_keywords': 'baz missing',
            'action': 'leave',
            'selected_tickets': '1,2',
        })

        batch = BatchModifyModule(self.env)
        self.assertTrue(batch.match_request(req))
        with self.assertRaises(RequestDone):
            batch.process_request(req)

        self.assertFieldValue(1, 'keywords', 'foo, one, three, four')
        self.assertFieldValue(2, 'keywords', 'two, one, three, four')

    def test_list_fields_rem(self):
        req = MockRequest(self.env, method='POST', authname='has_bm',
                          path_info='/batchmodify', args={
            'batchmod_mode_keywords': '-',
            'batchmod_primary_keywords': 'foo two',
            'batchmod_secondary_keywords': '*****',
            'action': 'leave',
            'selected_tickets': '1,2',
        })

        batch = BatchModifyModule(self.env)
        self.assertTrue(batch.match_request(req))
        with self.assertRaises(RequestDone):
            batch.process_request(req)

        self.assertFieldValue(1, 'keywords', 'one')
        self.assertFieldValue(2, 'keywords', 'baz')

    def test_list_fields_set(self):
        req = MockRequest(self.env, method='POST', authname='has_bm',
                          path_info='/batchmodify', args={
            'batchmod_mode_keywords': '=',
            'batchmod_primary_keywords': 'orange',
            'batchmod_secondary_keywords': '*****',
            'action': 'leave',
            'selected_tickets': '1,2',
        })

        batch = BatchModifyModule(self.env)
        self.assertTrue(batch.match_request(req))
        with self.assertRaises(RequestDone):
            batch.process_request(req)

        self.assertFieldValue(1, 'keywords', 'orange')
        self.assertFieldValue(2, 'keywords', 'orange')

    def test_action_with_state_change(self):
        """Actions can have change status."""
        req = MockRequest(self.env, method='POST', authname='has_bm',
                          path_info='/batchmodify', args={
            'action': 'acknowledge',
            'batchmod_value_comment': '',
            'selected_tickets': '1,2',
        })

        batch = BatchModifyModule(self.env)
        self.assertTrue(batch.match_request(req))
        with self.assertRaises(RequestDone):
            batch.process_request(req)

        self.assertFieldValue(1, 'status', 'acknowledged')
        self.assertFieldValue(2, 'status', 'acknowledged')

    def test_action_with_side_effects(self):
        """Actions can have operations with side effects."""
        req = MockRequest(self.env, method='POST', authname='has_bm',
                          path_info='/batchmodify', args={
            'action': 'reassign',
            'action_reassign_reassign_owner': 'user3',
            'batchmod_value_comment': '',
            'selected_tickets': '1,2',
        })

        batch = BatchModifyModule(self.env)
        self.assertTrue(batch.match_request(req))
        with self.assertRaises(RequestDone):
            batch.process_request(req)

        self.assertFieldValue(1, 'owner', 'user3')
        self.assertFieldValue(2, 'owner', 'user3')
        self.assertFieldValue(1, 'status', 'assigned')
        self.assertFieldValue(2, 'status', 'assigned')

    def test_timeline_events(self):
        """Regression test for #11288"""
        req1 = MockRequest(self.env)
        tktmod = web_ui.TicketModule(self.env)
        now = datetime_now(utc)
        start = now - timedelta(hours=1)
        stop = now + timedelta(hours=1)
        events = tktmod.get_timeline_events(req1, start, stop,
                                            ['ticket_details'])
        self.assertTrue(all(ev[0] != 'batchmodify' for ev in events))

        prio_ids = {}
        for i in xrange(20):
            priority = ('', 'minor', 'major', 'critical')[i % 4]
            t = insert_ticket(self.env, summary='Ticket %d' % i,
                              priority=priority)
            prio_ids.setdefault(t['priority'], []).append(t.id)
        tktids = prio_ids['critical'] + prio_ids['major'] + \
                 prio_ids['minor'] + prio_ids['']

        req2 = MockRequest(self.env, method='POST', authname='has_ta_&_bm',
                          path_info='/batchmodify', args={
            'batchmod_value_summary': 'batch updated ticket',
            'batchmod_value_owner': 'ticket11288',
            'batchmod_value_reporter': 'ticket11288',
            'action': 'leave',
            'selected_tickets': ','.join(str(t) for t in tktids),
        })

        batch = BatchModifyModule(self.env)
        self.assertTrue(batch.match_request(req2))
        with self.assertRaises(RequestDone):
            batch.process_request(req2)

        # shuffle ticket_change records
        with self.env.db_transaction as db:
            rows = db('SELECT * FROM ticket_change')
            db.execute('DELETE FROM ticket_change')
            rows = rows[0::4] + rows[1::4] + rows[2::4] + rows[3::4]
            db.executemany('INSERT INTO ticket_change VALUES (%s)' %
                           ','.join(('%s',) * len(rows[0])),
                           rows)

        events = tktmod.get_timeline_events(req1, start, stop,
                                            ['ticket_details'])
        events = [ev for ev in events if ev[0] == 'batchmodify']
        self.assertEqual(1, len(events))
        batch_ev = events[0]
        self.assertEqual('has_ta_&_bm', batch_ev[2])
        self.assertEqual(tktids, batch_ev[3][0])
        self.assertEqual('updated', batch_ev[3][1])

        context = web_context(req2)
        self.assertEqual(req2.href.query(id=','.join(str(t) for t in tktids)),
                         tktmod.render_timeline_event(context, 'url',
                                                      batch_ev))

    def test_modify_summary_and_description(self):
        """The ticket summary and description cannot be modified."""
        req = MockRequest(self.env, authname='has_ta_&_bm', method='POST',
                          path_info='/batchmodify', args={
            'batchmod_value_summary': 'the new summary',
            'batchmod_value_description': 'the new description',
            'batchmod_value_comment': '',
            'action': 'leave',
            'selected_tickets': '1,2',
        })

        module = BatchModifyModule(self.env)
        self.assertTrue(module.match_request(req))
        with self.assertRaises(RequestDone):
            module.process_request(req)

        self.assertFieldValue(1, 'description', 'the desc')
        self.assertFieldValue(1, 'summary', 'Ticket 1')
        self.assertFieldValue(2, 'description', 'the desc')
        self.assertFieldValue(2, 'summary', 'Ticket 2')

    def test_modify_reporter_with_ticket_admin(self):
        """User with TICKET_ADMIN can batch modify the reporter."""
        req = MockRequest(self.env, method='POST', authname='has_ta_&_bm',
                          path_info='/batchmodify', args={
            'batchmod_value_reporter': 'user2',
            'batchmod_value_comment': '',
            'action': 'leave',
            'selected_tickets': '1,2',
        })

        module = BatchModifyModule(self.env)
        self.assertTrue(module.match_request(req))
        with self.assertRaises(RequestDone):
            module.process_request(req)

        self.assertFieldValue(1, 'reporter', 'user2')
        self.assertFieldValue(2, 'reporter', 'user2')

    def test_modify_reporter_without_ticket_admin(self):
        """User without TICKET_ADMIN cannot batch modify the reporter."""
        req = MockRequest(self.env, method='POST', authname='has_bm',
                          path_info='/batchmodify', args={
            'batchmod_value_reporter': 'user2',
            'batchmod_value_comment': '',
            'action': 'leave',
            'selected_tickets': '1,2',
        })

        module = BatchModifyModule(self.env)
        self.assertTrue(module.match_request(req))
        with self.assertRaises(RequestDone):
            module.process_request(req)

        self.assertFieldValue(1, 'reporter', 'user1')
        self.assertFieldValue(2, 'reporter', 'user1')

    def test_validate_ticket_comment_size(self):
        """The [ticket] max_comment_size value is enforced."""
        module = BatchModifyModule(self.env)
        self.env.config.set('ticket', 'max_comment_size', 5)
        req1 = MockRequest(self.env, authname='has_bm', method='POST',
                           path_info='/batchmodify', args={
            'batchmod_value_comment': '12345',
            'action': 'leave',
            'selected_tickets': '1,2',
        })
        req2 = MockRequest(self.env, authname='has_bm', method='POST',
                           path_info='/batchmodify', args={
            'batchmod_value_comment': '123456',
            'action': 'leave',
            'selected_tickets': '1,2',
        })

        self.assertTrue(module.match_request(req1))
        with self.assertRaises(RequestDone):
            module.process_request(req1)

        self.assertEqual([], req1.chrome['warnings'])
        self.assertCommentAdded(1, '12345')
        self.assertCommentAdded(2, '12345')

        self.assertTrue(module.match_request(req2))
        with self.assertRaises(RequestDone):
            module.process_request(req2)

        self.assertEqual(1, len(req2.chrome['warnings']))
        self.assertEqual("The ticket comment is invalid: Must be less than or "
                         "equal to 5 characters",
                         unicode(req2.chrome['warnings'][0]))
        self.assertEqual(1, len(model.Ticket(self.env, 1).get_changelog()))
        self.assertEqual(1, len(model.Ticket(self.env, 2).get_changelog()))

    def test_validate_select_fields(self):
        """The select field values are validated."""
        req = MockRequest(self.env, authname='has_bm', method='POST',
                          path_info='/batchmodify', args={
            'batchmod_value_component': 'component3',
            'action': 'leave',
            'selected_tickets': '1,2',
        })

        module = BatchModifyModule(self.env)
        self.assertTrue(module.match_request(req))
        with self.assertRaises(RequestDone):
            module.process_request(req)

        self.assertEqual(1, len(req.chrome['warnings']))
        self.assertEqual('The ticket field <strong>component</strong> is '
                         'invalid: "component3" is not a valid value',
                         unicode(req.chrome['warnings'][0]))

    def test_validate_ticket_custom_field_max_size(self):
        """The [ticket-custom] max_size attribute is enforced."""
        module = BatchModifyModule(self.env)
        req1 = MockRequest(self.env, authname='has_bm', method='POST',
                           path_info='/batchmodify', args={
            'batchmod_value_text1': '12345',
            'action': 'leave',
            'selected_tickets': '1,2',
        })
        req2 = MockRequest(self.env, authname='has_bm', method='POST',
                           path_info='/batchmodify', args={
            'batchmod_value_text1': '123456',
            'action': 'leave',
            'selected_tickets': '1,2',
        })

        self.assertTrue(module.match_request(req1))
        with self.assertRaises(RequestDone):
            module.process_request(req1)

        self.assertEqual([], req1.chrome['warnings'])
        self.assertEqual('12345', model.Ticket(self.env, 1)['text1'])
        self.assertEqual('12345', model.Ticket(self.env, 2)['text1'])

        self.assertTrue(module.match_request(req2))
        with self.assertRaises(RequestDone):
            module.process_request(req2)

        self.assertEqual(1, len(req2.chrome['warnings']))
        self.assertEqual("The ticket field <strong>Text1</strong> is "
                         "invalid: Must be less than or equal to 5 "
                         "characters", unicode(req2.chrome['warnings'][0]))
        self.assertEqual('12345', model.Ticket(self.env, 1)['text1'])
        self.assertEqual('12345', model.Ticket(self.env, 2)['text1'])

    def test_validate_time_fields(self):
        """The time fields are validated."""
        module = BatchModifyModule(self.env)
        req1 = MockRequest(self.env, authname='has_bm', method='POST',
                           path_info='/batchmodify', args={
            'batchmod_value_time1': '2016-01-02T12:34:56Z',
            'action': 'leave',
            'selected_tickets': '1,2',
        })
        req2 = MockRequest(self.env, authname='has_bm', method='POST',
                           path_info='/batchmodify', args={
            'batchmod_value_time1': 'invalid',
            'action': 'leave',
            'selected_tickets': '1,2',
        })
        dt = datetime(2016, 1, 2, 12, 34, 56, tzinfo=utc)

        self.assertTrue(module.match_request(req1))
        with self.assertRaises(RequestDone):
            module.process_request(req1)

        self.assertEqual(dt, model.Ticket(self.env, 1)['time1'])
        self.assertEqual(dt, model.Ticket(self.env, 2)['time1'])
        self.assertEqual([], req1.chrome['warnings'])

        self.assertTrue(module.match_request(req2))
        with self.assertRaises(RequestDone):
            module.process_request(req2)

        self.assertEqual(1, len(req2.chrome['warnings']))
        self.assertRegexpMatches(unicode(req2.chrome['warnings'][0]),
            'The ticket field <strong>Time1</strong> is invalid: "invalid" '
            'is an invalid date, or the date format is not known. '
            'Try "[^"]+" or "[^"]+" instead.')
        self.assertEqual(dt, model.Ticket(self.env, 1)['time1'])
        self.assertEqual(dt, model.Ticket(self.env, 2)['time1'])

    def test_ticket_manipulators(self):
        """The ticket manipulators are called to valid the ticket."""
        module = BatchModifyModule(self.env)
        self._insert_component('component3')
        self._insert_component('component4')
        self.env.enable_component(self.ticket_manipulators[0])
        self.env.enable_component(self.ticket_manipulators[1])
        req1 = MockRequest(self.env, authname='has_bm', method='POST',
                           path_info='/batchmodify', args={
            'batchmod_value_component': 'component3',
            'action': 'leave',
            'selected_tickets': '1,2',
        })

        self.assertTrue(module.match_request(req1))
        with self.assertRaises(RequestDone):
            module.process_request(req1)

        self.assertEqual(1, len(req1.chrome['warnings']))
        self.assertEqual("The ticket field <strong>component</strong> is "
                         "invalid: Invalid Component",
                         unicode(req1.chrome['warnings'][0]))
        self.assertFieldValue(1, 'component', 'component1')
        self.assertFieldValue(2, 'component', 'component2')

        req2 = MockRequest(self.env, authname='has_bm', method='POST',
                           path_info='/batchmodify', args={
            'batchmod_value_component': 'component4',
            'action': 'leave',
            'selected_tickets': '1,2',
        })

        self.assertTrue(module.match_request(req2))
        with self.assertRaises(RequestDone):
            module.process_request(req2)

        self.assertEqual([], req2.chrome['warnings'])
        self.assertFieldValue(1, 'component', 'component4')
        self.assertFieldValue(2, 'component', 'component4')

        req3 = MockRequest(self.env, authname='has_bm', method='POST',
                           path_info='/batchmodify', args={
            'batchmod_value_comment': 'this comment has the badword!',
            'batchmod_value_component': 'component3',
            'action': 'leave',
            'selected_tickets': '1,2',
        })

        self.assertTrue(module.match_request(req3))
        with self.assertRaises(RequestDone):
            module.process_request(req3)

        self.assertEqual("The ticket comment is invalid: Word is not allowed "
                         "in comment", unicode(req3.chrome['warnings'][0]))
        self.assertFieldValue(1, 'component', 'component4')
        self.assertFieldValue(2, 'component', 'component4')

    def test_post_process_request_add_template_data(self):
        """Template data added by post_process_request."""
        self._insert_ticket("Ticket 1", status='new')
        self._insert_ticket("Ticket 2", status='new')
        req = MockRequest(self.env, path_info='/query')
        req.session['query_href'] = '/query?status=!closed'
        batch = BatchModifyModule(self.env)
        data_in = {'tickets': [{'id': 1}, {'id': 2}]}

        data_out = batch.post_process_request(req, 'query.html', data_in,
                                              'text/html')[1]

        self.assertTrue(data_out['batch_modify'])
        self.assertEqual(['leave', 'resolve', 'reassign', 'acknowledge',
                          'accept'],
                         [a[0] for a in data_out['action_controls']])

    def test_actions_added_by_additional_ticket_action_controllers(self):
        """Actions added by custom ticket action controller.

        Regression test for #12938.
        """
        class TestOperation(Component):
            """TicketActionController that directly provides an action."""
            implements(api.ITicketActionController)

            def get_ticket_actions(self, req, ticket):
                return [(0, 'test')]

            def get_all_status(self):
                return []

            def render_ticket_action_control(self, req, ticket, action):
                return "test", '', "This is a null action."

            def get_ticket_changes(self, req, ticket, action):
                return {}

            def apply_action_side_effects(self, req, ticket, action):
                pass

        self._insert_ticket("Ticket 1", status='new')
        self._insert_ticket("Ticket 2", status='new')
        req = MockRequest(self.env, path_info='/query')
        req.session['query_href'] = '/query?status=!closed'
        batch = BatchModifyModule(self.env)
        data_in = {'tickets': [{'id': 1}, {'id': 2}]}
        self.env.config.set('ticket', 'workflow',
                            'ConfigurableTicketWorkflow, TestOperation')
        self.env.enable_component(TestOperation)

        data_out = batch.post_process_request(req, 'query.html', data_in,
                                              'text/html')[1]

        self.assertEqual(['leave', 'test', 'resolve', 'reassign',
                          'acknowledge', 'accept'],
                         [a[0] for a in data_out['action_controls']])

    def test_post_process_request_error_handling(self):
        """Exception not raised in post_process_request error handling.
        """
        module = BatchModifyModule(self.env)
        req = MockRequest(self.env, path_info='/query')
        self.assertEqual((None, None, None),
                         module.post_process_request(req, None, None, None))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ChangeListTestCase))
    suite.addTest(unittest.makeSuite(BatchModifyTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
