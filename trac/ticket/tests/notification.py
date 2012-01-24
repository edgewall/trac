# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
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

from trac.util.datefmt import utc
from trac.ticket.model import Ticket
from trac.ticket.notification import TicketNotifyEmail
from trac.test import EnvironmentStub, Mock, MockPerm
from trac.tests.notification import SMTPThreadedServer, parse_smtp_message, \
                                    smtp_address
                                    
import base64
from datetime import datetime
import os
import quopri
import re
import unittest

SMTP_TEST_PORT = 7000 + os.getpid() % 1000
MAXBODYWIDTH = 76
notifysuite = None


class NotificationTestCase(unittest.TestCase):
    """Notification test cases that send email over SMTP"""
    
    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.env.config.set('project', 'name', 'TracTest')
        self.env.config.set('notification', 'smtp_enabled', 'true')
        self.env.config.set('notification', 'always_notify_owner', 'true')
        self.env.config.set('notification', 'always_notify_reporter', 'true')
        self.env.config.set('notification', 'smtp_always_cc', 
                            'joe.user@example.net, joe.bar@example.net')
        self.env.config.set('notification', 'use_public_cc', 'true')
        self.env.config.set('notification', 'smtp_port', str(SMTP_TEST_PORT))
        self.env.config.set('notification', 'smtp_server','localhost')
        self.req = Mock(href=self.env.href, abs_href=self.env.abs_href, tz=utc,
                        perm=MockPerm())

    def tearDown(self):
        """Signal the notification test suite that a test is over"""
        notifysuite.tear_down()
        self.env.reset_db()

    def test_recipients(self):
        """To/Cc recipients"""
        ticket = Ticket(self.env)
        ticket['reporter'] = '"Joe User" < joe.user@example.org >'
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
        cc_list = self.env.config.get('notification', 'smtp_always_cc')
        cc_list = "%s, %s" % (cc_list, ticket['cc'])
        for r in cc_list.replace(',', ' ').split():
            self.failIf(r not in recipients)
        # checks that owner has been notified
        self.failIf(smtp_address(ticket['owner']) not in recipients)
        # checks that reporter has been notified
        self.failIf(smtp_address(ticket['reporter']) not in recipients)

    def test_no_recipient(self):
        """No recipient case"""
        self.env.config.set('notification', 'smtp_always_cc', '')
        ticket = Ticket(self.env)
        ticket['reporter'] = 'anonymous'
        ticket['summary'] = 'Foo'
        ticket.insert()
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=True)
        sender = notifysuite.smtpd.get_sender()
        recipients = notifysuite.smtpd.get_recipients()
        message = notifysuite.smtpd.get_message()
        # checks that no message has been sent
        self.failIf(recipients)
        self.failIf(sender)
        self.failIf(message)

    def test_cc_only(self):
        """Notification w/o explicit recipients but Cc: (#3101)"""
        ticket = Ticket(self.env)
        ticket['summary'] = 'Foo'
        ticket.insert()
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=True)
        recipients = notifysuite.smtpd.get_recipients()
        # checks that all cc recipients have been notified
        cc_list = self.env.config.get('notification', 'smtp_always_cc')
        for r in cc_list.replace(',', ' ').split():
            self.failIf(r not in recipients)

    def test_structure(self):
        """Basic SMTP message structure (headers, body)"""
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
        (headers, body) = parse_smtp_message(message)
        # checks for header existence
        self.failIf(not headers)
        # checks for body existance
        self.failIf(not body)
        # checks for expected headers
        self.failIf('Date' not in headers)
        self.failIf('Subject' not in headers)
        self.failIf('Message-ID' not in headers)
        self.failIf('From' not in headers)

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
        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', \
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        tz = ['UT', 'GMT', 'EST', 'EDT', 'CST', 'CDT', 'MST', 'MDT',
              'PST', 'PDT']
        ticket = Ticket(self.env)
        ticket['reporter'] = '"Joe User" <joe.user@example.org>'
        ticket['summary'] = 'This is a summary'
        ticket.insert()
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=True)
        message = notifysuite.smtpd.get_message()
        (headers, body) = parse_smtp_message(message)
        self.failIf('Date' not in headers)
        mo = date_re.match(headers['Date'])
        self.failIf(not mo)
        if mo.group('day'):
            self.failIf(mo.group('day') not in days)
        self.failIf(int(mo.group('dm')) not in range(1, 32))
        self.failIf(mo.group('month') not in months)
        self.failIf(int(mo.group('hour')) not in range(0, 24))
        if mo.group('tz'):
            self.failIf(mo.group('tz') not in tz)

    def test_bcc_privacy(self):
        """Visibility of recipients"""
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
            (headers, body) = parse_smtp_message(message)
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
                # Each recipient of the 'Cc' list should appear 
                # in the 'Cc' header
                self.failIf(rcpt not in cc)
                # Check the message has actually been sent to the recipients
                self.failIf(rcpt not in rcptlist)
            # Build the list of the expected 'Bcc' recipients 
            bccrcpt = self.env.config.get('notification', 'smtp_always_bcc')
            bcclist = [bccr.strip() for bccr in bccrcpt.split(',')]
            for rcpt in bcclist:
                # Check none of the 'Bcc' recipients appears 
                # in the 'To' header
                self.failIf(rcpt in to)
                # Check the message has actually been sent to the recipients
                self.failIf(rcpt not in rcptlist)
        run_bcc_feature(True)
        run_bcc_feature(False)

    def test_short_login(self):
        """Email addresses without a FQDN"""
        def _test_short_login(enabled):
            ticket = Ticket(self.env)
            ticket['reporter'] = 'joeuser'
            ticket['summary'] = 'This is a summary'
            ticket.insert()
            # Be sure that at least one email address is valid, so that we 
            # send a notification even if other addresses are not valid
            self.env.config.set('notification', 'smtp_always_cc',
                                'joe.bar@example.net')
            if enabled:
                self.env.config.set('notification', 'use_short_addr', 'true')
            tn = TicketNotifyEmail(self.env)
            tn.notify(ticket, newticket=True)
            message = notifysuite.smtpd.get_message()
            (headers, body) = parse_smtp_message(message)
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
            self.failIf(self.env.config.get('notification',
                        'smtp_always_cc') not in cclist)
        # Validate with and without the short addr option enabled
        for enable in [False, True]:
            _test_short_login(enable)

    def test_default_domain(self):
        """Default domain name"""
        def _test_default_domain(enabled):
            self.env.config.set('notification', 'always_notify_owner',
                                'false')
            self.env.config.set('notification', 'always_notify_reporter',
                                'false')
            self.env.config.set('notification', 'smtp_always_cc', '')
            ticket = Ticket(self.env)
            ticket['cc'] = 'joenodom, joewithdom@example.com'
            ticket['summary'] = 'This is a summary'
            ticket.insert()
            # Be sure that at least one email address is valid, so that we 
            # send a notification even if other addresses are not valid
            self.env.config.set('notification', 'smtp_always_cc',
                                'joe.bar@example.net')
            if enabled:
                self.env.config.set('notification', 'smtp_default_domain',
                                    'example.org')
            tn = TicketNotifyEmail(self.env)
            tn.notify(ticket, newticket=True)
            message = notifysuite.smtpd.get_message()
            (headers, body) = parse_smtp_message(message)
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
        """Login-to-email mapping"""
        self.env.config.set('notification', 'always_notify_owner', 'false')
        self.env.config.set('notification', 'always_notify_reporter', 'true')
        self.env.config.set('notification', 'smtp_always_cc',
                            'joe@example.com')
        self.env.known_users = [('joeuser', 'Joe User',
                                'user-joe@example.com')]
        ticket = Ticket(self.env)
        ticket['reporter'] = 'joeuser'
        ticket['summary'] = 'This is a summary'
        ticket.insert()
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=True)
        message = notifysuite.smtpd.get_message()
        (headers, body) = parse_smtp_message(message)
        # Msg should always have a 'To' field
        self.failIf('To' not in headers)
        tolist = [addr.strip() for addr in headers['To'].split(',')]
        # 'To' list should have been resolved to the real email address
        self.failIf('user-joe@example.com' not in tolist)
        self.failIf('joeuser' in tolist)
        
    def test_ignore_domains(self):
        """Non-SMTP domain exclusion"""
        self.env.config.set('notification', 'ignore_domains',
                            'example.com, example.org')
        self.env.known_users = \
            [('kerberos@example.com', 'No Email', ''), 
             ('kerberos@example.org', 'With Email', 'kerb@example.net')]
        ticket = Ticket(self.env)
        ticket['reporter'] = 'kerberos@example.com'
        ticket['owner'] = 'kerberos@example.org'
        ticket['summary'] = 'This is a summary'
        ticket.insert()
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=True)
        message = notifysuite.smtpd.get_message()
        (headers, body) = parse_smtp_message(message)
        # Msg should always have a 'To' field
        self.failIf('To' not in headers)
        tolist = [addr.strip() for addr in headers['To'].split(',')]
        # 'To' list should not contain addresses with non-SMTP domains
        self.failIf('kerberos@example.com' in tolist)
        self.failIf('kerberos@example.org' in tolist)
        # 'To' list should have been resolved to the actual email address
        self.failIf('kerb@example.net' not in tolist)
        self.failIf(len(tolist) != 1)
        
    def test_admit_domains(self):
        """SMTP domain inclusion"""
        self.env.config.set('notification', 'admit_domains',
                            'localdomain, server')
        ticket = Ticket(self.env)
        ticket['reporter'] = 'joeuser@example.com'
        ticket['summary'] = 'This is a summary'
        ticket['cc'] = 'joe.user@localdomain, joe.user@unknown, ' \
                       'joe.user@server'
        ticket.insert()
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=True)
        message = notifysuite.smtpd.get_message()
        (headers, body) = parse_smtp_message(message)
        # Msg should always have a 'To' field
        self.failIf('Cc' not in headers)
        cclist = [addr.strip() for addr in headers['Cc'].split(',')]
        # 'Cc' list should contain addresses with SMTP included domains
        self.failIf('joe.user@localdomain' not in cclist)
        self.failIf('joe.user@server' not in cclist)
        # 'Cc' list should not contain non-FQDN domains
        self.failIf('joe.user@unknown' in cclist)
        self.failIf(len(cclist) != 2+2)

    def test_multiline_header(self):
        """Encoded headers split into multiple lines"""
        self.env.config.set('notification', 'mime_encoding', 'qp')
        ticket = Ticket(self.env)
        ticket['reporter'] = 'joe.user@example.org'
        # Forces non-ascii characters
        ticket['summary'] = u'A_very %s súmmäry' % u' '.join(['long'] * 20)
        ticket.insert()
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=True)
        message = notifysuite.smtpd.get_message()
        (headers, body) = parse_smtp_message(message)
        # Discards the project name & ticket number
        subject = headers['Subject']
        summary = subject[subject.find(':')+2:]
        self.failIf(ticket['summary'] != summary)

    def test_mimebody_b64(self):
        """MIME Base64/utf-8 encoding"""
        self.env.config.set('notification', 'mime_encoding', 'base64')
        ticket = Ticket(self.env)
        ticket['reporter'] = 'joe.user@example.org'
        ticket['summary'] = u'This is a long enough summary to cause Trac ' \
                            u'to generate a multi-line (2 lines) súmmäry'
        ticket.insert()
        self._validate_mimebody((base64, 'base64', 'utf-8'), \
                                ticket, True)

    def test_mimebody_qp(self):
        """MIME QP/utf-8 encoding"""
        self.env.config.set('notification', 'mime_encoding', 'qp')
        ticket = Ticket(self.env)
        ticket['reporter'] = 'joe.user@example.org'
        ticket['summary'] = u'This is a long enough summary to cause Trac ' \
                            u'to generate a multi-line (2 lines) súmmäry'
        ticket.insert()
        self._validate_mimebody((quopri, 'quoted-printable', 'utf-8'),
                                ticket, True)

    def test_mimebody_none_7bit(self):
        """MIME None encoding resulting in 7bit"""
        self.env.config.set('notification', 'mime_encoding', 'none')
        ticket = Ticket(self.env)
        ticket['reporter'] = 'joe.user'
        ticket['summary'] = u'This is a summary'
        ticket.insert()
        self._validate_mimebody((None, '7bit', 'utf-8'), \
                                ticket, True)

    def test_mimebody_none_8bit(self):
        """MIME None encoding resulting in 8bit"""
        self.env.config.set('notification', 'mime_encoding', 'none')
        ticket = Ticket(self.env)
        ticket['reporter'] = 'joe.user'
        ticket['summary'] = u'This is a summary for Jöe Usèr'
        ticket.insert()
        self._validate_mimebody((None, '8bit', 'utf-8'), \
                                ticket, True)

    def test_md5_digest(self):
        """MD5 digest w/ non-ASCII recipient address (#3491)"""
        self.env.config.set('notification', 'always_notify_owner', 'false')
        self.env.config.set('notification', 'always_notify_reporter', 'true')
        self.env.config.set('notification', 'smtp_always_cc', '')
        ticket = Ticket(self.env)
        ticket['reporter'] = u'"Jöe Usèr" <joe.user@example.org>'
        ticket['summary'] = u'This is a summary'
        ticket.insert()
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=True)
        message = notifysuite.smtpd.get_message()
        (headers, body) = parse_smtp_message(message)

    def test_updater(self):
        """No-self-notification option"""
        def _test_updater(disable):
            if disable:
                self.env.config.set('notification', 'always_notify_updater',
                                    'false')
            ticket = Ticket(self.env)
            ticket['reporter'] = 'joe.user@example.org'
            ticket['summary'] = u'This is a súmmäry'
            ticket['cc'] = 'joe.bar@example.com'
            ticket.insert()
            ticket['component'] = 'dummy'
            now = datetime.now(utc)
            ticket.save_changes('joe.bar2@example.com', 'This is a change',
                                when=now)
            tn = TicketNotifyEmail(self.env)
            tn.notify(ticket, newticket=False, modtime=now)
            message = notifysuite.smtpd.get_message()
            (headers, body) = parse_smtp_message(message)
            # checks for header existence
            self.failIf(not headers)
            # checks for updater in the 'To' recipient list
            self.failIf('To' not in headers)
            tolist = [addr.strip() for addr in headers['To'].split(',')]
            if disable:
                self.failIf('joe.bar2@example.com' in tolist)
            else:
                self.failIf('joe.bar2@example.com' not in tolist)

        # Validate with and without a default domain
        for disable in [False, True]:
            _test_updater(disable)

    def test_updater_only(self):
        """Notification w/ updater, w/o any other recipient (#4188)"""
        self.env.config.set('notification', 'always_notify_owner', 'false')
        self.env.config.set('notification', 'always_notify_reporter', 'false')
        self.env.config.set('notification', 'always_notify_updater', 'true')
        self.env.config.set('notification', 'smtp_always_cc', '')
        self.env.config.set('notification', 'smtp_always_bcc', '')
        self.env.config.set('notification', 'use_public_cc', 'false')
        self.env.config.set('notification', 'use_short_addr', 'false')
        self.env.config.set('notification', 'smtp_replyto', 
                            'joeuser@example.net')
        ticket = Ticket(self.env)
        ticket['summary'] = 'Foo'
        ticket.insert()
        ticket['summary'] = 'Bar'
        ticket['component'] = 'New value'
        ticket.save_changes('joe@example.com', 'this is my comment')        
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=True)
        recipients = notifysuite.smtpd.get_recipients()
        self.failIf(recipients is None)
        self.failIf(len(recipients) != 1)
        self.failIf(recipients[0] != 'joe@example.com')

    def test_updater_is_reporter(self):
        """Notification to reporter w/ updater option disabled (#3780)"""
        self.env.config.set('notification', 'always_notify_owner', 'false')
        self.env.config.set('notification', 'always_notify_reporter', 'true')
        self.env.config.set('notification', 'always_notify_updater', 'false')
        self.env.config.set('notification', 'smtp_always_cc', '')
        self.env.config.set('notification', 'smtp_always_bcc', '')
        self.env.config.set('notification', 'use_public_cc', 'false')
        self.env.config.set('notification', 'use_short_addr', 'false')
        self.env.config.set('notification', 'smtp_replyto', 
                            'joeuser@example.net')
        ticket = Ticket(self.env)
        ticket['summary'] = 'Foo'
        ticket['reporter'] = u'joe@example.org'
        ticket.insert()
        ticket['summary'] = 'Bar'
        ticket['component'] = 'New value'
        ticket.save_changes('joe@example.org', 'this is my comment')        
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=True)
        recipients = notifysuite.smtpd.get_recipients()
        self.failIf(recipients is None)
        self.failIf(len(recipients) != 1)
        self.failIf(recipients[0] != 'joe@example.org')

    def _validate_mimebody(self, mime, ticket, newtk):
        """Body of a ticket notification message"""
        (mime_decoder, mime_name, mime_charset) = mime
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=newtk)
        message = notifysuite.smtpd.get_message()
        (headers, body) = parse_smtp_message(message)
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
        # checks the width of each body line
        for line in body.splitlines():
            self.failIf(len(line) > MAXBODYWIDTH)
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
        # body starts with one of more summary lines, first line is prefixed 
        # with the ticket number such as #<n>: summary        
        # finds the banner after the summary
        banner_delim_re = re.compile(r'^\-+\+\-+$')
        bodyheader = []
        while ( not banner_delim_re.match(bodylines[0]) ):
            bodyheader.append(bodylines.pop(0))
        # summary should be present
        self.failIf(not bodyheader)
        # banner should not be empty
        self.failIf(not bodylines)
        # extracts the ticket ID from the first line
        (tknum, bodyheader[0]) = bodyheader[0].split(' ', 1)
        self.assertEqual(tknum[0], '#')
        try:
            tkid = int(tknum[1:-1])
            self.assertEqual(tkid, 1)
        except ValueError:
            raise AssertionError, "invalid ticket number"
        self.assertEqual(tknum[-1], ':')
        summary = ' '.join(bodyheader)
        self.assertEqual(summary, ticket['summary'])
        # now checks the banner contents
        self.failIf(not banner_delim_re.match(bodylines[0]))
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
                    ticket_link = self.env.abs_href.ticket(ticket.id)
                    self.assertEqual(line[12:].strip(), "<%s>" % ticket_link)
                # note project title / URL are not validated yet

        # ticket properties which are not expected in the banner
        xlist = ['summary', 'description', 'comment', 'time', 'changetime']
        # check banner content (field exists, msg value matches ticket value)
        for p in [prop for prop in ticket.values.keys() if prop not in xlist]:
            self.failIf(not props.has_key(p))
            # Email addresses might be obfuscated
            if '@' in ticket[p] and '@' in props[p]:
                self.failIf(props[p].split('@')[0] != ticket[p].split('@')[0])
            else:
                self.failIf(props[p] != ticket[p])

    def test_props_format_ambiwidth_single(self):
        self.env.config.set('notification', 'mime_encoding', 'none')
        self.env.config.set('notification', 'ambiguous_char_width', '')
        ticket = Ticket(self.env)
        ticket['summary'] = u'This is a summary'
        ticket['reporter'] = u'аnonymoиs'
        ticket['status'] = u'new'
        ticket['owner'] = u'somеbody'
        ticket['type'] = u'バグ(dеfеct)'
        ticket['priority'] = u'メジャー(mаjor)'
        ticket['milestone'] = u'マイルストーン1'
        ticket['component'] = u'コンポーネント1'
        ticket['version'] = u'2.0 аlphа'
        ticket['resolution'] = u'fixed'
        ticket['keywords'] = u''
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
        ticket['summary'] = u'This is a summary'
        ticket['reporter'] = u'аnonymoиs'
        ticket['status'] = u'new'
        ticket['owner'] = u'somеbody'
        ticket['type'] = u'バグ(dеfеct)'
        ticket['priority'] = u'メジャー(mаjor)'
        ticket['milestone'] = u'マイルストーン1'
        ticket['component'] = u'コンポーネント1'
        ticket['version'] = u'2.0 аlphа'
        ticket['resolution'] = u'fixed'
        ticket['keywords'] = u''
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
        ticket['summary'] = u'This is a summary'
        ticket['reporter'] = u'joe@foobar.foo.bar.example.org'
        ticket['status'] = u'new'
        ticket['owner'] = u'joe.bar@foobar.foo.bar.example.org'
        ticket['type'] = u'defect'
        ticket['priority'] = u'major'
        ticket['milestone'] = u'milestone1'
        ticket['component'] = u'component1'
        ticket['version'] = u'2.0'
        ticket['resolution'] = u'fixed'
        ticket['keywords'] = u''
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
        ticket['summary'] = u'This is a summary'
        ticket['reporter'] = u'joe@foobar.foo.bar.example.org'
        ticket['status'] = u'new'
        ticket['owner'] = u'joe.bar@foobar.foo.bar.example.org'
        ticket['type'] = u'defect'
        ticket['priority'] = u'major'
        ticket['milestone'] = u'milestone1'
        ticket['component'] = u'component1'
        ticket['version'] = u'2.0'
        ticket['resolution'] = u'fixed'
        ticket['keywords'] = u''
        ticket.insert()
        formatted = """\
  Reporter:                          |      Owner:
  joe@foobar.foo.bar.example.org     |  joe.bar@foobar.foo.bar.example.org
      Type:  defect                  |     Status:  new
  Priority:  major                   |  Milestone:  milestone1
 Component:  component1              |    Version:  2.0
Resolution:  fixed                   |   Keywords:"""
        self._validate_props_format(formatted, ticket)

    def test_props_format_wrap_leftside(self):
        self.env.config.set('notification', 'mime_encoding', 'none')
        ticket = Ticket(self.env)
        ticket['summary'] = u'This is a summary'
        ticket['reporter'] = u'anonymous'
        ticket['status'] = u'new'
        ticket['owner'] = u'somebody'
        ticket['type'] = u'defect'
        ticket['priority'] = u'major'
        ticket['milestone'] = u'milestone1'
        ticket['component'] = u'Lorem ipsum dolor sit amet, consectetur ' \
                              u'adipisicing elit, sed do eiusmod tempor ' \
                              u'incididunt ut labore et dolore magna ' \
                              u'aliqua. Ut enim ad minim veniam, quis ' \
                              u'nostrud exercitation ullamco laboris nisi ' \
                              u'ut aliquip ex ea commodo consequat. Duis ' \
                              u'aute irure dolor in reprehenderit in ' \
                              u'voluptate velit esse cillum dolore eu ' \
                              u'fugiat nulla pariatur. Excepteur sint ' \
                              u'occaecat cupidatat non proident, sunt in ' \
                              u'culpa qui officia deserunt mollit anim id ' \
                              u'est laborum.'
        ticket['version'] = u'2.0'
        ticket['resolution'] = u'fixed'
        ticket['keywords'] = u''
        ticket.insert()
        formatted = """\
  Reporter:  anonymous                           |      Owner:  somebody
      Type:  defect                              |     Status:  new
  Priority:  major                               |  Milestone:  milestone1
 Component:  Lorem ipsum dolor sit amet,         |    Version:  2.0
  consectetur adipisicing elit, sed do eiusmod   |   Keywords:
  tempor incididunt ut labore et dolore magna    |
  aliqua. Ut enim ad minim veniam, quis nostrud  |
  exercitation ullamco laboris nisi ut aliquip   |
  ex ea commodo consequat. Duis aute irure       |
  dolor in reprehenderit in voluptate velit      |
  esse cillum dolore eu fugiat nulla pariatur.   |
  Excepteur sint occaecat cupidatat non          |
  proident, sunt in culpa qui officia deserunt   |
  mollit anim id est laborum.                    |
Resolution:  fixed                               |"""
        self._validate_props_format(formatted, ticket)

    def test_props_format_wrap_leftside_unicode(self):
        self.env.config.set('notification', 'mime_encoding', 'none')
        ticket = Ticket(self.env)
        ticket['summary'] = u'This is a summary'
        ticket['reporter'] = u'anonymous'
        ticket['status'] = u'new'
        ticket['owner'] = u'somebody'
        ticket['type'] = u'defect'
        ticket['priority'] = u'major'
        ticket['milestone'] = u'milestone1'
        ticket['component'] = u'Trac は BSD ライセンスのもとで配' \
                              u'布されています。[1:]このライセ' \
                              u'ンスの全文は、配布ファイルに' \
                              u'含まれている [3:COPYING] ファイル' \
                              u'と同じものが[2:オンライン]で参' \
                              u'照できます。'
        ticket['version'] = u'2.0'
        ticket['resolution'] = u'fixed'
        ticket['keywords'] = u''
        ticket.insert()
        formatted = """\
  Reporter:  anonymous                           |      Owner:  somebody
      Type:  defect                              |     Status:  new
  Priority:  major                               |  Milestone:  milestone1
 Component:  Trac は BSD ライセンスのもとで配布  |    Version:  2.0
  されています。[1:]このライセンスの全文は、配   |   Keywords:
  布ファイルに含まれている [3:COPYING] ファイル  |
  と同じものが[2:オンライン]で参照できます。     |
Resolution:  fixed                               |"""
        self._validate_props_format(formatted, ticket)

    def test_props_format_wrap_rightside(self):
        self.env.config.set('notification', 'mime_encoding', 'none')
        ticket = Ticket(self.env)
        ticket['summary'] = u'This is a summary'
        ticket['reporter'] = u'anonymous'
        ticket['status'] = u'new'
        ticket['owner'] = u'somebody'
        ticket['type'] = u'defect'
        ticket['priority'] = u'major'
        ticket['milestone'] = u'Lorem ipsum dolor sit amet, consectetur ' \
                              u'adipisicing elit, sed do eiusmod tempor ' \
                              u'incididunt ut labore et dolore magna ' \
                              u'aliqua. Ut enim ad minim veniam, quis ' \
                              u'nostrud exercitation ullamco laboris nisi ' \
                              u'ut aliquip ex ea commodo consequat. Duis ' \
                              u'aute irure dolor in reprehenderit in ' \
                              u'voluptate velit esse cillum dolore eu ' \
                              u'fugiat nulla pariatur. Excepteur sint ' \
                              u'occaecat cupidatat non proident, sunt in ' \
                              u'culpa qui officia deserunt mollit anim id ' \
                              u'est laborum.'
        ticket['component'] = u'component1'
        ticket['version'] = u'2.0'
        ticket['resolution'] = u'fixed'
        ticket['keywords'] = u''
        ticket.insert()
        formatted = """\
  Reporter:  anonymous   |      Owner:  somebody
      Type:  defect      |     Status:  new
  Priority:  major       |  Milestone:  Lorem ipsum dolor sit amet,
 Component:  component1  |  consectetur adipisicing elit, sed do eiusmod
Resolution:  fixed       |  tempor incididunt ut labore et dolore magna
                         |  aliqua. Ut enim ad minim veniam, quis nostrud
                         |  exercitation ullamco laboris nisi ut aliquip ex
                         |  ea commodo consequat. Duis aute irure dolor in
                         |  reprehenderit in voluptate velit esse cillum
                         |  dolore eu fugiat nulla pariatur. Excepteur sint
                         |  occaecat cupidatat non proident, sunt in culpa
                         |  qui officia deserunt mollit anim id est
                         |  laborum.
                         |    Version:  2.0
                         |   Keywords:"""
        self._validate_props_format(formatted, ticket)

    def test_props_format_wrap_rightside_unicode(self):
        self.env.config.set('notification', 'mime_encoding', 'none')
        ticket = Ticket(self.env)
        ticket['summary'] = u'This is a summary'
        ticket['reporter'] = u'anonymous'
        ticket['status'] = u'new'
        ticket['owner'] = u'somebody'
        ticket['type'] = u'defect'
        ticket['priority'] = u'major'
        ticket['milestone'] = u'Trac 在经过修改的BSD协议下发布。' \
                              u'[1:]协议的完整文本可以[2:在线查' \
                              u'看]也可在发布版的 [3:COPYING] 文' \
                              u'件中找到。'
        ticket['component'] = u'component1'
        ticket['version'] = u'2.0'
        ticket['resolution'] = u'fixed'
        ticket['keywords'] = u''
        ticket.insert()
        formatted = """\
  Reporter:  anonymous   |      Owner:  somebody
      Type:  defect      |     Status:  new
  Priority:  major       |  Milestone:  Trac 在经过修改的BSD协议下发布。
 Component:  component1  |  [1:]协议的完整文本可以[2:在线查看]也可在发布版
Resolution:  fixed       |  的 [3:COPYING] 文件中找到。
                         |    Version:  2.0
                         |   Keywords:"""
        self._validate_props_format(formatted, ticket)

    def test_props_format_wrap_bothsides(self):
        self.env.config.set('notification', 'mime_encoding', 'none')
        ticket = Ticket(self.env)
        ticket['summary'] = u'This is a summary'
        ticket['reporter'] = u'anonymous'
        ticket['status'] = u'new'
        ticket['owner'] = u'somebody'
        ticket['type'] = u'defect'
        ticket['priority'] = u'major'
        ticket['milestone'] = u'Lorem ipsum dolor sit amet, consectetur ' \
                              u'adipisicing elit, sed do eiusmod tempor ' \
                              u'incididunt ut labore et dolore magna ' \
                              u'aliqua. Ut enim ad minim veniam, quis ' \
                              u'nostrud exercitation ullamco laboris nisi ' \
                              u'ut aliquip ex ea commodo consequat. Duis ' \
                              u'aute irure dolor in reprehenderit in ' \
                              u'voluptate velit esse cillum dolore eu ' \
                              u'fugiat nulla pariatur. Excepteur sint ' \
                              u'occaecat cupidatat non proident, sunt in ' \
                              u'culpa qui officia deserunt mollit anim id ' \
                              u'est laborum.'
        ticket['component'] = ticket['milestone']
        ticket['version'] = u'2.0'
        ticket['resolution'] = u'fixed'
        ticket['keywords'] = u''
        ticket.insert()
        formatted = """\
  Reporter:  anonymous               |      Owner:  somebody
      Type:  defect                  |     Status:  new
  Priority:  major                   |  Milestone:  Lorem ipsum dolor sit
 Component:  Lorem ipsum dolor sit   |  amet, consectetur adipisicing elit,
  amet, consectetur adipisicing      |  sed do eiusmod tempor incididunt ut
  elit, sed do eiusmod tempor        |  labore et dolore magna aliqua. Ut
  incididunt ut labore et dolore     |  enim ad minim veniam, quis nostrud
  magna aliqua. Ut enim ad minim     |  exercitation ullamco laboris nisi
  veniam, quis nostrud exercitation  |  ut aliquip ex ea commodo consequat.
  ullamco laboris nisi ut aliquip    |  Duis aute irure dolor in
  ex ea commodo consequat. Duis      |  reprehenderit in voluptate velit
  aute irure dolor in reprehenderit  |  esse cillum dolore eu fugiat nulla
  in voluptate velit esse cillum     |  pariatur. Excepteur sint occaecat
  dolore eu fugiat nulla pariatur.   |  cupidatat non proident, sunt in
  Excepteur sint occaecat cupidatat  |  culpa qui officia deserunt mollit
  non proident, sunt in culpa qui    |  anim id est laborum.
  officia deserunt mollit anim id    |    Version:  2.0
  est laborum.                       |   Keywords:
Resolution:  fixed                   |"""
        self._validate_props_format(formatted, ticket)

    def test_props_format_wrap_bothsides_unicode(self):
        self.env.config.set('notification', 'mime_encoding', 'none')
        self.env.config.set('notification', 'ambiguous_char_width', 'double')
        ticket = Ticket(self.env)
        ticket['summary'] = u'This is a summary'
        ticket['reporter'] = u'anonymous'
        ticket['status'] = u'new'
        ticket['owner'] = u'somebody'
        ticket['type'] = u'defect'
        ticket['priority'] = u'major'
        ticket['milestone'] = u'Trac 在经过修改的BSD协议下发布。' \
                              u'[1:]协议的完整文本可以[2:在线查' \
                              u'看]也可在发布版的 [3:COPYING] 文' \
                              u'件中找到。'
        ticket['component'] = u'Trac は BSD ライセンスのもとで配' \
                              u'布されています。[1:]このライセ' \
                              u'ンスの全文は、𠀋配布ファイル' \
                              u'に含まれている[3:CОPYING]ファイ' \
                              u'ルと同じものが[2:オンライン]で' \
                              u'参照できます。'
        ticket['version'] = u'2.0'
        ticket['resolution'] = u'fixed'
        ticket['keywords'] = u''
        ticket.insert()
        formatted = """\
  Reporter:  anonymous               |      Owner:  somebody
      Type:  defect                  |     Status:  new
  Priority:  major                   |  Milestone:  Trac 在经过修改的BSD协
 Component:  Trac は BSD ライセンス  |  议下发布。[1:]协议的完整文本可以[2:
  のもとで配布されています。[1:]こ   |  在线查看]也可在发布版的 [3:COPYING]
  のライセンスの全文は、𠀋配布ファ   |  文件中找到。
  イルに含まれている[3:CОPYING]フ   |    Version:  2.0
  ァイルと同じものが[2:オンライン]   |   Keywords:
  で参照できます。                   |
Resolution:  fixed                   |"""
        self._validate_props_format(formatted, ticket)

    def _validate_props_format(self, expected, ticket):
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=True)
        message = notifysuite.smtpd.get_message()
        (headers, body) = parse_smtp_message(message)
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
        ticket = Ticket(self.env)
        ticket['summary'] = 'My Summary'
        ticket['description'] = 'Some description'
        ticket.insert()
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=True)
        self.assertNotEqual(None, notifysuite.smtpd.get_message())
        self.assertEqual('My Summary', ticket['summary'])
        self.assertEqual('Some description', ticket['description'])
        valid_fieldnames = set([f['name'] for f in ticket.fields])
        current_fieldnames = set(ticket.values.keys())
        self.assertEqual(set(), current_fieldnames - valid_fieldnames)

    def test_notification_get_message_id_unicode(self):
        ticket = Ticket(self.env)
        ticket['summary'] = 'My Summary'
        ticket['description'] = 'Some description'
        ticket.insert()
        self.env.config.set('project', 'url', u"пиво Müller ")
        tn = TicketNotifyEmail(self.env)
        tn.ticket = ticket
        tn.get_message_id('foo')
        


class NotificationTestSuite(unittest.TestSuite):
    """Thin test suite wrapper to start and stop the SMTP test server"""

    def __init__(self):
        """Start the local SMTP test server"""
        unittest.TestSuite.__init__(self)
        self.smtpd = SMTPThreadedServer(SMTP_TEST_PORT)
        self.smtpd.start()
        self.addTest(unittest.makeSuite(NotificationTestCase, 'test'))
        self.remaining = self.countTestCases()

    def tear_down(self):
        """Reset the local SMTP test server"""
        self.smtpd.cleanup()
        self.remaining = self.remaining-1
        if self.remaining > 0:
            return
        # stop the SMTP test server when all tests have been completed
        self.smtpd.stop()

def suite():
    global notifysuite
    if not notifysuite:
        notifysuite = NotificationTestSuite()
    return notifysuite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
