# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2014 Edgewall Software
# Copyright (C) 2003-2005 Daniel Lundin <daniel@edgewall.com>
# Copyright (C) 2005-2006 Emmanuel Blot <emmanuel.blot@free.fr>
# Copyright (C) 2008 Stephen Hansen
# Copyright (C) 2009 Robert Corsaro
# Copyright (C) 2010-2012 Steffen Hoffmann
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import hashlib
import os
import re
import smtplib
from email.charset import BASE64, QP, SHORTEST, Charset
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, parseaddr, getaddresses
from subprocess import Popen, PIPE

from genshi.builder import tag

from trac.config import (BoolOption, ConfigurationError, IntOption, Option,
                         OrderedExtensionsOption)
from trac.core import Component, ExtensionPoint, TracError, implements
from trac.notification.api import (
    get_target_id, IEmailAddressResolver, IEmailDecorator, IEmailSender,
    INotificationDistributor, INotificationFormatter, INotificationSubscriber,
    NotificationSystem)
from trac.util.compat import close_fds
from trac.util.datefmt import time_now, to_utimestamp
from trac.util.text import CRLF, exception_to_unicode, fix_eol, to_unicode
from trac.util.translation import _, tag_


__all__ = ['AlwaysEmailSubscriber', 'EMAIL_LOOKALIKE_PATTERN',
           'EmailDistributor', 'FromAuthorEmailDecorator', 'MAXHEADERLEN',
           'RecipientMatcher', 'SendmailEmailSender', 'SessionEmailResolver',
           'SmtpEmailSender', 'create_charset', 'create_header',
           'create_message_id', 'create_mime_multipart', 'create_mime_text',
           'get_from_author', 'set_header']


MAXHEADERLEN = 76
EMAIL_LOOKALIKE_PATTERN = (
        # the local part
        r"[a-zA-Z0-9.'+_-]+" '@'
        # the domain name part (RFC:1035)
        '(?:[a-zA-Z0-9_-]+\.)+' # labels (but also allow '_')
        '[a-zA-Z](?:[-a-zA-Z\d]*[a-zA-Z\d])?' # TLD
        )

_mime_encoding_re = re.compile(r'=\?[^?]+\?[bq]\?[^?]+\?=', re.IGNORECASE)

local_hostname = None


def create_charset(mime_encoding):
    """Create an appropriate email charset for the given encoding.

    Valid options are 'base64' for Base64 encoding, 'qp' for
    Quoted-Printable, and 'none' for no encoding, in which case mails will
    be sent as 7bit if the content is all ASCII, or 8bit otherwise.
    """
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


def set_header(message, key, value, charset):
    """Create and add or replace a header."""
    email = None
    if isinstance(value, (tuple, list)):
        value, email = value
    if not isinstance(value, basestring):
        value = to_unicode(value)
    header = create_header(key, value, charset)
    if email:
        header = str(header).replace('\\', r'\\') \
                            .replace('"', r'\"')
        header = '"%s" <%s>' % (header, email)
    if key in message:
        message.replace_header(key, header)
    else:
        message[key] = header


def create_mime_multipart(subtype):
    """Create an appropriate email `MIMEMultipart`."""
    msg = MIMEMultipart(subtype)
    del msg['Content-Transfer-Encoding']
    return msg


def create_mime_text(body, format, charset):
    """Create an appropriate email `MIMEText`."""
    if isinstance(body, unicode):
        body = body.encode('utf-8')
    msg = MIMEText(body, format)
    # Message class computes the wrong type from MIMEText constructor,
    # which does not take a Charset object as initializer. Reset the
    # encoding type to force a new, valid evaluation
    del msg['Content-Transfer-Encoding']
    msg.set_charset(charset)
    return msg


def create_message_id(env, targetid, from_email, time, more=None):
    """Generate a predictable, but sufficiently unique message ID."""
    items = [env.project_url.encode('utf-8'), targetid, to_utimestamp(time)]
    if more is not None:
        items.append(more.encode('ascii', 'ignore'))
    source = '.'.join(str(item) for item in items)
    hash_type = NotificationSystem(env).message_id_hash
    try:
        h = hashlib.new(hash_type)
    except:
        raise ConfigurationError(_("Unknown hash type '%(type)s'",
                                   type=hash_type))
    h.update(source)
    host = from_email[from_email.find('@') + 1:]
    return '<%03d.%s@%s>' % (len(source), h.hexdigest(), host)


