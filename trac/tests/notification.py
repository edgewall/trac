# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2006 Edgewall Software
# Copyright (C) 2005-2006 Emmanuel Blot <emmanuel.blot@free.fr>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Include a basic SMTP server, based on L. Smithson 
# (lsmithson@open-networks.co.uk) extensible Python SMTP Server
#

from trac.config import Configuration
from trac.core import TracError
from trac.ticket.model import Ticket
from trac.ticket.notification import TicketNotifyEmail
from trac.test import EnvironmentStub

import socket
import string
import threading
import unittest
import re
import base64
import quopri

smtp_test_port = 8225
LF = '\n'
CR = '\r'
email_re = re.compile(r"([\w\d_\.\-])+\@(([\w\d\-])+\.)+([\w\d]{2,4})+")
notifysuite = None


class SMTPServerInterface:
    """
    A base class for the imlementation of an application specific SMTP
    Server. Applications should subclass this and overide these
    methods, which by default do nothing.

    A method is defined for each RFC821 command. For each of these
    methods, 'args' is the complete command received from the
    client. The 'data' method is called after all of the client DATA
    is received.

    If a method returns 'None', then a '250 OK'message is
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
    return (address[sep:end], address[start:end],)


#
# This drives the state for a single RFC821 message.
#
class SMTPServerEngine:
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
        self.impl = impl;
        self.socket = socket;
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
            completeLine = 0
            # Make sure an entire line is received before handing off
            # to the state engine. Thanks to John Hall for pointing
            # this out.
            while not completeLine:
                lump = self.socket.recv(1024);
                if len(lump):
                    data += lump
                    if (len(data) >= 2) and data[-2:] == '\r\n':
                        completeLine = 1
                        if self.state != SMTPServerEngine.ST_DATA:
                            rsp, keep = self.do_command(data)
                        else:
                            rsp = self.do_data(data)
                            if rsp == None:
                                continue
                        self.socket.send(rsp + "\r\n")
                        if keep == 0:
                            self.socket.close()
                            return
                else:
                    # EOF
                    return
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
                return ("503 Bad command sequence", 1)
            self.state = SMTPServerEngine.ST_MAIL
            rv = self.impl.mail_from(data[5:])
        elif cmd == "RCPT":
            if (self.state != SMTPServerEngine.ST_MAIL) and \
               (self.state != SMTPServerEngine.ST_RCPT):
                return ("503 Bad command sequence", 1)
            self.state = SMTPServerEngine.ST_RCPT
            rv = self.impl.rcpt_to(data[5:])
        elif cmd == "DATA":
            if self.state != SMTPServerEngine.ST_RCPT:
                return ("503 Bad command sequence", 1)
            self.state = SMTPServerEngine.ST_DATA
            self.data_accum = ""
            return ("354 OK, Enter data, terminated with a \\r\\n.\\r\\n", 1)
        else:
            return ("505 Eh? WTF was that?", 1)

        if rv:
            return (rv, keep)
        else:
            return("250 OK", keep)

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


class SMTPServer:
    """
    A single threaded SMTP Server connection manager. Listens for
    incoming SMTP connections on a given port. For each connection,
    the SMTPServerEngine is chugged, passing the given instance of
    SMTPServerInterface. 
    """
    
    def __init__(self, port):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(("", port))

    def serve(self, impl):
        while ( self._resume ):
            nsd = self._socket.accept()
            engine = SMTPServerEngine(nsd[0], impl)
            engine.chug()

    def start(self):
        self._socket.listen(1)
        self._resume = True        
        
    def stop(self):
        self._resume = False
        
    def terminate(self):
        self._socket.close()


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
            self.sender = strip_address(args[5:].replace('\r\n','').strip())
        
    def rcpt_to(self, args):
        if args.lower().startswith('to:'):
            rcpt = args[3:].replace('\r\n','').strip()
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
    Run a SMTP server for a single connection, within a dediceted thread
    """

    def __init__(self, port):
        self.port = port
        self.server = SMTPServer(port)
        self.store  = SMTPServerStore()
        threading.Thread.__init__(self)
      
    def run(self):
        self.server.serve(impl = self.store)

    def start(self):
        self.server.start()
        threading.Thread.start(self)
        
    def stop(self):
        self.server.stop()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(('localhost', self.port))
        r = s.send("QUIT\r\n");
        self.join()
        self.server.terminate()

    def get_sender(self):
        return self.store.sender

    def get_recipients(self):
        return self.store.recipients

    def get_message(self):
        return self.store.message


