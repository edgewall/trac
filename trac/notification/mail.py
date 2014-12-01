# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2014 Edgewall Software
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

import os
import re
import smtplib
import time
from email.MIMEText import MIMEText
from hashlib import md5
from subprocess import Popen, PIPE

from genshi.builder import tag

from trac.config import BoolOption, ConfigurationError, IntOption, Option
from trac.core import *
from trac.notification.api import IEmailSender, NotificationSystem
from trac.util.compat import close_fds
from trac.util.datefmt import to_utimestamp
from trac.util.text import CRLF, fix_eol, to_unicode
from trac.util.translation import _, tag_


__all__ = ['EMAIL_LOOKALIKE_PATTERN', 'MAXHEADERLEN', 'RecipientMatcher',
           'SendmailEmailSender', 'SmtpEmailSender', 'create_charset',
           'create_header', 'create_message_id', 'create_mime_text']


MAXHEADERLEN = 76
EMAIL_LOOKALIKE_PATTERN = (
        # the local part
        r"[a-zA-Z0-9.'+_-]+" '@'
        # the domain name part (RFC:1035)
        '(?:[a-zA-Z0-9_-]+\.)+' # labels (but also allow '_')
        '[a-zA-Z](?:[-a-zA-Z\d]*[a-zA-Z\d])?' # TLD
        )

_mime_encoding_re = re.compile(r'=\?[^?]+\?[bq]\?[^?]+\?=', re.IGNORECASE)



def create_charset(mime_encoding):
    """Create an appropriate email charset for the given encoding.

    Valid options are 'base64' for Base64 encoding, 'qp' for
    Quoted-Printable, and 'none' for no encoding, in which case mails will
    be sent as 7bit if the content is all ASCII, or 8bit otherwise.
    """
    from email.Charset import BASE64, QP, SHORTEST, Charset
    charset = Charset()
    charset.input_charset = 'utf-8'
    charset.output_charset = 'utf-8'
    charset.input_codec = 'utf-8'
    charset.output_codec = 'utf-8'
    pref = mime_encoding.lower()
    if pref == 'base64':
        charset.header_encoding = BASE64
        charset.body_encoding = BASE64
    elif pref in ('qp', 'quoted-printable'):
        charset.header_encoding = QP
        charset.body_encoding = QP
    elif pref == 'none':
        charset.header_encoding = SHORTEST
        charset.body_encoding = None
    else:
        raise TracError(_("Invalid email encoding setting: %(mime_encoding)s",
                          mime_encoding=mime_encoding))
    return charset


def create_header(key, name, charset):
    """Create an appropriate email Header."""
    from email.Header import Header
    maxlength = MAXHEADERLEN-(len(key)+2)
    # Do not sent ridiculous short headers
    if maxlength < 10:
        raise TracError(_("Header length is too short"))
    # when it matches mime-encoding, encode as mime even if only
    # ascii characters
    if not _mime_encoding_re.search(name):
        try:
            tmp = name.encode('ascii')
            return Header(tmp, 'ascii', maxlinelen=maxlength)
        except UnicodeEncodeError:
            pass
    return Header(name.encode(charset.output_codec), charset,
                  maxlinelen=maxlength)


def create_mime_text(body, format, charset):
    """Create an appropriate email `MIMEText`."""
    msg = MIMEText(body, format)
    # Message class computes the wrong type from MIMEText constructor,
    # which does not take a Charset object as initializer. Reset the
    # encoding type to force a new, valid evaluation
    del msg['Content-Transfer-Encoding']
    msg.set_charset(charset)
    return msg


def create_message_id(env, targetid, from_email, time, more=''):
    """Generate a predictable, but sufficiently unique message ID."""
    s = '%s.%s.%d.%s' % (env.project_url.encode('utf-8'),
                         targetid, to_utimestamp(time),
                         more.encode('ascii', 'ignore'))
    dig = md5(s).hexdigest()
    host = from_email[from_email.find('@') + 1:]
    return '<%03d.%s@%s>' % (len(s), dig, host)


