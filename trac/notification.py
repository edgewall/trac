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
from abc import ABCMeta, abstractmethod
from subprocess import Popen, PIPE

from genshi.builder import tag

from trac import __version__
from trac.config import BoolOption, ConfigurationError, ExtensionOption, \
                        IntOption, ListOption, Option
from trac.core import *
from trac.util.compat import close_fds
from trac.util.html import to_fragment
from trac.util.text import CRLF, fix_eol, to_unicode
from trac.util.translation import _, deactivate, reactivate, tag_

MAXHEADERLEN = 76
EMAIL_LOOKALIKE_PATTERN = (
    # the local part
    r"[a-zA-Z0-9.'+_-]+" '@'
    # the domain name part (RFC:1035)
    '(?:[a-zA-Z0-9_-]+\.)+'  # labels (but also allow '_')
    '[a-zA-Z](?:[-a-zA-Z\d]*[a-zA-Z\d])?'  # TLD
)


class IEmailSender(Interface):
    """Extension point interface for components that allow sending e-mail."""

    def send(self, from_addr, recipients, message):
        """Send message to recipients."""


class NotificationSystem(Component):

    email_sender = ExtensionOption('notification', 'email_sender',
                                   IEmailSender, 'SmtpEmailSender',
        """Name of the component implementing `IEmailSender`.

        This component is used by the notification system to send emails.
        Trac currently provides `SmtpEmailSender` for connecting to an SMTP
        server, and `SendmailEmailSender` for running a `sendmail`-compatible
        executable. (''since 0.12'')""")

    smtp_enabled = BoolOption('notification', 'smtp_enabled', 'false',
        """Enable email notification.""")

    smtp_from = Option('notification', 'smtp_from', 'trac@localhost',
        """Sender address to use in notification emails.

        At least one of `smtp_from` and `smtp_replyto` must be set, otherwise
        Trac refuses to send notification mails.""")

    smtp_from_name = Option('notification', 'smtp_from_name', '',
        """Sender name to use in notification emails.""")

    smtp_from_author = BoolOption('notification', 'smtp_from_author', 'false',
        """Use the author of the change as the sender in notification emails
           (e.g. reporter of a new ticket, author of a comment). If the
           author hasn't set an email address, `smtp_from` and
           `smtp_from_name` are used instead.
           (''since 1.0'')""")

    smtp_replyto = Option('notification', 'smtp_replyto', 'trac@localhost',
        """Reply-To address to use in notification emails.

        At least one of `smtp_from` and `smtp_replyto` must be set, otherwise
        Trac refuses to send notification mails.""")

    smtp_always_cc_list = ListOption(
        'notification', 'smtp_always_cc', '', sep=(',', ' '),
        doc="""Comma-separated list of email addresses to always send
               notifications to. Addresses can be seen by all recipients
               (Cc:).""")

    smtp_always_bcc_list = ListOption(
        'notification', 'smtp_always_bcc', '', sep=(',', ' '),
        doc="""Comma-separated list of email addresses to always send
               notifications to. Addresses are not public (Bcc:).
               (''since 0.10'')""")

    smtp_default_domain = Option('notification', 'smtp_default_domain', '',
        """Default host/domain to append to addresses that do not specify
           one. Fully qualified addresses are not modified. The default
           domain is appended to all username/login for which an email
           address cannot be found in the user settings.""")

    ignore_domains_list = ListOption('notification', 'ignore_domains', '',
        doc="""Comma-separated list of domains that should not be considered
           part of email addresses (for usernames with Kerberos domains).""")

    admit_domains_list = ListOption('notification', 'admit_domains', '',
        doc="""Comma-separated list of domains that should be considered as
        valid for email addresses (such as localdomain).""")

    mime_encoding = Option('notification', 'mime_encoding', 'none',
        """Specifies the MIME encoding scheme for emails.

        Supported values are: `none`, the default value which uses 7-bit
        encoding if the text is plain ASCII or 8-bit otherwise. `base64`,
        which works with any kind of content but may cause some issues with
        touchy anti-spam/anti-virus engine. `qp` or `quoted-printable`,
        which works best for european languages (more compact than base64) if
        8-bit encoding cannot be used.
        (''since 0.10'')""")

    use_public_cc = BoolOption('notification', 'use_public_cc', 'false',
        """Addresses in the To and Cc fields are visible to all recipients.

        If this option is disabled, recipients are put in the Bcc list.
        (''since 0.10'')""")

    use_short_addr = BoolOption('notification', 'use_short_addr', 'false',
        """Permit email address without a host/domain (i.e. username only).

        The SMTP server should accept those addresses, and either append
        a FQDN or use local delivery. See also `smtp_default_domain`. Do not
        use this option with a public SMTP server. (''since 0.10'')""")

    smtp_subject_prefix = Option('notification', 'smtp_subject_prefix',
                                 '__default__',
        """Text to prepend to subject line of notification emails.

        If the setting is not defined, then `[$project_name]` is used as the
        prefix. If no prefix is desired, then specifying an empty option
        will disable it. (''since 0.10.1'')""")

    @property
    def smtp_always_cc(self):  # For backward compatibility
        return self.config.get('notification', 'smtp_always_cc')

    @property
    def smtp_always_bcc(self):  # For backward compatibility
        return self.config.get('notification', 'smtp_always_bcc')

    @property
    def ignore_domains(self):  # For backward compatibility
        return self.config.get('notification', 'ignore_domains')

    @property
    def admit_domains(self):  # For backward compatibility
        return self.config.get('notification', 'admit_domains')

    def send_email(self, from_addr, recipients, message):
        """Send message to recipients via e-mail."""
        self.email_sender.send(from_addr, recipients, message)


