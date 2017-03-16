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

from trac.notification.api import parse_subscriber_config


class ParseSubscriberConfigTestCase(unittest.TestCase):

    def test_empty(self):
        actual = parse_subscriber_config([])
        self.assertEqual({}, actual)
        self.assertEqual([], actual['UnknownSubscriber'])

    def test_subscriber(self):
        config = [('1', 'TicketOwnerSubscriber')]
        expected = {
            'TicketOwnerSubscriber': [
                {'name': '1', 'adverb': 'always', 'format': None,
                 'priority': 100, 'distributor': 'email',
                 'class': 'TicketOwnerSubscriber'},
            ],
        }
        self.assertEqual(expected, parse_subscriber_config(config))

    def test_subscriber_with_attributes(self):
        config = [
            ('1.adverb',      'never'),
            ('1.distributor', 'webhook'),
            ('1.format',      'text/html'),
            ('1.priority',    '42'),
            ('1',             'TicketOwnerSubscriber'),
        ]
        expected = {
            'TicketOwnerSubscriber': [
                {'name': '1', 'adverb': 'never', 'format': 'text/html',
                 'priority': 42, 'distributor': 'webhook',
                 'class': 'TicketOwnerSubscriber'},
            ],
        }
        self.assertEqual(expected, parse_subscriber_config(config))

    def test_subscriber_with_unknown_attributes(self):
        config = [
            ('1',           'TicketOwnerSubscriber'),
            ('1.blah',      'blah'),
            ('1.blah.blah', 'blah.blah'),
        ]
        expected = {
            'TicketOwnerSubscriber': [
                {'name': '1', 'adverb': 'always', 'format': None,
                 'priority': 100, 'distributor': 'email',
                 'blah': 'blah', 'blah.blah': 'blah.blah',
                 'class': 'TicketOwnerSubscriber'},
            ],
        }
        self.assertEqual(expected, parse_subscriber_config(config))

    def test_multiple_subscribers_with_attributes(self):
        config = [
            ('0',             'TicketOwnerSubscriber'),
            ('1',             'TicketOwnerSubscriber'),
            ('1.adverb',      'never'),
            ('1.distributor', 'webhook'),
            ('1.format',      'text/html'),
            ('1.priority',    '43'),
            ('2',             'TicketOwnerSubscriber'),
            ('2.priority',    '42'),
        ]
        expected = {
            'TicketOwnerSubscriber': [
                {'name': '2', 'adverb': 'always', 'format': None,
                 'priority': 42, 'distributor': 'email',
                 'class': 'TicketOwnerSubscriber'},
                {'name': '1', 'adverb': 'never', 'format': 'text/html',
                 'priority': 43, 'distributor': 'webhook',
                 'class': 'TicketOwnerSubscriber'},
                {'name': '0', 'adverb': 'always', 'format': None,
                 'priority': 100, 'distributor': 'email',
                 'class': 'TicketOwnerSubscriber'},
            ],
        }
        self.assertEqual(expected, parse_subscriber_config(config))

    def test_multiple_subscriber_types_with_attributes(self):
        config = [
            ('ticket_updater',             'TicketUpdaterSubscriber'),
            ('ticket_updater.adverb',      'never'),
            ('ticket_updater.distributor', 'webhook'),
            ('ticket_updater.format',      'text/html'),
            ('ticket_updater.priority',    '43'),
            ('ticket_owner',               'TicketOwnerSubscriber'),
            ('ticket_owner.distributor',   'email'),
            ('ticket_owner.priority',      '42'),
        ]
        expected = {
            'TicketOwnerSubscriber': [
                {'name': 'ticket_owner', 'adverb': 'always',
                 'format': None, 'priority': 42,
                 'distributor': 'email', 'class': 'TicketOwnerSubscriber'},
            ],
            'TicketUpdaterSubscriber': [
                {'name': 'ticket_updater', 'adverb': 'never',
                 'format': 'text/html', 'priority': 43,
                 'distributor': 'webhook', 'class': 'TicketUpdaterSubscriber'},
            ],
        }
        self.assertEqual(expected, parse_subscriber_config(config))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ParseSubscriberConfigTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
