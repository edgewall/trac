# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2005 Daniel Lundin <daniel@edgewall.com>
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

import time
import smtplib
import re

from genshi.builder import tag

from trac import __version__
from trac.config import BoolOption, IntOption, Option
from trac.core import *
from trac.util.text import CRLF
from trac.util.translation import _

MAXHEADERLEN = 76
EMAIL_LOOKALIKE_PATTERN = (
        # the local part
        r"[a-zA-Z0-9.'=+_-]+" '@'
        # the domain name part (RFC:1035)
        '(?:[a-zA-Z0-9_-]+\.)+' # labels (but also allow '_')
        '[a-zA-Z](?:[-a-zA-Z\d]*[a-zA-Z\d])?' # TLD
        )

class NotificationSystem(Component):

    smtp_enabled = BoolOption('notification', 'smtp_enabled', 'false',
        """Enable SMTP (email) notification.""")

    smtp_server = Option('notification', 'smtp_server', 'localhost',
        """SMTP server hostname to use for email notifications.""")

    smtp_port = IntOption('notification', 'smtp_port', 25,
        """SMTP server port to use for email notification.""")

    smtp_user = Option('notification', 'smtp_user', '',
        """Username for SMTP server. (''since 0.9'').""")

    smtp_password = Option('notification', 'smtp_password', '',
        """Password for SMTP server. (''since 0.9'').""")

    smtp_from = Option('notification', 'smtp_from', 'trac@localhost',
        """Sender address to use in notification emails.""")
        
    smtp_from_name = Option('notification', 'smtp_from_name', '',
        """Sender name to use in notification emails.""")

    smtp_replyto = Option('notification', 'smtp_replyto', 'trac@localhost',
        """Reply-To address to use in notification emails.""")

    smtp_always_cc = Option('notification', 'smtp_always_cc', '',
        """Email address(es) to always send notifications to,
           addresses can be seen by all recipients (Cc:).""")

    smtp_always_bcc = Option('notification', 'smtp_always_bcc', '',
        """Email address(es) to always send notifications to,
           addresses do not appear publicly (Bcc:). (''since 0.10'').""")
           
    smtp_default_domain = Option('notification', 'smtp_default_domain', '',
        """Default host/domain to append to address that do not specify one""")
        
    ignore_domains = Option('notification', 'ignore_domains', '',
        """Comma-separated list of domains that should not be considered
           part of email addresses (for usernames with Kerberos domains)""")
           
    admit_domains = Option('notification', 'admit_domains', '',
        """Comma-separated list of domains that should be considered as
        valid for email addresses (such as localdomain)""")
           
    mime_encoding = Option('notification', 'mime_encoding', 'base64',
        """Specifies the MIME encoding scheme for emails.
        
        Valid options are 'base64' for Base64 encoding, 'qp' for
        Quoted-Printable, and 'none' for no encoding. Note that the no encoding
        means that non-ASCII characters in text are going to cause problems
        with notifications (''since 0.10'').""")

    use_public_cc = BoolOption('notification', 'use_public_cc', 'false',
        """Recipients can see email addresses of other CC'ed recipients.
        
        If this option is disabled (the default), recipients are put on BCC
        (''since 0.10'').""")

    use_short_addr = BoolOption('notification', 'use_short_addr', 'false',
        """Permit email address without a host/domain (i.e. username only)
        
        The SMTP server should accept those addresses, and either append
        a FQDN or use local delivery (''since 0.10'').""")
        
    use_tls = BoolOption('notification', 'use_tls', 'false',
        """Use SSL/TLS to send notifications (''since 0.10'').""")
    
    smtp_subject_prefix = Option('notification', 'smtp_subject_prefix',
                                 '__default__', 
        """Text to prepend to subject line of notification emails. 
        
        If the setting is not defined, then the [$project_name] prefix.
        If no prefix is desired, then specifying an empty option 
        will disable it.(''since 0.10.1'').""")


class Notify(object):
    """Generic notification class for Trac.
    
    Subclass this to implement different methods.
    """

    def __init__(self, env):
        self.env = env
        self.config = env.config
        self.db = env.get_db_cnx()

        from trac.web.chrome import Chrome
        self.template = Chrome(self.env).load_template(self.template_name,
                                                       method='text')
        # FIXME: actually, we would need a Context with a different
        #        PermissionCache for each recipient
        self.data = Chrome(self.env).populate_data(None, {'CRLF': CRLF})

    def notify(self, resid):
        (torcpts, ccrcpts) = self.get_recipients(resid)
        self.begin_send()
        self.send(torcpts, ccrcpts)
        self.finish_send()

    def get_recipients(self, resid):
        """Return a pair of list of subscribers to the resource 'resid'.
        
        First list represents the direct recipients (To:), second list
        represents the recipients in carbon copy (Cc:).
        """
        raise NotImplementedError

    def begin_send(self):
        """Prepare to send messages.
        
        Called before sending begins.
        """

    def send(self, torcpts, ccrcpts):
        """Send message to recipients."""
        raise NotImplementedError

    def finish_send(self):
        """Clean up after sending all messages.
        
        Called after sending all messages.
        """


