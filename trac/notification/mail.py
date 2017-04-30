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
from trac.util import lazy
from trac.util.compat import close_fds
from trac.util.datefmt import time_now, to_utimestamp
from trac.util.text import CRLF, exception_to_unicode, fix_eol, to_unicode
from trac.util.translation import _, tag_
from trac.web.session import get_session_attribute


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
        '(?:[a-zA-Z0-9_-]+\.)+'  # labels (but also allow '_')
        '[a-zA-Z](?:[-a-zA-Z\d]*[a-zA-Z\d])?'  # TLD
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
    if event.author and NotificationSystem(env).smtp_from_author:
        matcher = RecipientMatcher(env)
        from_ = matcher.match_from_author(event.author)
        if from_:
            return from_


class RecipientMatcher(object):

    nodomaddr_re = re.compile(r"^[-A-Za-z0-9!*+/=_.]+$")

    def __init__(self, env):
        self.env = env
        addrfmt = EMAIL_LOOKALIKE_PATTERN
        self.notify_sys = NotificationSystem(env)
        admit_domains = self.notify_sys.admit_domains_list
        if admit_domains:
            localfmt, domainfmt = addrfmt.split('@')
            domains = [domainfmt]
            domains.extend(re.escape(x) for x in admit_domains)
            addrfmt = r'%s@(?:%s)' % (localfmt, '|'.join(domains))
        self.shortaddr_re = re.compile(r'(%s)$' % addrfmt, re.IGNORECASE)
        self.longaddr_re = re.compile(r'(.*)\s+<\s*(%s)\s*>$' % addrfmt,
                                      re.IGNORECASE)
        self.ignore_domains = set(x.lower()
                                  for x in self.notify_sys.ignore_domains_list)
        self.users = self.env.get_known_users(as_dict=True)

    @lazy
    def use_short_addr(self):
        return self.notify_sys.use_short_addr

    @lazy
    def smtp_default_domain(self):
        return self.notify_sys.smtp_default_domain

    def is_email(self, address):
        if not address:
            return False
        match = self.shortaddr_re.match(address)
        if match:
            domain = address[address.find('@') + 1:].lower()
            if domain not in self.ignore_domains:
                return True
        return False

    def match_recipient(self, address):
        if not address or address == 'anonymous':
            return None

        if address in self.users:
            sid = address
            auth = 1
            address = (self.users[address][1] or '').strip() or sid
        else:
            sid = None
            auth = 0
            address = address.strip()

        if not self.is_email(address) and self.nodomaddr_re.match(address):
            if self.use_short_addr:
                return sid, auth, address
            if self.smtp_default_domain:
                address = "%s@%s" % (address, self.smtp_default_domain)
                return sid, auth, address
            self.env.log.debug("Email address w/o domain: %s", address)
            return None

        mo = self.shortaddr_re.match(address)
        if mo:
            return sid, auth, mo.group(1)
        mo = self.longaddr_re.match(address)
        if mo:
            return sid, auth, mo.group(2)
        self.env.log.debug("Invalid email address: %s", address)
        return None

    def match_from_author(self, author):
        if author:
            author = author.strip()
        recipient = self.match_recipient(author)
        if not recipient:
            return None
        sid, authenticated, address = recipient
        if not address:
            return None
        from_name = None
        if sid and authenticated and sid in self.users:
            from_name = self.users[sid][0]
        if not from_name:
            mo = self.longaddr_re.match(author)
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
        include_missing=False,
        doc="""Comma separated list of email resolver components in the order
        they will be called.  If an email address is resolved, the remaining
        resolvers will not be called.
        """)

    default_format = Option('notification', 'default_format.email',
        'text/plain', doc="Default format to distribute email notifications.")

    def __init__(self):
        self._charset = create_charset(self.config.get('notification',
                                                       'mime_encoding'))

    # INotificationDistributor methods

    def transports(self):
        yield 'email'

    def distribute(self, transport, recipients, event):
        if transport != 'email':
            return
        if not self.config.getbool('notification', 'smtp_enabled'):
            self.log.debug("%s skipped because smtp_enabled set to false",
                           self.__class__.__name__)
            return

        formats = {}
        for f in self.formatters:
            for style, realm in f.get_supported_styles(transport):
                if realm == event.realm:
                    formats[style] = f
        if not formats:
            self.log.error("%s No formats found for %s %s",
                           self.__class__.__name__, transport, event.realm)
            return
        self.log.debug("%s has found the following formats capable of "
                       "handling '%s' of '%s': %s", self.__class__.__name__,
                       transport, event.realm, ', '.join(formats.keys()))

        matcher = RecipientMatcher(self.env)
        notify_sys = NotificationSystem(self.env)
        always_cc = set(notify_sys.smtp_always_cc_list)
        addresses = {}
        for sid, auth, addr, fmt in recipients:
            if fmt not in formats:
                self.log.debug("%s format %s not available for %s %s",
                               self.__class__.__name__, fmt, transport,
                               event.realm)
                continue

            if sid and not addr:
                for resolver in self.resolvers:
                    addr = resolver.get_address_for_session(sid, auth) or None
                    if addr:
                        self.log.debug(
                            "%s found the address '%s' for '%s [%s]' via %s",
                            self.__class__.__name__, addr, sid, auth,
                            resolver.__class__.__name__)
                        break
            if sid and auth and not addr:
                addr = sid
            if notify_sys.smtp_default_domain and \
                    not notify_sys.use_short_addr and \
                    addr and matcher.nodomaddr_re.match(addr):
                addr = '%s@%s' % (addr, notify_sys.smtp_default_domain)
            if not addr:
                self.log.debug("%s was unable to find an address for "
                               "'%s [%s]'", self.__class__.__name__, sid, auth)
            elif matcher.is_email(addr) or \
                    notify_sys.use_short_addr and \
                    matcher.nodomaddr_re.match(addr):
                addresses.setdefault(fmt, set()).add(addr)
                if sid and auth and sid in always_cc:
                    always_cc.discard(sid)
                    always_cc.add(addr)
                elif notify_sys.use_public_cc:
                    always_cc.add(addr)
            else:
                self.log.debug("%s was unable to use an address '%s' for '%s "
                               "[%s]'", self.__class__.__name__, addr, sid,
                               auth)

        outputs = {}
        failed = []
        for fmt, formatter in formats.iteritems():
            if fmt not in addresses and fmt != 'text/plain':
                continue
            try:
                outputs[fmt] = formatter.format(transport, fmt, event)
            except Exception as e:
                self.log.warn('%s caught exception while '
                              'formatting %s to %s for %s: %s%s',
                              self.__class__.__name__, event.realm, fmt,
                              transport, formatter.__class__,
                              exception_to_unicode(e, traceback=True))
                failed.append(fmt)

        # Fallback to text/plain when formatter is broken
        if failed and 'text/plain' in outputs:
            for fmt in failed:
                addresses.setdefault('text/plain', set()) \
                         .update(addresses.pop(fmt, ()))

        for fmt, addrs in addresses.iteritems():
            self.log.debug("%s is sending event as '%s' to: %s",
                           self.__class__.__name__, fmt, ', '.join(addrs))
            message = self._create_message(fmt, outputs)
            if message:
                addrs = set(addrs)
                cc_addrs = sorted(addrs & always_cc)
                bcc_addrs = sorted(addrs - always_cc)
                self._do_send(transport, event, message, cc_addrs, bcc_addrs)
            else:
                self.log.warn("%s cannot send event '%s' as '%s': %s",
                              self.__class__.__name__, event.realm, fmt,
                              ', '.join(addrs))

    def _create_message(self, format, outputs):
        if format not in outputs:
            return None
        message = create_mime_multipart('related')
        maintype, subtype = format.split('/')
        preferred = create_mime_text(outputs[format], subtype, self._charset)
        if format != 'text/plain' and 'text/plain' in outputs:
            alternative = create_mime_multipart('alternative')
            alternative.attach(create_mime_text(outputs['text/plain'],
                                                'plain', self._charset))
            alternative.attach(preferred)
            preferred = alternative
        message.attach(preferred)
        return message

    def _do_send(self, transport, event, message, cc_addrs, bcc_addrs):
        notify_sys = NotificationSystem(self.env)
        smtp_from = notify_sys.smtp_from
        smtp_from_name = notify_sys.smtp_from_name or self.env.project_name
        smtp_replyto = notify_sys.smtp_replyto
        if not notify_sys.use_short_addr and notify_sys.smtp_default_domain:
            if smtp_from and '@' not in smtp_from:
                smtp_from = '%s@%s' % (smtp_from,
                                       notify_sys.smtp_default_domain)
            if smtp_replyto and '@' not in smtp_replyto:
                smtp_replyto = '%s@%s' % (smtp_replyto,
                                          notify_sys.smtp_default_domain)

        headers = {}
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
        headers['Reply-To'] = smtp_replyto

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
        notify_sys.send_email(from_addr, list(to_addrs), message.as_string())


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
        return get_session_attribute(self.env, sid, authenticated, 'email')


class AlwaysEmailSubscriber(Component):
    """Implement a policy to -always- send an email to a certain address.

    Controlled via the smtp_always_cc and smtp_always_bcc option in the
    notification section of trac.ini.
    """

    implements(INotificationSubscriber)

    def matches(self, event):
        matcher = RecipientMatcher(self.env)
        klass = self.__class__.__name__
        format = None
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
        return set(getlist('smtp_always_cc')) | \
               set(getlist('smtp_always_bcc'))


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
