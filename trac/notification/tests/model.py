# -*- coding: utf-8 -*-
#
# Copyright (C) 2016 Edgewall Software
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
from datetime import datetime

from trac.notification.model import Subscription
from trac.test import EnvironmentStub, MockRequest
from trac.util.datefmt import to_utimestamp, utc


class SubscriptionTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def tearDown(self):
        self.env.reset_db()

    def _add_subscriber(self, req, class_, distributor='email',
                        format='text/plain', adverb='always'):
        session = req.session
        args = {'sid': session.sid, 'authenticated': session.authenticated,
                'distributor': distributor, 'format': format, 'adverb': adverb,
                'class': class_}
        return Subscription.add(self.env, args)

    def _insert_rows(self):
        rows = [
            ('joe', 1, 'email', 'text/plain', 1, 'always', 'EmailSubscriber1'),
            ('joe', 1, 'email', 'text/html',  2, 'always', 'EmailSubscriber2'),
            ('joe', 1, 'email', 'text/plain', 3, 'always', 'EmailSubscriber3'),
            ('joe', 1, 'xmpp',  'text/html',  1, 'always', 'XmppSubscriber1'),
            ('joe', 1, 'xmpp',  'text/plain', 2, 'never',  'XmppSubscriber2'),
            ('joe', 1, 'xmpp',  'text/html',  3, 'never',  'XmppSubscriber3'),
            ('joe', 1, 'irc',   'text/plain', 1, 'never',  'IrcSubscriber1'),
            ('joe', 1, 'irc',   'text/plain', 2, 'never',  'IrcSubscriber2'),
            ('joe', 1, 'irc',   'text/plain', 3, 'never',  'IrcSubscriber3'),
            ('jes', 1, 'email', 'text/html',  1, 'always', 'EmailSubscriber1'),
            ('jes', 1, 'email', 'text/plain', 2, 'never',  'EmailSubscriber2'),
            ('jes', 1, 'email', 'text/html',  3, 'always', 'EmailSubscriber3'),
            ('jan', 1, 'xmpp',  'text/plain', 1, 'always', 'XmppSubscriber1'),
            ('jan', 1, 'xmpp',  'text/html',  2, 'never',  'XmppSubscriber2'),
            ('jan', 1, 'xmpp',  'text/plain', 3, 'never',  'XmppSubscriber3'),
            ('jim', 1, 'irc',   'text/html',  1, 'always', 'IrcSubscriber1'),
            ('jim', 1, 'irc',   'text/plain', 2, 'never',  'IrcSubscriber2'),
            ('jim', 1, 'irc',   'text/html',  3, 'always', 'IrcSubscriber3'),
        ]
        ts = to_utimestamp(datetime(2016, 2, 3, 12, 34, 56, 987654, utc))
        with self.env.db_transaction as db:
            cursor = db.cursor()
            cursor.executemany("""
                INSERT INTO notify_subscription (
                    time, changetime, sid, authenticated, distributor,
                    format, priority, adverb, class)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [(ts + idx, ts + idx * 2) + row for idx, row
                                                in enumerate(rows)])

    def _props(self, items, name):
        return [item[name] for item in items]

    def test_add(self):
        req = MockRequest(self.env, authname='joe')
        with self.env.db_transaction:
            self._add_subscriber(req, 'TicketSubscriber1', format='text/html')
            self._add_subscriber(req, 'TicketSubscriber2')
            self._add_subscriber(req, 'TicketSubscriber3', format='text/html')
            self._add_subscriber(req, 'XmppSubscriber1', distributor='xmpp',
                                 adverb='never')
        self.assertEqual(
            [(u'joe', 1, u'email', u'text/html', 1, u'always',
              u'TicketSubscriber1'),
             (u'joe', 1, u'email', u'text/plain', 2, u'always',
              u'TicketSubscriber2'),
             (u'joe', 1, u'email', u'text/html', 3, u'always',
              u'TicketSubscriber3'),
             (u'joe', 1, u'xmpp',  u'text/plain', 1, u'never',
              u'XmppSubscriber1')],
            self.env.db_query("""\
                SELECT sid, authenticated, distributor, format, priority,
                       adverb, class
                FROM notify_subscription
                WHERE sid=%s AND authenticated=%s
                ORDER BY distributor, priority""", ('joe', 1)))

    def test_delete(self):
        req = MockRequest(self.env, authname='joe')
        with self.env.db_transaction:
            ids = [self._add_subscriber(req, 'TicketSubscriber1'),
                   self._add_subscriber(req, 'TicketSubscriber2'),
                   self._add_subscriber(req, 'TicketSubscriber3'),
                   self._add_subscriber(req, 'XmppSubscriber1',
                                        distributor='xmpp', adverb='never'),
                   self._add_subscriber(req, 'XmppSubscriber2',
                                        distributor='xmpp')]
        self.assertEqual(5, self.env.db_query("""\
            SELECT COUNT(*) FROM notify_subscription
            WHERE sid=%s AND authenticated=%s""", ('joe', 1))[0][0])

        Subscription.delete(self.env, ids[1])
        rows = self.env.db_query("""\
            SELECT id, distributor, priority, class FROM notify_subscription
            WHERE sid=%s AND authenticated=%s
            ORDER BY distributor, priority""", ('joe', 1))
        self.assertEqual((ids[0], 'email', 1, 'TicketSubscriber1'), rows[0])
        self.assertEqual((ids[2], 'email', 2, 'TicketSubscriber3'), rows[1])
        self.assertEqual((ids[3], 'xmpp', 1, 'XmppSubscriber1'), rows[2])
        self.assertEqual((ids[4], 'xmpp', 2, 'XmppSubscriber2'), rows[3])
        self.assertEqual(4, len(rows))

    def test_find_by_sid_and_distributor(self):
        self._insert_rows()
        items = Subscription.find_by_sid_and_distributor(self.env, 'joe', True,
                                                         'xmpp')
        self.assertEqual(['joe'] * 3, self._props(items, 'sid'))
        self.assertEqual([1] * 3, self._props(items, 'authenticated'))
        self.assertEqual(['xmpp'] * 3, self._props(items, 'distributor'))
        self.assertEqual(['text/html', 'text/plain', 'text/html'],
                         self._props(items, 'format'))
        self.assertEqual([1, 2, 3], self._props(items, 'priority'))
        self.assertEqual(['always', 'never', 'never'], self._props(items, 'adverb'))
        self.assertEqual(['XmppSubscriber1', 'XmppSubscriber2',
                          'XmppSubscriber3'], self._props(items, 'class'))

    def test_find_by_sids_and_class(self):
        self._insert_rows()
        sids = [('joe', True), ('jes', True), ('jan', True), ('jim', True)]
        items = Subscription.find_by_sids_and_class(self.env, sids,
                                                    'IrcSubscriber3')
        self.assertEqual(['joe', 'jim'], self._props(items, 'sid'))
        self.assertEqual([1] * 2, self._props(items, 'authenticated'))
        self.assertEqual(['irc'] * 2, self._props(items, 'distributor'))
        self.assertEqual(['text/plain', 'text/html'],
                         self._props(items, 'format'))
        self.assertEqual([3, 3], self._props(items, 'priority'))
        self.assertEqual(['never', 'always'], self._props(items, 'adverb'))
        self.assertEqual(['IrcSubscriber3', 'IrcSubscriber3'],
                         self._props(items, 'class'))

    def test_move(self):
        def query_subs():
            return self.env.db_query("""\
                SELECT distributor, priority, class
                FROM notify_subscription WHERE sid=%s AND authenticated=%s
                ORDER BY distributor, priority""", ('joe', 1))

        req = MockRequest(self.env, authname='joe')
        with self.env.db_transaction:
            rule_ids = {}
            for class_, distributor in [('EmailSubscriber1', 'email'),
                                        ('EmailSubscriber2', 'email'),
                                        ('EmailSubscriber3', 'email'),
                                        ('EmailSubscriber4', 'email'),
                                        ('XmppSubscriber1',  'xmpp'),
                                        ('XmppSubscriber2',  'xmpp')]:
                rule_ids[(class_, distributor)] = \
                    self._add_subscriber(req, class_, distributor)
        self.assertEqual([('email', 1, 'EmailSubscriber1'),
                          ('email', 2, 'EmailSubscriber2'),
                          ('email', 3, 'EmailSubscriber3'),
                          ('email', 4, 'EmailSubscriber4'),
                          ('xmpp',  1, 'XmppSubscriber1'),
                          ('xmpp',  2, 'XmppSubscriber2'),
                         ], query_subs())

        Subscription.move(self.env, rule_ids[('EmailSubscriber3', 'email')], 1)
        self.assertEqual([('email', 1, 'EmailSubscriber3'),
                          ('email', 2, 'EmailSubscriber1'),
                          ('email', 3, 'EmailSubscriber2'),
                          ('email', 4, 'EmailSubscriber4'),
                          ('xmpp',  1, 'XmppSubscriber1'),
                          ('xmpp',  2, 'XmppSubscriber2'),
                         ], query_subs())

        Subscription.move(self.env, rule_ids[('EmailSubscriber1', 'email')], 4)
        self.assertEqual([('email', 1, 'EmailSubscriber3'),
                          ('email', 2, 'EmailSubscriber2'),
                          ('email', 3, 'EmailSubscriber4'),
                          ('email', 4, 'EmailSubscriber1'),
                          ('xmpp',  1, 'XmppSubscriber1'),
                          ('xmpp',  2, 'XmppSubscriber2'),
                         ], query_subs())

        Subscription.move(self.env, rule_ids[('EmailSubscriber3', 'email')], 3)
        self.assertEqual([('email', 1, 'EmailSubscriber2'),
                          ('email', 2, 'EmailSubscriber4'),
                          ('email', 3, 'EmailSubscriber3'),
                          ('email', 4, 'EmailSubscriber1'),
                          ('xmpp',  1, 'XmppSubscriber1'),
                          ('xmpp',  2, 'XmppSubscriber2'),
                         ], query_subs())

    def test_replace_all(self):
        def query(sid, authenticated):
            return self.env.db_query("""\
                SELECT distributor, format, priority, adverb, class
                FROM notify_subscription
                WHERE sid=%s AND authenticated=%s
                ORDER BY distributor, priority""", (sid, authenticated))

        req = MockRequest(self.env, authname='joe')
        sess = req.session
        items = [
            ('email', 'text/plain', 'always', 'TicketSubscriber1'),
            ('email', 'text/html',  'always', 'TicketSubscriber2'),
            ('email', 'text/html',  'always', 'TicketSubscriber3'),
            ('xmpp',  'text/html',  'never',  'XmppSubscriber1'),
            ('xmpp',  'text/plain', 'always', 'XmppSubscriber2'),
        ]
        items = [dict(zip(('distributor', 'format', 'adverb', 'class'), item))
                 for item in items]
        Subscription.replace_all(self.env, sess.sid, sess.authenticated, items)
        rows = query('joe', 1)
        expected = [
            ('email', 'text/plain', 1, 'always', 'TicketSubscriber1'),
            ('email', 'text/html',  2, 'always', 'TicketSubscriber2'),
            ('email', 'text/html',  3, 'always', 'TicketSubscriber3'),
            ('xmpp',  'text/html',  1, 'never',  'XmppSubscriber1'),
            ('xmpp',  'text/plain', 2, 'always', 'XmppSubscriber2'),
        ]
        self.assertEqual(expected, rows)

        items = [
            ('email', 'text/plain', 'never',  'TicketSubscriber3'),
            ('xmpp',  'text/html',  'always', 'XmppSubscriber1'),
        ]
        items = [dict(zip(('distributor', 'format', 'adverb', 'class'), item))
                 for item in items]
        Subscription.replace_all(self.env, sess.sid, sess.authenticated, items)
        rows = query('joe', 1)
        expected = [
            ('email', 'text/plain', 1, 'never',  'TicketSubscriber3'),
            ('xmpp',  'text/html',  1, 'always', 'XmppSubscriber1'),
        ]
        self.assertEqual(expected, rows)

        Subscription.replace_all(self.env, sess.sid, sess.authenticated, [])
        self.assertEqual([], query('joe', 1))

    def test_update_format_by_distributor_and_sid(self):
        self._insert_rows()
        Subscription.update_format_by_distributor_and_sid(
            self.env, 'email', 'joe', True, 'application/pdf')
        rows = self.env.db_query("""\
            SELECT distributor, format, priority, adverb, class
            FROM notify_subscription
            WHERE sid=%s AND authenticated=%s
            ORDER BY distributor, priority""", ('joe', 1))
        expected = [
            ('email', 'application/pdf', 1, 'always', 'EmailSubscriber1'),
            ('email', 'application/pdf', 2, 'always', 'EmailSubscriber2'),
            ('email', 'application/pdf', 3, 'always', 'EmailSubscriber3'),
            ('irc',   'text/plain',      1, 'never',  'IrcSubscriber1'),
            ('irc',   'text/plain',      2, 'never',  'IrcSubscriber2'),
            ('irc',   'text/plain',      3, 'never',  'IrcSubscriber3'),
            ('xmpp',  'text/html',       1, 'always', 'XmppSubscriber1'),
            ('xmpp',  'text/plain',      2, 'never',  'XmppSubscriber2'),
            ('xmpp',  'text/html',       3, 'never',  'XmppSubscriber3'),
        ]
        self.assertEqual(expected, rows)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(SubscriptionTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
