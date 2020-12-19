# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2020 Edgewall Software
# Copyright (C) 2005-2006 Emmanuel Blot <emmanuel.blot@free.fr>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.
#
# Include a basic SMTP server, based on L. Smithson
# (lsmithson@open-networks.co.uk) extensible Python SMTP Server
#

import base64
import io
import quopri
import re
import unittest
from datetime import datetime, timedelta

from trac.attachment import Attachment
from trac.notification.api import NotificationSystem
from trac.perm import PermissionSystem
from trac.test import EnvironmentStub, MockRequest, mkdtemp
from trac.tests.notification import SMTP_TEST_PORT, SMTPThreadedServer, \
                                    parse_smtp_message
from trac.ticket.model import Ticket
from trac.ticket.notification import (
    BatchTicketChangeEvent, Subscription, TicketChangeEvent,
    TicketNotificationSystem)
from trac.ticket.test import insert_ticket
from trac.ticket.web_ui import TicketModule
from trac.util.datefmt import datetime_now, utc

MAXBODYWIDTH = 76
smtpd = None


def setUpModule():
    global smtpd
    smtpd = SMTPThreadedServer(SMTP_TEST_PORT)
    smtpd.start()


def tearDownModule():
    smtpd.stop()


def notify_ticket_created(env, ticket):
    smtpd.cleanup()
    event = TicketChangeEvent('created', ticket, ticket['time'],
                              ticket['reporter'])
    NotificationSystem(env).notify(event)


def notify_ticket_changed(env, ticket, author='anonymous'):
    smtpd.cleanup()
    event = TicketChangeEvent('changed', ticket, ticket['changetime'], author)
    NotificationSystem(env).notify(event)


def config_subscriber(env, updater=False, owner=False, reporter=False):
    section = 'notification-subscriber'
    env.config.set(section, 'always_notify_cc', 'CarbonCopySubscriber')
    if updater:
        env.config.set(section, 'always_notify_updater',
                       'TicketUpdaterSubscriber')
        env.config.set(section, 'always_notify_previous_updater',
                       'TicketPreviousUpdatersSubscriber')
    if owner:
        env.config.set(section, 'always_notify_owner',
                       'TicketOwnerSubscriber')
    if reporter:
        env.config.set(section, 'always_notify_reporter',
                       'TicketReporterSubscriber')
    del NotificationSystem(env).subscriber_defaults


def config_smtp(env):
    env.config.set('project', 'name', 'TracTest')
    env.config.set('notification', 'smtp_enabled', 'true')
    env.config.set('notification', 'smtp_port', str(SMTP_TEST_PORT))
    env.config.set('notification', 'smtp_server', smtpd.host)
    # Note: when specifying 'localhost', the connection may be attempted
    #       for '::1' first, then only '127.0.0.1' after a 1s timeout


def extract_recipients(header):
    rcpts = [rcpt.strip() for rcpt in header.split(',')]
    return [rcpt for rcpt in rcpts if rcpt]


class RecipientTestCase(unittest.TestCase):
    """Notification test cases for email recipients."""

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        config_smtp(self.env)

    def tearDown(self):
        smtpd.cleanup()
        self.env.reset_db()

    def _insert_ticket(self, **props):
        return insert_ticket(self.env, **props)

    def test_no_recipients(self):
        """No recipient case"""
        ticket = insert_ticket(self.env, reporter='anonymous', summary='Foo')
        notify_ticket_created(self.env, ticket)
        recipients = smtpd.get_recipients()
        sender = smtpd.get_sender()
        message = smtpd.get_message()
        self.assertEqual(0, len(recipients))
        self.assertIsNone(sender)
        self.assertIsNone(message)

    def _test_smtp_always_cc(self, key, sep):
        cc_list = ('joe.user@example.net', 'joe.bar@example.net')
        self.env.config.set('notification', key, sep.join(cc_list))
        ticket = self._insert_ticket(reporter='joe.bar@example.org',
                                     owner='joe.user@example.net',
                                     summary='New ticket recipients')

        notify_ticket_created(self.env, ticket)
        recipients = smtpd.get_recipients()

        self.assertEqual(2, len(recipients))
        for r in cc_list:
            self.assertIn(r, recipients)

    def test_smtp_always_cc_comma_separator(self):
        self._test_smtp_always_cc('smtp_always_cc', ', ')

    def test_smtp_always_cc_space_separator(self):
        self._test_smtp_always_cc('smtp_always_cc', ' ')

    def test_smtp_always_bcc_comma_separator(self):
        self._test_smtp_always_cc('smtp_always_bcc', ', ')

    def test_smtp_always_bcc_space_separator(self):
        self._test_smtp_always_cc('smtp_always_bcc', ' ')

    def test_cc_permission_group_new_ticket(self):
        """Permission groups are resolved in CC for new ticket."""
        config_subscriber(self.env)
        ticket = self._insert_ticket(reporter='joe.bar@example.org',
                                     owner='joe.user@example.net',
                                     cc='group1, user1@example.net',
                                     summary='CC permission group')
        group1 = ('user2@example.net', 'user3@example.net')
        perm = PermissionSystem(self.env)
        for user in group1:
            perm.grant_permission(user, 'group1')

        notify_ticket_created(self.env, ticket)
        recipients = smtpd.get_recipients()

        self.assertEqual(3, len(recipients))
        for user in group1 + ('user1@example.net',):
            self.assertIn(user, recipients)

    def test_cc_permission_group_changed_ticket(self):
        """Permission groups are resolved in CC for ticket change."""
        config_subscriber(self.env)
        ticket = self._insert_ticket(reporter='joe.bar@example.org',
                                     owner='joe.user@example.net',
                                     cc='user1@example.net',
                                     summary='CC permission group')
        group1 = ('user2@example.net',)
        perm = PermissionSystem(self.env)
        for user in group1:
            perm.grant_permission(user, 'group1')

        ticket['cc'] += ', group1'
        ticket.save_changes('joe.bar2@example.com', 'This is a change')
        notify_ticket_changed(self.env, ticket)
        recipients = smtpd.get_recipients()

        self.assertEqual(2, len(recipients))
        for user in group1 + ('user1@example.net',):
            self.assertIn(user, recipients)

    def test_new_ticket_recipients(self):
        """Report and CC list should be in recipient list for new tickets."""
        config_subscriber(self.env, updater=True)
        always_cc = ('joe.user@example.net', 'joe.bar@example.net')
        ticket_cc = ('joe.user@example.com', 'joe.bar@example.org')
        self.env.config.set('notification', 'smtp_always_cc',
                            ', '.join(always_cc))
        ticket = insert_ticket(self.env, reporter='joe.bar@example.org',
                               owner='joe.user@example.net',
                               cc=' '.join(ticket_cc),
                               summary='New ticket recipients')
        notify_ticket_created(self.env, ticket)
        recipients = smtpd.get_recipients()
        for r in always_cc + ticket_cc + \
                (ticket['owner'], ticket['reporter']):
            self.assertIn(r, recipients)

    def test_cc_only(self):
        """Notification w/o explicit recipients but Cc: (#3101)"""
        always_cc = ('joe.user@example.net', 'joe.bar@example.net')
        self.env.config.set('notification', 'smtp_always_cc',
                            ', '.join(always_cc))
        ticket = insert_ticket(self.env, summary='Foo')
        notify_ticket_created(self.env, ticket)
        recipients = smtpd.get_recipients()
        for r in always_cc:
            self.assertIn(r, recipients)

    def test_always_notify_updater(self):
        """The `always_notify_updater` option."""
        def _test_updater(enabled):
            config_subscriber(self.env, updater=enabled)
            ticket = insert_ticket(self.env, reporter='joe.user@example.org',
                                   summary='This is a súmmäry')
            now = datetime_now(utc)
            ticket.save_changes('joe.bar2@example.com', 'This is a change',
                                when=now)
            notify_ticket_changed(self.env, ticket)
            recipients = smtpd.get_recipients()
            if enabled:
                self.assertEqual(1, len(recipients))
                self.assertIn('joe.bar2@example.com', recipients)
            else:
                self.assertEqual(0, len(recipients))
                self.assertNotIn('joe.bar2@example.com', recipients)

        # Validate with and without a default domain
        for enable in False, True:
            _test_updater(enable)

    def test_always_notify_owner(self):
        """The `always_notify_owner` option."""
        def _test_reporter(enabled):
            config_subscriber(self.env, owner=enabled)
            ticket = insert_ticket(self.env, summary='Foo',
                                   reporter='joe@example.org',
                                   owner='jim@example.org')
            now = datetime_now(utc)
            ticket.save_changes('joe@example.org', 'this is my comment',
                                when=now)
            notify_ticket_changed(self.env, ticket)
            recipients = smtpd.get_recipients()
            if enabled:
                self.assertEqual(1, len(recipients))
                self.assertEqual('jim@example.org', recipients[0])
            else:
                self.assertEqual(0, len(recipients))

        for enable in False, True:
            _test_reporter(enable)

    def test_always_notify_reporter(self):
        """Notification to reporter w/ updater option disabled (#3780)"""
        def _test_reporter(enabled):
            config_subscriber(self.env, reporter=enabled)
            ticket = insert_ticket(self.env, summary='Foo',
                                   reporter='joe@example.org')
            now = datetime_now(utc)
            ticket.save_changes('joe@example.org', 'this is my comment',
                                when=now)
            notify_ticket_changed(self.env, ticket)
            recipients = smtpd.get_recipients()
            if enabled:
                self.assertEqual(1, len(recipients))
                self.assertEqual('joe@example.org', recipients[0])
            else:
                self.assertEqual(0, len(recipients))

        for enable in False, True:
            _test_reporter(enable)

    def test_notify_new_tickets(self):
        """Notification to NewTicketSubscribers."""
        def _test_new_ticket():
            ticket = Ticket(self.env)
            ticket['reporter'] = 'user4'
            ticket['owner'] = 'user5'
            ticket['summary'] = 'New Ticket Subscribers'
            ticket.insert()
            notify_ticket_created(self.env, ticket)
            return ticket

        def _add_new_ticket_subscriber(sid, authenticated):
            Subscription.add(self.env, {
                'sid': sid, 'authenticated': authenticated,
                'distributor': 'email', 'format': None, 'adverb': 'always',
                'class': 'NewTicketSubscriber'
            })

        _test_new_ticket()
        recipients = smtpd.get_recipients()
        self.assertEqual(0, len(recipients))

        self.env.insert_users([
            ('user1', 'User One', 'joe@example.org', 1),
            ('user2', 'User Two', 'bar@example.org', 1),
            ('58bd3a', 'User Three', 'jim@example.org', 0),
        ])
        _add_new_ticket_subscriber('user1', 1)
        _add_new_ticket_subscriber('58bd3a', 0)

        ticket = _test_new_ticket()
        recipients = smtpd.get_recipients()
        self.assertEqual(2, len(recipients))
        self.assertIn('joe@example.org', recipients)
        self.assertIn('jim@example.org', recipients)

        ticket.save_changes('user4', 'this is my comment',
                            when=datetime_now(utc))
        notify_ticket_changed(self.env, ticket)

        recipients = smtpd.get_recipients()
        self.assertEqual(0, len(recipients))

    def test_no_duplicates(self):
        """Email addresses should be found only once in the recipient list."""
        self.env.config.set('notification', 'smtp_always_cc',
                            'joe.user@example.com')
        ticket = insert_ticket(self.env, reporter='joe.user@example.com',
                               owner='joe.user@example.com',
                               cc='joe.user@example.com',
                               summary='No duplicates')
        notify_ticket_created(self.env, ticket)
        recipients = smtpd.get_recipients()
        self.assertEqual(1, len(recipients))
        self.assertIn('joe.user@example.com', recipients)

    def test_long_forms(self):
        """Long forms of SMTP email addresses 'Display Name <address>'"""
        config_subscriber(self.env, updater=True, owner=True)
        ticket = insert_ticket(self.env,
           reporter='"Joe" <joe.user@example.com>',
           owner='Joe <joe.user@example.net>',
           cc=' \u00a0 Jóe \u3000 < joe.user@example.org > \u00a0 ',
           summary='Long form')
        notify_ticket_created(self.env, ticket)
        recipients = smtpd.get_recipients()
        self.assertEqual(3, len(recipients))
        self.assertIn('joe.user@example.com', recipients)
        self.assertIn('joe.user@example.net', recipients)
        self.assertIn('joe.user@example.org', recipients)


