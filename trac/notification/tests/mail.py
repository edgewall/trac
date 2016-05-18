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
from email import message_from_string

from genshi.builder import tag

import trac.tests.compat
from trac.core import Component, implements
from trac.notification.api import (
    IEmailSender, INotificationFormatter, INotificationSubscriber,
    NotificationEvent, NotificationSystem,
)
from trac.notification.model import Subscription
from trac.test import EnvironmentStub
from trac.util.datefmt import datetime_now, utc
from trac.web.session import DetachedSession


class TestEmailSender(Component):

    implements(IEmailSender)

    def __init__(self):
        self.history = []

    def send(self, from_addr, recipients, message):
        self.history.append((from_addr, recipients,
                             message_from_string(message)))


class TestFormatter(Component):

    implements(INotificationFormatter)

    def get_supported_styles(self, transport):
        if transport == 'email':
            yield 'text/plain', 'test'
            yield 'text/html', 'test'

    def format(self, transport, style, event):
        if transport != 'email':
            return
        text = event.target.text
        if style == 'text/plain':
            if 'raise-text-plain' in text:
                raise ValueError()
            return unicode(text)
        if style == 'text/html':
            if 'raise-text-html' in text:
                raise ValueError()
            return unicode(tag.p(text))


class TestSubscriber(Component):

    implements(INotificationSubscriber)

    def _find_subscriptions(self):
        klass = self.__class__.__name__
        return Subscription.find_by_class(self.env, klass)

    def matches(self, event):
        if event.realm == 'test':
            for model in self._find_subscriptions():
                yield model.subscription_tuple()

    def description(self):
        return self.__class__.__name__

    def requires_authentication(self):
        return False

    def default_subscriptions(self):
        return ()


class TestNotificationEvent(NotificationEvent): pass


class TestModel(object):

    realm = 'test'

    def __init__(self, text):
        self.text = text


class EmailDistributorTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=['trac.*', TestEmailSender,
                                           TestFormatter, TestSubscriber])
        config = self.env.config
        config.set('notification', 'smtp_from', 'trac@example.org')
        config.set('notification', 'smtp_enabled', 'enabled')
        config.set('notification', 'smtp_always_cc', 'cc@example.org')
        config.set('notification', 'smtp_always_bcc', 'bcc@example.org')
        config.set('notification', 'email_sender', 'TestEmailSender')
        self.sender = TestEmailSender(self.env)
        self.notsys = NotificationSystem(self.env)
        with self.env.db_transaction:
            self._add_session('foo', email='foo@example.org')
            self._add_session('bar', email='bar@example.org',
                              name=u"Bäŕ's name")

    def tearDown(self):
        self.env.reset_db()

    def _notify_event(self, text, category='created', time=None, author=None):
        self.sender.history[:] = ()
        event = TestNotificationEvent('test', category, TestModel(text),
                                      time or datetime_now(utc), author=author)
        self.notsys.notify(event)

    def _add_session(self, sid, **attrs):
        session = DetachedSession(self.env, sid)
        for name, value in attrs.iteritems():
            session[name] = value
        session.save()

    def _add_subscription(self, **kwargs):
        subscription = {'sid': None, 'authenticated': 1, 'distributor': 'email',
                        'format': 'text/plain', 'adverb': 'always',
                        'class': 'TestSubscriber'}
        subscription.update(kwargs)
        Subscription.add(self.env, subscription)

    def test_smtp_disabled(self):
        self.env.config.set('notification', 'smtp_enabled', 'disabled')
        with self.env.db_transaction:
            self._add_subscription(sid='foo')
            self._add_subscription(sid='bar')
        self._notify_event('blah')
        self.assertEqual([], self.sender.history)

    def _assert_mail(self, message, content_type, body):
        self.assertNotIn('Bcc', message)
        self.assertEqual('multipart/related', message.get_content_type())
        payload = list(message.get_payload())
        self.assertEqual([content_type],
                         [p.get_content_type() for p in payload])
        self.assertEqual([body], [p.get_payload() for p in payload])

    def _assert_alternative_mail(self, message, body_plain, body_html):
        self.assertNotIn('Bcc', message)
        self.assertEqual('multipart/related', message.get_content_type())
        payload = list(message.get_payload())
        self.assertEqual(['multipart/alternative'],
                         [p.get_content_type() for p in payload])
        alternative = list(payload[0].get_payload())
        self.assertEqual(['text/plain', 'text/html'],
                         [p.get_content_type() for p in alternative])
        self.assertEqual([body_plain, body_html],
                         [p.get_payload() for p in alternative])

    def test_plain(self):
        with self.env.db_transaction:
            self._add_subscription(sid='foo')
            self._add_subscription(sid='bar')
        self._notify_event('blah')

        history = self.sender.history
        self.assertNotEqual([], history)
        self.assertEqual(1, len(history))
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual(set(('foo@example.org', 'bar@example.org',
                              'cc@example.org', 'bcc@example.org')),
                         set(recipients))
        self._assert_mail(message, 'text/plain', 'blah')

    def test_html(self):
        with self.env.db_transaction:
            self._add_subscription(sid='foo', format='text/html')
        self._notify_event('blah')

        history = self.sender.history
        self.assertNotEqual([], history)
        self.assertEqual(2, len(history))
        for from_addr, recipients, message in history:
            if 'foo@example.org' in recipients:
                self.assertEqual('trac@example.org', from_addr)
                self.assertEqual(['foo@example.org'], recipients)
                self._assert_alternative_mail(message, 'blah', '<p>blah</p>')
            if 'cc@example.org' in recipients:
                self.assertEqual('trac@example.org', from_addr)
                self.assertEqual(set(('cc@example.org', 'bcc@example.org')),
                                 set(recipients))
                self._assert_mail(message, 'text/plain', 'blah')

    def test_plain_and_html(self):
        with self.env.db_transaction:
            self._add_subscription(sid='foo', format='text/plain')
            self._add_subscription(sid='bar', format='text/html')
        self._notify_event('blah')

        history = self.sender.history
        self.assertNotEqual([], history)
        self.assertEqual(2, len(history))
        for from_addr, recipients, message in history:
            if 'foo@example.org' in recipients:
                self.assertEqual(set(('foo@example.org', 'cc@example.org',
                                      'bcc@example.org')),
                                 set(recipients))
                self._assert_mail(message, 'text/plain', 'blah')
            if 'bar@example.org' in recipients:
                self.assertEqual(['bar@example.org'], recipients)
                self._assert_alternative_mail(message, 'blah', '<p>blah</p>')

    def test_broken_plain_formatter(self):
        with self.env.db_transaction:
            self._add_subscription(sid='foo', format='text/plain')
            self._add_subscription(sid='bar', format='text/html')
        self._notify_event('raise-text-plain')

        history = self.sender.history
        self.assertNotEqual([], history)
        self.assertEqual(1, len(history))
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual(['bar@example.org'], recipients)
        self._assert_mail(message, 'text/html', '<p>raise-text-plain</p>')

    def test_broken_html_formatter(self):
        with self.env.db_transaction:
            self._add_subscription(sid='foo', format='text/html')
            self._add_subscription(sid='bar', format='text/plain')
        self._notify_event('raise-text-html')

        # fallback to text/plain
        history = self.sender.history
        self.assertNotEqual([], history)
        self.assertEqual(1, len(history))
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual(set(('foo@example.org', 'bar@example.org',
                              'cc@example.org', 'bcc@example.org')),
                         set(recipients))
        self._assert_mail(message, 'text/plain', 'raise-text-html')

    def test_broken_plain_and_html_formatter(self):
        with self.env.db_transaction:
            self._add_subscription(sid='foo', format='text/plain')
            self._add_subscription(sid='bar', format='text/html')
        self._notify_event('raise-text-plain raise-text-html')

        history = self.sender.history
        self.assertEqual([], history)

    def test_username_in_always_cc(self):
        self.env.config.set('notification', 'smtp_always_cc',
                            'foo, cc@example.org')
        self.env.config.set('notification', 'smtp_always_bcc',
                            'bar, foo, bcc@example.org')
        self._notify_event('blah')

        history = self.sender.history
        self.assertNotEqual([], history)
        self.assertEqual(1, len(history))
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual(set(('foo@example.org', 'bar@example.org',
                              'cc@example.org', 'bcc@example.org')),
                         set(recipients))
        self.assertEqual('cc@example.org, foo@example.org', message['Cc'])
        self.assertEqual(None, message['Bcc'])
        self._assert_mail(message, 'text/plain', 'blah')

    def test_from_author_disabled(self):
        self.env.config.set('notification', 'smtp_from_author', 'disabled')
        with self.env.db_transaction:
            self._add_subscription(sid='bar')

        self._notify_event('blah', author='bar')
        history = self.sender.history
        self.assertNotEqual([], history)
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual('"My Project" <trac@example.org>', message['From'])
        self.assertEqual(1, len(history))

        self._notify_event('blah', author=None)
        history = self.sender.history
        self.assertNotEqual([], history)
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual('"My Project" <trac@example.org>', message['From'])
        self.assertEqual(1, len(history))

        self.env.config.set('notification', 'smtp_from_name', 'Trac')
        self._notify_event('blah', author=None)
        history = self.sender.history
        self.assertNotEqual([], history)
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual('"Trac" <trac@example.org>', message['From'])
        self.assertEqual(1, len(history))

    def test_from_author_enabled(self):
        self.env.config.set('notification', 'smtp_from_author', 'enabled')
        with self.env.db_transaction:
            self._add_subscription(sid='foo')
            self._add_subscription(sid='bar')

        self._notify_event('blah', author='bar')
        history = self.sender.history
        self.assertNotEqual([], history)
        from_addr, recipients, message = history[0]
        self.assertEqual('bar@example.org', from_addr)
        self.assertEqual('"=?utf-8?b?QsOkxZUncyBuYW1l?=" <bar@example.org>',
                         message['From'])
        self.assertEqual(1, len(history))

        self._notify_event('blah', author='foo')
        history = self.sender.history
        self.assertNotEqual([], history)
        from_addr, recipients, message = history[0]
        self.assertEqual('foo@example.org', from_addr)
        self.assertEqual('foo@example.org', message['From'])
        self.assertEqual(1, len(history))

        self._notify_event('blah', author=None)
        history = self.sender.history
        self.assertNotEqual([], history)
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual('"My Project" <trac@example.org>', message['From'])
        self.assertEqual(1, len(history))

        self.env.config.set('notification', 'smtp_from_name', 'Trac')
        self._notify_event('blah', author=None)
        history = self.sender.history
        self.assertNotEqual([], history)
        from_addr, recipients, message = history[0]
        self.assertEqual('trac@example.org', from_addr)
        self.assertEqual('"Trac" <trac@example.org>', message['From'])
        self.assertEqual(1, len(history))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(EmailDistributorTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
