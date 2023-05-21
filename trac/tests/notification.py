# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2023 Edgewall Software
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

import base64
import hmac
import os
import re
import threading
import unittest
from email.header import decode_header as _email_decode_header

try:
    from ._aiosmtpd import SMTPThreadedServer
except ImportError:
    from ._smtpd import SMTPThreadedServer

from trac.config import ConfigurationError
from trac.notification import SendmailEmailSender, SmtpEmailSender
from trac.test import EnvironmentStub, makeSuite

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
    suite.addTest(makeSuite(SendmailEmailSenderTestCase))
    suite.addTest(makeSuite(SmtpEmailSenderTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