class RecipientMatcher(object):

    nodomaddr_re = re.compile(r'[\w\d_\.\-]+')

    def __init__(self, env):
        self.env = env
        addrfmt = EMAIL_LOOKALIKE_PATTERN
        notify_sys = NotificationSystem(env)
        admit_domains = notify_sys.admit_domains_list
        if admit_domains:
            localfmt, domainfmt = addrfmt.split('@')
            domains = '|'.join(re.escape(x) for x in admit_domains)
            addrfmt = r'%s@(?:(?:%s)|%s)' % (localfmt, domainfmt, domains)
        self.shortaddr_re = re.compile(r'\s*(%s)\s*$' % addrfmt)
        self.longaddr_re = re.compile(r'^\s*(.*)\s+<\s*(%s)\s*>\s*$' % addrfmt)
        self.ignore_domains = [x.lower()
                               for x in notify_sys.ignore_domains_list]

        # Get the name and email addresses of all known users
        self.name_map = {}
        self.email_map = {}
        for username, name, email in self.env.get_known_users():
            if name:
                self.name_map[username] = name
            if email:
                self.email_map[username] = email

    def match_recipient(self, address):
        if not address:
            return None

        def is_email(address):
            pos = address.find('@')
            if pos == -1:
                return False
            if address[pos+1:].lower() in self.ignore_domains:
                return False
            return True

        if address == 'anonymous':
            return None
        sid = None
        auth = 0
        if address in self.email_map:
            sid = address
            auth = 1
            address = self.email_map[address]
        elif not is_email(address) and self.nodomaddr_re.match(address):
            if self.env.config.getbool('notification', 'use_short_addr'):
                return (None, 0, address)
            domain = self.env.config.get('notification',
                                         'smtp_default_domain')
            if domain:
                address = "%s@%s" % (address, domain)
            else:
                self.env.log.info("Email address w/o domain: %s", address)
                return None

        mo = self.shortaddr_re.search(address)
        if mo:
            return (sid, auth, mo.group(1))
        mo = self.longaddr_re.search(address)
        if mo:
            return (sid, auth, mo.group(2))
        self.env.log.info("Invalid email address: %s", address)
        return None


class SmtpEmailSender(Component):
    """E-mail sender connecting to an SMTP server."""

    implements(IEmailSender)

    smtp_server = Option('notification', 'smtp_server', 'localhost',
        """SMTP server hostname to use for email notifications.""")

    smtp_port = IntOption('notification', 'smtp_port', 25,
        """SMTP server port to use for email notification.""")

    smtp_user = Option('notification', 'smtp_user', '',
        """Username for authenticating with SMTP server.""")

    smtp_password = Option('notification', 'smtp_password', '',
        """Password for authenticating with SMTP server.""")

    use_tls = BoolOption('notification', 'use_tls', 'false',
        """Use SSL/TLS to send notifications over SMTP.""")

    def send(self, from_addr, recipients, message):
        # Ensure the message complies with RFC2822: use CRLF line endings
        message = fix_eol(message, CRLF)

        self.log.info("Sending notification through SMTP at %s:%d to %s",
                      self.smtp_server, self.smtp_port, recipients)
        try:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
        except smtplib.socket.error as e:
            raise ConfigurationError(
                tag_("SMTP server connection error (%(error)s). Please "
                     "modify %(option1)s or %(option2)s in your "
                     "configuration.",
                     error=to_unicode(e),
                     option1=tag.code("[notification] smtp_server"),
                     option2=tag.code("[notification] smtp_port")))
        # server.set_debuglevel(True)
        if self.use_tls:
            server.ehlo()
            if 'starttls' not in server.esmtp_features:
                raise TracError(_("TLS enabled but server does not support"
                                  " TLS"))
            server.starttls()
            server.ehlo()
        if self.smtp_user:
            server.login(self.smtp_user.encode('utf-8'),
                         self.smtp_password.encode('utf-8'))
        start = time.time()
        server.sendmail(from_addr, recipients, message)
        t = time.time() - start
        if t > 5:
            self.log.warning("Slow mail submission (%.2f s), "
                             "check your mail setup", t)
        if self.use_tls:
            # avoid false failure detection when the server closes
            # the SMTP connection with TLS enabled
            import socket
            try:
                server.quit()
            except socket.sslerror:
                pass
        else:
            server.quit()


class SendmailEmailSender(Component):
    """E-mail sender using a locally-installed sendmail program."""

    implements(IEmailSender)

    sendmail_path = Option('notification', 'sendmail_path', 'sendmail',
        """Path to the sendmail executable.

        The sendmail program must accept the `-i` and `-f` options.
         (''since 0.12'')""")

    def send(self, from_addr, recipients, message):
        # Use native line endings in message
        message = fix_eol(message, os.linesep)

        self.log.info("Sending notification through sendmail at %s to %s",
                      self.sendmail_path, recipients)
        cmdline = [self.sendmail_path, '-i', '-f', from_addr] + recipients
        self.log.debug("Sendmail command line: %s", cmdline)
        try:
            child = Popen(cmdline, bufsize=-1, stdin=PIPE, stdout=PIPE,
                          stderr=PIPE, close_fds=close_fds)
        except OSError as e:
            raise ConfigurationError(
                tag_("Sendmail error (%(error)s). Please modify %(option)s "
                     "in your configuration.",
                     error=to_unicode(e),
                     option=tag.code("[notification] sendmail_path")))
        out, err = child.communicate(message)
        if child.returncode or err:
            raise Exception("Sendmail failed with (%s, %s), command: '%s'"
                            % (child.returncode, err.strip(), cmdline))
