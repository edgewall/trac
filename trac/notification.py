# -*- coding: iso-8859-1 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# Copyright (C) 2003-2005 Daniel Lundin <daniel@edgewall.com>
# Copyright (C) 2005-2006 Emmanuel Blot <emmanuel.blot@free.fr>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#

from trac import __version__
from trac.core import TracError
from trac.util import CRLF, wrap
from trac.web.clearsilver import HDFWrapper
from trac.web.main import populate_hdf

import time
import smtplib
import re


class Notify:
    """Generic notification class for Trac. Subclass this to implement
    different methods."""

    db = None
    hdf = None

    def __init__(self, env):
        self.env = env
        self.config = env.config
        self.db = env.get_db_cnx()
        self.hdf = HDFWrapper(loadpaths=[env.get_templates_dir(),
                                         self.config.get('trac', 'templates_dir')])
        populate_hdf(self.hdf, env)

    def notify(self, resid):
        (torcpts, ccrcpts) = self.get_recipients(resid)
        self.begin_send()
        self.send(torcpts, ccrcpts)
        self.finish_send()

    def get_recipients(self, resid):
        """Return a pair of list of subscribers to the resource 'resid'.
           First list represents the direct recipients (To:),
           second list represents the recipients in carbon copy (Cc:)"""
        raise NotImplementedError

    def begin_send(self):
        """Prepare to send messages. Called before sending begins."""
        pass

    def send(self, torcpts, ccrcpts):
        """Send message to recipients."""
        raise NotImplementedError

    def finish_send(self):
        """Clean up after sending all messages. Called after sending all messages."""
        pass


