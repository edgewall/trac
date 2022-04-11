# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2022 Edgewall Software
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
# This file does not contain unit tests, but provides a set of
# classes to run SMTP notification tests
#

import asyncore
import base64
import hmac
import os
import re
import smtpd
import threading
import unittest
from email.header import decode_header as _email_decode_header

from trac.config import ConfigurationError
from trac.notification import SendmailEmailSender, SmtpEmailSender
from trac.test import EnvironmentStub

LF = '\n'
CR = '\r'
SMTP_TEST_PORT = 7000 + os.getpid() % 1000
header_re = re.compile(r'^=\?(?P<charset>[\w\d\-]+)\?(?P<code>[qb])\?(?P<value>.*)\?=$')


class SMTPServerInterface(object):
    """
    A base class for the implementation of an application specific SMTP
    Server. Applications should subclass this and override these
    methods, which by default do nothing.

    A method is defined for each RFC821 command. For each of these
    methods, 'args' is the complete command received from the
    client. The 'data' method is called after all of the client DATA
    is received.

    If a method returns 'None', then a '250 OK' message is
    automatically sent to the client. If a subclass returns a non-null
    string then it is returned instead.
    """

    def helo(self, args):
        return None

    def mail_from(self, args):
        return None

    def rcpt_to(self, args):
        return None

    def data(self, args):
        return None

    def quit(self, args):
        return None

    def reset(self, args):
        return None


#
# Some helper functions for manipulating from & to addresses etc.
#
def strip_address(address):
    """
    Strip the leading & trailing <> from an address.  Handy for
    getting FROM: addresses.
    """
    start = address.find(b'<') + 1
    end = address.find(b'>')
    return address[start:end]


def _b64decode(value):
    value = base64.b64decode(value)
    return str(value, 'utf-8')


def _b64encode(value):
    if isinstance(value, str):
        value = value.encode('utf-8')
    value = base64.b64encode(value)
    return str(value, 'ascii')


class SMTPChannel(smtpd.SMTPChannel):

    authmethod = None
    authenticating = None

    @property
    def user(self):
        return self.smtp_server.user

    @property
    def password(self):
        return self.smtp_server.password

    def found_terminator(self):
        line = self._emptystring.join(self.received_lines)
        if self.authenticating:
            self.received_lines = []
            self.smtp_AUTH(line)
        else:
            self.authenticating = line.split(' ', 1)[0].upper() == 'AUTH'
            super().found_terminator()

    def push(self, msg):
        if msg == '250 HELP':
            super().push('250-AUTH ' + self.authmethod)
        super().push(msg)
        if self.authenticating and not msg.startswith('3'):
            self.authenticating = False
        if msg.startswith('5'):
            self.close_when_done()


class SMTPChannelAuthPlain(SMTPChannel):

    authmethod = 'PLAIN'

    def smtp_AUTH(self, arg):
        values = arg.split(' ', 1)
        if len(values) == 0 or values[0] != self.authmethod:
            self.push('535 Authentication failed')
            return
        try:
            creds = _b64decode(values[1])
        except:
            self.push('535 Authentication failed')
            return
        creds = creds.split('\0')
        if len(creds) != 3 or len(creds[0]) != 0 and creds[0] != creds[1]:
            self.push('535 Authentication failed')
            return
        user = creds[1]
        password = creds[2]
        if self.user == user and self.password == password:
            self.push('235 Authentication successful')
        else:
            self.push('535 Authentication failed')


class SMTPChannelAuthLogin(SMTPChannel):

    authmethod = 'LOGIN'
    incoming_user = None

    def smtp_AUTH(self, arg):
        if self.incoming_user:
            try:
                password = _b64decode(arg)
            except:
                password = None
            if self.incoming_user == self.user and password == self.password:
                self.push('235 Authentication successful')
            else:
                self.push('535 Authentication failed')
            return

        values = arg.split(' ', 1)
        if len(values) == 0:
            self.push('535 Authentication failed')
            return

        if values[0] == self.authmethod:
            if len(values) == 2:
                try:
                    self.incoming_user = _b64decode(values[1])
                except:
                    self.push('535 Authentication failed')
                    return
                self.push('334 ' + _b64encode('Password'))
            else:
                self.push('334 ' + _b64encode('Username'))
        else:
            try:
                self.incoming_user = _b64decode(values[0])
            except:
                self.push('535 Authentication failed')
                return
            self.push('334 ' + _b64encode('Password'))