class NotifyEmail(Notify):
    """Baseclass for notification by email."""

    smtp_server = 'localhost'
    smtp_port = 25
    from_email = 'trac+tickets@localhost'
    subject = ''
    template_name = None
    nodomaddr_re = re.compile(r'[\w\d_\.\-]+')
    addrsep_re = re.compile(r'[;\s,]+')

    def __init__(self, env):
        global EMAIL_LOOKALIKE_PATTERN
        Notify.__init__(self, env)

        addrfmt = EMAIL_LOOKALIKE_PATTERN
        admit_domains = self.env.config.get('notification', 'admit_domains')
        if admit_domains:
            pos = addrfmt.find('@')
            domains = '|'.join([x.strip() for x in \
                                admit_domains.replace('.','\.').split(',')])
            addrfmt = r'%s@(?:(?:%s)|%s)' % (addrfmt[:pos], addrfmt[pos+1:], 
                                              domains)
        self.shortaddr_re = re.compile(r'%s$' % addrfmt)
        self.longaddr_re = re.compile(r'^\s*(.*)\s+<(%s)>\s*$' % addrfmt);
        self._use_tls = self.env.config.getbool('notification', 'use_tls')
        self._init_pref_encoding()
        domains = self.env.config.get('notification', 'ignore_domains', '')
        self._ignore_domains = [x.strip() for x in domains.lower().split(',')]
        # Get the email addresses of all known users
        self.email_map = {}
        for username, name, email in self.env.get_known_users(self.db):
            if email:
                self.email_map[username] = email
                
    def _init_pref_encoding(self):
        from email.Charset import Charset, QP, BASE64
        self._charset = Charset()
        self._charset.input_charset = 'utf-8'
        pref = self.env.config.get('notification', 'mime_encoding').lower()
        if pref == 'base64':
            self._charset.header_encoding = BASE64
            self._charset.body_encoding = BASE64
            self._charset.output_charset = 'utf-8'
            self._charset.input_codec = 'utf-8'
            self._charset.output_codec = 'utf-8'
        elif pref in ['qp', 'quoted-printable']:
            self._charset.header_encoding = QP
            self._charset.body_encoding = QP
            self._charset.output_charset = 'utf-8'
            self._charset.input_codec = 'utf-8'
            self._charset.output_codec = 'utf-8'
        elif pref == 'none':
            self._charset.header_encoding = None
            self._charset.body_encoding = None
            self._charset.input_codec = None
            self._charset.output_charset = 'ascii'
        else:
            raise TracError(_('Invalid email encoding setting: %s' % pref))

    def notify(self, resid, subject):
        self.subject = subject

        if not self.config.getbool('notification', 'smtp_enabled'):
            return
        self.smtp_server = self.config['notification'].get('smtp_server')
        self.smtp_port = self.config['notification'].getint('smtp_port')
        self.from_email = self.config['notification'].get('smtp_from')
        self.from_name = self.config['notification'].get('smtp_from_name')
        self.replyto_email = self.config['notification'].get('smtp_replyto')
        self.from_email = self.from_email or self.replyto_email
        if not self.from_email and not self.replyto_email:
            raise TracError(tag(tag.p('Unable to send email due to identity '
                                        'crisis.'),
                                  tag.p('Neither ', tag.b('notification.from'),
                                        ' nor ', tag.b('notification.reply_to'),
                                        'are specified in the configuration.')),
                              'SMTP Notification Error')

        # Authentication info (optional)
        self.user_name = self.config['notification'].get('smtp_user')
        self.password = self.config['notification'].get('smtp_password')

        Notify.notify(self, resid)

    def format_header(self, key, name, email=None):
        from email.Header import Header
        maxlength = MAXHEADERLEN-(len(key)+2)
        # Do not sent ridiculous short headers
        if maxlength < 10:
            raise TracError(_("Header length is too short"))
        try:
            tmp = name.encode('ascii')
            header = Header(tmp, 'ascii', maxlinelen=maxlength)
        except UnicodeEncodeError:
            header = Header(name, self._charset, maxlinelen=maxlength)
        if not email:
            return header
        else:
            return '"%s" <%s>' % (header, email)

    def add_headers(self, msg, headers):
        for h in headers:
            msg[h] = self.encode_header(h, headers[h])

    def get_smtp_address(self, address):
        if not address:
            return None

        def is_email(address):
            pos = address.find('@')
            if pos == -1:
                return False
            if address[pos+1:].lower() in self._ignore_domains:
                return False
            return True

        if not is_email(address):
            if address == 'anonymous':
                return None
            if self.email_map.has_key(address):
                address = self.email_map[address]
            elif NotifyEmail.nodomaddr_re.match(address):
                if self.config.getbool('notification', 'use_short_addr'):
                    return address
                domain = self.config.get('notification', 'smtp_default_domain')
                if domain:
                    address = "%s@%s" % (address, domain)
                else:
                    self.env.log.info("Email address w/o domain: %s" % address)
                    return None

        mo = self.shortaddr_re.search(address)
        if mo:
            return mo.group(0)
        mo = self.longaddr_re.search(address)
        if mo:
            return mo.group(2)
        self.env.log.info("Invalid email address: %s" % address)
        return None

    def encode_header(self, key, value):
        if isinstance(value, tuple):
            return self.format_header(key, value[0], value[1])
        if isinstance(value, list):
            items = []
            for v in value:
                items.append(self.encode_header(v))
            return ',\n\t'.join(items)
        mo = self.longaddr_re.match(value)
        if mo:
            return self.format_header(key, mo.group(1), mo.group(2))
        return self.format_header(key, value)

    def begin_send(self):
        self.server = smtplib.SMTP(self.smtp_server, self.smtp_port)
        # self.server.set_debuglevel(True)
        if self._use_tls:
            self.server.ehlo()
            if not self.server.esmtp_features.has_key('starttls'):
                raise TracError(_("TLS enabled but server does not support " \
                                  "TLS"))
            self.server.starttls()
            self.server.ehlo()
        if self.user_name:
            self.server.login(self.user_name.encode('utf-8'),
                              self.password.encode('utf-8'))

    def send(self, torcpts, ccrcpts, mime_headers={}):
        from email.MIMEText import MIMEText
        from email.Utils import formatdate
        stream = self.template.generate(**self.data)
        body = stream.render('text')
        projname = self.config.get('project', 'name')
        public_cc = self.config.getbool('notification', 'use_public_cc')
        headers = {}
        headers['X-Mailer'] = 'Trac %s, by Edgewall Software' % __version__
        headers['X-Trac-Version'] =  __version__
        headers['X-Trac-Project'] =  projname
        headers['X-URL'] = self.config.get('project', 'url')
        headers['Precedence'] = 'bulk'
        headers['Auto-Submitted'] = 'auto-generated'
        headers['Subject'] = self.subject
        headers['From'] = (self.from_name or projname, self.from_email)
        headers['Reply-To'] = self.replyto_email

        def build_addresses(rcpts):
            """Format and remove invalid addresses"""
            return filter(lambda x: x, \
                          [self.get_smtp_address(addr) for addr in rcpts])

        def remove_dup(rcpts, all):
            """Remove duplicates"""
            tmp = []
            for rcpt in rcpts:
                if not rcpt in all:
                    tmp.append(rcpt)
                    all.append(rcpt)
            return (tmp, all)

        toaddrs = build_addresses(torcpts)
        ccaddrs = build_addresses(ccrcpts)
        accparam = self.config.get('notification', 'smtp_always_cc')
        accaddrs = accparam and \
                   build_addresses(accparam.replace(',', ' ').split()) or []
        bccparam = self.config.get('notification', 'smtp_always_bcc')
        bccaddrs = bccparam and \
                   build_addresses(bccparam.replace(',', ' ').split()) or []

        recipients = []
        (toaddrs, recipients) = remove_dup(toaddrs, recipients)
        (ccaddrs, recipients) = remove_dup(ccaddrs, recipients)
        (accaddrs, recipients) = remove_dup(accaddrs, recipients)
        (bccaddrs, recipients) = remove_dup(bccaddrs, recipients)
        
        # if there is not valid recipient, leave immediately
        if len(recipients) < 1:
            self.env.log.info('no recipient for a ticket notification')
            return

        pcc = accaddrs
        if public_cc:
            pcc += ccaddrs
            if toaddrs:
                headers['To'] = ', '.join(toaddrs)
        if pcc:
            headers['Cc'] = ', '.join(pcc)
        headers['Date'] = formatdate()
        # sanity check
        if not self._charset.body_encoding:
            try:
                dummy = body.encode('ascii')
            except UnicodeDecodeError:
                raise TracError(_("Ticket contains non-ASCII chars. " \
                                  "Please change encoding setting"))
        msg = MIMEText(body, 'plain')
        # Message class computes the wrong type from MIMEText constructor,
        # which does not take a Charset object as initializer. Reset the
        # encoding type to force a new, valid evaluation
        del msg['Content-Transfer-Encoding']
        msg.set_charset(self._charset)
        self.add_headers(msg, headers);
        self.add_headers(msg, mime_headers);
        self.env.log.info("Sending SMTP notification to %s:%d to %s"
                           % (self.smtp_server, self.smtp_port, recipients))
        msgtext = msg.as_string()
        # Ensure the message complies with RFC2822: use CRLF line endings
        recrlf = re.compile("\r?\n")
        msgtext = CRLF.join(recrlf.split(msgtext))
        start = time.time()
        self.server.sendmail(msg['From'], recipients, msgtext)
        t = time.time() - start
        if t > 5:
            self.env.log.warning('Slow mail submission (%.2f s), '
                                 'check your mail setup' % t)

    def finish_send(self):
        if self._use_tls:
            # avoid false failure detection when the server closes
            # the SMTP connection with TLS enabled
            import socket
            try:
                self.server.quit()
            except socket.sslerror:
                pass
        else:
            self.server.quit()