def get_from_author(env, event):
    if event.author and env.config.getbool('notification',
                                           'smtp_from_author'):
        matcher = RecipientMatcher(env)
        from_ = matcher.match_from_author(event.author)
        if from_:
            return from_


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

    def match_from_author(self, author):
        recipient = self.match_recipient(author)
        if not recipient:
            return None
        sid, authenticated, address = recipient
        from_name = None
        if sid and authenticated:
            from_name = self.name_map.get(sid)
        if not from_name:
            mo = self.longaddr_re.search(author)
            if mo:
                from_name = mo.group(1)
        return (from_name, address) if from_name else address


class EmailDistributor(Component):
    """Distributes notification events as emails."""

    implements(INotificationDistributor)

    formatters = ExtensionPoint(INotificationFormatter)
    decorators = ExtensionPoint(IEmailDecorator)

    resolvers = OrderedExtensionsOption('notification',
        'email_address_resolvers', IEmailAddressResolver,
        'SessionEmailResolver',
        """Comma seperated list of email resolver components in the order
        they will be called.  If an email address is resolved, the remaining
        resolvers will not be called.
        """)

    def __init__(self):
        self._charset = create_charset(self.config.get('notification',
                                                       'mime_encoding'))

    # INotificationDistributor
    def transports(self):
        yield 'email'

    def distribute(self, transport, recipients, event):
        if transport != 'email':
            return
        if not self.config.getbool('notification', 'smtp_enabled'):
            self.log.debug("EmailDistributor smtp_enabled set to false")
            return

        formats = {}
        for f in self.formatters:
            for style, realm in f.get_supported_styles(transport):
                if realm == event.realm:
                    formats[style] = f
        if not formats:
            self.log.error("EmailDistributor No formats found for %s %s",
                           transport, event.realm)
            return
        self.log.debug("EmailDistributor has found the following formats "
                       "capable of handling '%s' of '%s': %s", transport,
                       event.realm, ', '.join(formats.keys()))

        notify_sys = NotificationSystem(self.env)
        always_cc = set(notify_sys.smtp_always_cc_list)
        use_public_cc = notify_sys.use_public_cc
        addresses = {}
        for sid, authed, addr, fmt in recipients:
            if fmt not in formats:
                self.log.debug("EmailDistributor format %s not available for "
                               "%s %s", fmt, transport, event.realm)
                continue

            if sid and not addr:
                for resolver in self.resolvers:
                    addr = resolver.get_address_for_session(sid, authed)
                    if addr:
                        status = 'authenticated' if authed else \
                                 'not authenticated'
                        self.log.debug("EmailDistributor found the address "
                                       "'%s' for '%s (%s)' via %s", addr, sid,
                                       status, resolver.__class__.__name__)
                        break
            if addr:
                addresses.setdefault(fmt, set()).add(addr)
                if use_public_cc or sid and sid in always_cc:
                    always_cc.add(addr)
            else:
                status = 'authenticated' if authed else 'not authenticated'
                self.log.debug("EmailDistributor was unable to find an "
                               "address for: %s (%s)", sid, status)

        outputs = {}
        failed = []
        for fmt, formatter in formats.iteritems():
            if fmt not in addresses and fmt != 'text/plain':
                continue
            try:
                outputs[fmt] = formatter.format(transport, fmt, event)
            except Exception as e:
                self.log.warn('EmailDistributor caught exception while '
                              'formatting %s to %s for %s: %s%s',
                              event.realm, fmt, transport, formatter.__class__,
                              exception_to_unicode(e, traceback=True))
                failed.append(fmt)

        # Fallback to text/plain when formatter is broken
        if failed and 'text/plain' in outputs:
            for fmt in failed:
                addresses.setdefault('text/plain', set()) \
                         .update(addresses.pop(fmt, ()))

        for fmt, addrs in addresses.iteritems():
            self.log.debug("EmailDistributor is sending event as '%s' to: %s",
                           fmt, ', '.join(addrs))
            message = self._create_message(fmt, outputs)
            if message:
                addrs = set(addrs)
                cc_addrs = sorted(addrs & always_cc)
                bcc_addrs = sorted(addrs - always_cc)
                self._do_send(transport, event, message, cc_addrs, bcc_addrs)
            else:
                self.log.warn("EmailDistributor cannot send event '%s' as "
                              "'%s': %s", event.realm, fmt, ', '.join(addrs))

    def _create_message(self, format, outputs):
        if format not in outputs:
            return None
        message = create_mime_multipart('related')
        maintype, subtype = format.split('/')
        preferred = create_mime_text(outputs[format], subtype, self._charset)
        if format != 'text/plain' and 'text/plain' in outputs:
            alternative = create_mime_multipart('alternative')
            alternative.attach(create_mime_text(outputs['text/plain'], 'plain',
                                                self._charset))
            alternative.attach(preferred)
            preferred = alternative
        message.attach(preferred)
        return message

    def _do_send(self, transport, event, message, cc_addrs, bcc_addrs):
        config = self.config['notification']
        smtp_from = config.get('smtp_from')
        smtp_from_name = config.get('smtp_from_name') or self.env.project_name
        smtp_reply_to = config.get('smtp_replyto')

        headers = dict()
        headers['X-Mailer'] = 'Trac %s, by Edgewall Software'\
                              % self.env.trac_version
        headers['X-Trac-Version'] = self.env.trac_version
        headers['X-Trac-Project'] = self.env.project_name
        headers['X-URL'] = self.env.project_url
        headers['X-Trac-Realm'] = event.realm
        headers['Precedence'] = 'bulk'
        headers['Auto-Submitted'] = 'auto-generated'
        if isinstance(event.target, (list, tuple)):
            targetid = ','.join(map(get_target_id, event.target))
        else:
            targetid = get_target_id(event.target)
        rootid = create_message_id(self.env, targetid, smtp_from, None,
                                   more=event.realm)
        if event.category == 'created':
            headers['Message-ID'] = rootid
        else:
            headers['Message-ID'] = create_message_id(self.env, targetid,
                                                      smtp_from, event.time,
                                                      more=event.realm)
            headers['In-Reply-To'] = rootid
            headers['References'] = rootid
        headers['Date'] = formatdate()
        headers['From'] = (smtp_from_name, smtp_from) \
                          if smtp_from_name else smtp_from
        headers['To'] = 'undisclosed-recipients: ;'
        if cc_addrs:
            headers['Cc'] = ', '.join(cc_addrs)
        if bcc_addrs:
            headers['Bcc'] = ', '.join(bcc_addrs)
        headers['Reply-To'] = smtp_reply_to

        for k, v in headers.iteritems():
            set_header(message, k, v, self._charset)
        for decorator in self.decorators:
            decorator.decorate_message(event, message, self._charset)

        from_name, from_addr = parseaddr(str(message['From']))
        to_addrs = set()
        for name in ('To', 'Cc', 'Bcc'):
            values = map(str, message.get_all(name, ()))
            to_addrs.update(addr for name, addr in getaddresses(values)
                                 if addr)
        del message['Bcc']
        NotificationSystem(self.env).send_email(from_addr, list(to_addrs),
                                                message.as_string())


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
        global local_hostname
        # Ensure the message complies with RFC2822: use CRLF line endings
        message = fix_eol(message, CRLF)

        self.log.info("Sending notification through SMTP at %s:%d to %s",
                      self.smtp_server, self.smtp_port, recipients)
        try:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port,
                                  local_hostname)
            local_hostname = server.local_hostname
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
        start = time_now()
        server.sendmail(from_addr, recipients, message)
        t = time_now() - start
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


