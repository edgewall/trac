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
import io
import unittest

from trac.core import TracError
from trac.perm import PermissionCache, PermissionSystem
from trac.resource import Resource, ResourceNotFound
from trac.test import EnvironmentStub, MockRequest
from trac.ticket.api import TicketSystem
from trac.ticket.model import Milestone, Ticket
from trac.ticket.web_ui import DefaultTicketPolicy, TicketModule
from trac.util.datefmt import (datetime_now, format_date, format_datetime,
                               timezone, to_utimestamp, user_time, utc)
from trac.util.html import HTMLTransform
from trac.web.api import HTTPBadRequest, RequestDone
from trac.web.chrome import Chrome


def insert_ticket(env, **kw):
    """Helper for inserting a ticket into the database"""
    ticket = Ticket(env)
    for k, v in kw.items():
        ticket[k] = v
    ticket.insert()
    return ticket


class TicketModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.env.config.set('trac', 'permission_policies',
            'DefaultTicketPolicy, DefaultPermissionPolicy, '
            'LegacyAttachmentPolicy')
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
        return insert_ticket(self.env, **kw)

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
                         unicode(field['rendered']))

    def test_ticket_property_diff_owner_add(self):
        """Property diff message when ticket owner is added."""
        t = self._create_ticket_with_change({'owner': ''},
                                            {'owner': 'owner2'})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['owner']

        self.assertEqual("set to <em>owner2</em>", unicode(field['rendered']))

    def test_ticket_property_diff_owner_remove(self):
        """Property diff message when ticket owner is removed."""
        t = self._create_ticket_with_change({'owner': 'owner1'},
                                            {'owner': ''})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['owner']

        self.assertEqual("<em>owner1</em> deleted", unicode(field['rendered']))

    def test_ticket_property_diff_reporter_change(self):
        """Property diff message when ticket reporter is changed."""
        t = self._create_ticket_with_change({'reporter': 'reporter1'},
                                            {'reporter': 'reporter2'})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['reporter']

        self.assertEqual("changed from <em>reporter1</em> to "
                         "<em>reporter2</em>", unicode(field['rendered']))

    def test_ticket_property_diff_reporter_add(self):
        """Property diff message when ticket reporter is added."""
        t = self._create_ticket_with_change({'reporter': ''},
                                            {'reporter': 'reporter2'})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['reporter']

        self.assertEqual("set to <em>reporter2</em>",
                         unicode(field['rendered']))

    def test_ticket_property_diff_reporter_remove(self):
        """Property diff message when ticket reporter is removed."""
        t = self._create_ticket_with_change({'reporter': 'reporter1'},
                                            {'reporter': ''})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['reporter']

        self.assertEqual("<em>reporter1</em> deleted",
                         unicode(field['rendered']))

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
        with self.assertRaises(TracError) as cm:
            self.ticket_module.process_request(req)
        self.assertEqual('Comment 42 not found', unicode(cm.exception))

    def test_edit_comment_validate_max_comment_size(self):
        """The [ticket] max_comment_size attribute is validated during
        ticket comment edit.
        """
        perm_sys = PermissionSystem(self.env)
        perm_sys.grant_permission('user1', 'TICKET_VIEW')
        perm_sys.grant_permission('user1', 'TICKET_APPEND')
        self.env.config.set('ticket', 'max_comment_size', 5)
        ticket = self._insert_ticket(summary='the summary')
        ticket.save_changes('user1', '12345')
        req = MockRequest(
            self.env, method='POST', authname='user1',
            path_info='/ticket/%d' % ticket.id,
            args={'id': '1', 'edit_comment': True, 'cnum_edit': '1',
                  'edited_comment': '123456'})

        self.assertTrue(self.ticket_module.match_request(req))
        self.ticket_module.process_request(req)

        self.assertIn("Ticket comment is too long (must be less than 5 "
                      "characters)", unicode(req.chrome['warnings'][0]))

    def test_preview_comment_validate_max_comment_size(self):
        """The [ticket] max_comment_size attribute is validated during
        ticket comment edit preview.
        """
        perm_sys = PermissionSystem(self.env)
        perm_sys.grant_permission('user1', 'TICKET_VIEW')
        perm_sys.grant_permission('user1', 'TICKET_APPEND')
        self.env.config.set('ticket', 'max_comment_size', 5)
        ticket = self._insert_ticket(summary='the summary')
        ticket.save_changes('user1', '12345')
        req = MockRequest(
            self.env, method='POST', authname='user1',
            path_info='/ticket/%d' % ticket.id,
            args={'id': '1', 'preview_comment': True, 'cnum_edit': '1',
                  'edited_comment': '123456'})

        self.assertTrue(self.ticket_module.match_request(req))
        self.ticket_module.process_request(req)

        self.assertIn("Ticket comment is too long (must be less than 5 "
                      "characters)", unicode(req.chrome['warnings'][0]))

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
        self.assertIsNone(Ticket(self.env, 1)['timefield'])

        req = MockRequest(self.env, method='GET', path_info='/ticket/1')
        self.assertTrue(self.ticket_module.match_request(req))
        data = self.ticket_module.process_request(req)[1]
        self.assertIsNone(data['ticket']['timefield'])

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
            self.env.db_transaction("""
                UPDATE ticket_custom SET value='invalid'
                WHERE ticket=1 AND name='timefield'
                """)
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
        self.assertIsNone(ticket['timefield'])

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
            template, data = self.ticket_module.process_request(req)
            content = Chrome(self.env).render_fragment(req, template, data)
            # select('//td[@headers="h_timefield"') replacement
            class TimefieldExtractor(HTMLTransform):
                pick_next_text = False
                value = ''
                def handle_starttag(self, tag, attrs):
                    if tag == 'td':
                        for name, value in attrs:
                            if name == 'headers' and value == 'h_timefield':
                                self.pick_next_text = True
                def handle_data(self, data):
                    if self.pick_next_text:
                        self.value += data
                def handle_endtag(self, tag):
                    if self.pick_next_text:
                        self.pick_next_text = False

            extractor = TimefieldExtractor(io.BytesIO())
            extractor.feed(content.encode('utf-8'))
            return extractor.value.decode('utf-8').strip()

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
        self.assertTrue(self.ticket_module.match_request(req))
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

    def test_change_milestone_requires_milestone_view(self):
        """Changing ticket milestone requires MILESTONE_VIEW."""
        perm_sys = PermissionSystem(self.env)
        self._insert_ticket(summary='the summary')
        for name in ('milestone1', 'milestone2'):
            m = Milestone(self.env)
            m.name = name
            m.insert()

        def make_req(authname):
            return MockRequest(self.env, authname=authname, method='GET',
                               path_info='/ticket/1')

        def get_milestone_field(fields):
            for field in fields:
                if 'milestone' == field['name']:
                    return field

        perm_sys.grant_permission('user', 'TICKET_VIEW')
        req = make_req('user')

        self.assertTrue(self.ticket_module.match_request(req))
        data = self.ticket_module.process_request(req)[1]
        milestone_field = get_milestone_field(data['fields'])
        self.assertFalse(milestone_field['editable'])
        self.assertEqual([], milestone_field['optgroups'][0]['options'])
        self.assertEqual([], milestone_field['optgroups'][1]['options'])

        perm_sys.grant_permission('user_w_mv', 'TICKET_VIEW')
        perm_sys.grant_permission('user_w_mv', 'MILESTONE_VIEW')
        req = make_req('user_w_mv')

        self.assertTrue(self.ticket_module.match_request(req))
        data = self.ticket_module.process_request(req)[1]
        milestone_field = get_milestone_field(data['fields'])
        self.assertTrue(milestone_field['editable'])
        self.assertEqual([], milestone_field['optgroups'][0]['options'])
        self.assertEqual(['milestone1', 'milestone2'],
                         milestone_field['optgroups'][1]['options'])