class SmtpEmailSender(Component):
    """E-mail sender connecting to an SMTP server."""

    implements(IEmailSender)

    smtp_server = Option('notification', 'smtp_server', 'localhost',
        """SMTP server hostname to use for email notifications.""")

    smtp_port = IntOption('notification', 'smtp_port', 25,
        """SMTP server port to use for email notification.""")

    smtp_user = Option('notification', 'smtp_user', '',
        """Username for authenticating with SMTP server. (''since 0.9'')""")

    smtp_password = Option('notification', 'smtp_password', '',
        """Password for authenticating with SMTP server. (''since 0.9'')""")

    use_tls = BoolOption('notification', 'use_tls', 'false',
        """Use SSL/TLS to send notifications over SMTP. (''since 0.10'')""")

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


class Notify(object):
    """Generic notification class for Trac.

    Subclass this to implement different methods.
    """
    __metaclass__ = ABCMeta

    def __init__(self, env):
        self.env = env
        self.config = env.config

        from trac.web.chrome import Chrome
        self.template = Chrome(self.env).load_template(self.template_name,
                                                       method='text')
        # FIXME: actually, we would need a different
        #        PermissionCache for each recipient
        self.data = Chrome(self.env).populate_data(None, {'CRLF': CRLF})

    def notify(self, resid):
        torcpts, ccrcpts = self.get_recipients(resid)
        self.begin_send()
        self.send(torcpts, ccrcpts)
        self.finish_send()

    @abstractmethod
    def get_recipients(self, resid):
        """Return a pair of list of subscribers to the resource 'resid'.

        First list represents the direct recipients (To:), second list
        represents the recipients in carbon copy (Cc:).
        """
        pass

    def begin_send(self):
        """Prepare to send messages.

        Called before sending begins.
        """

    @abstractmethod
    def send(self, torcpts, ccrcpts):
        """Send message to recipients."""
        pass

    def finish_send(self):
        """Clean up after sending all messages.

        Called after sending all messages.
        """