class SessionEmailResolver(Component):
    """Gets the email address from the user preferences / session."""

    implements(IEmailAddressResolver)

    def get_address_for_session(self, sid, authenticated):
        with self.env.db_query as db:
            cursor = db.cursor()
            cursor.execute("""
                SELECT value
                  FROM session_attribute
                 WHERE sid=%s
                   AND authenticated=%s
                   AND name=%s
            """, (sid, 1 if authenticated else 0, 'email'))
            result = cursor.fetchone()
            if result:
                return result[0]
            return None


class AlwaysEmailSubscriber(Component):
    """Implement a policy to -always- send an email to a certain address.

    Controlled via the smtp_always_cc and smtp_always_bcc option in the
    notification section of trac.ini.
    """

    implements(INotificationSubscriber)

    def matches(self, event):
        matcher = RecipientMatcher(self.env)
        klass = self.__class__.__name__
        format = 'text/plain'
        priority = 0
        for address in self._get_address_list():
            recipient = matcher.match_recipient(address)
            if recipient:
                sid, authenticated, address = recipient
                yield (klass, 'email', sid, authenticated, address, format,
                       priority, 'always')

    def description(self):
        return None  # not configurable

    def requires_authentication(self):
        return False

    def default_subscriptions(self):
        return ()

    def _get_address_list(self):
        section = self.config['notification']
        def getlist(name):
            return section.getlist(name, sep=(',', ' '), keep_empty=False)
        return set(getlist('smtp_always_cc')) | set(getlist('smtp_always_bcc'))


class FromAuthorEmailDecorator(Component):
    """Implement a policy to use the author of the event as the sender in
    notification emails.

    Controlled via the smtp_from_author option in the notification section
    of trac.ini.
    """

    implements(IEmailDecorator)

    def decorate_message(self, event, message, charset):
        from_ = get_from_author(self.env, event)
        if from_:
            set_header(message, 'From', from_, charset)
