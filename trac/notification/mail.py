# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2020 Edgewall Software
# Copyright (C) 2003-2005 Daniel Lundin <daniel@edgewall.com>
# Copyright (C) 2005-2006 Emmanuel Blot <emmanuel.blot@free.fr>
# Copyright (C) 2008 Stephen Hansen
# Copyright (C) 2009 Robert Corsaro
# Copyright (C) 2010-2012 Steffen Hoffmann
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import hashlib
import os
import re
import smtplib
from email import policy
from email.charset import BASE64, QP, SHORTEST, Charset
from email.header import Header
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate, parseaddr, getaddresses
from subprocess import Popen, PIPE

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
from trac.util.html import tag
from trac.util.text import CRLF, exception_to_unicode, fix_eol, to_unicode
from trac.util.translation import _, tag_
from trac.web.session import get_session_attribute


__all__ = ['AlwaysEmailSubscriber', 'EMAIL_LOOKALIKE_PATTERN',
           'EmailDistributor', 'FromAuthorEmailDecorator', 'MAXHEADERLEN',
           'RecipientMatcher', 'SendmailEmailSender', 'SessionEmailResolver',
           'SmtpEmailSender', 'create_charset', 'create_header',
           'create_message_id', 'create_mime_multipart', 'create_mime_text',
           'get_message_addresses', 'get_from_author', 'set_header']


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

# When default policy is used if [notification] mime_encoding is 'none'
# and a line is exceeded max_line_length (78 bytes by default), 'base64'
# or 'quoted-printable' is used for Content-Transfer-Encoding header.
# Using the custom policy avoids the behavior.
_policy_default = policy.SMTP  # newline is CRLF
_policy_8bit = _policy_default.clone(max_line_length=998)