class SMTPChannelAuthCramMd5(SMTPChannel):

    authmethod = 'CRAM-MD5'
    challenge = None

    def smtp_AUTH(self, arg):
        if self.challenge:
            try:
                user, hash_ = _b64decode(arg).split(' ', 1)
            except:
                self.push('535 Authentication failed')
                return
            rehash = hmac.HMAC(self.password.encode('utf-8'), self.challenge,
                               'md5').hexdigest()
            if user == self.user and hash_ == rehash:
                self.push('235 Authentication successful')
            else:
                self.push('535 Authentication failed')
            return
        else:
            self.challenge = os.urandom(64)
            self.push('334 ' + _b64encode(self.challenge))


class SMTPServer(smtpd.SMTPServer):

    user = None
    password = None
    message = None

    def __init__(self, localaddr, **kwargs):
        if 'channel_class' in kwargs:
            self.channel_class = kwargs.pop('channel_class') or \
                                 smtpd.SMTPChannel
        if 'user' in kwargs:
            self.user = kwargs.pop('user')
        if 'password' in kwargs:
            self.password = kwargs.pop('password')
        super().__init__(localaddr, None, decode_data=True, **kwargs)

    def process_message(self, peer, mailfrom, rcpttos, data, **kwargs):
        kwargs['peer'] = peer
        kwargs['mailfrom'] = mailfrom
        kwargs['rcpttos'] = rcpttos
        kwargs['data'] = data.replace('\n', '\r\n')
        self.message = kwargs

    def clear_message(self):
        self.message = None


class SMTPThreadedServer(threading.Thread):
    """
    Run a SMTP server for a single connection, within a dedicated thread
    """
    host = '127.0.0.1'
    port = None
    socket_map = None
    server = None
    authmethod = None
    user = None
    password = None
    authchannels = {
        'PLAIN': SMTPChannelAuthPlain,
        'LOGIN': SMTPChannelAuthLogin,
        'CRAM-MD5': SMTPChannelAuthCramMd5,
    }

    def __init__(self, port, authmethod=None, user=None, password=None):
        self.port = port
        self.authmethod = authmethod
        self.user = user
        self.password = password
        self.socket_map = {}
        super().__init__(target=asyncore.loop,
                         args=(0.1, True, self.socket_map))
        self.daemon = True

    def start(self):
        channel_class = self.authchannels.get(self.authmethod)
        self.server = SMTPServer((self.host, self.port), map=self.socket_map,
                                  channel_class=channel_class,
                                  user=self.user, password=self.password)
        super().start()

    def stop(self):
        self.server.close()
        self.join()

    def get_sender(self):
        message = self.server.message
        return message and message['mailfrom']

    def get_recipients(self):
        message = self.server.message
        return message['rcpttos'] if message else []

    def get_message(self):
        message = self.server.message
        return message and message['data']

    def cleanup(self):
        self.server.clear_message()


def decode_header(header):
    """ Decode a MIME-encoded header value """
    l = []
    for s, charset in _email_decode_header(header):
        if charset:
            s = str(s, charset)
        elif isinstance(s, bytes):
            s = str(s, 'utf-8')
        l.append(s)
    return ''.join(l)


def parse_smtp_message(msg, decode=True):
    """ Split a SMTP message into its headers and body.
        Returns a (headers, body) tuple
        We do not use the email/MIME Python facilities here
        as they may accept invalid RFC822 data, or data we do not
        want to support nor generate """
    if msg is None:
        raise AssertionError('msg is None')
    headers = {}
    lh = None
    lval = None
    body = None
    # last line does not contain the final line ending
    msg += '\r\n'
    for line in msg.splitlines(True):
        if body is not None:
            # append current line to the body
            if line[-2] == CR:
                body += line[0:-2]
                body += '\n'
            else:
                raise AssertionError("body misses CRLF: %s (0x%x)"
                                     % (line, ord(line[-1])))
        else:
            if line[-2] != CR:
                # RFC822 requires CRLF at end of field line
                raise AssertionError("header field misses CRLF: %s (0x%x)"
                                     % (line, ord(line[-1])))
            # discards CR
            line = line[0:-2]
            if line.strip() == '':
                # end of headers, body starts
                body = ''
            else:
                val = None
                if line[0] in ' \t':
                    # continuation of the previous line
                    if not lh:
                        # unexpected multiline
                        raise AssertionError("unexpected folded line: %s"
                                             % line)
                    val = line.strip(' \t')
                    if lval:
                        val = ' ' + val
                    # appends the current line to the previous one
                    if not isinstance(headers[lh], tuple):
                        headers[lh] += val
                    else:
                        headers[lh][-1] += val
                else:
                    # splits header name from value
                    (h, v) = line.split(':', 1)
                    val = v.strip()
                    if h in headers:
                        if isinstance(headers[h], tuple):
                            headers[h] += val
                        else:
                            headers[h] = (headers[h], val)
                    else:
                        headers[h] = val
                    # stores the last header (for multi-line headers)
                    lh = h
                lval = val
    # decode headers
    if decode:
        for h in headers:
            v = headers[h]
            if isinstance(v, tuple):
                v = tuple(map(decode_header, v))
            else:
                v = decode_header(v)
            headers[h] = v
    # returns the headers and the message body
    return headers, body


class SendmailEmailSenderTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def test_sendmail_path_not_found_raises(self):
        sender = SendmailEmailSender(self.env)
        self.env.config.set('notification', 'sendmail_path',
                            os.path.join(os.path.dirname(__file__),
                                         'sendmail'))
        self.assertRaises(ConfigurationError, sender.send,
                          'admin@domain.com', ['foo@domain.com'], "")


class SmtpEmailSenderTestCase(unittest.TestCase):

    maxDiff = None

    message = (
        'From: admin@example.com\r\n'
        'To: foo@example.com\r\n'
        'Subject: test mail\r\n'
        '\r\n'
        'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do\r\n'
        'eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut\r\n'
        'enim ad minim veniam, quis nostrud exercitation ullamco laboris\r\n'
        'nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in\r\n'
        'reprehenderit in voluptate velit esse cillum dolore eu fugiat\r\n'
        'nulla pariatur. Excepteur sint occaecat cupidatat non proident,\r\n'
        'sunt in culpa qui officia deserunt mollit anim id est laborum.'
    )

    def setUp(self):
        self.env = EnvironmentStub()

    def test_smtp_server_not_found_raises(self):
        sender = SmtpEmailSender(self.env)
        self.env.config.set('notification', 'smtp_server', 'localhost')
        self.env.config.set('notification', 'smtp_port', '65536')
        self.assertRaises(ConfigurationError, sender.send,
                          'admin@domain.com', ['foo@domain.com'], "")

    def test_smtp_anonymous(self):
        self._test_smtp()

    def test_smtp_auth_plain_with_ascii_creds(self):
        self._test_smtp('PLAIN', 'tracuser', 'password')

    def test_smtp_auth_plain_with_unicode_creds(self):
        self._test_smtp('PLAIN', 'trácusér', 'paśsẅørd')

    def test_smtp_auth_login_with_ascii_creds(self):
        self._test_smtp('LOGIN', 'tracuser', 'password')

    def test_smtp_auth_login_with_unicode_creds(self):
        self._test_smtp('LOGIN', 'trácusér', 'paśsẅørd')

    def test_smtp_auth_cram_md5_with_ascii_creds(self):
        self._test_smtp('CRAM-MD5', 'tracuser', 'password')

    def test_smtp_auth_cram_md5_with_unicode_creds(self):
        self._test_smtp('CRAM-MD5', 'trácusér', 'paśsẅørd')

    def _test_smtp(self, authmethod=None, user=None, password=None):
        self.env.config.set('notification', 'smtp_server', '127.0.0.1')
        self.env.config.set('notification', 'smtp_port', str(SMTP_TEST_PORT))
        if authmethod:
            self.env.config.set('notification', 'smtp_user', user)
            self.env.config.set('notification', 'smtp_password', password)

        smtpd = SMTPThreadedServer(SMTP_TEST_PORT, authmethod, user, password)
        try:
            smtpd.start()
            sender = SmtpEmailSender(self.env)
            sender.send('admin@example.com', ['foo@example.com'], self.message)
        finally:
            smtpd.stop()

        self.assertEqual('admin@example.com', smtpd.get_sender())
        self.assertEqual(set(['foo@example.com']), set(smtpd.get_recipients()))
        self.assertEqual(self.message, smtpd.get_message())


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(SendmailEmailSenderTestCase))
    suite.addTest(unittest.makeSuite(SmtpEmailSenderTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