class NotificationTestCase(unittest.TestCase):
    """Notification test cases that send email over SMTP"""

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        config_smtp(self.env)
        self.env.config.set('trac', 'base_url', 'http://localhost/trac')
        self.env.config.set('project', 'url', 'http://localhost/project.url')
        self.env.config.set('notification', 'smtp_enabled', 'true')
        self.env.config.set('notification', 'smtp_always_cc',
                            'joe.user@example.net, joe.bar@example.net')
        self.env.config.set('notification', 'use_public_cc', 'true')
        self.req = MockRequest(self.env)

    def tearDown(self):
        """Signal the notification test suite that a test is over"""
        smtpd.cleanup()
        self.env.reset_db()

    def _insert_ticket(self, **props):
        reporter = props.pop('reporter', 'joeuser')
        summary = props.pop('summary', 'Summary')
        return insert_ticket(self.env, reporter=reporter, summary=summary,
                             **props)

    def test_structure(self):
        """Basic SMTP message structure (headers, body)"""
        ticket = insert_ticket(self.env,
                               reporter='"Joe User" <joe.user@example.org>',
                               owner='joe.user@example.net',
                               cc='joe.user@example.com, joe.bar@example.org, '
                                  'joe.bar@example.net',
                               summary='This is a summary')
        notify_ticket_created(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)
        # checks for header existence
        self.assertTrue(headers)
        # checks for body existence
        self.assertTrue(body)
        # checks for expected headers
        self.assertIn('Date', headers)
        self.assertIn('Subject', headers)
        self.assertEqual('<073.8a48f9c2ab2dc64e820e391f8f784a04@localhost>',
                         headers['Message-ID'])
        self.assertIn('From', headers)
        self.assertIn('\n-- \nTicket URL: <', body)

    def test_date(self):
        """Date format compliance (RFC822)
           we do not support 'military' format"""
        date_str = r"^((?P<day>\w{3}),\s*)*(?P<dm>\d{2})\s+" \
                   r"(?P<month>\w{3})\s+(?P<year>\d{4})\s+" \
                   r"(?P<hour>\d{2}):(?P<min>[0-5][0-9])" \
                   r"(:(?P<sec>[0-5][0-9]))*\s" \
                   r"((?P<tz>\w{2,3})|(?P<offset>[+\-]\d{4}))$"
        date_re = re.compile(date_str)
        # python time module does not detect incorrect time values
        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        tz = ['UT', 'GMT', 'EST', 'EDT', 'CST', 'CDT', 'MST', 'MDT',
              'PST', 'PDT']
        ticket = insert_ticket(self.env,
                               reporter='"Joe User" <joe.user@example.org>',
                               summary='This is a summary')
        notify_ticket_created(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)
        self.assertIn('Date', headers)
        mo = date_re.match(headers['Date'])
        self.assertTrue(mo)
        if mo.group('day'):
            self.assertIn(mo.group('day'), days)
        self.assertIn(int(mo.group('dm')), range(1, 32))
        self.assertIn(mo.group('month'), months)
        self.assertIn(int(mo.group('hour')), range(24))
        if mo.group('tz'):
            self.assertIn(mo.group('tz'), tz)

    def test_bcc_privacy(self):
        """Visibility of recipients"""
        def run_bcc_feature(public_cc):
            # CC list should be private
            self.env.config.set('notification', 'use_public_cc', public_cc)
            self.env.config.set('notification', 'smtp_always_bcc',
                                'joe.foobar@example.net')
            ticket = insert_ticket(self.env,
                                   reporter='"Joe User" <joe.user@example.org>',
                                   summary='This is a summary')
            notify_ticket_created(self.env, ticket)
            message = smtpd.get_message()
            headers, body = parse_smtp_message(message)
            # Msg should have a To header
            self.assertEqual('undisclosed-recipients: ;', headers['To'])
            # Extract the list of 'Cc' recipients from the message
            cc = extract_recipients(headers['Cc'])
            # Extract the list of the actual SMTP recipients
            rcptlist = smtpd.get_recipients()
            # Build the list of the expected 'Cc' recipients
            ccrcpt = self.env.config.getlist('notification', 'smtp_always_cc')
            for rcpt in ccrcpt:
                # Each recipient of the 'Cc' list should appear
                # in the 'Cc' header
                self.assertIn(rcpt, cc)
                # Check the message has actually been sent to the recipients
                self.assertIn(rcpt, rcptlist)
            # Build the list of the expected 'Bcc' recipients
            bccrcpt = self.env.config.getlist('notification',
                                              'smtp_always_bcc')
            for rcpt in bccrcpt:
                # Check the message has actually been sent to the recipients
                self.assertIn(rcpt, rcptlist)
        for public in False, True:
            run_bcc_feature(public)

    def test_short_login(self):
        """Email addresses without a FQDN"""
        def _test_short_login(use_short_addr, username, address):
            config_subscriber(self.env, reporter=True)
            ticket = insert_ticket(self.env, reporter=username,
                                   summary='This is a summary')
            # Be sure that at least one email address is valid, so that we
            # send a notification even if other addresses are not valid
            self.env.config.set('notification', 'smtp_always_cc',
                                'joe.bar@example.net, john')
            self.env.config.set('notification', 'use_short_addr',
                                'enabled' if use_short_addr else 'disabled')
            notify_ticket_created(self.env, ticket)
            message = smtpd.get_message()
            recipients = set(smtpd.get_recipients())
            headers, body = parse_smtp_message(message)
            # Msg should always have a 'To' field
            if use_short_addr:
                self.assertEqual(address, headers['To'])
            else:
                self.assertEqual('undisclosed-recipients: ;', headers['To'])
            # Msg should have a 'Cc' field
            self.assertIn('Cc', headers)
            cclist = set(extract_recipients(headers['Cc']))
            if use_short_addr:
                # Msg should be delivered to the reporter
                self.assertEqual({'joe.bar@example.net', 'john'}, cclist)
                self.assertEqual({address, 'joe.bar@example.net', 'john'},
                                 recipients)
            else:
                # Msg should not be delivered to the reporter
                self.assertEqual({'joe.bar@example.net'}, cclist)
                self.assertEqual({'joe.bar@example.net'}, recipients)

        # Validate with and without the short addr option enabled
        self.env.insert_users([('bar', 'Bar User', ''),
                               ('qux', 'Qux User', 'qux-mail')])
        for use_short_addr in (False, True):
            _test_short_login(use_short_addr, 'foo', 'foo')
            _test_short_login(use_short_addr, 'bar', 'bar')
            _test_short_login(use_short_addr, 'qux', 'qux-mail')

    def test_default_domain(self):
        """Default domain name"""
        def _test_default_domain(enable):
            config_subscriber(self.env)
            self.env.config.set('notification', 'smtp_always_cc', '')
            ticket = insert_ticket(self.env, cc='joenodom, foo, bar, qux, '
                                                'joewithdom@example.com',
                                   summary='This is a summary')
            # Be sure that at least one email address is valid, so that we
            # send a notification even if other addresses are not valid
            self.env.config.set('notification', 'smtp_always_cc',
                                'joe.bar@example.net')
            self.env.config.set('notification', 'smtp_default_domain',
                                'example.org' if enable else '')
            notify_ticket_created(self.env, ticket)
            message = smtpd.get_message()
            headers, body = parse_smtp_message(message)
            # Msg should always have a 'Cc' field
            self.assertIn('Cc', headers)
            cclist = set(extract_recipients(headers['Cc']))
            if enable:
                self.assertEqual({'joenodom@example.org', 'foo@example.org',
                                  'bar@example.org', 'qux-mail@example.org',
                                  'joewithdom@example.com',
                                  'joe.bar@example.net'}, cclist)
            else:
                self.assertEqual({'joewithdom@example.com',
                                  'joe.bar@example.net'}, cclist)

        # Validate with and without a default domain
        self.env.insert_users([('bar', 'Bar User', ''),
                               ('qux', 'Qux User', 'qux-mail')])
        for enable in (False, True):
            _test_default_domain(enable)

    def test_email_map(self):
        """Login-to-email mapping"""
        config_subscriber(self.env, reporter=True, owner=True)
        self.env.config.set('notification', 'smtp_always_cc',
                            'joe@example.com')
        self.env.insert_users(
            [('joeuser', 'Joe User', 'user-joe@example.com'),
             ('jim@domain', 'Jim User', 'user-jim@example.com')])
        ticket = insert_ticket(self.env, reporter='joeuser', owner='jim@domain',
                               summary='This is a summary')
        notify_ticket_created(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)
        tolist = sorted(extract_recipients(headers['To']))
        cclist = sorted(extract_recipients(headers['Cc']))
        # 'To' list should have been resolved to the real email address
        self.assertEqual(['user-jim@example.com', 'user-joe@example.com'],
                         tolist)
        self.assertEqual(['joe@example.com'], cclist)

    def test_from_author(self):
        """Using the reporter or change author as the notification sender"""
        self.env.config.set('notification', 'smtp_from', 'trac@example.com')
        self.env.config.set('notification', 'smtp_from_name', 'My Trac')
        self.env.config.set('notification', 'smtp_from_author', 'true')
        self.env.insert_users(
            [('joeuser', 'Joe User', 'user-joe@example.com'),
             ('jim@domain', 'Jim User', 'user-jim@example.com'),
             ('noemail', 'No e-mail', ''),
             ('noname', '', 'user-noname@example.com')])
        def modtime(delta):
            return datetime(2016, 8, 21, 12, 34, 56, 987654, utc) + \
                   timedelta(seconds=delta)
        # Ticket creation uses the reporter
        ticket = insert_ticket(self.env, reporter='joeuser',
                               summary='This is a summary', when=modtime(0))
        notify_ticket_created(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)
        self.assertEqual('Joe User <user-joe@example.com>', headers['From'])
        self.assertEqual('<047.54e62c60198a043f858f1311784a5791@example.com>',
                         headers['Message-ID'])
        self.assertNotIn('In-Reply-To', headers)
        self.assertNotIn('References', headers)
        # Ticket change uses the change author
        ticket['summary'] = 'Modified summary'
        ticket.save_changes('jim@domain', 'Made some changes', modtime(1))
        notify_ticket_changed(self.env, ticket, 'jim@domain')
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)
        self.assertEqual('Jim User <user-jim@example.com>', headers['From'])
        self.assertEqual('<062.a890ee4ad5488fb49e60b68099995ba3@example.com>',
                         headers['Message-ID'])
        self.assertEqual('<047.54e62c60198a043f858f1311784a5791@example.com>',
                         headers['In-Reply-To'])
        self.assertEqual('<047.54e62c60198a043f858f1311784a5791@example.com>',
                         headers['References'])
        # Known author without name uses e-mail address only
        ticket['summary'] = 'Final summary'
        ticket.save_changes('noname', 'Final changes', modtime(2))
        notify_ticket_changed(self.env, ticket, 'noname')
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)
        self.assertEqual('user-noname@example.com', headers['From'])
        self.assertEqual('<062.732a7b25a21f5a86478c4fe47e86ade4@example.com>',
                         headers['Message-ID'])
        # Known author without e-mail uses smtp_from and smtp_from_name
        ticket['summary'] = 'Other summary'
        ticket.save_changes('noemail', 'More changes', modtime(3))
        notify_ticket_changed(self.env, ticket, 'noemail')
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)
        self.assertEqual('My Trac <trac@example.com>', headers['From'])
        self.assertEqual('<062.98cff27cb9fabd799bcb09f9edd6c99e@example.com>',
                         headers['Message-ID'])
        # Unknown author with name and e-mail address
        ticket['summary'] = 'Some summary'
        ticket.save_changes('Test User <test@example.com>', 'Some changes',
                            modtime(4))
        notify_ticket_changed(self.env, ticket, 'Test User <test@example.com>')
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)
        self.assertEqual('Test User <test@example.com>', headers['From'])
        self.assertEqual('<062.6e08a363c340c1d4e2ed84c6123a1e9d@example.com>',
                         headers['Message-ID'])
        # Unknown author with e-mail address only
        ticket['summary'] = 'Some summary'
        ticket.save_changes('test@example.com', 'Some changes', modtime(5))
        notify_ticket_changed(self.env, ticket, 'test@example.com')
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)
        self.assertEqual('test@example.com', headers['From'])
        self.assertEqual('<062.5eb050ae6f322c33dde5940a5f318343@example.com>',
                         headers['Message-ID'])
        # Unknown author uses smtp_from and smtp_from_name
        ticket['summary'] = 'Better summary'
        ticket.save_changes('unknown', 'Made more changes', modtime(6))
        notify_ticket_changed(self.env, ticket, 'unknown')
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)
        self.assertEqual('My Trac <trac@example.com>', headers['From'])
        self.assertEqual('<062.6d5543782e7aba4100302487e75ce16f@example.com>',
                         headers['Message-ID'])

    def test_ignore_domains(self):
        """Non-SMTP domain exclusion"""
        config_subscriber(self.env, reporter=True, owner=True)
        self.env.config.set('notification', 'ignore_domains',
                            'example.com, example.org')
        self.env.insert_users(
            [('kerberos@example.com', 'No Email', ''),
             ('kerberos@example.org', 'With Email', 'kerb@example.net')])
        ticket = insert_ticket(self.env, reporter='kerberos@example.com',
                               owner='kerberos@example.org',
                               summary='This is a summary')
        notify_ticket_created(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)
        tolist = set(extract_recipients(headers['To']))
        cclist = set(extract_recipients(headers['Cc']))
        # 'To' list should not contain addresses with non-SMTP domains
        self.assertNotIn('kerberos@example.com', tolist)
        self.assertNotIn('kerberos@example.org', tolist)
        # 'To' list should have been resolved to the actual email address
        self.assertEqual({'kerb@example.net'}, tolist)
        # 'Cc' list should have been resolved to the actual email address
        self.assertEqual({'joe.bar@example.net', 'joe.user@example.net'},
                         cclist)

    def test_admit_domains(self):
        """SMTP domain inclusion"""
        config_subscriber(self.env, reporter=True)
        self.env.config.set('notification', 'admit_domains',
                            'localdomain, server')
        ticket = insert_ticket(self.env, reporter='joeuser@example.com',
                               summary='This is a summary',
                               cc='joe.user@localdomain, joe.user@unknown, '
                                  'joe.user@server')
        notify_ticket_created(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)
        # Msg should always have a 'To' field
        self.assertEqual('joeuser@example.com', headers['To'])
        self.assertIn('Cc', headers)
        cclist = set(extract_recipients(headers['Cc']))
        # 'Cc' list should contain addresses with SMTP included domains
        self.assertIn('joe.user@localdomain', cclist)
        self.assertIn('joe.user@server', cclist)
        # 'Cc' list should not contain non-FQDN domains
        self.assertNotIn('joe.user@unknown', cclist)
        self.assertEqual({'joe.user@localdomain', 'joe.user@server',
                          'joe.user@example.net', 'joe.bar@example.net'},
                         cclist)

    def test_multiline_header(self):
        """Encoded headers split into multiple lines"""
        self.env.config.set('notification', 'mime_encoding', 'qp')
        ticket = insert_ticket(self.env, reporter='joe.user@example.org',
                               summary='A_very %s súmmäry'
                                       % ' '.join(['long'] * 20))
        notify_ticket_created(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)
        # Discards the project name & ticket number
        subject = headers['Subject']
        summary = subject[subject.find(':')+2:]
        self.assertEqual(ticket['summary'], summary)

    def test_mimebody_b64(self):
        """MIME Base64/utf-8 encoding"""
        self.env.config.set('notification', 'mime_encoding', 'base64')
        summary = 'This is a long enough summary to cause Trac ' \
                  'to generate a multi-line (2 lines) súmmäry'
        ticket = insert_ticket(self.env, reporter='joe.user@example.org',
                               summary=summary)
        self._validate_mimebody((base64.b64decode, 'base64', 'utf-8'),
                                ticket, True)

    def test_mimebody_qp(self):
        """MIME QP/utf-8 encoding"""
        self.env.config.set('notification', 'mime_encoding', 'qp')
        summary = 'This is a long enough summary to cause Trac ' \
                  'to generate a multi-line (2 lines) súmmäry'
        ticket = insert_ticket(self.env, reporter='joe.user@example.org',
                               summary=summary)
        self._validate_mimebody((quopri.decodestring, 'quoted-printable',
                                 'utf-8'), ticket, True)

    def test_mimebody_none_7bit(self):
        """MIME None encoding resulting in 7bit"""
        self.env.config.set('notification', 'mime_encoding', 'none')
        ticket = insert_ticket(self.env, reporter='joe.user',
                               summary='This is a summary')
        self._validate_mimebody((None, '7bit', 'utf-8'), ticket, True)

    def test_mimebody_none_8bit(self):
        """MIME None encoding resulting in 8bit"""
        self.env.config.set('notification', 'mime_encoding', 'none')
        ticket = insert_ticket(self.env, reporter='joe.user',
                               summary='This is a summary for Jöe Usèr')
        self._validate_mimebody((None, '8bit', 'utf-8'), ticket, True)

    def _test_msgid_digest(self, hash_type):
        """MD5 digest w/ non-ASCII recipient address (#3491)"""
        config_subscriber(self.env, reporter=True)
        self.env.config.set('notification', 'smtp_always_cc', '')
        if hash_type:
            self.env.config.set('notification', 'message_id_hash', hash_type)
        ticket = insert_ticket(self.env, summary='This is a summary',
                               reporter='"Jöe Usèr" <joe.user@example.org>')
        notify_ticket_created(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)
        self.assertEqual('joe.user@example.org', headers['To'])
        self.assertNotIn('Cc', headers)
        return headers

    def test_md5_digest(self):
        headers = self._test_msgid_digest(None)
        self.assertEqual('<071.cbea352f8c4fa58e4b10d24c17b091e6@localhost>',
                         headers['Message-ID'])

    def test_sha1_digest(self):
        headers = self._test_msgid_digest('sha1')
        self.assertEqual(
            '<071.0b6459808bc3603bd642b9a478928d9b5542a803@localhost>',
            headers['Message-ID'])

    def test_add_to_cc_list(self):
        """Members added to CC list receive notifications."""
        config_subscriber(self.env)
        ticket = insert_ticket(self.env, summary='Foo')
        ticket['cc'] = 'joe.user1@example.net'
        now = datetime_now(utc)
        ticket.save_changes('joe.bar@example.com', 'Added to cc', now)
        notify_ticket_changed(self.env, ticket)
        recipients = smtpd.get_recipients()
        self.assertIn('joe.user1@example.net', recipients)

    def test_previous_cc_list(self):
        """Members removed from CC list receive notifications"""
        config_subscriber(self.env)
        ticket = insert_ticket(self.env, summary='Foo',
                               cc='joe.user1@example.net')
        ticket['cc'] = 'joe.user2@example.net'
        now = datetime_now(utc)
        ticket.save_changes('joe.bar@example.com', 'Removed from cc', now)
        notify_ticket_changed(self.env, ticket)
        recipients = smtpd.get_recipients()
        self.assertIn('joe.user1@example.net', recipients)
        self.assertIn('joe.user2@example.net', recipients)

    def test_previous_owner(self):
        """Previous owner is notified when ticket is reassigned (#2311)
           if always_notify_owner is set to True"""
        def _test_owner(enabled):
            config_subscriber(self.env, owner=enabled)
            prev_owner = 'joe.user1@example.net'
            ticket = insert_ticket(self.env, summary='Foo', owner=prev_owner)
            ticket['owner'] = new_owner = 'joe.user2@example.net'
            now = datetime_now(utc)
            ticket.save_changes('joe.bar@example.com', 'Changed owner', now)
            notify_ticket_changed(self.env, ticket)
            recipients = smtpd.get_recipients()
            if enabled:
                self.assertIn(prev_owner, recipients)
                self.assertIn(new_owner, recipients)
            else:
                self.assertNotIn(prev_owner, recipients)
                self.assertNotIn(new_owner, recipients)

        for enable in False, True:
            _test_owner(enable)

    def _validate_mimebody(self, mime, ticket, newtk):
        """Body of a ticket notification message"""
        mime_decoder, mime_name, mime_charset = mime
        if newtk:
            notify_ticket_created(self.env, ticket)
        else:
            notify_ticket_changed(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)
        self.assertIn('MIME-Version', headers)
        self.assertIn('Content-Type', headers)
        self.assertTrue(re.compile(r"1.\d").match(headers['MIME-Version']))
        ctype_mo = re.match(r'\s*([^;\s]*)\s*(?:;\s*boundary="([^"]*)")?',
                            headers['Content-Type'])
        self.assertEqual('multipart/related', ctype_mo.group(1))
        boundary_re = re.compile(r'(?:\r\n)*^--%s(?:--)?(?:\r\n|\Z)' %
                                 re.escape(ctype_mo.group(2)), re.MULTILINE)
        body = boundary_re.split(message)[1]
        headers, body = parse_smtp_message(body)
        self.assertIn('Content-Type', headers)
        self.assertIn('Content-Transfer-Encoding', headers)
        type_re = re.compile(r'^text/plain;\scharset="([\w\-\d]+)"$')
        charset = type_re.match(headers['Content-Type'])
        self.assertTrue(charset)
        charset = charset.group(1)
        self.assertEqual(mime_charset, charset)
        self.assertEqual(headers['Content-Transfer-Encoding'], mime_name)
        # checks the width of each body line
        for line in body.splitlines():
            self.assertTrue(len(line) <= MAXBODYWIDTH)
        # attempts to decode the body, following the specified MIME encoding
        # and charset
        try:
            if mime_decoder:
                body = mime_decoder(body)
                body = str(body, charset)
        except Exception as e:
            raise AssertionError(e)
        # now processes each line of the body
        bodylines = body.splitlines()
        # body starts with one of more summary lines, first line is prefixed
        # with the ticket number such as #<n>: summary
        # finds the banner after the summary
        banner_delim_re = re.compile(r'^\-+\+\-+$')
        bodyheader = []
        while not banner_delim_re.match(bodylines[0]):
            bodyheader.append(bodylines.pop(0))
        # summary should be present
        self.assertTrue(bodyheader)
        # banner should not be empty
        self.assertTrue(bodylines)
        # extracts the ticket ID from the first line
        tknum, bodyheader[0] = bodyheader[0].split(' ', 1)
        self.assertEqual('#', tknum[0])
        try:
            tkid = int(tknum[1:-1])
            self.assertEqual(1, tkid)
        except ValueError:
            raise AssertionError("invalid ticket number")
        self.assertEqual(':', tknum[-1])
        summary = ' '.join(bodyheader)
        self.assertEqual(summary, ticket['summary'])
        # now checks the banner contents
        self.assertTrue(banner_delim_re.match(bodylines[0]))
        banner = True
        footer = None
        props = {}
        for line in bodylines[1:]:
            # detect end of banner
            if banner_delim_re.match(line):
                banner = False
                continue
            if banner:
                # parse banner and fill in a property dict
                properties = line.split('|')
                self.assertEqual(2, len(properties))
                for prop in properties:
                    if prop.strip() == '':
                        continue
                    k, v = prop.split(':')
                    props[k.strip().lower()] = v.strip()
            # detect footer marker (weak detection)
            if not footer:
                if line.strip() == '--':
                    footer = 0
                    continue
            # check footer
            if footer is not None:
                footer += 1
                # invalid footer detection
                self.assertTrue(footer <= 3)
                # check ticket link
                if line[:11] == 'Ticket URL:':
                    ticket_link = self.env.abs_href.ticket(ticket.id)
                    self.assertEqual(line[12:].strip(), "<%s>" % ticket_link)
                # note project title / URL are not validated yet

        # ticket properties which are not expected in the banner
        xlist = ['summary', 'description', 'comment', 'time', 'changetime']
        # check banner content (field exists, msg value matches ticket value)
        for p in [prop for prop in ticket.values if prop not in xlist]:
            self.assertIn(p, props)
            # Email addresses might be obfuscated
            if '@' in ticket[p] and '@' in props[p]:
                self.assertEqual(props[p].split('@')[0],
                                 ticket[p].split('@')[0])
            else:
                self.assertEqual(props[p], ticket[p])

    def test_props_format_ambiwidth_single(self):
        self.env.config.set('notification', 'mime_encoding', 'none')
        self.env.config.set('notification', 'ambiguous_char_width', '')
        ticket = Ticket(self.env)
        ticket['summary'] = 'This is a summary'
        ticket['reporter'] = 'аnonymoиs'
        ticket['status'] = 'new'
        ticket['owner'] = 'somеbody'
        ticket['type'] = 'バグ(dеfеct)'
        ticket['priority'] = 'メジャー(mаjor)'
        ticket['milestone'] = 'マイルストーン1'
        ticket['component'] = 'コンポーネント1'
        ticket['version'] = '2.0 аlphа'
        ticket['resolution'] = 'fixed'
        ticket['keywords'] = ''
        ticket.insert()
        formatted = """\
  Reporter:  аnonymoиs        |      Owner:  somеbody
      Type:  バグ(dеfеct)     |     Status:  new
  Priority:  メジャー(mаjor)  |  Milestone:  マイルストーン1
 Component:  コンポーネント1  |    Version:  2.0 аlphа
Resolution:  fixed            |   Keywords:"""
        self._validate_props_format(formatted, ticket)

    def test_props_format_ambiwidth_double(self):
        self.env.config.set('notification', 'mime_encoding', 'none')
        self.env.config.set('notification', 'ambiguous_char_width', 'double')
        ticket = Ticket(self.env)
        ticket['summary'] = 'This is a summary'
        ticket['reporter'] = 'аnonymoиs'
        ticket['status'] = 'new'
        ticket['owner'] = 'somеbody'
        ticket['type'] = 'バグ(dеfеct)'
        ticket['priority'] = 'メジャー(mаjor)'
        ticket['milestone'] = 'マイルストーン1'
        ticket['component'] = 'コンポーネント1'
        ticket['version'] = '2.0 аlphа'
        ticket['resolution'] = 'fixed'
        ticket['keywords'] = ''
        ticket.insert()
        formatted = """\
  Reporter:  аnonymoиs       |      Owner:  somеbody
      Type:  バグ(dеfеct)    |     Status:  new
  Priority:  メジャー(mаjor)  |  Milestone:  マイルストーン1
 Component:  コンポーネント1   |    Version:  2.0 аlphа
Resolution:  fixed             |   Keywords:"""
        self._validate_props_format(formatted, ticket)

    def test_props_format_obfuscated_email(self):
        self.env.config.set('notification', 'mime_encoding', 'none')
        ticket = Ticket(self.env)
        ticket['summary'] = 'This is a summary'
        ticket['reporter'] = 'joe@foobar.foo.bar.example.org'
        ticket['status'] = 'new'
        ticket['owner'] = 'joe.bar@foobar.foo.bar.example.org'
        ticket['type'] = 'defect'
        ticket['priority'] = 'major'
        ticket['milestone'] = 'milestone1'
        ticket['component'] = 'component1'
        ticket['version'] = '2.0'
        ticket['resolution'] = 'fixed'
        ticket['keywords'] = ''
        ticket.insert()
        formatted = """\
  Reporter:  joe@…       |      Owner:  joe.bar@…
      Type:  defect      |     Status:  new
  Priority:  major       |  Milestone:  milestone1
 Component:  component1  |    Version:  2.0
Resolution:  fixed       |   Keywords:"""
        self._validate_props_format(formatted, ticket)

    def test_props_format_obfuscated_email_disabled(self):
        self.env.config.set('notification', 'mime_encoding', 'none')
        self.env.config.set('trac', 'show_email_addresses', 'true')
        ticket = Ticket(self.env)
        ticket['summary'] = 'This is a summary'
        ticket['reporter'] = 'joe@foobar.foo.bar.example.org'
        ticket['status'] = 'new'
        ticket['owner'] = 'joe.bar@foobar.foo.bar.example.org'
        ticket['type'] = 'defect'
        ticket['priority'] = 'major'
        ticket['milestone'] = 'milestone1'
        ticket['component'] = 'component1'
        ticket['version'] = '2.0'
        ticket['resolution'] = 'fixed'
        ticket['keywords'] = ''
        ticket.insert()
        formatted = """\
  Reporter:                          |      Owner:
  joe@foobar.foo.bar.example.org     |  joe.bar@foobar.foo.bar.example.org
      Type:  defect                  |     Status:  new
  Priority:  major                   |  Milestone:  milestone1
 Component:  component1              |    Version:  2.0
Resolution:  fixed                   |   Keywords:"""
        self._validate_props_format(formatted, ticket)

    def test_props_format_show_full_names(self):
        self.env.insert_users([
            ('joefoo', 'Joę Fœœ', 'joe@foobar.foo.bar.example.org'),
            ('joebar', 'Jœe Bær', 'joe.bar@foobar.foo.bar.example.org')
        ])
        self.env.config.set('notification', 'mime_encoding', 'none')
        ticket = Ticket(self.env)
        ticket['summary'] = 'This is a summary'
        ticket['reporter'] = 'joefoo'
        ticket['status'] = 'new'
        ticket['owner'] = 'joebar'
        ticket['type'] = 'defect'
        ticket['priority'] = 'major'
        ticket['milestone'] = 'milestone1'
        ticket['component'] = 'component1'
        ticket['version'] = '2.0'
        ticket['resolution'] = 'fixed'
        ticket['keywords'] = ''
        ticket.insert()
        formatted = """\
  Reporter:  Joę Fœœ     |      Owner:  Jœe Bær
      Type:  defect      |     Status:  new
  Priority:  major       |  Milestone:  milestone1
 Component:  component1  |    Version:  2.0
Resolution:  fixed       |   Keywords:"""
        self._validate_props_format(formatted, ticket)

    def test_props_format_wrap_leftside(self):
        self.env.config.set('notification', 'mime_encoding', 'none')
        ticket = Ticket(self.env)
        ticket['summary'] = 'This is a summary'
        ticket['reporter'] = 'anonymous'
        ticket['status'] = 'new'
        ticket['owner'] = 'somebody'
        ticket['type'] = 'defect'
        ticket['priority'] = 'major'
        ticket['milestone'] = 'milestone1'
        ticket['component'] = 'Lorem ipsum dolor sit amet, consectetur ' \
                              'adipisicing elit, sed do eiusmod tempor ' \
                              'incididunt ut labore et dolore magna ' \
                              'aliqua. Ut enim ad minim veniam, quis ' \
                              'nostrud exercitation ullamco laboris nisi ' \
                              'ut aliquip ex ea commodo consequat. Duis ' \
                              'aute irure dolor in reprehenderit in ' \
                              'voluptate velit esse cillum dolore eu ' \
                              'fugiat nulla pariatur. Excepteur sint ' \
                              'occaecat cupidatat non proident, sunt in ' \
                              'culpa qui officia deserunt mollit anim id ' \
                              'est laborum.'
        ticket['version'] = '2.0'
        ticket['resolution'] = 'fixed'
        ticket['keywords'] = ''
        ticket.insert()
        formatted = """\
  Reporter:  anonymous                           |      Owner:  somebody
      Type:  defect                              |     Status:  new
  Priority:  major                               |  Milestone:  milestone1
 Component:  Lorem ipsum dolor sit amet,         |    Version:  2.0
  consectetur adipisicing elit, sed do eiusmod   |
  tempor incididunt ut labore et dolore magna    |
  aliqua. Ut enim ad minim veniam, quis nostrud  |
  exercitation ullamco laboris nisi ut aliquip   |
  ex ea commodo consequat. Duis aute irure       |
  dolor in reprehenderit in voluptate velit      |
  esse cillum dolore eu fugiat nulla pariatur.   |
  Excepteur sint occaecat cupidatat non          |
  proident, sunt in culpa qui officia deserunt   |
  mollit anim id est laborum.                    |
Resolution:  fixed                               |   Keywords:"""
        self._validate_props_format(formatted, ticket)

    def test_props_format_wrap_leftside_unicode(self):
        self.env.config.set('notification', 'mime_encoding', 'none')
        ticket = Ticket(self.env)
        ticket['summary'] = 'This is a summary'
        ticket['reporter'] = 'anonymous'
        ticket['status'] = 'new'
        ticket['owner'] = 'somebody'
        ticket['type'] = 'defect'
        ticket['priority'] = 'major'
        ticket['milestone'] = 'milestone1'
        ticket['component'] = 'Trac は BSD ライセンスのもとで配' \
                              '布されています。[1:]このライセ' \
                              'ンスの全文は、配布ファイルに' \
                              '含まれている [3:COPYING] ファイル' \
                              'と同じものが[2:オンライン]で参' \
                              '照できます。'
        ticket['version'] = '2.0'
        ticket['resolution'] = 'fixed'
        ticket['keywords'] = ''
        ticket.insert()
        formatted = """\
  Reporter:  anonymous                           |      Owner:  somebody
      Type:  defect                              |     Status:  new
  Priority:  major                               |  Milestone:  milestone1
 Component:  Trac は BSD ライセンスのもとで配布  |    Version:  2.0
  されています。[1:]このライセンスの全文は、配   |
  布ファイルに含まれている [3:COPYING] ファイル  |
  と同じものが[2:オンライン]で参照できます。     |
Resolution:  fixed                               |   Keywords:"""
        self._validate_props_format(formatted, ticket)

    def test_props_format_wrap_rightside(self):
        self.env.config.set('notification', 'mime_encoding', 'none')
        ticket = Ticket(self.env)
        ticket['summary'] = 'This is a summary'
        ticket['reporter'] = 'anonymous'
        ticket['status'] = 'new'
        ticket['owner'] = 'somebody'
        ticket['type'] = 'defect'
        ticket['priority'] = 'major'
        ticket['milestone'] = 'Lorem ipsum dolor sit amet, consectetur ' \
                              'adipisicing elit, sed do eiusmod tempor ' \
                              'incididunt ut labore et dolore magna ' \
                              'aliqua. Ut enim ad minim veniam, quis ' \
                              'nostrud exercitation ullamco laboris nisi ' \
                              'ut aliquip ex ea commodo consequat. Duis ' \
                              'aute irure dolor in reprehenderit in ' \
                              'voluptate velit esse cillum dolore eu ' \
                              'fugiat nulla pariatur. Excepteur sint ' \
                              'occaecat cupidatat non proident, sunt in ' \
                              'culpa qui officia deserunt mollit anim id ' \
                              'est laborum.'
        ticket['component'] = 'component1'
        ticket['version'] = '2.0 Standard and International Edition'
        ticket['resolution'] = 'fixed'
        ticket['keywords'] = ''
        ticket.insert()
        formatted = """\
  Reporter:  anonymous   |      Owner:  somebody
      Type:  defect      |     Status:  new
  Priority:  major       |  Milestone:  Lorem ipsum dolor sit amet,
                         |  consectetur adipisicing elit, sed do eiusmod
                         |  tempor incididunt ut labore et dolore magna
                         |  aliqua. Ut enim ad minim veniam, quis nostrud
                         |  exercitation ullamco laboris nisi ut aliquip ex
                         |  ea commodo consequat. Duis aute irure dolor in
                         |  reprehenderit in voluptate velit esse cillum
                         |  dolore eu fugiat nulla pariatur. Excepteur sint
                         |  occaecat cupidatat non proident, sunt in culpa
                         |  qui officia deserunt mollit anim id est
                         |  laborum.
 Component:  component1  |    Version:  2.0 Standard and International
                         |  Edition
Resolution:  fixed       |   Keywords:"""
        self._validate_props_format(formatted, ticket)

    def test_props_format_wrap_rightside_unicode(self):
        self.env.config.set('notification', 'mime_encoding', 'none')
        ticket = Ticket(self.env)
        ticket['summary'] = 'This is a summary'
        ticket['reporter'] = 'anonymous'
        ticket['status'] = 'new'
        ticket['owner'] = 'somebody'
        ticket['type'] = 'defect'
        ticket['priority'] = 'major'
        ticket['milestone'] = 'Trac 在经过修改的BSD协议下发布。' \
                              '[1:]协议的完整文本可以[2:在线查' \
                              '看]也可在发布版的 [3:COPYING] 文' \
                              '件中找到。'
        ticket['component'] = 'component1'
        ticket['version'] = '2.0'
        ticket['resolution'] = 'fixed'
        ticket['keywords'] = ''
        ticket.insert()
        formatted = """\
  Reporter:  anonymous   |      Owner:  somebody
      Type:  defect      |     Status:  new
  Priority:  major       |  Milestone:  Trac 在经过修改的BSD协议下发布。
                         |  [1:]协议的完整文本可以[2:在线查看]也可在发布版
                         |  的 [3:COPYING] 文件中找到。
 Component:  component1  |    Version:  2.0
Resolution:  fixed       |   Keywords:"""
        self._validate_props_format(formatted, ticket)

    def test_props_format_wrap_bothsides(self):
        self.env.config.set('notification', 'mime_encoding', 'none')
        ticket = Ticket(self.env)
        ticket['summary'] = 'This is a summary'
        ticket['reporter'] = 'anonymous'
        ticket['status'] = 'new'
        ticket['owner'] = 'somebody'
        ticket['type'] = 'defect'
        ticket['priority'] = 'major'
        ticket['milestone'] = 'Lorem ipsum dolor sit amet, consectetur ' \
                              'adipisicing elit, sed do eiusmod tempor ' \
                              'incididunt ut labore et dolore magna ' \
                              'aliqua. Ut enim ad minim veniam, quis ' \
                              'nostrud exercitation ullamco laboris nisi ' \
                              'ut aliquip ex ea commodo consequat. Duis ' \
                              'aute irure dolor in reprehenderit in ' \
                              'voluptate velit esse cillum dolore eu ' \
                              'fugiat nulla pariatur. Excepteur sint ' \
                              'occaecat cupidatat non proident, sunt in ' \
                              'culpa qui officia deserunt mollit anim id ' \
                              'est laborum.'
        ticket['component'] = ('Lorem ipsum dolor sit amet, consectetur '
                               'adipisicing elit, sed do eiusmod tempor '
                               'incididunt ut labore et dolore magna aliqua.')
        ticket['version'] = '2.0'
        ticket['resolution'] = 'fixed'
        ticket['keywords'] = 'Ut enim ad minim veniam, ....'
        ticket.insert()
        formatted = """\
  Reporter:  anonymous               |      Owner:  somebody
      Type:  defect                  |     Status:  new
  Priority:  major                   |  Milestone:  Lorem ipsum dolor sit
                                     |  amet, consectetur adipisicing elit,
                                     |  sed do eiusmod tempor incididunt ut
                                     |  labore et dolore magna aliqua. Ut
                                     |  enim ad minim veniam, quis nostrud
                                     |  exercitation ullamco laboris nisi
                                     |  ut aliquip ex ea commodo consequat.
                                     |  Duis aute irure dolor in
                                     |  reprehenderit in voluptate velit
                                     |  esse cillum dolore eu fugiat nulla
 Component:  Lorem ipsum dolor sit   |  pariatur. Excepteur sint occaecat
  amet, consectetur adipisicing      |  cupidatat non proident, sunt in
  elit, sed do eiusmod tempor        |  culpa qui officia deserunt mollit
  incididunt ut labore et dolore     |  anim id est laborum.
  magna aliqua.                      |    Version:  2.0
Resolution:  fixed                   |   Keywords:  Ut enim ad minim
                                     |  veniam, ...."""
        self._validate_props_format(formatted, ticket)

    def test_props_format_wrap_bothsides_unicode(self):
        self.env.config.set('notification', 'mime_encoding', 'none')
        self.env.config.set('notification', 'ambiguous_char_width', 'double')
        ticket = Ticket(self.env)
        ticket['summary'] = 'This is a summary'
        ticket['reporter'] = 'anonymous'
        ticket['status'] = 'new'
        ticket['owner'] = 'somebody'
        ticket['type'] = 'defect'
        ticket['priority'] = 'major'
        ticket['milestone'] = 'Trac 在经过修改的BSD协议下发布。' \
                              '[1:]协议的完整文本可以[2:在线查' \
                              '看]也可在发布版的 [3:COPYING] 文' \
                              '件中找到。'
        ticket['component'] = 'Trac は BSD ライセンスのもとで配' \
                              '布されています。[1:]このライセ' \
                              'ンスの全文は、※配布ファイル' \
                              'に含まれている[3:CОPYING]ファイ' \
                              'ルと同じものが[2:オンライン]で' \
                              '参照できます。'
        ticket['version'] = '2.0 International Edition'
        ticket['resolution'] = 'fixed'
        ticket['keywords'] = ''
        ticket.insert()
        formatted = """\
  Reporter:  anonymous               |      Owner:  somebody
      Type:  defect                  |     Status:  new
  Priority:  major                   |  Milestone:  Trac 在经过修改的BSD协
 Component:  Trac は BSD ライセンス  |  议下发布。[1:]协议的完整文本可以[2:
  のもとで配布されています。[1:]こ   |  在线查看]也可在发布版的 [3:COPYING]
  のライセンスの全文は、※配布ファ   |  文件中找到。
  イルに含まれている[3:CОPYING]フ   |    Version:  2.0 International
  ァイルと同じものが[2:オンライン]   |  Edition
  で参照できます。                   |
Resolution:  fixed                   |   Keywords:"""
        self._validate_props_format(formatted, ticket)

    def test_props_format_wrap_ticket_10283(self):
        self.env.config.set('notification', 'mime_encoding', 'none')
        for name, value in (('blockedby', 'text'),
                            ('blockedby.label', 'Blocked by'),
                            ('blockedby.order', '6'),
                            ('blocking', 'text'),
                            ('blocking.label', 'Blocking'),
                            ('blocking.order', '5'),
                            ('deployment', 'text'),
                            ('deployment.label', 'Deployment state'),
                            ('deployment.order', '1'),
                            ('nodes', 'text'),
                            ('nodes.label', 'Related nodes'),
                            ('nodes.order', '3'),
                            ('privacy', 'text'),
                            ('privacy.label', 'Privacy sensitive'),
                            ('privacy.order', '2'),
                            ('sensitive', 'text'),
                            ('sensitive.label', 'Security sensitive'),
                            ('sensitive.order', '4')):
            self.env.config.set('ticket-custom', name, value)

        ticket = Ticket(self.env)
        ticket['summary'] = 'This is a summary'
        ticket['reporter'] = 'anonymous'
        ticket['owner'] = 'somebody'
        ticket['type'] = 'defect'
        ticket['status'] = 'closed'
        ticket['priority'] = 'normal'
        ticket['milestone'] = 'iter_01'
        ticket['component'] = 'XXXXXXXXXXXXXXXXXXXXXXXXXX'
        ticket['resolution'] = 'fixed'
        ticket['keywords'] = ''
        ticket['deployment'] = ''
        ticket['privacy'] = '0'
        ticket['nodes'] = 'XXXXXXXXXX'
        ticket['sensitive'] = '0'
        ticket['blocking'] = ''
        ticket['blockedby'] = ''
        ticket.insert()

        formatted = """\
          Reporter:  anonymous                   |             Owner:
                                                 |  somebody
              Type:  defect                      |            Status:
                                                 |  closed
          Priority:  normal                      |         Milestone:
                                                 |  iter_01
         Component:  XXXXXXXXXXXXXXXXXXXXXXXXXX  |        Resolution:
                                                 |  fixed
          Keywords:                              |  Deployment state:
 Privacy sensitive:  0                           |     Related nodes:
                                                 |  XXXXXXXXXX
Security sensitive:  0                           |          Blocking:
        Blocked by:                              |"""
        self._validate_props_format(formatted, ticket)

    def _validate_props_format(self, expected, ticket):
        notify_ticket_created(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)
        bodylines = body.splitlines()
        # Extract ticket properties
        delim_re = re.compile(r'^\-+\+\-+$')
        while not delim_re.match(bodylines[0]):
            bodylines.pop(0)
        lines = []
        for line in bodylines[1:]:
            if delim_re.match(line):
                break
            lines.append(line)
        self.assertEqual(expected, '\n'.join(lines))

    def test_notification_does_not_alter_ticket_instance(self):
        ticket = insert_ticket(self.env, summary='My Summary',
                               description='Some description')
        notify_ticket_created(self.env, ticket)
        self.assertIsNotNone(smtpd.get_message())
        self.assertEqual('My Summary', ticket['summary'])
        self.assertEqual('Some description', ticket['description'])
        valid_fieldnames = {f['name'] for f in ticket.fields}
        current_fieldnames = set(ticket.values)
        self.assertEqual(set(), current_fieldnames - valid_fieldnames)

    def test_mime_meta_characters_in_from_header(self):
        """MIME encoding with meta characters in From header"""

        self.env.config.set('notification', 'smtp_from', 'trac@example.com')
        self.env.config.set('notification', 'mime_encoding', 'base64')
        ticket = insert_ticket(self.env, reporter='joeuser',
                               summary='This is a summary')

        def notify(from_name):
            self.env.config.set('notification', 'smtp_from_name', from_name)
            notify_ticket_created(self.env, ticket)
            message = smtpd.get_message()
            headers, body = parse_smtp_message(message, decode=False)
            return message, headers, body

        message, headers, body = notify('Träc')
        self.assertIn(headers['From'],
                      ('=?utf-8?b?VHLDpGM=?= <trac@example.com>',
                       '=?utf-8?q?Tr=C3=A4c?= <trac@example.com>'))
        message, headers, body = notify('Trac\\')
        self.assertEqual(r'"Trac\\" <trac@example.com>', headers['From'])
        message, headers, body = notify('Trac"')
        self.assertEqual(r'"Trac\"" <trac@example.com>', headers['From'])
        message, headers, body = notify('=?utf-8?q?e_?=')
        self.assertEqual('=?utf-8?b?PeKAiz91dGYtOD9xP2VfPz0=?= '
                         '<trac@example.com>', headers['From'])

    def test_mime_meta_characters_in_subject_header(self):
        """MIME encoding with meta characters in Subject header"""

        self.env.config.set('notification', 'smtp_from', 'trac@example.com')
        self.env.config.set('notification', 'mime_encoding', 'base64')
        summary = '=?utf-8?q?e_?='
        ticket = insert_ticket(self.env, reporter='joeuser', summary=summary)
        notify_ticket_created(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)
        self.assertEqual('[TracTest] #1: =\u200b?utf-8?q?e_?=',
                         headers['Subject'])
        self.assertIn('\nSubject: [TracTest] #1: '
                      '=?utf-8?b?PeKAiz91dGYtOD9xP2VfPz0=?=', message)

    def test_mail_headers(self):
        def validates(headers):
            self.assertEqual('http://localhost/project.url',
                             headers.get('X-URL'))
            self.assertEqual('ticket', headers.get('X-Trac-Realm'))
            self.assertEqual(str(ticket.id), headers.get('X-Trac-Ticket-ID'))

        when = datetime(2015, 1, 1, tzinfo=utc)
        ticket = insert_ticket(self.env, reporter='joeuser', summary='Summary',
                               when=when)
        notify_ticket_created(self.env, ticket)
        headers, body = parse_smtp_message(smtpd.get_message())
        validates(headers)
        self.assertEqual('http://localhost/trac/ticket/%d' % ticket.id,
                         headers.get('X-Trac-Ticket-URL'))

        ticket.save_changes(comment='New comment 1',
                            when=when + timedelta(days=1))
        notify_ticket_changed(self.env, ticket)
        headers, body = parse_smtp_message(smtpd.get_message())
        validates(headers)
        self.assertEqual('http://localhost/trac/ticket/%d#comment:1' %
                         ticket.id, headers.get('X-Trac-Ticket-URL'))

        ticket.save_changes(comment='Reply to comment:1', replyto='1',
                            when=when + timedelta(days=2))
        notify_ticket_changed(self.env, ticket)
        headers, body = parse_smtp_message(smtpd.get_message())
        validates(headers)
        self.assertEqual('http://localhost/trac/ticket/%d#comment:2' %
                         ticket.id, headers.get('X-Trac-Ticket-URL'))

    def test_property_change_author_is_obfuscated(self):
        ticket = self._insert_ticket(owner='user1@d.com',
                                     reporter='user2@d.com',
                                     cc='user3@d.com, user4@d.com')
        ticket['owner'] = 'user2@d.com'
        ticket['reporter'] = 'user1@d.com'
        ticket['cc'] = 'user4@d.com'
        ticket.save_changes('user0@d.com', "The comment")

        notify_ticket_changed(self.env, ticket)
        message = smtpd.get_message()
        body = parse_smtp_message(message)[1]

        self.assertIn('Changes (by user0@…)', body)
        self.assertIn('* owner:  user1@… => user2@…\n', body)
        self.assertIn('* reporter:  user2@… => user1@…\n', body)
        self.assertIn('* cc: user3@… (removed)\n', body)

    def test_comment_change_author_is_obfuscated(self):
        ticket = self._insert_ticket()
        ticket.save_changes('user@d.com', "The comment")

        notify_ticket_changed(self.env, ticket)
        message = smtpd.get_message()
        body = parse_smtp_message(message)[1]

        self.assertIn('Comment (by user@…)', body)

    def test_property_change_author_is_not_obfuscated(self):
        self.env.config.set('trac', 'show_email_addresses', True)
        self.env.config.set('trac', 'show_full_names', False)
        ticket = self._insert_ticket(owner='user1@d.com',
                                     reporter='user2@d.com',
                                     cc='user3@d.com, user4@d.com')
        ticket['owner'] = 'user2@d.com'
        ticket['reporter'] = 'user1@d.com'
        ticket['cc'] = 'user4@d.com'
        ticket.save_changes('user0@d.com', "The comment")

        notify_ticket_changed(self.env, ticket)
        message = smtpd.get_message()
        body = parse_smtp_message(message)[1]

        self.assertIn('Changes (by user0@d.com)', body)
        self.assertIn('* owner:  user1@d.com => user2@d.com\n', body)
        self.assertIn('* reporter:  user2@d.com => user1@d.com\n', body)
        self.assertIn('* cc: user3@d.com (removed)\n', body)

    def test_comment_author_is_not_obfuscated(self):
        self.env.config.set('trac', 'show_email_addresses', True)
        self.env.config.set('trac', 'show_full_names', False)
        ticket = self._insert_ticket()
        ticket.save_changes('user@d.com', "The comment")

        notify_ticket_changed(self.env, ticket)
        message = smtpd.get_message()
        body = parse_smtp_message(message)[1]

        self.assertIn('Comment (by user@d.com)', body)

    def test_property_change_author_full_name(self):
        self.env.config.set('trac', 'show_email_addresses', True)
        self.env.insert_users([
            ('user0', 'Ußęr0', 'user0@d.org'),
            ('user1', 'Ußęr1', 'user1@d.org'),
            ('user2', 'Ußęr2', 'user2@d.org'),
            ('user3', 'Ußęr3', 'user3@d.org'),
            ('user4', 'Ußęr4', 'user4@d.org'),
        ])
        ticket = self._insert_ticket(owner='user1', reporter='user2',
                                     cc='user3, user4')
        ticket['owner'] = 'user2'
        ticket['reporter'] = 'user1'
        ticket['cc'] = 'user4'
        ticket.save_changes('user0', "The comment")

        notify_ticket_changed(self.env, ticket)
        message = smtpd.get_message()
        body = parse_smtp_message(message)[1]

        self.assertIn('Changes (by Ußęr0)', body)
        self.assertIn('* owner:  Ußęr1 => Ußęr2\n', body)
        self.assertIn('* reporter:  Ußęr2 => Ußęr1\n', body)
        self.assertIn('* cc: Ußęr3 (removed)\n', body)

    def test_comment_author_full_name(self):
        self.env.config.set('trac', 'show_email_addresses', True)
        self.env.insert_users([
            ('user', 'Thę Ußęr', 'user@domain.org')
        ])
        ticket = self._insert_ticket()
        ticket.save_changes('user', "The comment")

        notify_ticket_changed(self.env, ticket)
        message = smtpd.get_message()
        body = parse_smtp_message(message)[1]

        self.assertIn('Comment (by Thę Ußęr)', body)


