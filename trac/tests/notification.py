# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2013 Edgewall Software
# Copyright (C) 2005-2006 Emmanuel Blot <emmanuel.blot@free.fr>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Include a basic SMTP server, based on L. Smithson
# (lsmithson@open-networks.co.uk) extensible Python SMTP Server
#
# This file does not contain unit tests, but provides a set of
# classes to run SMTP notification tests
#

import base64
import os
import quopri
import re
import socket
import string
import threading
import unittest
from contextlib import closing

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
    start = string.index(address, '<') + 1
    end = string.index(address, '>')
    return address[start:end]


def split_to(address):
    """
    Return 'address' as undressed (host, fulladdress) tuple.
    Handy for use with TO: addresses.
    """
    start = string.index(address, '<') + 1
    sep = string.index(address, '@') + 1
    end = string.index(address, '>')
    return address[sep:end], address[start:end]


#
# This drives the state for a single RFC821 message.
#
class SMTPServerEngine(object):
    """
    Server engine that calls methods on the SMTPServerInterface object
    passed at construction time. It is constructed with a bound socket
    connection to a client. The 'chug' method drives the state,
    returning when the client RFC821 transaction is complete.
    """

    ST_INIT = 0
    ST_HELO = 1
    ST_MAIL = 2
    ST_RCPT = 3
    ST_DATA = 4
    ST_QUIT = 5

    def __init__(self, socket, impl):
        self.impl = impl
        self.socket = socket
        self.state = SMTPServerEngine.ST_INIT

    def chug(self):
        """
        Chug the engine, till QUIT is received from the client. As
        each RFC821 message is received, calls are made on the
        SMTPServerInterface methods on the object passed at
        construction time.
        """
        self.socket.send("220 Welcome to Trac notification test server\r\n")
        while 1:
            data = ''
            complete_line = 0
            # Make sure an entire line is received before handing off
            # to the state engine. Thanks to John Hall for pointing
            # this out.
            while not complete_line:
                try:
                    lump = self.socket.recv(1024)
                    if lump:
                        data += lump
                        if len(data) >= 2 and data[-2:] == '\r\n':
                            complete_line = 1
                            if self.state != SMTPServerEngine.ST_DATA:
                                rsp, keep = self.do_command(data)
                            else:
                                rsp = self.do_data(data)
                                if rsp is None:
                                    continue
                            self.socket.send(rsp + "\r\n")
                            if keep == 0:
                                self.socket.close()
                                return
                    else:
                        # EOF
                        return
                except socket.error:
                    return

    def do_command(self, data):
        """Process a single SMTP Command"""
        cmd = data[0:4]
        cmd = string.upper(cmd)
        keep = 1
        rv = None
        if cmd == "HELO":
            self.state = SMTPServerEngine.ST_HELO
            rv = self.impl.helo(data[5:])
        elif cmd == "RSET":
            rv = self.impl.reset(data[5:])
            self.data_accum = ""
            self.state = SMTPServerEngine.ST_INIT
        elif cmd == "NOOP":
            pass
        elif cmd == "QUIT":
            rv = self.impl.quit(data[5:])
            keep = 0
        elif cmd == "MAIL":
            if self.state != SMTPServerEngine.ST_HELO:
                return "503 Bad command sequence", 1
            self.state = SMTPServerEngine.ST_MAIL
            rv = self.impl.mail_from(data[5:])
        elif cmd == "RCPT":
            if (self.state != SMTPServerEngine.ST_MAIL) and \
               (self.state != SMTPServerEngine.ST_RCPT):
                return "503 Bad command sequence", 1
            self.state = SMTPServerEngine.ST_RCPT
            rv = self.impl.rcpt_to(data[5:])
        elif cmd == "DATA":
            if self.state != SMTPServerEngine.ST_RCPT:
                return "503 Bad command sequence", 1
            self.state = SMTPServerEngine.ST_DATA
            self.data_accum = ""
            return "354 OK, Enter data, terminated with a \\r\\n.\\r\\n", 1
        else:
            return "505 Eh? WTF was that?", 1

        if rv:
            return rv, keep
        else:
            return "250 OK", keep

    def do_data(self, data):
        """
        Process SMTP Data. Accumulates client DATA until the
        terminator is found.
        """
        self.data_accum = self.data_accum + data
        if len(self.data_accum) > 4 and self.data_accum[-5:] == '\r\n.\r\n':
            self.data_accum = self.data_accum[:-5]
            rv = self.impl.data(self.data_accum)
            self.state = SMTPServerEngine.ST_HELO
            if rv:
                return rv
            else:
                return "250 OK - Data and terminator. found"
        else:
            return None