class NotifyEmail(Notify):
    """Baseclass for notification by email."""

    smtp_server = 'localhost'
    smtp_port = 25
    from_email = 'trac+tickets@localhost'
    subject = ''
    server = None
    email_map = None
    template_name = None
    shortaddr_re = re.compile(r"([\w\d_\.\-])+\@(([\w\d\-])+\.)+([\w\d]{2,4})+")
    longaddr_re = re.compile(r"^\s*(.*)\s+<([\w\d_\-\.]+\@(([\w\d\-])+\.)+([\w\d]{2,4})+)>\s*$");

    def __init__(self, env):
        Notify.__init__(self, env)

        self._init_pref_encoding()
        # Get the email addresses of all known users
        self.email_map = {}
        for username, name, email in self.env.get_known_users(self.db):
            if email:
                self.email_map[username] = email
                
    def _init_pref_encoding(self):
        from email.Charset import Charset, QP, BASE64
        self._charset = Charset()
        self._charset.input_charset = 'utf-8'
        self._charset.input_codec = 'utf-8'
        pref = self.env.config.get('notification', 'mime_encoding').lower()
        if pref == 'base64':
            self._charset.header_encoding = BASE64
            self._charset.body_encoding = BASE64
            self._charset.output_charset = 'utf-8'
            self._charset.output_codec = 'utf-8'    
            self._pref_encoding = 'base64'
        elif pref in ['qp', 'quoted-printable']:
            self._charset.header_encoding = QP
            self._charset.body_encoding = QP
            self._charset.output_charset = 'utf-8'
            self._charset.output_codec = 'utf-8'    
            self._pref_encoding = 'quoted-printable'
        elif pref == 'none':
            self._charset.header_encoding = None
            self._charset.body_encoding = None
            self._charset.output_charset = 'ascii'
            self._charset.output_codec = 'ascii'    
            self._pref_encoding = None
        else:
            raise TracError, 'Invalid email encoding setting: %s' % pref

    def notify(self, resid, subject):
        self.subject = subject

        if not self.config.getbool('notification', 'smtp_enabled'):
            return
        self.smtp_server = self.config.get('notification', 'smtp_server')
        self.smtp_port = int(self.config.get('notification', 'smtp_port'))
        self.from_email = self.config.get('notification', 'smtp_from')
        self.replyto_email = self.config.get('notification', 'smtp_replyto')
        self.from_email = self.from_email or self.replyto_email
        if not self.from_email and not self.replyto_email:
            raise TracError('Unable to send email due to identity crisis.<br />'
                            'Both <b>notification.from</b> and'
                            ' <b>notification.reply_to</b> are unspecified'
                            ' in configuration.',
                            'SMTP Notification Error')

        # Authentication info (optional)
        self.user_name = self.config.get('notification', 'smtp_user')
        self.password = self.config.get('notification', 'smtp_password')

        Notify.notify(self, resid)

    def get_email_addresses(self, txt):
        import email.Utils
        emails = [x[1] for x in  email.Utils.getaddresses([str(txt)])]
        return filter(lambda x: x.find('@') > -1, emails)

    def format_header(self, name, email=None):
        from email.Header import Header
        try:
            name = unicode(name, 'ascii')
        except UnicodeDecodeError:
            name = Header(name, self._charset)
        if not email:
            return name
        else:
            return "%s <%s>" % (name, email)

    def add_headers(self, msg, headers):
        for h in headers:
            msg[h] = self.encode_header(headers[h])

    def get_smtp_address(self, fulladdr):
        mo = NotifyEmail.shortaddr_re.search(fulladdr)
        if mo:
            return mo.group(0)
        if start >= 0:
            return fulladdr[start+1:-1]
        return fulladdr

    def encode_header(self, value):
        if isinstance(value, tuple):
            return self.format_header(value[0], value[1])
        if isinstance(value, list):
            items = []
            for v in value:
                items.append(self.encode_header(v))
            return ',\n\t'.join(items)
        mo = NotifyEmail.longaddr_re.match(value)
        if mo:
            return self.format_header(mo.group(1), mo.group(2))
        return self.format_header(value)

    def begin_send(self):
        self.server = smtplib.SMTP(self.smtp_server, self.smtp_port)
        if self.user_name:
            self.server.login(self.user_name, self.password)

    def send(self, torcpts, ccrcpts, mime_headers={}):
        from email.MIMEText import MIMEText
        from email.Utils import formatdate, formataddr
        body = self.hdf.render(self.template_name)
        projname = self.config.get('project', 'name')
        public_cc = self.config.getbool('notification', 'allow_public_cc')
        headers = {}
        headers['X-Mailer'] = 'Trac %s, by Edgewall Software' % __version__
        headers['X-Trac-Version'] =  __version__
        headers['X-Trac-Project'] =  projname
        headers['X-URL'] = self.config.get('project', 'url')
        headers['Subject'] = self.subject
        headers['From'] = (projname, self.from_email)
        headers['Sender'] = self.from_email
        headers['Reply-To'] = self.replyto_email
        headers['To'] = torcpts
        if public_cc:
            headers['Cc'] = ccrcpts
        headers['Date'] = formatdate()
        charset = 'utf-8'
        if not self._pref_encoding:
            try:
                dummy = unicode(body, 'ascii')
            except UnicodeDecodeError:
                raise TracError, "Ticket contains non-Ascii chars. " \
                                 "Please change encoding setting"
            charset = 'ascii'
        else:
            charset = 'utf-8'
        msg = MIMEText(body, 'plain', charset)
        del msg['Content-Transfer-Encoding']
        if self._pref_encoding:
            msg['Content-Transfer-Encoding'] = self._pref_encoding
        msg.set_charset(self._charset)
        self.add_headers(msg, headers);
        self.add_headers(msg, mime_headers);
        recipients = []
        for r in torcpts + ccrcpts:
            recipients.append(self.get_smtp_address(r))
        self.env.log.debug("Sending SMTP notification to %s on port %d to %s"
                           % (self.smtp_server, self.smtp_port, recipients))
        msgtext = msg.as_string()
        self.server.sendmail(msg['From'], recipients, msgtext)

    def finish_send(self):
        self.server.quit()
