# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Edgewall Software
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

from trac.core import Component, implements
from trac.notification.mail import EmailDistributor, AlwaysEmailSubscriber
from trac.notification.model import Subscription
from trac.notification.prefs import NotificationPreferences
from trac.prefs.web_ui import PreferencesModule
from trac.test import EnvironmentStub, MockRequest
from trac.ticket.notification import CarbonCopySubscriber, TicketFormatter
from trac.web.api import RequestDone


class NotificationPreferencesTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.prefs_mod = PreferencesModule(self.env)
        ids = self._add_subscriptions([
            {'sid': 'foo', 'class_': 'TicketOwnerSubscriber'},
            {'sid': 'foo', 'class_': 'CarbonCopySubscriber'},
            {'sid': 'foo', 'class_': 'TicketReporterSubscriber'},
            {'sid': 'bar', 'class_': 'CarbonCopySubscriber'},
        ])
        self.foo_rule0 = ids[0]
        self.foo_rule1 = ids[1]
        self.foo_rule2 = ids[2]
        self.bar_rule0 = ids[3]

    def tearDown(self):
        self.env.reset_db()

    def _add_subscription(self, **kwargs):
        props = {'sid': None, 'authenticated': 1, 'distributor': 'email',
                 'format': 'text/plain', 'adverb': 'always',
                 'class': 'TicketOwnerSubscriber'}
        props.update((k.rstrip('_'),
                      (v or None) if isinstance(v, basestring) else v)
                     for k, v in kwargs.iteritems())
        assert props['sid'] is not None
        return Subscription.add(self.env, props)

    def _add_subscriptions(self, rows):
        with self.env.db_transaction:
            return [self._add_subscription(**row) for row in rows]

    def _get_rules(self, sid, authenticated=1):
        return self.env.db_query("""
            SELECT distributor, format, priority, adverb, class
            FROM notify_subscription
            WHERE sid=%s AND authenticated=1
            ORDER BY distributor, priority
            """, (sid,))

    def _request(self, **kwargs):
        kwargs.setdefault('method', 'POST')
        kwargs.setdefault('path_info', '/prefs/notification')
        return MockRequest(self.env, **kwargs)

    def _process(self, req):
        self.assertTrue(self.prefs_mod.match_request(req))
        return self.prefs_mod.process_request(req)

    def test_add_rule(self):
        args = {'action': 'add-rule_email', 'new-adverb-email': 'never',
                'format-email': '', 'new-rule-email': 'TicketOwnerSubscriber'}
        req = self._request(authname='baz', args=args)
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual(
            [('email', None, 1, 'never', 'TicketOwnerSubscriber')],
            self._get_rules('baz'))

        args = {'action': 'add-rule_email', 'new-adverb-email': 'always',
                'format-email': 'text/plain',
                'new-rule-email': 'CarbonCopySubscriber'}
        req = self._request(authname='baz', args=args)
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual(
            [('email', None, 1, 'never', 'TicketOwnerSubscriber'),
             ('email', 'text/plain', 2, 'always', 'CarbonCopySubscriber')],
            self._get_rules('baz'))

    def test_delete_rule(self):
        req = self._request(authname='foo',
                            args={'action': 'delete-rule_%d' % self.foo_rule1})
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual(
            [('email', 'text/plain', 1, 'always', 'TicketOwnerSubscriber'),
             ('email', 'text/plain', 2, 'always', 'TicketReporterSubscriber')],
            self._get_rules('foo'))

        # try to delete non-existent rule
        rules = self._get_rules('foo')
        req = self._request(authname='foo',
                            args={'action': 'delete-rule_%d' % self.foo_rule1})
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual(rules, self._get_rules('foo'))

        # try to delete non-owned rules
        rules = self._get_rules('bar')
        req = self._request(authname='foo',
                            args={'action': 'delete-rule_%d' % self.bar_rule0})
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual(rules, self._get_rules('bar'))

    def test_move_rule(self):
        # move to last
        req = self._request(authname='foo',
                            args={'action': 'move-rule_%d-3' % self.foo_rule1})
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual(
            [('email', 'text/plain', 1, 'always', 'TicketOwnerSubscriber'),
             ('email', 'text/plain', 2, 'always', 'TicketReporterSubscriber'),
             ('email', 'text/plain', 3, 'always', 'CarbonCopySubscriber')],
            self._get_rules('foo'))
        self.assertEqual(
            [('email', 'text/plain', 1, 'always', 'CarbonCopySubscriber')],
            self._get_rules('bar'))

        # move to first
        req = self._request(authname='foo',
                            args={'action': 'move-rule_%d-1' % self.foo_rule1})
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual(
            [('email', 'text/plain', 1, 'always', 'CarbonCopySubscriber'),
             ('email', 'text/plain', 2, 'always', 'TicketOwnerSubscriber'),
             ('email', 'text/plain', 3, 'always', 'TicketReporterSubscriber')],
            self._get_rules('foo'))

        # move to same position
        rules = self._get_rules('foo')
        req = self._request(authname='foo',
                            args={'action': 'move-rule_%d-1' % self.foo_rule1})
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual(rules, self._get_rules('foo'))

        # try to move to out of range
        rules = self._get_rules('foo')
        req = self._request(authname='foo', args={'action': 'move-rule_%d-42' %
                                                            self.foo_rule1})
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual(rules, self._get_rules('foo'))

        # try to move non-owned rules
        rules = self._get_rules('foo')
        req = self._request(authname='bar',
                            args={'action': 'move-rule_%d-3' % self.foo_rule1})
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual(rules, self._get_rules('foo'))

        rules = self._get_rules('foo')

        # try to move non-existent rule
        req = self._request(authname='foo', args={'action': 'move-rule_42-1'})
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual(rules, self._get_rules('foo'))

        # invalid id
        req = self._request(authname='foo',
                            args={'action': 'move-rule_0-1'})
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual(rules, self._get_rules('foo'))
        req = self._request(authname='foo',
                            args={'action': 'move-rule_a-1'})
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual(rules, self._get_rules('foo'))

        # invalid priority
        req = self._request(authname='foo',
                            args={'action': 'move-rule_%d-0' % self.foo_rule1})
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual(rules, self._get_rules('foo'))
        req = self._request(authname='foo',
                            args={'action': 'move-rule_%d-a' % self.foo_rule1})
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual(rules, self._get_rules('foo'))

    def test_set_format(self):
        # set text/html
        req = self._request(authname='foo', args={'action': 'set-format_email',
                                                  'format-email': 'text/html'})
        self.assertNotIn('notification.format.email', req.session)
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual(
            [('email', 'text/html', 1, 'always', 'TicketOwnerSubscriber'),
             ('email', 'text/html', 2, 'always', 'CarbonCopySubscriber'),
             ('email', 'text/html', 3, 'always', 'TicketReporterSubscriber')],
            self._get_rules('foo'))
        self.assertEqual(
            [('email', 'text/plain', 1, 'always', 'CarbonCopySubscriber')],
            self._get_rules('bar'))
        self.assertEqual('text/html', req.session['notification.format.email'])

        # set default format
        req = self._request(authname='foo', args={'action': 'set-format_email',
                                                  'format-email': ''})
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual(
            [('email', None, 1, 'always', 'TicketOwnerSubscriber'),
             ('email', None, 2, 'always', 'CarbonCopySubscriber'),
             ('email', None, 3, 'always', 'TicketReporterSubscriber')],
            self._get_rules('foo'))
        self.assertNotIn('notification.format.email', req.session)

    def test_replace(self):
        arg_list = [
            ('action', 'replace_all'),
            ('format-email', 'text/plain'),
            ('adverb-email', 'always'),
            ('adverb-email', 'never'),
            ('adverb-email', 'always'),
            ('adverb-email', 'always'),
            ('class-email', 'TicketOwnerSubscriber'),
            ('class-email', 'CarbonCopySubscriber'),
            ('class-email', 'TicketReporterSubscriber'),
            ('class-email', 'TicketUpdaterSubscriber'),
        ]
        req = self._request(authname='foo', arg_list=arg_list)
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual(
            [('email', 'text/plain', 1, 'always', 'TicketOwnerSubscriber'),
             ('email', 'text/plain', 2, 'never', 'CarbonCopySubscriber'),
             ('email', 'text/plain', 3, 'always', 'TicketReporterSubscriber'),
             ('email', 'text/plain', 4, 'always', 'TicketUpdaterSubscriber')],
            self._get_rules('foo'))
        self.assertEqual(
            [('email', 'text/plain', 1, 'always', 'CarbonCopySubscriber')],
            self._get_rules('bar'))

        arg_list = [
            ('action', 'replace_all'), ('format-email', ''),
            ('adverb-email', 'always'),
            ('class-email', 'TicketOwnerSubscriber'),
        ]
        req = self._request(authname='foo', arg_list=arg_list)
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual(
            [('email', None, 1, 'always', 'TicketOwnerSubscriber')],
            self._get_rules('foo'))

        arg_list = [('action', 'replace_all'), ('format-email', '')]
        req = self._request(authname='foo', arg_list=arg_list)
        self.assertRaises(RequestDone, self._process, req)
        self.assertEqual([], self._get_rules('foo'))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(NotificationPreferencesTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