class CustomFieldMaxSizeTestCase(unittest.TestCase):
    """Tests for [ticket-custom] max_size attribute."""

    def setUp(self):
        self.env = EnvironmentStub()
        self.ticket_module = TicketModule(self.env)

    def tearDown(self):
        self.env.reset_db()

    def _setup_env_and_req(self, max_size, field_value):
        self.env.config.set('ticket-custom', 'text1', 'text')
        self.env.config.set('ticket-custom', 'text1.max_size', max_size)
        ticket = insert_ticket(self.env, summary='summary', text1='init')
        change_time = Ticket(self.env, ticket.id)['changetime']
        view_time = str(to_utimestamp(change_time))
        req = MockRequest(
            self.env, method='POST', path_info='/ticket/%d' % ticket.id,
            args={'submit': 'Submit changes', 'field_text1': field_value,
                  'action': 'leave', 'view_time': view_time})
        return req

    def test_ticket_custom_field_greater_than_max_size(self):
        """Validation fails for a ticket custom field with content length
        greater than max_size.
        """
        max_size = 5
        field_value = 'a' * (max_size + 1)
        req = self._setup_env_and_req(max_size, field_value)

        self.assertTrue(self.ticket_module.match_request(req))
        self.ticket_module.process_request(req)

        self.assertTrue(req.args['preview'])
        self.assertEqual(1, len(req.chrome['warnings']))
        self.assertIn("Ticket field 'Text1' is too long (must be less "
                      "than 5 characters)", req.chrome['warnings'])

    def test_ticket_custom_field_less_than_max_size(self):
        """Validation succeeds for a ticket custom field with content length
        less than or equal to max_size.
        """
        max_size = 5
        field_value = 'a' * max_size
        req = self._setup_env_and_req(max_size, field_value)

        self.assertTrue(self.ticket_module.match_request(req))
        with self.assertRaises(RequestDone):
            self.ticket_module.process_request(req)

        self.assertEqual(0, len(req.chrome['warnings']))
        self.assertEqual(field_value, Ticket(self.env, 1)['text1'])

    def test_ticket_custom_field_max_size_is_zero(self):
        """Validation is skipped when max_size attribute is <= 0."""
        max_size = 0
        field_value = 'a' * 100
        req = self._setup_env_and_req(max_size, field_value)

        self.assertTrue(self.ticket_module.match_request(req))
        with self.assertRaises(RequestDone):
            self.ticket_module.process_request(req)

        self.assertEqual(0, len(req.chrome['warnings']))
        self.assertEqual(field_value, Ticket(self.env, 1)['text1'])


class DefaultTicketPolicyTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=('trac.ticket.*', 'trac.perm.*'))
        self.env.config.set('trac', 'permission_policies',
                            'DefaultTicketPolicy,DefaultPermissionPolicy')
        self.perm_sys = PermissionSystem(self.env)
        self.policy = DefaultTicketPolicy(self.env)

    def tearDown(self):
        self.env.reset_db()

    def _create_ticket(self, reporter):
        return insert_ticket(self.env, reporter=reporter,
                             summary='The summary', description='The text.')

    def test_reporter_can_edit_own_ticket_description(self):
        """Authenticated user can modify description of ticket they
        reported. The authenticated user must have TICKET_CHGPROP or 
        TICKET_APPEND.
        """
        self.perm_sys.grant_permission('somebody1', 'TICKET_CHGPROP')
        self.perm_sys.grant_permission('somebody2', 'TICKET_APPEND')
        ticket1 = self._create_ticket('somebody1')
        ticket2 = self._create_ticket('somebody2')
        ticket3 = self._create_ticket('somebody3')
        action = 'TICKET_EDIT_DESCRIPTION'

        perm_cache = PermissionCache(self.env, 'somebody1', ticket1.resource)
        self.assertIn(action, perm_cache)
        self.assertTrue(self.policy.check_permission(
            action, perm_cache.username, ticket1.resource, perm_cache))

        perm_cache = PermissionCache(self.env, 'somebody2', ticket2.resource)
        self.assertIn(action, perm_cache)
        self.assertTrue(self.policy.check_permission(
            action, perm_cache.username, ticket2.resource, perm_cache))

        perm_cache = PermissionCache(self.env, 'somebody3', ticket3.resource)
        self.assertNotIn(action, perm_cache)
        self.assertIsNone(self.policy.check_permission(
            action, perm_cache.username, ticket3.resource, perm_cache))

    def test_reporter_cannot_edit_other_ticket_description(self):
        """Authenticated user cannot modify description of ticket they
        didn't report.
        """
        ticket = self._create_ticket('somebodyelse')
        perm_cache = PermissionCache(self.env, 'somebody', ticket.resource)
        action = 'TICKET_EDIT_DESCRIPTION'

        self.assertNotIn(action, perm_cache)
        self.assertIsNone(self.policy.check_permission(
            action, perm_cache.username, ticket.resource, perm_cache))

    def test_anonymous_cannot_edit_ticket_description(self):
        """Anonymous user cannot modify description of ticket they
        reported.
        """
        ticket = self._create_ticket('anonymous')
        perm_cache = PermissionCache(self.env, 'anonymous')
        action = 'TICKET_EDIT_DESCRIPTION'

        self.assertNotIn('TICKET_EDIT_DESCRIPTION',
                         perm_cache(ticket.resource))
        self.assertIsNone(self.policy.check_permission(
            action, perm_cache.username, ticket.resource, perm_cache))

    def _test_edit_ticket_comment(self, commenter, editor):
        ticket = self._create_ticket(commenter)
        ticket.save_changes(commenter, comment='The comment')
        comment_resource = Resource('comment', 1, parent=ticket.resource)
        perm_cache = PermissionCache(self.env, editor, comment_resource)
        return perm_cache, comment_resource

    def test_user_can_edit_own_ticket_comment(self):
        """Authenticated user can modify their own ticket comment.
        """
        self.perm_sys.grant_permission('somebody', 'TICKET_APPEND')
        perm_cache, resource = \
            self._test_edit_ticket_comment('somebody', 'somebody')
        action = 'TICKET_EDIT_COMMENT'

        self.assertIn(action, perm_cache)
        self.assertTrue(self.policy.check_permission(
            action, perm_cache.username, resource, perm_cache))

    def test_user_must_have_ticket_append_to_edit(self):
        """Authenticated user must have TICKET_APPEND to edit own ticket 
        comment.
        """
        perm_cache, resource = \
            self._test_edit_ticket_comment('somebody', 'somebody')
        action = 'TICKET_EDIT_COMMENT'

        self.assertNotIn(action, perm_cache)
        self.assertIsNone(self.policy.check_permission(
            action, perm_cache.username, resource, perm_cache))

    def test_user_cannot_edit_other_ticket_comment(self):
        """Authenticated user cannot modify the ticket comment of another
        user.
        """
        self.perm_sys.grant_permission('somebody', 'TICKET_APPEND')
        perm_cache, resource = \
            self._test_edit_ticket_comment('someother', 'somebody')
        action = 'TICKET_EDIT_COMMENT'

        self.assertNotIn(action, perm_cache)
        self.assertIsNone(self.policy.check_permission(
            action, perm_cache.username, resource, perm_cache))

    def test_anonymous_cannot_edit_ticket_comment(self):
        """Anonymous user cannot modify a ticket comment.
        """
        self.perm_sys.grant_permission('anonymous', 'TICKET_APPEND')
        perm_cache, resource = \
            self._test_edit_ticket_comment('anonymous', 'anonymous')
        action = 'TICKET_EDIT_COMMENT'

        self.assertNotIn(action, perm_cache)
        self.assertIsNone(self.policy.check_permission(
            action, perm_cache.username, resource, perm_cache))

    def _test_change_milestone(self, editor):
        milestone = Milestone(self.env)
        milestone.name = 'milestone1'
        milestone.insert()
        perm_cache = PermissionCache(self.env, editor, milestone.resource)
        return perm_cache, milestone.resource

    def test_user_with_milestone_view_can_change_milestone(self):
        """User with MILESTONE_VIEW can change the ticket milestone.
        """
        self.perm_sys.grant_permission('user_w_mv', 'MILESTONE_VIEW')
        action = 'TICKET_CHG_MILESTONE'
        perm_cache, resource = self._test_change_milestone('user_w_mv')

        self.assertIn(action, perm_cache)
        self.assertTrue(self.policy.check_permission(
            action, perm_cache.username, resource, perm_cache))

    def test_user_without_milestone_view_cannot_change_milestone(self):
        """User without MILESTONE_VIEW cannot change the ticket milestone.
        """
        action = 'TICKET_CHG_MILESTONE'
        perm_cache, resource = self._test_change_milestone('user_w_mv')

        self.assertNotIn(action, perm_cache)
        self.assertIsNone(self.policy.check_permission(
            action, perm_cache.username, resource, perm_cache))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TicketModuleTestCase))
    suite.addTest(unittest.makeSuite(CustomFieldMaxSizeTestCase))
    suite.addTest(unittest.makeSuite(DefaultTicketPolicyTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