class FormatSubjectTestCase(unittest.TestCase):

    custom_template = """\
${prefix} (${
   'new' if not changes
   else ticket.resolution if ticket.status == 'closed'
   else ticket.status if 'status' in changes.fields
   else 'commented' if 'comment' in changes.fields
                       and changes.fields['comment']['new']
   else 'updated'
}) #${ticket.id}: ${summary}"""


    def setUp(self):
        self.env = EnvironmentStub()
        TicketNotificationSystem(self.env).environment_created()
        self.env.config.set('project', 'name', 'TracTest')
        self.env.config.set('notification', 'smtp_port', str(SMTP_TEST_PORT))
        self.env.config.set('notification', 'smtp_server', 'localhost')
        self.env.config.set('notification', 'smtp_enabled', 'true')

    def tearDown(self):
        smtpd.cleanup()
        self.env.reset_db()

    def _insert_ticket(self):
        return insert_ticket(self.env, reporter='user@domain.com',
                             summary='The summary',
                             description='The description')

    def test_format_subject_new_ticket(self):
        ticket = self._insert_ticket()

        notify_ticket_created(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)

        self.assertEqual('[TracTest] #1: The summary', headers['Subject'])

    def test_format_subject_ticket_change(self):
        ticket = self._insert_ticket()
        ticket['description'] = 'The changed description'
        ticket.save_changes(author='user@domain.com')

        notify_ticket_changed(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)

        self.assertEqual('Re: [TracTest] #1: The summary', headers['Subject'])

    def test_format_subject_ticket_summary_changed(self):
        ticket = self._insert_ticket()
        ticket['summary'] = 'The changed summary'
        ticket.save_changes(author='user@domain.com')

        notify_ticket_changed(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)

        self.assertEqual('Re: [TracTest] #1: The changed summary '
                         '(was: The summary)', headers['Subject'])

    def test_format_subject_custom_template_new_ticket(self):
        """Format subject with a custom template for a new ticket."""
        ticket = self._insert_ticket()
        self.env.config.set('notification', 'ticket_subject_template',
                            self.custom_template)

        notify_ticket_created(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)

        self.assertEqual('[TracTest] (new) #1: The summary',
                         headers['Subject'])

    def test_format_subject_custom_template_changed_ticket(self):
        """Format subject with a custom template for a ticket with
        a changed property.
        """
        ticket = self._insert_ticket()
        ticket['description'] = 'The changed description'
        ticket.save_changes(author='user@domain.com')
        self.env.config.set('notification', 'ticket_subject_template',
                            self.custom_template)

        notify_ticket_changed(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)

        self.assertEqual('Re: [TracTest] (updated) #1: The summary',
                         headers['Subject'])

    def test_format_subject_custom_template_commented_ticket(self):
        """Format subject with a custom template for a ticket with
        a changed property and a comment.
        """
        ticket = self._insert_ticket()
        ticket['description'] = 'The changed description'
        ticket.save_changes(author='user@domain.com', comment='the comment')
        self.env.config.set('notification', 'ticket_subject_template',
                            self.custom_template)

        notify_ticket_changed(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)

        self.assertEqual('Re: [TracTest] (commented) #1: The summary',
                         headers['Subject'])

    def test_format_subject_custom_template_status_changed_ticket(self):
        """Format subject with a custom template for a ticket with
        changed status.
        """
        ticket = self._insert_ticket()
        ticket['status'] = 'accepted'
        ticket.save_changes(author='user@domain.com')
        self.env.config.set('notification', 'ticket_subject_template',
                            self.custom_template)

        notify_ticket_changed(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)

        self.assertEqual('Re: [TracTest] (accepted) #1: The summary',
                         headers['Subject'])

    def test_format_subject_custom_template_closed_ticket(self):
        """Format subject with a custom template for a closed ticket."""
        ticket = self._insert_ticket()
        ticket['status'] = 'closed'
        ticket['resolution'] = 'worksforme'
        ticket.save_changes(author='user@domain.com')
        self.env.config.set('notification', 'ticket_subject_template',
                            self.custom_template)

        notify_ticket_changed(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)

        self.assertEqual('Re: [TracTest] (worksforme) #1: The summary',
                         headers['Subject'])

    def test_format_subject_custom_template_with_hash(self):
        """Format subject with a custom template with leading #."""
        ticket = self._insert_ticket()
        self.env.config.set('notification', 'ticket_subject_template',
                            '#${ticket.id}: ${summary}')

        notify_ticket_created(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)

        self.assertEqual('#1: The summary', headers['Subject'])

    def test_format_subject_custom_template_with_double_hash(self):
        """Format subject with a custom template with leading ##."""
        ticket = self._insert_ticket()
        self.env.config.set('notification', 'ticket_subject_template',
                            '##${prefix}## #${ticket.id}: ${summary}')

        notify_ticket_created(self.env, ticket)
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)

        self.assertEqual('##[TracTest]## #1: The summary', headers['Subject'])


class AttachmentNotificationTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True, path=mkdtemp())
        config_smtp(self.env)
        config_subscriber(self.env, reporter=True)

    def tearDown(self):
        """Signal the notification test suite that a test is over"""
        smtpd.cleanup()
        self.env.reset_db_and_disk()

    def _insert_attachment(self, author):
        ticket = insert_ticket(self.env, summary='Ticket summary',
                               reporter=author)
        attachment = Attachment(self.env, 'ticket', ticket.id)
        attachment.description = "The attachment description"
        attachment.author = author
        attachment.insert('foo.txt', io.BytesIO(), 1)
        return attachment

    def test_ticket_notify_attachment_enabled_attachment_added(self):
        self._insert_attachment('user@example.com')

        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)

        self.assertIn("Re: [TracTest] #1: Ticket summary", headers['Subject'])
        self.assertIn(" * Attachment \"foo.txt\" added", body)
        self.assertIn("The attachment description", body)

    def test_ticket_notify_attachment_enabled_attachment_removed(self):
        attachment = self._insert_attachment('user@example.com')
        attachment.delete()

        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)

        self.assertIn("Re: [TracTest] #1: Ticket summary", headers['Subject'])
        self.assertIn(" * Attachment \"foo.txt\" removed", body)
        self.assertIn("The attachment description", body)

    def test_author_is_obfuscated(self):
        self.env.config.set('trac', 'show_email_addresses', False)
        self.env.config.set('trac', 'show_full_names', False)
        self._insert_attachment('user@example.com')

        message = smtpd.get_message()
        body = parse_smtp_message(message)[1]

        self.assertIn('Changes (by user@…)', body)

    def test_author_is_not_obfuscated(self):
        self.env.config.set('trac', 'show_email_addresses', True)
        self.env.config.set('trac', 'show_full_names', False)
        self._insert_attachment('user@example.com')

        message = smtpd.get_message()
        body = parse_smtp_message(message)[1]

        self.assertIn('Changes (by user@example.com)', body)

    def test_author_full_name(self):
        self.env.config.set('trac', 'show_email_addresses', True)
        self.env.insert_users([
            ('user', 'Thę Ußęr', 'user@domain.org')
        ])
        self._insert_attachment('user')

        message = smtpd.get_message()
        body = parse_smtp_message(message)[1]

        self.assertIn('Changes (by Thę Ußęr)', body)


class BatchTicketNotificationTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True, path=mkdtemp())
        config_smtp(self.env)
        self.env.config.set('project', 'url', 'http://localhost/project.url')

        self.tktids = []
        with self.env.db_transaction as db:
            for n in range(2):
                for priority in ('', 'blah', 'blocker', 'critical', 'major',
                                 'minor', 'trivial'):
                    idx = len(self.tktids)
                    owner = 'owner@example.org' if idx == 0 else 'anonymous'
                    reporter = 'reporter@example.org' \
                               if idx == 1 else 'anonymous'
                    cc = 'cc1@example.org, cc2@example.org' if idx == 2 else ''
                    when = datetime(2001, 7, 12, 12, 34, idx, 0, utc)
                    ticket = insert_ticket(self.env, summary='Summary %s:%d'
                                                             % (priority, idx),
                                           priority=priority, owner=owner,
                                           reporter=reporter, cc=cc, when=when)
                    self.tktids.append(ticket.id)
        self.tktids.reverse()
        config_subscriber(self.env, updater=True, reporter=True)

    def tearDown(self):
        smtpd.cleanup()
        self.env.reset_db_and_disk()

    def _change_tickets(self, author, new_values, comment, when=None):
        if when is None:
            when = datetime(2016, 8, 21, 12, 34, 56, 987654, utc)
        with self.env.db_transaction:
            for tktid in self.tktids:
                t = Ticket(self.env, tktid)
                for name, value in new_values.items():
                    t[name] = value
                t.save_changes(author, comment, when=when)
        return BatchTicketChangeEvent(self.tktids, when, author, comment,
                                      new_values, 'leave')
    def _notify(self, event):
        smtpd.cleanup()
        NotificationSystem(self.env).notify(event)
        recipients = sorted(smtpd.get_recipients())
        sender = smtpd.get_sender()
        message = smtpd.get_message()
        headers, body = parse_smtp_message(message)
        body = body.splitlines()
        return recipients, sender, message, headers, body

    def test_batchmod_notify(self):
        self.assertEqual(1, min(self.tktids))
        self.assertEqual(14, max(self.tktids))
        new_values = {'milestone': 'milestone1'}
        author = 'author@example.org'
        comment = 'batch-modify'
        when = datetime(2016, 8, 21, 12, 34, 56, 987654, utc)
        event = self._change_tickets(author, new_values, comment, when)

        recipients, sender, message, headers, body = self._notify(event)

        self.assertEqual(['author@example.org', 'cc1@example.org',
                          'cc2@example.org', 'reporter@example.org'],
                         recipients)
        self.assertEqual('trac@localhost', sender)
        self.assertIn('Date', headers)
        self.assertEqual('[TracTest] Batch modify: #3, #10, #4, #11, #5, #12, '
                         '#6, #13, #7, #14, ...', headers['Subject'])
        self.assertEqual('TracTest <trac@localhost>', headers['From'])
        self.assertEqual('<078.0b9de298f9080302285a0e333c75dd47@localhost>',
                         headers['Message-ID'])
        self.assertIn('Batch modification to #3, #10, #4, #11, #5, #12, #6, '
                      '#13, #7, #14, #1, #2, #8, #9 by author@example.org:',
                      body)
        self.assertIn('-- ', body)
        self.assertIn('Tickets URL: <http://example.org/trac.cgi/query?id=3'
                      '%2C10%2C4%2C11%2C5%2C12%2C6%2C13%2C7%2C14%2C1%2C2%2C8'
                      '%2C9>', body)

    def test_format_subject_custom_template_with_hash(self):
        """Format subject with a custom template with leading #."""
        self.env.config.set('notification', 'batch_subject_template',
                            '#${prefix}# Batch modify')

        event = self._change_tickets(
            author='author@example.org',
            new_values={'milestone': 'milestone1'},
            comment='batch-modify')

        recipients, sender, message, headers, body = self._notify(event)

        self.assertEqual('#[TracTest]# Batch modify', headers['Subject'])

    def test_format_subject_custom_template_with_double_hash(self):
        """Format subject with a custom template with leading ##."""
        self.env.config.set('notification', 'batch_subject_template',
                            '##${prefix}## Batch modify')

        event = self._change_tickets(
            author='author@example.org',
            new_values={'milestone': 'milestone1'},
            comment='batch-modify')

        recipients, sender, message, headers, body = self._notify(event)

        self.assertEqual('##[TracTest]## Batch modify', headers['Subject'])


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(RecipientTestCase))
    suite.addTest(unittest.makeSuite(NotificationTestCase))
    suite.addTest(unittest.makeSuite(FormatSubjectTestCase))
    suite.addTest(unittest.makeSuite(AttachmentNotificationTestCase))
    suite.addTest(unittest.makeSuite(BatchTicketNotificationTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