class SMTPServer(object):
    """
    A single threaded SMTP Server connection manager. Listens for
    incoming SMTP connections on a given port. For each connection,
    the SMTPServerEngine is chugged, passing the given instance of
    SMTPServerInterface.
    """

    def __init__(self, host, port):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((host, port))
        self._socket_service = None

    def serve(self, impl):
        while self._resume:
            try:
                nsd = self._socket.accept()
            except socket.error:
                return
            self._socket_service = nsd[0]
            engine = SMTPServerEngine(self._socket_service, impl)
            engine.chug()
            self._socket_service = None

    def start(self):
        self._socket.listen(1)
        self._resume = True

    def stop(self):
        self._resume = False

    def terminate(self):
        if self._socket_service:
            # force the blocking socket to stop waiting for data
            try:
                #self._socket_service.shutdown(2)
                self._socket_service.close()
            except AttributeError:
                # the SMTP server may also discard the socket
                pass
            self._socket_service = None
        if self._socket:
            #self._socket.shutdown(2)
            self._socket.close()
            self._socket = None


class SMTPServerStore(SMTPServerInterface):
    """
    Simple store for SMTP data
    """

    def __init__(self):
        self.reset(None)

    def helo(self, args):
        self.reset(None)

    def mail_from(self, args):
        if args.lower().startswith('from:'):
            self.sender = strip_address(args[5:].replace('\r\n', '').strip())

    def rcpt_to(self, args):
        if args.lower().startswith('to:'):
            rcpt = args[3:].replace('\r\n', '').strip()
            self.recipients.append(strip_address(rcpt))

    def data(self, args):
        self.message = args

    def quit(self, args):
        pass

    def reset(self, args):
        self.sender = None
        self.recipients = []
        self.message = None


class SMTPThreadedServer(threading.Thread):
    """
    Run a SMTP server for a single connection, within a dedicated thread
    """

    def __init__(self, port):
        self.host = '127.0.0.1'
        self.port = port
        self.server = SMTPServer(self.host, port)
        self.store = SMTPServerStore()
        threading.Thread.__init__(self)

    def run(self):
        # run from within the SMTP server thread
        self.server.serve(impl=self.store)

    def start(self):
        # run from the main thread
        self.server.start()
        threading.Thread.start(self)

    def stop(self):
        # run from the main thread
        self.server.stop()
        # send a message to make the SMTP server quit gracefully
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            try:
                s.connect(('127.0.0.1', self.port))
                s.send("QUIT\r\n")
            except socket.error:
                pass
        # wait for the SMTP server to complete (for up to 2 secs)
        self.join(2.0)
        # clean up the SMTP server (and force quit if needed)
        self.server.terminate()

    def get_sender(self):
        return self.store.sender

    def get_recipients(self):
        return self.store.recipients

    def get_message(self):
        return self.store.message

    def cleanup(self):
        self.store.reset(None)


def decode_header(header):
    """ Decode a MIME-encoded header value """
    mo = header_re.match(header)
    # header does not seem to be MIME-encoded
    if not mo:
        return header
    # attempts to decode the header,
    # following the specified MIME encoding and charset
    try:
        encoding = mo.group('code').lower()
        if encoding == 'q':
            val = quopri.decodestring(mo.group('value'), header=True)
        elif encoding == 'b':
            val = base64.decodestring(mo.group('value'))
        else:
            raise AssertionError("unsupported encoding: %s" % encoding)
        header = unicode(val, mo.group('charset'))
    except Exception as e:
        raise AssertionError(e)
    return header


def parse_smtp_message(msg):
    """ Split a SMTP message into its headers and body.
        Returns a (headers, body) tuple
        We do not use the email/MIME Python facilities here
        as they may accept invalid RFC822 data, or data we do not
        want to support nor generate """
    headers = {}
    lh = None
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
                    val = decode_header(line.strip(' \t'))
                    # appends the current line to the previous one
                    if not isinstance(headers[lh], tuple):
                        headers[lh] += val
                    else:
                        headers[lh][-1] = headers[lh][-1] + val
                else:
                    # splits header name from value
                    (h, v) = line.split(':', 1)
                    val = decode_header(v.strip())
                    if h in headers:
                        if isinstance(headers[h], tuple):
                            headers[h] += val
                        else:
                            headers[h] = (headers[h], val)
                    else:
                        headers[h] = val
                    # stores the last header (for multi-line headers)
                    lh = h
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

    def setUp(self):
        self.env = EnvironmentStub()

    def test_smtp_server_not_found_raises(self):
        sender = SmtpEmailSender(self.env)
        self.env.config.set('notification', 'smtp_server', 'localhost')
        self.env.config.set('notification', 'smtp_port', '65536')
        self.assertRaises(ConfigurationError, sender.send,
                          'admin@domain.com', ['foo@domain.com'], "")


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(SendmailEmailSenderTestCase))
    suite.addTest(unittest.makeSuite(SmtpEmailSenderTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