def create_charset(mime_encoding):
    """Create an appropriate email charset for the given encoding.

    Valid options are 'base64' for Base64 encoding, 'qp' for
    Quoted-Printable, and 'none' for no encoding, in which case emails
    will be sent as 7bit if the content is all ASCII, or 8bit otherwise.
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


def create_header(key, value, charset):
    """Create an email Header.

    The `key` is always a string and will be converted to the
    appropriate `charset`. The `value` can either be a string or a
    two-element tuple where the first item is the name and the
    second item is the email address.

    See `set_header()` for a helper that sets a header directly on a
    message.
    """
    maxlength = MAXHEADERLEN-(len(key)+2)
    # Do not sent very short headers
    if maxlength < 10:
        raise TracError(_("Header length is too short"))

    email = None
    if isinstance(value, (tuple, list)):
        value, email = value
    if not isinstance(value, str):
        value = to_unicode(value)
    if not value:
        return email

    # when it matches mime-encoding, encode as mime even if only
    # ascii characters
    header = None
    if not _mime_encoding_re.search(value):
        try:
            tmp = value.encode('ascii')
        except UnicodeEncodeError:
            pass
        else:
            header = Header(tmp, 'ascii', maxlinelen=maxlength)
    if not header:
        header = Header(value.encode(charset.output_codec), charset,
                        maxlinelen=maxlength)
    header = str(header)
    if email:
        header = header.replace('\\', r'\\').replace('"', r'\"')
        header = '"%s" <%s>' % (header, email)
    return header


def create_address_header(addresses):
    """Create address header instance to pass to `set_header`.

    The `addresses` is a list or an iterable of addresses. The item can
    either be `str`, a `(name, address)` tuple or a `(None, address)`.
    """
    if isinstance(addresses, str):
        addresses = [(None, addresses)]
    l = []
    for item in addresses:
        if isinstance(item, Address):
            l.append(item)
            continue
        if isinstance(item, str):
            name = None
            addr = item
        elif isinstance(item, (list, tuple)):
            name, addr = item
        else:
            raise ValueError('Unrecognized item %r' % item)
        if '@' in addr:
            username, domain = addr.rsplit('@', 1)
        else:
            username = addr
            domain = ''
        l.append(Address(_replace_encoded_words(name or ''), username, domain))
    return l


def set_header(message, key, value=None, charset=None, addresses=None):
    """Create and add or replace a header in a `EmailMessage`.

    The `key` is always a string. The `value` can either be `None`, a
    string or a two-element tuple where the first item is the name and
    the second item is the email address.

    The `addresses` can either be a list or an iterable of a two-element
    tuple. When the `addresses` is given, the `value` will be ignored.

    The `charset` is no longer used.

    Example::

        set_header(my_message, 'From', ('Trac', 'noreply@ourcompany.com'))

        set_header(my_message, 'To',
                   addresses=[('Foo', 'foo@example.org'),
                              ('Bar', 'bar@example.org')])
    """
    if addresses is not None:
        header = create_address_header(addresses)
    elif isinstance(value, (list, tuple)):  # a pair of name and address
        header = create_address_header([value])
    elif isinstance(value, Address):
        header = value
    elif value is None:
        header = ''
    else:
        header = _replace_encoded_words(str(value))
    if key in message:
        message.replace_header(key, header)
    else:
        message[key] = header


_encoded_words_re = re.compile(r'=\?')


def _replace_encoded_words(text):
    """Replace '=?' with '=\u200b?' to avoid decoding encoded-words by
    `EmailMessage`.
    """
    if text:
        text = _encoded_words_re.sub('=\u200b?', text)
    return text


def create_mime_multipart(subtype):
    """Create a multipart email message.

    The `subtype` is a string that describes the type of multipart
    message you are defining. You should pick one that is defined
    by the email standards. The function does not check if the `subtype`
    is valid.

    The most common examples are:

    * `related` infers that each part is in an integrated whole, like
      images that are embedded in a html part.
    * `alternative` infers that the message contains different formats
      and the client can choose which to display based on capabilities
      and user preferences, such as a text/html with an alternative
      text/plain.
    """
    msg = EmailMessage()
    if subtype == 'related':
        msg.make_related()
    elif subtype == 'alternative':
        msg.make_alternative()
    elif subtype == 'mixed':
        msg.make_mixed()
    else:
        raise ValueError("subtype must be one of ('related', 'multipart', "
                         "'mixed'), not %r" % subtype)
    msg['MIME-Version'] = '1.0'
    return msg


def create_mime_text(body, format, charset):
    """Create a `EmailMessage` that can be added to an email message.

    :param body: a string with the body of the message.
    :param format: each text has a EmailMessage, like `text/plain`. The
        supertype is always `text`, so in the `format` parameter you
        pass the subtype, like `plain` or `html`.
    :param charset: should be created using `create_charset()`.
    """
    if isinstance(body, bytes):
        body = str(body, 'utf-8')
    cte = {BASE64: 'base64', QP: 'quoted-printable'}.get(charset.body_encoding)
    msg = EmailMessage(_policy_8bit if cte is None else _policy_default)
    msg['MIME-Version'] = '1.0'
    msg.set_content(body, subtype=format, cte=cte)
    return msg


def create_message_id(env, targetid, from_email, time, more=None):
    """Generate a predictable, but sufficiently unique message ID.

    In case you want to set the "Message ID" header, this convenience
    function will generate one by running a hash algorithm over a number
    of properties.

    :param env: the `Environment`
    :param targetid: a string that identifies the target, like
        `NotificationEvent.target`
    :param from_email: the email address that the message is sent from
    :param time: a Python `datetime`
    :param more: a string that contains additional information that
        makes this message unique
    """
    items = [env.project_url, targetid, to_utimestamp(time)]
    if more is not None:
        items.append(more.encode('ascii', 'ignore'))
    source = b'.'.join(item if isinstance(item, bytes) else
                       str(item).encode('utf-8')
                       for item in items)
    hash_type = NotificationSystem(env).message_id_hash
    try:
        h = hashlib.new(hash_type)
    except:
        raise ConfigurationError(_("Unknown hash type '%(type)s'",
                                   type=hash_type))
    h.update(source)
    host = from_email[from_email.find('@') + 1:]
    return '<%03d.%s@%s>' % (len(source), h.hexdigest(), host)


def get_message_addresses(message, name):
    return getaddresses(str(header) for header in message.get_all(name, ()))


def get_from_author(env, event):
    """Get the author name and email from a given `event`.

    The `event` parameter should be of the type `NotificationEvent`.
    If you only have the username of a Trac user, you should instead
    use the `RecipientMatcher` to find the user's details.

    The method returns a tuple that contains the name and email address
    of the user. For example: `('developer', 'developer@ourcompany.com')`.
    This tuple can be parsed by `set_header()`.
    """
    if event.author and NotificationSystem(env).smtp_from_author:
        matcher = RecipientMatcher(env)
        from_ = matcher.match_from_author(event.author)
        if from_:
            return from_


class RecipientMatcher(object):
    """Matches user names and email addresses.

    :param env: The `trac.env.Enviroment`
    """
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
        self.shortaddr_re = re.compile(r'<?(%s)>?$' % addrfmt, re.IGNORECASE)
        self.longaddr_re = re.compile(r'(.*)\s+<\s*(%s)\s*>$' % addrfmt,
                                      re.IGNORECASE)
        self.ignore_domains = set(x.lower()
                                  for x in self.notify_sys.ignore_domains_list)

    @lazy
    def use_short_addr(self):
        return self.notify_sys.use_short_addr

    @lazy
    def smtp_default_domain(self):
        return self.notify_sys.smtp_default_domain

    @lazy
    def users(self):
        return self.env.get_known_users(as_dict=True)

    def is_email(self, address):
        """Check if an email address is valid.

        This method checks against the list of domains that are
        to be ignored, which is controlled by the `ignore_domains_list`
        configuration option.

        :param address: the address to validate
        :return: `True` if it is a valid email address that is not in
            the ignore list.
        """
        if not address:
            return False
        match = self.shortaddr_re.match(address)
        if match:
            domain = address[address.find('@') + 1:].lower()
            if domain not in self.ignore_domains:
                return True
        return False

    def match_recipient(self, address):
        """Convenience function to check for an email address

        The parameter `address` can either be a valid user name,
        or an email address. The method first checks if the parameter
        is a valid user name. If so, it will look up the address. If
        there is no match, the function will check if it is a valid
        email address.

        :return: A tuple with a session id, a `1` or `0` to indicate
            whether the user is authenticated, and the matched address.
            Returns `None` when `address` does not match a valid user,
            nor a valid email address. When `address` is an email address,
            the sid will be `None` and the authentication parameter
            will always be `0`
        """
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

        if self.nodomaddr_re.match(address):
            if self.use_short_addr:
                return sid, auth, address
            if self.smtp_default_domain:
                address = "%s@%s" % (address, self.smtp_default_domain)
                return sid, auth, address
            self.env.log.debug("Email address w/o domain: %s", address)
            return None

        mo = self.shortaddr_re.match(address)
        if mo:
            address = mo.group(1)
        else:
            mo = self.longaddr_re.match(address)
            if mo:
                address = mo.group(2)
        if not self.is_email(address):
            self.env.log.debug("Invalid email address: %s", address)
            return None
        return sid, auth, address

    def match_from_author(self, author):
        """Find a name and email address for a specific user

        :param author: The username that you want to query.
        :return: On success, a two-item tuple is returned, with the
            real name and the email address of the user.
        """
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
        they will be called. If an email address is resolved, the remaining
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
                       transport, event.realm, ', '.join(formats))

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
        for fmt, formatter in formats.items():
            if fmt not in addresses and fmt != 'text/plain':
                continue
            try:
                outputs[fmt] = formatter.format(transport, fmt, event)
            except Exception as e:
                self.log.warning('%s caught exception while '
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

        for fmt, addrs in addresses.items():
            self.log.debug("%s is sending event as '%s' to: %s",
                           self.__class__.__name__, fmt, ', '.join(addrs))
            message = self._create_message(fmt, outputs)
            if message:
                addrs = set(addrs)
                cc_addrs = sorted(addrs & always_cc)
                bcc_addrs = sorted(addrs - always_cc)
                self._do_send(transport, event, message, cc_addrs, bcc_addrs)
            else:
                self.log.warning("%s cannot send event '%s' as '%s': %s",
                                 self.__class__.__name__, event.realm, fmt,
                                 ', '.join(addrs))

    def _create_message(self, format, outputs):
        if format not in outputs:
            return None
        message = create_mime_multipart('related')
        maintype, subtype = format.split('/')
        preferred = create_mime_text(outputs[format], subtype, self._charset)
        if format != 'text/plain' and 'text/plain' in outputs:
            text = create_mime_text(outputs['text/plain'], 'plain',
                                    self._charset)
            alternative = create_mime_multipart('alternative')
            alternative.attach(text)
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
        headers['To'] = 'undisclosed-recipients: ;'
        for k, v in headers.items():
            set_header(message, k, v)

        set_header(message, 'From', (smtp_from_name, smtp_from)
                                    if smtp_from_name else smtp_from)
        if cc_addrs:
            set_header(message, 'Cc', addresses=cc_addrs)
        if bcc_addrs:
            set_header(message, 'Bcc', addresses=bcc_addrs)
        set_header(message, 'Reply-To', addresses=[smtp_replyto])

        for decorator in self.decorators:
            decorator.decorate_message(event, message, self._charset)

        from_name, from_addr = parseaddr(str(message['From']))
        to_addrs = set()
        for name in ('To', 'Cc', 'Bcc'):
            values = map(str, message.get_all(name, ()))
            to_addrs.update(addr for name, addr in getaddresses(values)
                                 if addr)
        del message['Bcc']
        notify_sys.send_email(from_addr, list(to_addrs), message.as_bytes())


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
        """)

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
            set_header(message, 'From', addresses=[from_])
