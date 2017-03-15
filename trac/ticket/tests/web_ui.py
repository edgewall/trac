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

from datetime import datetime, timedelta
import unittest

from trac.core import TracError
from trac.perm import PermissionSystem
from trac.resource import ResourceNotFound
from trac.test import EnvironmentStub, MockRequest
from trac.ticket.api import TicketSystem
from trac.ticket.model import Ticket
from trac.ticket.web_ui import TicketModule
from trac.util.datefmt import (datetime_now, format_date, format_datetime,
                               timezone, to_utimestamp, user_time, utc)
from trac.web.api import HTTPBadRequest, RequestDone
from trac.web.chrome import Chrome


class TicketModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.ticket_module = TicketModule(self.env)

    def tearDown(self):
        self.env.reset_db()

    def _create_ticket_with_change(self, old_props, new_props,
                                   author='anonymous'):
        """Create a ticket with `old_props` and apply properties
        in `new_props`.
        """
        t = Ticket(self.env)
        t.populate(old_props)
        t.insert()
        comment = new_props.pop('comment', None)
        t.populate(new_props)
        t.save_changes(author, comment=comment)
        return t

    def _insert_ticket(self, **kw):
        """Helper for inserting a ticket into the database"""
        ticket = Ticket(self.env)
        for k, v in kw.items():
            ticket[k] = v
        ticket.insert()
        return ticket

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

    def test_reporter_and_owner_full_name_is_displayed(self):
        """Full name of reporter and owner are used in ticket properties."""
        self.env.insert_users([('user1', 'User One', ''),
                               ('user2', 'User Two', '')])
        ticket = self._insert_ticket(reporter='user1', owner='user2')
        PermissionSystem(self.env).grant_permission('user2', 'TICKET_VIEW')
        req = MockRequest(self.env, authname='user2', method='GET',
                          args={'id': ticket.id, 'replyto': '1'})

        data = self.ticket_module.process_request(req)[1]

        self.assertEqual(u'<a class="trac-author" href="/trac.cgi/query?'
                         u'status=!closed&amp;reporter=user1">User One</a>',
                         unicode(data['reporter_link']))
        self.assertEqual(u'<a class="trac-author-user" href="/trac.cgi/query?'
                         u'status=!closed&amp;owner=user2">User Two</a>',
                         unicode(data['owner_link']))

    def test_quoted_reply_author_is_obfuscated(self):
        """Reply-to author is obfuscated in a quoted reply."""
        author = 'author <author@example.net>'
        tkt = self._create_ticket_with_change({}, {'comment': 'the comment'},
                                              author)
        req = MockRequest(self.env, method='GET',
                          args={'id': tkt.id, 'replyto': '1'})

        data = self.ticket_module.process_request(req)[1]

        comment = u"Replying to [comment:1 author <author@\u2026>]:\n> " \
                  u"the comment\n"
        self.assertEqual(comment, data['comment'])
        self.assertEqual(comment, data['change_preview']['comment'])

    def test_quoted_reply_author_full_name_is_displayed(self):
        """Full name of reply-to author is used in quoted reply."""
        self.env.insert_users([('author', 'The Author',
                                     'author@example.net')])
        tkt = self._create_ticket_with_change({}, {'comment': 'the comment'},
                                              'author')
        req = MockRequest(self.env, method='GET',
                          args={'id': tkt.id, 'replyto': '1'})

        data = self.ticket_module.process_request(req)[1]

        comment = u"Replying to [comment:1 The Author]:\n> " \
                  u"the comment\n"
        self.assertEqual(comment, data['comment'])
        self.assertEqual(comment, data['change_preview']['comment'])

    def test_ticket_property_diff_owner_change(self):
        """Property diff message when ticket owner is changed."""
        t = self._create_ticket_with_change({'owner': 'owner1'},
                                            {'owner': 'owner2'})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['owner']

        self.assertEqual("changed from <em>owner1</em> to <em>owner2</em>",
                         str(field['rendered']))

    def test_ticket_property_diff_owner_add(self):
        """Property diff message when ticket owner is added."""
        t = self._create_ticket_with_change({'owner': ''},
                                            {'owner': 'owner2'})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['owner']

        self.assertEqual("set to <em>owner2</em>", str(field['rendered']))

    def test_ticket_property_diff_owner_remove(self):
        """Property diff message when ticket owner is removed."""
        t = self._create_ticket_with_change({'owner': 'owner1'},
                                            {'owner': ''})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['owner']

        self.assertEqual("<em>owner1</em> deleted", str(field['rendered']))

    def test_ticket_property_diff_reporter_change(self):
        """Property diff message when ticket reporter is changed."""
        t = self._create_ticket_with_change({'reporter': 'reporter1'},
                                            {'reporter': 'reporter2'})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['reporter']

        self.assertEqual("changed from <em>reporter1</em> to "
                         "<em>reporter2</em>", str(field['rendered']))

    def test_ticket_property_diff_reporter_add(self):
        """Property diff message when ticket reporter is added."""
        t = self._create_ticket_with_change({'reporter': ''},
                                            {'reporter': 'reporter2'})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['reporter']

        self.assertEqual("set to <em>reporter2</em>", str(field['rendered']))

    def test_ticket_property_diff_reporter_remove(self):
        """Property diff message when ticket reporter is removed."""
        t = self._create_ticket_with_change({'reporter': 'reporter1'},
                                            {'reporter': ''})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['reporter']

        self.assertEqual("<em>reporter1</em> deleted", str(field['rendered']))

    def _test_invalid_cnum_raises(self, action, cnum=None):
        self._insert_ticket()
        req = MockRequest(self.env, args={'action': action, 'id': '1'})
        if cnum is not None:
            req.args.update({'cnum': cnum})

        self.assertRaises(HTTPBadRequest,
                          self.ticket_module.process_request, req)

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
        ticket = self._insert_ticket()
        req = MockRequest(
            self.env, method='POST', path_info='/ticket/%d' % ticket.id,
            args={'edit_comment': 'Submit changes', 'cnum_edit': '42'})
        self.assertTrue(self.ticket_module.match_request(req))
        self.assertRaises(TracError, self.ticket_module.process_request, req)

    def _test_template_data_for_time_field(self, req, value, expected, format):
        self.env.config.set('ticket-custom', 'timefield', 'time')
        if format:
            self.env.config.set('ticket-custom', 'timefield.format', format)
        self._insert_ticket(summary='Time fields', timefield=value)
        self.assertEqual(value, Ticket(self.env, 1)['timefield'])

        self.assertTrue(self.ticket_module.match_request(req))
        data = self.ticket_module.process_request(req)[1]

        for f in data['fields']:
            if f['name'] == 'timefield':
                self.assertEqual(expected, f['edit'])
                break
        else:
            self.fail('Missing timefield field')

    def test_template_data_for_time_field_with_formats(self):
        gmt12 = timezone('GMT +12:00')
        req = MockRequest(self.env, method='GET', path_info='/ticket/1',
                          tz=gmt12)
        value = datetime(2016, 1, 2, 23, 34, 45, tzinfo=utc)
        expected = user_time(req, format_datetime, value)
        self.assertIn('11', expected)  # check 11 in hour part

        self._test_template_data_for_time_field(req, value, expected, None)
        self._test_template_data_for_time_field(req, value, expected,
                                                'datetime')
        self._test_template_data_for_time_field(req, value, expected,
                                                'relative')

    def test_template_data_for_time_field_with_date_format(self):
        value = datetime(2016, 2, 22, 22, 22, 22, tzinfo=utc)
        self.env.config.set('ticket-custom', 'timefield', 'time')
        self.env.config.set('ticket-custom', 'timefield.format', 'date')
        self._insert_ticket(summary='Time fields', timefield=value)
        self.assertEqual(value, Ticket(self.env, 1)['timefield'])

        gmt12 = timezone('GMT +12:00')
        req = MockRequest(self.env, method='GET', path_info='/ticket/1',
                          tz=gmt12)
        expected = user_time(req, format_date, value)
        self.assertIn('23', expected)  # check 23 in day part
        self.assertTrue(self.ticket_module.match_request(req))
        data = self.ticket_module.process_request(req)[1]

        for f in data['fields']:
            if f['name'] == 'timefield':
                self.assertEqual(expected, f['edit'])
                break
        else:
            self.fail('Missing timefield field')

    def test_template_data_for_invalid_time_field(self):
        self.env.config.set('ticket-custom', 'timefield', 'time')
        self._insert_ticket(summary='Time fields',
                            timefield=datetime_now(utc))
        self.env.db_transaction("UPDATE ticket_custom SET value='invalid' "
                                "WHERE ticket=1 AND name='timefield'")
        self.assertEqual(None, Ticket(self.env, 1)['timefield'])

        req = MockRequest(self.env, method='GET', path_info='/ticket/1')
        self.assertTrue(self.ticket_module.match_request(req))
        data = self.ticket_module.process_request(req)[1]
        self.assertEqual(None, data['ticket']['timefield'])

        for f in data['fields']:
            if f['name'] == 'timefield':
                self.assertEqual('', f['edit'])
                break
        else:
            self.fail('Missing timefield field')

    def test_template_data_for_invalid_time_field_on_newticket(self):
        self.env.config.set('ticket-custom', 'timefield', 'time')
        req = MockRequest(self.env, method='GET', path_info='/newticket')
        req.args['timefield'] = 'invalid'
        self.assertTrue(self.ticket_module.match_request(req))
        data = self.ticket_module.process_request(req)[1]
        self.assertEqual('invalid', data['ticket']['timefield'])

        for f in data['fields']:
            if f['name'] == 'timefield':
                self.assertEqual('invalid', f['edit'])
                break
        else:
            self.fail('Missing timefield field')

    def test_template_data_changes_for_time_field(self):
        self.env.config.set('ticket-custom', 'timefield', 'time')
        dt1 = datetime(2015, 7, 8, tzinfo=utc)
        dt2 = datetime(2015, 12, 11, tzinfo=utc)
        with self.env.db_transaction:
            self._insert_ticket(summary='Time fields',
                                timefield=datetime_now(utc))
            self.env.db_transaction("UPDATE ticket_custom SET value='invalid' "
                                    "WHERE ticket=1 AND name='timefield'")
            t = Ticket(self.env, 1)
            t['timefield'] = dt1
            t.save_changes('anonymous')
            t = Ticket(self.env, 1)
            t['timefield'] = dt2
            t.save_changes('anonymous')

        req = MockRequest(self.env, method='GET', path_info='/ticket/1')
        self.assertTrue(self.ticket_module.match_request(req))
        data = self.ticket_module.process_request(req)[1]
        changes = data['changes']
        dt1_text = user_time(req, format_datetime, dt1)
        dt2_text = user_time(req, format_datetime, dt2)
        self.assertEqual(2, len(changes))
        self.assertEqual('', changes[0]['fields']['timefield']['old'])
        self.assertEqual(dt1_text, changes[0]['fields']['timefield']['new'])
        self.assertEqual(dt1_text, changes[1]['fields']['timefield']['old'])
        self.assertEqual(dt2_text, changes[1]['fields']['timefield']['new'])

    def test_submit_with_time_field(self):
        self.env.config.set('ticket-custom', 'timefield', 'time')
        self._insert_ticket(summary='Time fields', timefield='')
        ticket = Ticket(self.env, 1)
        args_base = {'submit': '*', 'action': 'leave', 'id': '1',
                     'field_summary': ticket['summary'],
                     'field_reporter': ticket['reporter'],
                     'field_description': ticket['description'],
                     'view_time': str(to_utimestamp(ticket['changetime']))}
        for f in ticket.fields:
            args_base['field_%s' % f['name']] = ticket[f['name']] or ''

        args = args_base.copy()
        args['field_timefield'] = 'invalid datetime'
        req = MockRequest(self.env, method='POST', path_info='/ticket/1',
                          args=args)
        self.assertTrue(self.ticket_module.match_request(req))
        self.ticket_module.process_request(req)
        warnings = req.chrome['warnings']
        self.assertNotEqual([], warnings)
        self.assertEqual(1, len(warnings))
        self.assertIn('is an invalid date, or the date format is not known.',
                      unicode(warnings[0]))
        ticket = Ticket(self.env, 1)
        self.assertEqual(None, ticket['timefield'])

        args = args_base.copy()
        args['field_timefield'] = '2016-01-02T12:34:56Z'
        req = MockRequest(self.env, method='POST', path_info='/ticket/1',
                          args=args)
        self.assertTrue(self.ticket_module.match_request(req))
        self.assertRaises(RequestDone, self.ticket_module.process_request, req)
        ticket = Ticket(self.env, 1)
        self.assertEqual(datetime(2016, 1, 2, 12, 34, 56, tzinfo=utc),
                         ticket['timefield'])

    def _test_render_time_field(self, format, req, value, expected):
        self.env.config.set('ticket-custom', 'timefield', 'time')
        self.env.config.set('ticket-custom', 'timefield.format', format)

        def timefield_text():
            self.assertTrue(self.ticket_module.match_request(req))
            rv = self.ticket_module.process_request(req)
            stream = Chrome(self.env).render_template(req, rv[0], rv[1], rv[2],
                                                      fragment=True)
            stream = stream.select('//td[@headers="h_timefield"]')
            return stream.render('text', encoding=None).strip()

        self._insert_ticket(summary='Time fields')
        self.assertEqual('', timefield_text())

        ticket = Ticket(self.env, 1)
        ticket['timefield'] = value
        ticket.save_changes('anonymous')
        self.assertEqual(expected, timefield_text())

    def test_render_time_field_date(self):
        req = MockRequest(self.env, method='GET', path_info='/ticket/1')
        value = datetime(2015, 7, 8, tzinfo=utc)
        expected = user_time(req, format_date, value)
        self._test_render_time_field('date', req, value, expected)

    def test_render_time_field_datetime(self):
        req = MockRequest(self.env, method='GET', path_info='/ticket/1')
        value = datetime(2015, 7, 8, 12, 34, 56, tzinfo=utc)
        expected = user_time(req, format_datetime, value)
        self._test_render_time_field('datetime', req, value, expected)

    def test_render_time_field_relative(self):
        req = MockRequest(self.env, method='GET', path_info='/ticket/1')
        value = datetime_now(utc) - timedelta(days=1)
        self._test_render_time_field('relative', req, value, '24 hours ago')

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

    def test_add_comment_requires_ticket_append(self):
        """Adding a ticket comment requires TICKET_APPEND."""
        ps = PermissionSystem(self.env)
        ps.grant_permission('user1', 'TICKET_VIEW')
        ps.grant_permission('user1', 'TICKET_APPEND')
        ps.grant_permission('user2', 'TICKET_VIEW')
        ps.grant_permission('user2', 'TICKET_CHGPROP')
        ticket = self._insert_ticket(summary='the summary')
        comment = 'the comment'

        def make_req(authname):
            change_time = Ticket(self.env, 1)['changetime']
            return MockRequest(
                self.env, authname=authname,
                method='POST', path_info='/ticket/1',
                args={'comment': comment, 'action': 'leave', 'submit': True,
                      'view_time': unicode(to_utimestamp(change_time))})

        req = make_req('user1')
        self.assertTrue(self.ticket_module.match_request(req))
        self.assertRaises(RequestDone, self.ticket_module.process_request,
                          req)
        self.assertEqual([], req.chrome['warnings'])
        self.assertEqual(comment,
                         ticket.get_change(1)['fields']['comment']['new'])

        req = make_req('user2')
        self.assertTrue(self.ticket_module.match_request(req))
        self.ticket_module.process_request(req)
        self.assertEqual(1, len(req.chrome['warnings']))
        self.assertEqual("No permissions to add a comment.",
                         unicode(req.chrome['warnings'][0]))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TicketModuleTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