class NotifyEmail(Notify):
    """Baseclass for notification by email."""

    from_email = 'trac+tickets@localhost'
    subject = ''
    template_name = None
    nodomaddr_re = re.compile(r'[\w\d_\.\-]+')
    addrsep_re = re.compile(r'[;\s,]+')

    def __init__(self, env):
        super(NotifyEmail, self).__init__(env)

        notify_sys = NotificationSystem(self.env)
        addrfmt = EMAIL_LOOKALIKE_PATTERN
        admit_domains = notify_sys.admit_domains_list
        if admit_domains:
            localfmt, domainfmt = addrfmt.split('@')
            domains = '|'.join(re.escape(x) for x in admit_domains)
            addrfmt = r'%s@(?:(?:%s)|%s)' % (localfmt, domainfmt, domains)
        self.shortaddr_re = re.compile(r'\s*(%s)\s*$' % addrfmt)
        self.longaddr_re = re.compile(r'^\s*(.*)\s+<\s*(%s)\s*>\s*$' % addrfmt)
        self._init_pref_encoding()
        self._ignore_domains = [x.lower()
                                for x in notify_sys.ignore_domains_list]
        # Get the name and email addresses of all known users
        self.name_map = {}
        self.email_map = {}
        for username, name, email in self.env.get_known_users():
            if name:
                self.name_map[username] = name
            if email:
                self.email_map[username] = email

    def _init_pref_encoding(self):
        from email.Charset import BASE64, QP, SHORTEST, Charset
        self._charset = Charset()
        self._charset.input_charset = 'utf-8'
        self._charset.output_charset = 'utf-8'
        self._charset.input_codec = 'utf-8'
        self._charset.output_codec = 'utf-8'
        pref = self.config.get('notification', 'mime_encoding').lower()
        if pref == 'base64':
            self._charset.header_encoding = BASE64
            self._charset.body_encoding = BASE64
        elif pref in ('qp', 'quoted-printable'):
            self._charset.header_encoding = QP
            self._charset.body_encoding = QP
        elif pref == 'none':
            self._charset.header_encoding = SHORTEST
            self._charset.body_encoding = None
        else:
            raise TracError(_("Invalid email encoding setting: %(pref)s",
                              pref=pref))

    def notify(self, resid, subject, author=None):
        self.subject = subject
        config = self.config['notification']
        if not config.getbool('smtp_enabled'):
            return
        from_email, from_name = '', ''
        if author and config.getbool('smtp_from_author'):
            from_email = self.get_smtp_address(author)
            if from_email:
                from_name = self.name_map.get(author, '')
                if not from_name:
                    mo = self.longaddr_re.search(author)
                    if mo:
                        from_name = mo.group(1)
        if not from_email:
            from_email = config.get('smtp_from')
            from_name = config.get('smtp_from_name') or self.env.project_name
        self.replyto_email = config.get('smtp_replyto')
        self.from_email = from_email or self.replyto_email
        self.from_name = from_name
        if not self.from_email and not self.replyto_email:
            message = tag(
                tag.p(_('Unable to send email due to identity crisis.')),
                # convert explicitly to `Fragment` to avoid breaking message
                # when passing `LazyProxy` object to `Fragment`
                tag.p(to_fragment(tag_(
                    "Neither %(from_)s nor %(reply_to)s are specified in the "
                    "configuration.",
                    from_=tag.strong("[notification] smtp_from"),
                    reply_to=tag.strong("[notification] smtp_replyto")))))
            raise TracError(message, _("SMTP Notification Error"))

        Notify.notify(self, resid)

    _mime_encoding_re = re.compile(r'=\?[^?]+\?[bq]\?[^?]+\?=', re.IGNORECASE)

    def format_header(self, key, name, email=None):
        from email.Header import Header
        maxlength = MAXHEADERLEN-(len(key)+2)
        # Do not sent ridiculous short headers
        if maxlength < 10:
            raise TracError(_("Header length is too short"))
        # when it matches mime-encoding, encode as mime even if only
        # ascii characters
        header = None
        if not self._mime_encoding_re.search(name):
            try:
                tmp = name.encode('ascii')
                header = Header(tmp, 'ascii', maxlinelen=maxlength)
            except UnicodeEncodeError:
                pass
        if not header:
            header = Header(name.encode(self._charset.output_codec),
                            self._charset, maxlinelen=maxlength)
        if not email:
            return header
        else:
            header = str(header).replace('\\', r'\\') \
                                .replace('"', r'\"')
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

        if address == 'anonymous':
            return None
        if address in self.email_map:
            address = self.email_map[address]
        elif not is_email(address) and NotifyEmail.nodomaddr_re.match(address):
            if self.config.getbool('notification', 'use_short_addr'):
                return address
            domain = self.config.get('notification', 'smtp_default_domain')
            if domain:
                address = "%s@%s" % (address, domain)
            else:
                self.env.log.info("Email address w/o domain: %s", address)
                return None

        mo = self.shortaddr_re.search(address)
        if mo:
            return mo.group(1)
        mo = self.longaddr_re.search(address)
        if mo:
            return mo.group(2)
        self.env.log.info("Invalid email address: %s", address)
        return None

    def encode_header(self, key, value):
        if isinstance(value, tuple):
            return self.format_header(key, value[0], value[1])
        mo = self.longaddr_re.match(value)
        if mo:
            return self.format_header(key, mo.group(1), mo.group(2))
        return self.format_header(key, value)

    def send(self, torcpts, ccrcpts, mime_headers={}):
        from email.MIMEText import MIMEText
        from email.Utils import formatdate
        stream = self.template.generate(**self.data)
        # don't translate the e-mail stream
        t = deactivate()
        try:
            body = stream.render('text', encoding='utf-8')
        finally:
            reactivate(t)
        public_cc = self.config.getbool('notification', 'use_public_cc')
        headers = {
            'X-Mailer': 'Trac %s, by Edgewall Software' % __version__,
            'X-Trac-Version': __version__,
            'X-Trac-Project': self.env.project_name,
            'X-URL': self.env.project_url,
            'Precedence': 'bulk',
            'Auto-Submitted': 'auto-generated',
            'Subject': self.subject,
            'From': (self.from_name, self.from_email) if self.from_name
                                                      else self.from_email,
            'Reply-To': self.replyto_email
        }

        def build_addresses(rcpts):
            """Format and remove invalid addresses"""
            return filter(lambda x: x,
                          [self.get_smtp_address(addr) for addr in rcpts])

        def remove_dup(rcpts, all):
            """Remove duplicates"""
            tmp = []
            for rcpt in rcpts:
                if not rcpt in all:
                    tmp.append(rcpt)
                    all.append(rcpt)
            return tmp, all

        notify_sys = NotificationSystem(self.env)
        toaddrs = build_addresses(torcpts)
        ccaddrs = build_addresses(ccrcpts)
        accaddrs = notify_sys.smtp_always_cc_list
        bccaddrs = notify_sys.smtp_always_bcc_list

        recipients = []
        toaddrs, recipients = remove_dup(toaddrs, recipients)
        ccaddrs, recipients = remove_dup(ccaddrs, recipients)
        accaddrs, recipients = remove_dup(accaddrs, recipients)
        bccaddrs, recipients = remove_dup(bccaddrs, recipients)

        # if there is not valid recipient, leave immediately
        if len(recipients) < 1:
            self.env.log.info("no recipient for a ticket notification")
            return

        pcc = accaddrs
        if public_cc:
            pcc += ccaddrs
            if toaddrs:
                headers['To'] = ', '.join(toaddrs)
        if pcc:
            headers['Cc'] = ', '.join(pcc)
        headers['Date'] = formatdate()
        msg = MIMEText(body, 'plain')
        # Message class computes the wrong type from MIMEText constructor,
        # which does not take a Charset object as initializer. Reset the
        # encoding type to force a new, valid evaluation
        del msg['Content-Transfer-Encoding']
        msg.set_charset(self._charset)
        self.add_headers(msg, headers)
        self.add_headers(msg, mime_headers)
        NotificationSystem(self.env).send_email(self.from_email, recipients,
                                                msg.as_string())