#
# Tests start here
#

def smtp_address(fulladdr):
    mo = email_re.search(fulladdr)
    if mo:
        return mo.group(0)
    if start >= 0:
        return fulladdr[start+1:-1]
    return fulladdr

class NotificationTestCase(unittest.TestCase):

    header_re = re.compile(r'^=\?(?P<charset>[\w\d\-]+)\?(?P<code>[qb])\?(?P<value>.*)\?=$')

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.env.config.set('project',      'name', 'TracTest')
        self.env.config.set('notification', 'smtp_enabled', 'true')
        self.env.config.set('notification', 'always_notify_owner', 'true')
        self.env.config.set('notification', 'always_notify_reporter', 'true')
        self.env.config.set('notification', 'smtp_always_cc', 
                            'joe.user@example.net, joe.bar@example.net')
        self.env.config.set('notification', 'use_public_cc', 'true')
        self.env.config.set('notification', 'smtp_port', "%d" % smtp_test_port)
        self.env.config.set('notification', 'smtp_server','localhost')

    def tearDown(self):
        notifysuite.tear_down()

    def test_recipients(self):
        """ Validate To/Cc recipients """
        ticket = Ticket(self.env)
        ticket['reporter'] = '"Joe User" <joe.user@example.org>'
        ticket['owner']    = 'joe.user@example.net'
        ticket['cc']       = 'joe.user@example.com, joe.bar@example.org, ' \
                             'joe.bar@example.net'
        ticket['summary'] = 'Foo'
        ticket.insert()
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=True)
        recipients = notifysuite.smtpd.get_recipients()
        # checks there is no duplicate in the recipient list
        rcpts = []
        for r in recipients:
            self.failIf(r in rcpts)
            rcpts.append(r)
        # checks that all cc recipients have been notified
        for r in ticket['cc'].replace(',', ' ').split():
            self.failIf(r not in recipients)
        # checks that owner has been notified
        self.failIf(smtp_address(ticket['owner']) not in recipients)
        # checks that reporter has been notified
        self.failIf(smtp_address(ticket['reporter']) not in recipients)

    def test_structure(self):
        """ Validate basic SMTP message structure """
        ticket = Ticket(self.env)
        ticket['reporter'] = '"Joe User" <joe.user@example.org>'
        ticket['owner']    = 'joe.user@example.net'
        ticket['cc']       = 'joe.user@example.com, joe.bar@example.org, ' \
                             'joe.bar@example.net'
        ticket['summary'] = 'This is a summary'
        ticket.insert()
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=True)
        message = notifysuite.smtpd.get_message()
        (headers, body) = self._parse_message(message)
        # checks for header existence
        self.failIf(not headers)
        # checks for body existance
        self.failIf(not body)
        # checks for expected headers
        self.failIf('Date' not in headers)
        self.failIf('Subject' not in headers)
        self.failIf('Message-ID' not in headers)
        self.failIf('From' not in headers)
        self.failIf('Sender' not in headers)

    def test_date(self):
        """ Validate date format 
            Date format hould be compliant with RFC822,
            we do not support 'military' format """ 
        date_str = r"^((?P<day>\w{3}),\s*)*(?P<dm>\d{2})\s+" \
                   r"(?P<month>\w{3})\s+(?P<year>200\d)\s+" \
                   r"(?P<hour>\d{2}):(?P<min>[0-5][0-9])" \
                   r"(:(?P<sec>[0-5][0-9]))*\s" \
                   r"((?P<tz>\w{2,3})|(?P<offset>[+\-]\d{4}))$"
        date_re = re.compile(date_str)
        # python time module does not detect incorrect time values
        days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
        months = ['Jan','Feb','Mar','Apr','May','Jun', \
                  'Jul','Aug','Sep','Oct','Nov','Dec']
        tz = ['UT','GMT','EST','EDT','CST','CDT','MST','MDT''PST','PDT']
        ticket = Ticket(self.env)
        ticket['reporter'] = '"Joe User" <joe.user@example.org>'
        ticket['summary'] = 'This is a summary'
        ticket.insert()
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=True)
        message = notifysuite.smtpd.get_message()
        (headers, body) = self._parse_message(message)
        self.failIf('Date' not in headers)
        mo = date_re.match(headers['Date'])
        self.failIf(not mo)
        if mo.group('day'):
            self.failIf(mo.group('day') not in days)
        self.failIf(int(mo.group('dm')) not in range(1,32))
        self.failIf(mo.group('month') not in months)
        self.failIf(int(mo.group('hour')) not in range(0,24))
        if mo.group('tz'):
            self.failIf(mo.group('tz') not in tz)

    def test_bcc_privacy(self):
        """ Validate visibility of recipients"""
        def run_bcc_feature(public):
            # CC list should be private
            self.env.config.set('notification', 'use_public_cc',
                                public and 'true' or 'false')
            self.env.config.set('notification', 'smtp_always_bcc', 
                                'joe.foobar@example.net')
            ticket = Ticket(self.env)
            ticket['reporter'] = '"Joe User" <joe.user@example.org>'
            ticket['summary'] = 'This is a summary'
            ticket.insert()
            tn = TicketNotifyEmail(self.env)
            tn.notify(ticket, newticket=True)
            message = notifysuite.smtpd.get_message()
            (headers, body) = self._parse_message(message)
            if public:
                # Msg should have a To list
                self.failIf('To' not in headers)
                # Extract the list of 'To' recipients from the message
                to = [rcpt.strip() for rcpt in headers['To'].split(',')]
            else:
                # Msg should not have a To list
                self.failIf('To' in headers)
                # Extract the list of 'To' recipients from the message
                to = []            
            # Extract the list of 'Cc' recipients from the message
            cc = [rcpt.strip() for rcpt in headers['Cc'].split(',')]
            # Extract the list of the actual SMTP recipients
            rcptlist = notifysuite.smtpd.get_recipients()
            # Build the list of the expected 'Cc' recipients 
            ccrcpt = self.env.config.get('notification', 'smtp_always_cc')
            cclist = [ccr.strip() for ccr in ccrcpt.split(',')]
            for rcpt in cclist:
                # Each recipient of the 'Cc' list should appear in the 'Cc' header
                self.failIf(rcpt not in cc)
                # Check the message has actually been sent to the recipients
                self.failIf(rcpt not in rcptlist)
            # Build the list of the expected 'Bcc' recipients 
            bccrcpt = self.env.config.get('notification', 'smtp_always_bcc')
            bcclist = [bccr.strip() for bccr in bccrcpt.split(',')]
            for rcpt in bcclist:
                # Check none of the 'Bcc' recipients appears in the 'To' header
                self.failIf(rcpt in to)
                # Check the message has actually been sent to the recipients
                self.failIf(rcpt not in rcptlist)
        run_bcc_feature(True)
        run_bcc_feature(False)

    def test_short_login(self):
        """ Validate no qualified addresses """
        def _test_short_login(enabled):
            ticket = Ticket(self.env)
            ticket['reporter'] = 'joeuser'
            ticket['summary'] = 'This is a summary'
            ticket.insert()
            # Be sure that at least one email address is valid, so that we 
            # send a notification even if other addresses are not valid
            self.env.config.set('notification', 'smtp_always_cc', \
                                'joe.bar@example.net')
            if enabled:
                self.env.config.set('notification', 'allow_short_addr', 'true')
            tn = TicketNotifyEmail(self.env)
            tn.notify(ticket, newticket=True)
            message = notifysuite.smtpd.get_message()
            (headers, body) = self._parse_message(message)
            # Msg should not have a 'To' header
            if not enabled:
                self.failIf('To' in headers)
            else:
                tolist = [addr.strip() for addr in headers['To'].split(',')]
            # Msg should have a 'Cc' field
            self.failIf('Cc' not in headers)
            cclist = [addr.strip() for addr in headers['Cc'].split(',')]
            if enabled:
                # Msg should be delivered to the reporter
                self.failIf(ticket['reporter'] not in tolist)
            else:
                # Msg should not be delivered to joeuser
                self.failIf(ticket['reporter'] in cclist)
            # Msg should still be delivered to the always_cc list
            self.failIf(self.env.config.get('notification', 'smtp_always_cc') \
                        not in cclist)
        # Validate with and without the short addr option enabled
        for enable in [False, True]:
            _test_short_login(enable)

    def test_default_domain(self):
        """ Validate support for default domain """
        def _test_default_domain(enabled):
            self.env.config.set('notification', 'always_notify_owner', 'false')
            self.env.config.set('notification', 'always_notify_reporter', 'false')
            self.env.config.set('notification', 'smtp_always_cc', '')
            ticket = Ticket(self.env)
            ticket['cc'] = 'joenodom, joewithdom@example.com'
            ticket['summary'] = 'This is a summary'
            ticket.insert()
            # Be sure that at least one email address is valid, so that we 
            # send a notification even if other addresses are not valid
            self.env.config.set('notification', 'smtp_always_cc', \
                                'joe.bar@example.net')
            if enabled:
                self.env.config.set('notification', 'smtp_default_domain', 'example.org')
            tn = TicketNotifyEmail(self.env)
            tn.notify(ticket, newticket=True)
            message = notifysuite.smtpd.get_message()
            (headers, body) = self._parse_message(message)
            # Msg should always have a 'Cc' field
            self.failIf('Cc' not in headers)
            cclist = [addr.strip() for addr in headers['Cc'].split(',')]
            self.failIf('joewithdom@example.com' not in cclist)
            self.failIf('joe.bar@example.net' not in cclist)
            if not enabled:
                self.failIf(len(cclist) != 2)
                self.failIf('joenodom' in cclist)
            else:
                self.failIf(len(cclist) != 3)
                self.failIf('joenodom@example.org' not in cclist)

        # Validate with and without a default domain
        for enable in [False, True]:
            _test_default_domain(enable)

    def test_email_map(self):
        """ Validate login-to-email map """
        self.env.config.set('notification', 'always_notify_owner', 'false')
        self.env.config.set('notification', 'always_notify_reporter', 'true')
        self.env.config.set('notification', 'smtp_always_cc', 'joe@example.com')
        self.env.known_users = [('joeuser', 'Joe User', 'user-joe@example.com')]
        ticket = Ticket(self.env)
        ticket['reporter'] = 'joeuser'
        ticket['summary'] = 'This is a summary'
        ticket.insert()
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=True)
        message = notifysuite.smtpd.get_message()
        (headers, body) = self._parse_message(message)
        # Msg should always have a 'To' field
        self.failIf('To' not in headers)
        tolist = [addr.strip() for addr in headers['To'].split(',')]
        # 'To' list should have been resolved to the real email address
        self.failIf('user-joe@example.com' not in tolist)
        self.failIf('joeuser' in tolist)

    def test_multiline_header(self):
        """ Validate encoded headers split into multiple lines """
        self.env.config.set('notification','mime_encoding', 'qp')
        ticket = Ticket(self.env)
        ticket['reporter'] = 'joe.user@example.org'
        # Forces non-ascii characters
        summary = u'A_very %s súmmäry' % u' '.join(['long'] * 20)
        ticket['summary'] = summary
        ticket.insert()
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=True)
        message = notifysuite.smtpd.get_message()
        (headers, body) = self._parse_message(message)
        # Discards the project name & ticket number
        subject = headers['Subject']
        summary = subject[subject.find(':')+2:].encode('utf-8')
        # Hack: we need to keep space chars in long headers
        tksummary = ticket['summary'].replace(' ', '_').encode('utf-8')
        self.failIf(summary != tksummary)

    def test_mimebody_b64(self):
        """ Validate MIME Base64/utf-8 encoding """
        self.env.config.set('notification','mime_encoding', 'base64')
        ticket = Ticket(self.env)
        ticket['reporter'] = 'joe.user@example.org'
        ticket['summary'] = u'This is a súmmäry'
        ticket.insert()
        self._validate_mimebody((base64, 'base64', 'utf-8'), \
                                ticket, True)

    def test_mimebody_qp(self):
        """ Validate MIME QP/utf-8 encoding """
        self.env.config.set('notification','mime_encoding', 'qp')
        ticket = Ticket(self.env)
        ticket['reporter'] = 'joe.user@example.org'
        ticket['summary'] = u'This is a súmmäry'
        ticket.insert()
        self._validate_mimebody((quopri, 'quoted-printable', 'utf-8'), \
                                ticket, True)

    def test_mimebody_none(self):
        """ Validate MIME None/ascii encoding """
        self.env.config.set('notification','mime_encoding', 'none')
        ticket = Ticket(self.env)
        ticket['reporter'] = 'joe.user@example.org'
        ticket['summary'] = u'This is a summary'
        ticket.insert()
        self._validate_mimebody((None, '7bit', 'ascii'), \
                                ticket, True)

    def _validate_mimebody(self, mime, ticket, newtk):
        """ Validate the body of a ticket notification message """
        (mime_decoder, mime_name, mime_charset) = mime
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=newtk)
        message = notifysuite.smtpd.get_message()
        (headers, body) = self._parse_message(message)
        self.failIf('MIME-Version' not in headers)
        self.failIf('Content-Type' not in headers)
        self.failIf('Content-Transfer-Encoding' not in headers)
        self.failIf(not re.compile(r"1.\d").match(headers['MIME-Version']))
        type_re = re.compile(r'^text/plain;\scharset="([\w\-\d]+)"$')
        charset = type_re.match(headers['Content-Type'])
        self.failIf(not charset)
        charset = charset.group(1)
        self.assertEqual(charset, mime_charset)
        self.assertEqual(headers['Content-Transfer-Encoding'], mime_name)
        # attempts to decode the body, following the specified MIME endoding 
        # and charset
        try:
            if mime_decoder:
                body = mime_decoder.decodestring(body)
            body = unicode(body, charset)
        except Exception, e:
            raise AssertionError, e
        # now processes each line of the body
        bodylines = body.splitlines()
        # checks the width of each line
        for line in bodylines:
            self.failIf(len(line) > 76)
        # body starts with a summary line, prefixed with the ticket number
        # #<n>: summary
        (tknum, summary) = bodylines[0].split(' ', 1)
        self.assertEqual(tknum[0], '#')
        try:
            tkid = int(tknum[1:-1])
            self.assertEqual(tkid, 1)
        except ValueError:
            raise AssertionError, "invalid ticket number"
        self.assertEqual(tknum[-1], ':')
        self.assertEqual(summary, ticket['summary'])
        # next step: checks the banner appears right after the summary
        banner_delim_re = re.compile(r'^\-+\+\-+$')
        self.failIf(not banner_delim_re.match(bodylines[1]))
        banner = True
        footer = None
        props = {}
        for line in bodylines[2:]:
            # detect end of banner
            if banner_delim_re.match(line):
                banner = False
                continue
            if banner:
                # parse banner and fill in a property dict
                properties = line.split('|')
                self.assertEqual(len(properties), 2)
                for prop in properties:
                    if prop.strip() == '':
                        continue
                    (k, v) = prop.split(':')
                    props[k.strip().lower()] = v.strip()
            # detect footer marker (weak detection)
            if not footer:
                if line.strip() == '--':
                    footer = 0
                    continue
            # check footer
            if footer != None:
                footer += 1
                # invalid footer detection
                self.failIf(footer > 3)
                # check ticket link
                if line[:11] == 'Ticket URL:':
                    self.assertEqual(line[12:].strip(), \
                                     "<%s>" % ticket['link'].strip())
                # note project title / URL are not validated yet

        # ticket properties which are not expected in the banner
        xlist = ['summary', 'description', 'link', 'comment']
        # check banner content (field exists, msg value matches ticket value)
        for p in [prop for prop in ticket.values.keys() if prop not in xlist]:
            self.failIf(not props.has_key(p))
            self.failIf(props[p] != ticket[p])

    def _decode_header(self, header):
        """ Decode a MIME-encoded header value """
        mo = NotificationTestCase.header_re.match(header)
        # header does not seem to be MIME-encoded
        if not mo:
            return header
        # attempts to decode the hedear, 
        # following the specified MIME endoding and charset
        decoders = { 'q' : quopri, 'b' : base64 }
        try:
            decoder = decoders[mo.group('code').lower()]
            val = decoder.decodestring(mo.group('value'))
            header = unicode(val, mo.group('charset'))
        except Exception, e:
            raise AssertionError, e
        return header

    def _parse_message(self, msg):
        """ Split a SMTP message into its headers and body.
            Returns a (headers, body) tuple 
            We do not use the email/MIME Python facilities here
            as they may accept invalid RFC822 data, or data we do not
            want to support nor generate """
        headers = {}
        lh = None
        body = None
        for line in msg.splitlines(True):
            if body != None:
                # append current line to the body
                if line[-2] == CR:
                    body += "%s\n" % line[0:-2]
                else:
                    body += line
            else:
                if line[-2] != CR:
                    # RFC822 requires CRLF at end of field line
                    raise AssertionError, "header field misses CRLF: %s (%d)" \
                                          % (line, int(line[-2]))
                # discards CR
                line = line[0:-2]
                if line.strip() == '':
                    # end of headers, body starts
                    body = '' 
                else:
                    val = None
                    if line[0] in ' \t':
                        # continution of the previous line
                        if not lh:
                            # unexpected multiline
                            raise AssertionError, \
                                 "unexpected folded line: %s" % line
                        val = self._decode_header(line.strip(' \t'))
                        # appends the current line to the previous one
                        if not isinstance(headers[lh], tuple):
                            headers[lh] += val
                        else:
                            headers[lh][-1] = headers[lh][-1] + val
                    else:
                        # splits header name from value
                        (h,v) = line.split(':',1)
                        val = self._decode_header(v.strip())
                        if headers.has_key(h):
                            if isinstance(headers[h], tuple):
                                headers[h] += val
                            else:
                                headers[h] = (headers[h], val)
                        else:
                            headers[h] = val
                        # stores the last header (for multilines headers)
                        lh = h
        # returns the headers and the message body
        return (headers, body)

class NotificationTestSuite(unittest.TestSuite):
    """ Thin test suite wrapper to start and stop the SMTP test server"""

    def __init__(self):
        unittest.TestSuite.__init__(self)
        self.smtpd = SMTPThreadedServer(smtp_test_port)
        self.smtpd.start()
        self.addTest(unittest.makeSuite(NotificationTestCase, 'test'))
        self.remaining = self.countTestCases()

    def tear_down(self):
        self.remaining = self.remaining-1
        if self.remaining > 0:
            return
        self.smtpd.stop()

def suite():
    global notifysuite
    if not notifysuite:
        notifysuite = NotificationTestSuite()
    return notifysuite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())

