# -*- coding: utf-8 -*-
#
# Copyright (C) 2014-2020 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

from datetime import datetime, timedelta
import io
import unittest

from trac.core import Component, TracError, implements
from trac.perm import PermissionCache, PermissionSystem
from trac.resource import Resource, ResourceNotFound
from trac.test import EnvironmentStub, MockRequest
from trac.ticket.api import (ITicketActionController, ITicketManipulator,
                             TicketSystem)
from trac.ticket.model import Milestone, Ticket, Version
from trac.ticket.test import insert_ticket
from trac.ticket.web_ui import DefaultTicketPolicy, TicketModule
from trac.util.datefmt import (datetime_now, format_date, format_datetime,
                               timezone, to_utimestamp, user_time, utc)
from trac.util.html import HTMLTransform
from trac.web.api import HTTPBadRequest, RequestDone
from trac.web.chrome import Chrome


class TicketModuleTestCase(unittest.TestCase):

    mock_components = None
    mock_ticket_operation = None
    mock_ticket_manipulator = None

    @classmethod
    def setUpClass(cls):

        class MockTicketOperation(Component):

            implements(ITicketActionController)

            def __init__(self):
                self.side_effect_count = 0

            def get_ticket_actions(self, req, ticket):
                return [(0, 'mock')]

            def get_all_status(self):
                return []

            def render_ticket_action_control(self, req, ticket, action):
                return 'test', '', "This is a mock operation."

            def get_ticket_changes(self, req, ticket, action):
                return {}

            def apply_action_side_effects(self, req, ticket, action):
                if action == 'mock':
                    self.side_effect_count += 1

        class MockTicketManipulator(Component):

            implements(ITicketManipulator)

            def __init__(self):
                self.validate_ticket_called = 0
                self.validate_comment_called = 0

            def prepare_ticket(self, req, ticket, fields, actions):
                pass

            def validate_ticket(self, req, ticket):
                self.validate_ticket_called += 1
                return []

            def validate_comment(self, req, comment):
                self.validate_comment_called += 1
                return []

        cls.mock_ticket_operation = MockTicketOperation
        cls.mock_ticket_manipulator = MockTicketManipulator
        cls.mock_components = (MockTicketOperation, MockTicketManipulator)

    @classmethod
    def tearDownClass(cls):
        from trac.core import ComponentMeta
        for m in cls.mock_components:
            ComponentMeta.deregister(m)

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
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
        t = insert_ticket(self.env, **old_props)
        comment = new_props.pop('comment', None)
        t.populate(new_props)
        t.save_changes(author, comment=comment)
        return t

    def _has_auto_preview(self, req):
        return any('/trac.cgi/chrome/common/js/auto_preview.js'
                   in s['attrs']['src']
                   for s in req.chrome['scripts'])

    def _insert_ticket(self, **kw):
        """Helper for inserting a ticket into the database"""
        return insert_ticket(self.env, **kw)

    def _prepare_newticket_post_request(self):
        self.env.config.set('ticket', 'default_component', 'component1')
        self.env.config.set('ticket', 'default_milestone', 'milestone1')
        req = MockRequest(self.env, method='GET', path_info='/newticket',
                          authname='user1')

        mod = TicketModule(self.env)
        self.assertTrue(mod.match_request(req))
        data = mod.process_request(req)[1]

        fields = {'field_%s' % f['name']: f.get('value', '')
                  for f in data['fields']}
        fields['field_summary'] = 'The summary'
        req = MockRequest(
            self.env, method='POST', path_info='/newticket', authname='user1',
            args=dict(action=data['action'], submit='Create ticket', **fields)
        )
        return req

    def _prepare_ticket_post_request(self, tid):
        path_info = '/ticket/%s' % tid
        req = MockRequest(self.env, method='GET', path_info=path_info,
                          authname='user1')

        mod = TicketModule(self.env)
        self.assertTrue(mod.match_request(req))
        data = mod.process_request(req)[1]

        start_time = to_utimestamp(data['start_time'])
        ticket = data['ticket']
        fields = {'field_%s' % f: v for f, v in ticket.values.iteritems()}
        req = MockRequest(
            self.env, method='POST', path_info=path_info, authname='user1',
            args=dict(action=data['action'], submit='Submit changes',
                      comment='', replyto='', start_time=start_time,
                      view_time=start_time, **fields)
        )
        return req

    def _process_ticket_request(self, req):
        mod = TicketModule(self.env)
        self.assertTrue(mod.match_request(req))
        try:
            data = mod.process_request(req)[1]
        except RequestDone:
            return None
        else:
            return data

    def _get_field_by_name(self, data, name):
        for field in data['fields']:
            if field['name'] == name:
                return field

    def test_ticket_module_as_default_handler(self):
        """The New Ticket mainnav entry is active when TicketModule is the
        `default_handler` and navigating to the base url. Test for regression
        of https://trac.edgewall.org/ticket/8791.
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

    def test_version_release_date_displayed(self):
        """Version release date is shown in ticket properties."""
        v1 = Version(self.env)
        v1.name = 'v1'
        v1.time = datetime_now(utc) - timedelta(weeks=2)
        v1.insert()
        v2 = Version(self.env)
        v2.name = 'v2'
        v2.insert()
        ticket = [self._insert_ticket(summary='ticket 1', version='v1'),
                  self._insert_ticket(summary='ticket 2', version='v2'),
                  self._insert_ticket(summary='ticket 3', version='v3')]

        def version_field(data):
            for field in data['fields']:
                if field['name'] == 'version':
                    return field

        # Version with release data.
        req = MockRequest(self.env, method='GET', args={'id': ticket[0].id})
        data = self.ticket_module.process_request(req)[1]
        self.assertIn(u'title="Released ',
                      unicode(version_field(data)['rendered']))

        # Version without release data.
        req = MockRequest(self.env, method='GET', args={'id': ticket[1].id})
        data = self.ticket_module.process_request(req)[1]
        self.assertNotIn(u'title="Released ',
                         unicode(version_field(data)['rendered']))

        # Non-existent version.
        req = MockRequest(self.env, method='GET', args={'id': ticket[2].id})
        data = self.ticket_module.process_request(req)[1]
        self.assertNotIn(u'title="Released ',
                         unicode(version_field(data)['rendered']))

    def test_comment_save(self):
        req = self._prepare_newticket_post_request()
        self._process_ticket_request(req)

        req = self._prepare_ticket_post_request(1)
        req.args['comment'] = 'The comment'
        data = self._process_ticket_request(req)

        self.assertIsNone(data)
        self.assertEqual([], req.chrome['warnings'])
        self.assertEqual(['303 See Other'], req.status_sent)
        self.assertEqual('http://example.org/trac.cgi/ticket/1#comment:1',
                         req.headers_sent['Location'])
        self.assertEqual(1, len(Ticket(self.env, 1).get_changelog()))

    def test_whitespace_comment_not_saved(self):
        req = self._prepare_newticket_post_request()
        self._process_ticket_request(req)

        req = self._prepare_ticket_post_request(1)
        req.args['comment'] = u'\u200b\t\t\n\n\n\n\u200b'
        data = self._process_ticket_request(req)

        self.assertIsNone(data)
        self.assertEqual([], req.chrome['warnings'])
        self.assertEqual(['303 See Other'], req.status_sent)
        self.assertEqual('http://example.org/trac.cgi/ticket/1',
                         req.headers_sent['Location'])
        self.assertEqual(0, len(Ticket(self.env, 1).get_changelog()))

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
        PermissionSystem(self.env).grant_permission('owner1', 'TICKET_VIEW')

        req = MockRequest(self.env, authname='owner1', args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['owner']

        self.assertEqual('changed from <span class="trac-author-user">owner1'
                         '</span> to <span class="trac-author">owner2</span>',
                         unicode(field['rendered']))

    def test_ticket_property_diff_owner_change_from_anonymous(self):
        """Property diff message when ticket owner is changed from anonymous.
        """
        t = self._create_ticket_with_change({'owner': 'anonymous'},
                                            {'owner': 'owner1'})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['owner']

        self.assertEqual('changed from <span class="trac-author-anonymous">'
                         'anonymous</span> to <span class="trac-author">'
                         'owner1</span>', unicode(field['rendered']))

    def test_ticket_property_diff_owner_add(self):
        """Property diff message when ticket owner is added."""
        t = self._create_ticket_with_change({'owner': ''},
                                            {'owner': 'owner2'})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['owner']

        self.assertEqual('set to <span class="trac-author">owner2</span>',
                         unicode(field['rendered']))

    def test_ticket_property_diff_owner_remove(self):
        """Property diff message when ticket owner is removed."""
        t = self._create_ticket_with_change({'owner': 'owner1'},
                                            {'owner': ''})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['owner']

        self.assertEqual('<span class="trac-author">owner1</span> removed',
                         unicode(field['rendered']))

    def test_ticket_property_diff_reporter_change(self):
        """Property diff message when ticket reporter is changed."""
        t = self._create_ticket_with_change({'reporter': 'reporter1'},
                                            {'reporter': 'reporter2'})
        PermissionSystem(self.env).grant_permission('reporter2', 'TICKET_VIEW')

        req = MockRequest(self.env, authname='reporter2', args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['reporter']

        self.assertEqual('changed from <span class="trac-author">reporter1'
                         '</span> to <span class="trac-author-user">reporter2'
                         '</span>', unicode(field['rendered']))

    def test_ticket_property_diff_reporter_add(self):
        """Property diff message when ticket reporter is added."""
        t = self._create_ticket_with_change({'reporter': ''},
                                            {'reporter': 'reporter2'})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['reporter']

        self.assertEqual('set to <span class="trac-author">reporter2</span>',
                         unicode(field['rendered']))

    def test_ticket_property_diff_reporter_remove(self):
        """Property diff message when ticket reporter is removed."""
        t = self._create_ticket_with_change({'reporter': 'reporter1'},
                                            {'reporter': ''})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['reporter']

        self.assertEqual('<span class="trac-author">reporter1</span> removed',
                         unicode(field['rendered']))

    def test_ticket_property_diff_cc_separator_changed(self):
        """No change when CC list separator changed."""
        t = self._create_ticket_with_change({'cc': 'user1@d.org, user2@d.org'},
                                            {'cc': 'user1@d.org; user2@d.org'})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]

        self.assertEqual(0, len(data['changes']))

    def test_ticket_property_diff_cc_duplicate_added(self):
        """No change when CC list duplicate added."""
        t = self._create_ticket_with_change({'cc': 'user1@d.org, user2@d.org'},
                                            {'cc': 'user1@d.org, user2@d.org, '
                                                   'user2@d.org'})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]

        self.assertEqual(0, len(data['changes']))

    def test_ticket_property_diff_keywords_separator_changed(self):
        t = self._create_ticket_with_change({'keywords': 'kw1 kw2'},
                                            {'keywords': 'kw1, kw2'})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['keywords']

        self.assertEqual(u'kw1 kw2 → kw1, kw2', unicode(field['rendered']))

    def test_ticket_property_diff_keywords_duplicate_added(self):
        t = self._create_ticket_with_change({'keywords': 'kw1 kw2'},
                                            {'keywords': 'kw1 kw2 kw2'})

        req = MockRequest(self.env, args={'id': t.id})
        data = self.ticket_module.process_request(req)[1]
        field = data['changes'][0]['fields']['keywords']

        self.assertEqual(u'kw1 kw2 → kw1 kw2 kw2', unicode(field['rendered']))

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

        self.assertEqual("The ticket comment is invalid: Must be less than or "
                         "equal to 5 characters",
                         unicode(req.chrome['warnings'][0]))

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

        self.assertEqual("The ticket comment is invalid: Must be less than or "
                         "equal to 5 characters",
                         unicode(req.chrome['warnings'][0]))

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
        self.assertEqual(u'\u2192 <span class="trac-field-new">%s</span>'
                         % dt1_text,
                         unicode(changes[0]['fields']['timefield']['rendered']))
        self.assertEqual(u'<span class="trac-field-old">%s</span> \u2192 '
                         u'<span class="trac-field-new">%s</span>'
                         % (dt1_text, dt2_text),
                         unicode(changes[1]['fields']['timefield']['rendered']))

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
        ps.revoke_permission('authenticated', 'TICKET_MODIFY')
        ps.grant_permission('user1', 'TICKET_APPEND')
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
        perm_sys.revoke_permission('anonymous', 'MILESTONE_VIEW')
        perm_sys.grant_permission('user_w_mv', 'MILESTONE_VIEW')
        self._insert_ticket(summary='the summary')

        def make_req(authname):
            return MockRequest(self.env, authname=authname, method='GET',
                               path_info='/ticket/1')

        def get_milestone_field(fields):
            for field in fields:
                if 'milestone' == field['name']:
                    return field

        req = make_req('user')

        self.assertTrue(self.ticket_module.match_request(req))
        data = self.ticket_module.process_request(req)[1]
        milestone_field = get_milestone_field(data['fields'])
        self.assertFalse(milestone_field['editable'])
        self.assertEqual([], milestone_field['optgroups'][0]['options'])
        self.assertEqual([], milestone_field['optgroups'][1]['options'])

        req = make_req('user_w_mv')

        self.assertTrue(self.ticket_module.match_request(req))
        data = self.ticket_module.process_request(req)[1]
        milestone_field = get_milestone_field(data['fields'])
        self.assertTrue(milestone_field['editable'])
        self.assertEqual([], milestone_field['optgroups'][0]['options'])
        self.assertEqual(['milestone1', 'milestone2',
                          'milestone3', 'milestone4'],
                         milestone_field['optgroups'][1]['options'])

    def test_newticket_has_auto_preview(self):
        """New ticket page has autopreview."""
        req = MockRequest(self.env, method='GET', path_info='/newticket')

        self.assertTrue(self.ticket_module.match_request(req))
        self.ticket_module.process_request(req)

        self.assertTrue(self._has_auto_preview(req))

    def test_newticket_autopreview_disabled_when_no_workflow_actions(self):
        """Newticket autopreview disabled when no workflow actions."""
        config = self.env.config
        config.remove('ticket-workflow', 'create')
        config.remove('ticket-workflow', 'create_and_assign')
        req = MockRequest(self.env, method='GET', path_info='/newticket')

        self.assertTrue(self.ticket_module.match_request(req))
        data = self.ticket_module.process_request(req)[1]

        self.assertEqual([], data['action_controls'])
        self.assertFalse(self._has_auto_preview(req))
        self.assertTrue(data['disable_submit'])

    def test_ticket_autopreview_disabled_when_no_workflow_actions(self):
        """Ticket autopreview disabled when no workflow actions."""
        config = self.env.config
        for option in config.options('ticket-workflow'):
            if not option[0].startswith('leave'):
                config.remove('ticket-workflow', option[0])
        self._insert_ticket(summary='the summary')
        req = MockRequest(self.env, method='GET', path_info='/ticket/1')

        self.assertTrue(self.ticket_module.match_request(req))
        data = self.ticket_module.process_request(req)[1]

        self.assertEqual([], data['action_controls'])
        self.assertFalse(self._has_auto_preview(req))
        self.assertTrue(data['disable_submit'])

    def test_new_ticket_without_ticket_edit_cc(self):
        """User without TICKET_EDIT_CC can only add themselves to CC.
        """
        PermissionSystem(self.env).grant_permission('user', 'TICKET_CREATE')
        req = MockRequest(self.env, authname='user', path_info='/newticket')

        self.assertTrue(self.ticket_module.match_request(req))
        data = self.ticket_module.process_request(req)[1]
        cc_field = self._get_field_by_name(data, 'cc')

        self.assertEqual('Add Cc', cc_field['edit_label'])
        self.assertEqual('user', cc_field['cc_entry'])
        self.assertEqual('add', cc_field['cc_action'])
        self.assertFalse(cc_field['cc_update'])

    def test_new_ticket_with_ticket_edit_cc(self):
        """User with TICKET_EDIT_CC can edit CC field."""
        for p in ('TICKET_CREATE', 'TICKET_EDIT_CC'):
            PermissionSystem(self.env).grant_permission('user', p)
        req = MockRequest(self.env, authname='user', path_info='/newticket')

        self.assertTrue(self.ticket_module.match_request(req))
        data = self.ticket_module.process_request(req)[1]
        cc_field = self._get_field_by_name(data, 'cc')

        for k in ('cc_action', 'cc_entry', 'cc_update', 'edit_label'):
            self.assertNotIn(k, cc_field)

    def test_existing_ticket_no_ticket_edit_cc(self):
        """User without TICKET_EDIT_CC can only add self to CC field."""
        PermissionSystem(self.env).grant_permission('user', 'TICKET_VIEW')
        self._insert_ticket(reporter='reporter')
        req = MockRequest(self.env, authname='user', path_info='/ticket/1')

        self.assertTrue(self.ticket_module.match_request(req))
        data = self.ticket_module.process_request(req)[1]
        cc_field = self._get_field_by_name(data, 'cc')

        self.assertIn('cc_entry', cc_field)
        self.assertEqual('user', cc_field['cc_entry'])
        self.assertIn('cc_action', cc_field)
        self.assertEqual('add', cc_field['cc_action'])

    def test_existing_ticket_ticket_edit_cc(self):
        """User with TICKET_EDIT_CC can modify the CC field."""
        ps = PermissionSystem(self.env)
        for perm in ('TICKET_EDIT_CC', 'TICKET_VIEW'):
            ps.grant_permission('user', perm)
        self._insert_ticket(reporter='reporter')
        req = MockRequest(self.env, authname='user', path_info='/ticket/1')

        self.assertTrue(self.ticket_module.match_request(req))
        data = self.ticket_module.process_request(req)[1]
        cc_field = self._get_field_by_name(data, 'cc')

        self.assertNotIn('cc_entry', cc_field)
        self.assertNotIn('cc_action', cc_field)

    def test_action_side_effects_applied(self):
        self.env.config.set('ticket', 'workflow',
                            'ConfigurableTicketWorkflow, '
                            'MockTicketOperation')
        ticket = self._insert_ticket(
            reporter='reporter', summary='the summary', status='new')
        change_time = Ticket(self.env, ticket.id)['changetime']
        view_time = str(to_utimestamp(change_time))
        req = MockRequest(
            self.env, method='POST', path_info='/ticket/1',
            args={'submit': True, 'action': 'mock', 'id': '1',
                  'view_time': view_time})
        operation = self.mock_ticket_operation(self.env)

        self.assertEqual(0, operation.side_effect_count)
        self.assertTrue(self.ticket_module.match_request(req))
        with self.assertRaises(RequestDone):
            self.ticket_module.process_request(req)

        self.assertEqual(1, operation.side_effect_count)
        self.assertIn(('DEBUG', "Side effect for MockTicketOperation"),
                      self.env.log_messages)

    def test_old_values_in_script_data_with_time_field(self):
        when = datetime(2009, 1, 12, 13, 21, 20, 123456, utc)
        when_ts = str(to_utimestamp(when))

        self.env.config.set('ticket-custom', 'due', 'text')
        self._reset_ticket_fields()
        for due in ('', 'invalid', '001234567890123456'):
            ticket = self._insert_ticket(when=when, reporter='joe',
                                         summary='the summary', status='new',
                                         due=due)
        self.env.config.set('ticket-custom', 'due', 'time')
        self._reset_ticket_fields()
        for due in ('', datetime(2010, 3, 14, 22, 30, 29, 234567, utc)):
            self._insert_ticket(when=when, reporter='joe',
                                summary='the summary', status='new', due=due)

        def get_old_values(method, path_info, **kwargs):
            req = MockRequest(self.env, method=method, path_info=path_info,
                              **kwargs)
            self.assertTrue(self.ticket_module.match_request(req))
            rv = self.ticket_module.process_request(req)
            self.assertEqual('ticket.html', rv[0])
            self.assertFalse(req.chrome['warnings'])
            return req.chrome['script_data']['old_values']

        old_values = get_old_values('GET', '/ticket/1')
        self.assertEqual(None, old_values['due'])
        self.assertEqual('2009-01-12T13:21:20Z', old_values['time'])
        self.assertEqual('2009-01-12T13:21:20Z', old_values['changetime'])
        old_values = get_old_values('GET', '/ticket/2')
        self.assertEqual(None, old_values['due'])
        old_values = get_old_values('GET', '/ticket/3')
        self.assertEqual('2009-02-13T23:31:30Z', old_values['due'])
        old_values = get_old_values('GET', '/ticket/4')
        self.assertEqual(None, old_values['due'])
        old_values = get_old_values('GET', '/ticket/5')
        self.assertEqual('2010-03-14T22:30:29Z', old_values['due'])

        old_values = get_old_values('POST', '/ticket/1',
            args={'field_due': 'now', 'preview': '1', 'action': 'leave',
                  'start_time': when_ts, 'view_time': when_ts})
        self.assertEqual(None, old_values['due'])
        self.assertEqual('2009-01-12T13:21:20Z', old_values['time'])
        self.assertEqual('2009-01-12T13:21:20Z', old_values['changetime'])
        old_values = get_old_values('POST', '/ticket/3',
            args={'field_due': '', 'preview': '1', 'action': 'leave',
                  'start_time': when_ts, 'view_time': when_ts})
        self.assertEqual('2009-02-13T23:31:30Z', old_values['due'])

    def test_newticket_ticket_validate_comment_not_called(self):
        req = self._prepare_newticket_post_request()

        self._process_ticket_request(req)

        self.assertEqual([], req.chrome['warnings'])
        self.assertEqual(['303 See Other'], req.status_sent)
        self.assertEqual('http://example.org/trac.cgi/ticket/1',
                         req.headers_sent['Location'])
        tm = self.mock_ticket_manipulator(self.env)
        self.assertEqual(0, tm.validate_comment_called)
        self.assertEqual(1, tm.validate_ticket_called)

    def _test_custom_field_with_ticketlink_query_option(self, ticketlink_query):
        ticket_custom = self.env.config['ticket-custom']
        ticket_custom.set('select1', 'select')
        ticket_custom.set('select1.options', 'one|two')
        if ticketlink_query:
            ticket_custom.set('select1.ticketlink_query', ticketlink_query)
        ticket_custom.set('checkbox1', 'checkbox')
        if ticketlink_query:
            ticket_custom.set('checkbox1.ticketlink_query', ticketlink_query)
        ticket_custom.set('radio1', 'radio')
        ticket_custom.set('radio1.options', '1|2')
        if ticketlink_query:
            ticket_custom.set('radio1.ticketlink_query', ticketlink_query)
        ticket_custom.set('text1', 'text')
        ticket_custom.set('text1.format', 'plain')
        if ticketlink_query:
            ticket_custom.set('text1.ticketlink_query', ticketlink_query)
        ticket_custom.set('text2', 'text')
        ticket_custom.set('text2.format', 'wiki')
        if ticketlink_query:
            ticket_custom.set('text2.ticketlink_query', ticketlink_query)
        ticket_custom.set('text3', 'text')
        ticket_custom.set('text3.format', 'reference')
        if ticketlink_query:
            ticket_custom.set('text3.ticketlink_query', ticketlink_query)
        ticket_custom.set('text4', 'text')
        ticket_custom.set('text4.format', 'list')
        if ticketlink_query:
            ticket_custom.set('text4.ticketlink_query', ticketlink_query)
        ticket_custom.set('textarea1', 'textarea')
        if ticketlink_query:
            ticket_custom.set('textarea1.ticketlink_query', ticketlink_query)
        ticket_custom.set('time1', 'time')
        if ticketlink_query:
            ticket_custom.set('time1.ticketlink_query', ticketlink_query)

        ticket = self._insert_ticket(
            reporter='reporter', summary='the summary', status='new',
            select1='two', checkbox1='1', radio1='2', text1='word1',
            text2='WordTwo', text3='word2', text4='word3 word4',
            textarea1='word5\nword6',
            time1=datetime(2010, 3, 14, 22, 30, 29, 234567, utc))
        req = MockRequest(self.env, method='GET', path_info='/ticket/1')

        self.assertTrue(self.ticket_module.match_request(req))
        data = self.ticket_module.process_request(req)[1]

        base = '<a href="/trac.cgi/query%s&amp;' % \
               (ticketlink_query if ticketlink_query \
                else self.env.config.get('query', 'ticketlink_query'))
        field = self._get_field_by_name(data, 'select1')
        self.assertEqual('%sselect1=two">two</a>' % base,
                         unicode(field['rendered']))
        field = self._get_field_by_name(data, 'checkbox1')
        self.assertEqual('%scheckbox1=1">yes</a>' % base,
                         unicode(field['rendered']))
        field = self._get_field_by_name(data, 'radio1')
        self.assertEqual('%sradio1=2">2</a>' % base,
                         unicode(field['rendered']))
        field = self._get_field_by_name(data, 'text1')
        self.assertNotIn('rendered', field)
        field = self._get_field_by_name(data, 'text2')
        self.assertNotIn('rendered', field)
        field = self._get_field_by_name(data, 'text3')
        self.assertEqual('%stext3=word2">word2</a>' % base,
                         unicode(field['rendered']))
        field = self._get_field_by_name(data, 'text4')
        self.assertEqual('%(base)stext4=~word3">word3</a> '
                         '%(base)stext4=~word4">word4</a>' % {'base': base},
                         unicode(field['rendered']))
        field = self._get_field_by_name(data, 'textarea1')
        self.assertNotIn('rendered', field)
        field = self._get_field_by_name(data, 'time1')
        self.assertNotIn('rendered', field)

    def test_custom_field_custom_ticketlink_query_option(self):
        """Custom fields with default ticketlink_query."""
        ticketlink_query = '?status=accepted'
        self._test_custom_field_with_ticketlink_query_option(ticketlink_query)

    def test_custom_field_custom_ticketlink_query_option_none(self):
        """Custom fields with custom ticketlink_query."""
        self._test_custom_field_with_ticketlink_query_option(None)

    def test_custom_field_custom_ticketlink_query_option_empty(self):
        """Custom fields with custom ticketlink_query."""
        self._test_custom_field_with_ticketlink_query_option('')

    def _reset_ticket_fields(self):
        tktsys = TicketSystem(self.env)
        tktsys.reset_ticket_fields()
        del tktsys.custom_fields


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
        self.assertIn("The ticket field <strong>Text1</strong> is invalid: "
                      "Must be less than or equal to 5 characters",
                      unicode(req.chrome['warnings'][0]))

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

    def _insert_ticket(self, reporter):
        return insert_ticket(self.env, reporter=reporter,
                             summary='The summary', description='The text.')

    def test_reporter_can_edit_own_ticket_description(self):
        """Authenticated user can modify description of ticket they
        reported. The authenticated user must have TICKET_CHGPROP or
        TICKET_APPEND.
        """
        self.perm_sys.grant_permission('somebody1', 'TICKET_CHGPROP')
        self.perm_sys.grant_permission('somebody2', 'TICKET_APPEND')
        ticket1 = self._insert_ticket('somebody1')
        ticket2 = self._insert_ticket('somebody2')
        ticket3 = self._insert_ticket('somebody3')
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
        ticket = self._insert_ticket('somebodyelse')
        perm_cache = PermissionCache(self.env, 'somebody', ticket.resource)
        action = 'TICKET_EDIT_DESCRIPTION'

        self.assertNotIn(action, perm_cache)
        self.assertIsNone(self.policy.check_permission(
            action, perm_cache.username, ticket.resource, perm_cache))

    def test_anonymous_cannot_edit_ticket_description(self):
        """Anonymous user cannot modify description of ticket they
        reported.
        """
        ticket = self._insert_ticket('anonymous')
        perm_cache = PermissionCache(self.env, 'anonymous')
        action = 'TICKET_EDIT_DESCRIPTION'

        self.assertNotIn('TICKET_EDIT_DESCRIPTION',
                         perm_cache(ticket.resource))
        self.assertIsNone(self.policy.check_permission(
            action, perm_cache.username, ticket.resource, perm_cache))

    def _test_edit_ticket_comment(self, commenter, editor):
        ticket = self._insert_ticket(commenter)
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
