# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2018 Edgewall Software
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

from collections import defaultdict
from operator import itemgetter

from trac.config import (BoolOption, ConfigSection, ExtensionOption,
                         ListOption, Option)
from trac.core import Component, Interface, ExtensionPoint
from trac.util import as_bool, lazy, to_list


__all__ = ['IEmailAddressResolver', 'IEmailDecorator', 'IEmailSender',
           'INotificationDistributor', 'INotificationFormatter',
           'INotificationSubscriber', 'NotificationEvent',
           'NotificationSystem', 'get_target_id', 'parse_subscriber_config']


class INotificationDistributor(Interface):
    """Deliver events over some transport (i.e. messaging protocol)."""

    def transports():
        """Return a list of supported transport names."""

    def distribute(transport, recipients, event):
        """Distribute the notification event.

        :param transport: the name of a supported transport
        :param recipients: a list of (sid, authenticated, address, format)
                           tuples, where either `sid` or `address` can be
                           `None`
        :param event: a `NotificationEvent`
        """


class INotificationFormatter(Interface):
    """Convert events into messages appropriate for a given transport."""

    def get_supported_styles(transport):
        """Return a list of supported styles.

        :param transport: the name of a transport
        :return: a list of tuples (style, realm)
        """

    def format(transport, style, event):
        """Convert the event to an appropriate message.

        :param transport: the name of a transport
        :param style: the name of a supported style
        :return: The return type of this method depends on transport and must
                 be compatible with the `INotificationDistributor` that
                 handles messages for this transport.
        """


class INotificationSubscriber(Interface):
    """Subscribe to notification events."""

    def matches(event):
        """Return a list of subscriptions that match the given event.

        :param event: a `NotificationEvent`
        :return: a list of tuples (class, distributor, sid, authenticated,
                 address, format, priority, adverb), where small `priority`
                 values override larger ones and `adverb` is either
                 'always' or 'never'.
        """

    def description():
        """Description of the subscription shown in the preferences UI."""

    def requires_authentication():
        """Can only authenticated users subscribe?"""

    def default_subscriptions():
        """Optionally return a list of default subscriptions.

        Default subscriptions that the module will automatically generate.
        This should only be used in reasonable situations, where users can be
        determined by the event itself.  For instance, ticket author has a
        default subscription that is controlled via trac.ini.  This is because
        we can lookup the ticket author during the event and create a
        subscription for them.  Default subscriptions should be low priority
        so that the user can easily override them.

        :return: a list of tuples (class, distributor, format, priority,
                 adverb)
        """


class IEmailAddressResolver(Interface):
    """Map sessions to email addresses."""

    def get_address_for_session(sid, authenticated):
        """Map a session id and authenticated flag to an e-mail address.

        :param sid: the session id
        :param authenticated: 1 for authenticated sessions, 0 otherwise
        :return: an email address or `None`
        """


class IEmailDecorator(Interface):
    def decorate_message(event, message, charset):
        """Manipulate the message before it is sent on it's way.

        :param event: a `NotificationEvent`
        :param message: an `email.message.Message` to manipulate
        :param charset: the `email.charset.Charset` to use
        """


class IEmailSender(Interface):
    """Extension point interface for components that allow sending e-mail."""

    def send(from_addr, recipients, message):
        """Send message to recipients."""


def get_target_id(target):
    """Extract the resource ID from event targets.

    :param target: a resource model (e.g. `Ticket` or `WikiPage`)
    :return: the resource ID
    """
    # Common Trac resource.
    if hasattr(target, 'id'):
        return str(target.id)
    # Wiki page special case.
    elif hasattr(target, 'name'):
        return target.name
    # Last resort: just stringify.
    return str(target)


def parse_subscriber_config(rawsubscriptions):
    """Given a list of options from [notification-subscriber]"""

    required_attrs = {
        'distributor': 'email',
        'priority': 100,
        'adverb': 'always',
        'format': None,
    }
    optional_attrs = {}
    known_attrs = required_attrs.copy()
    known_attrs.update(optional_attrs)

    byname = defaultdict(dict)
    for option, value in rawsubscriptions:
        parts = option.split('.', 1)
        name = parts[0]
        if len(parts) == 1:
            byname[name].update({'name': name, 'class': value.strip()})
        else:
            attribute = parts[1]
            known = known_attrs.get(attribute)
            if known is None or isinstance(known, basestring):
                pass
            elif isinstance(known, int):
                value = int(value)
            elif isinstance(known, bool):
                value = as_bool(value)
            elif isinstance(known, list):
                value = to_list(value)
            byname[name][attribute] = value

    byclass = defaultdict(list)
    for name, attributes in byname.items():
        for key, value in required_attrs.items():
            attributes.setdefault(key, value)
        byclass[attributes['class']].append(attributes)
    for values in byclass.values():
        values.sort(key=lambda value: (value['priority'], value['name']))

    return byclass


class NotificationEvent(object):
    """All data related to a particular notification event.

    :param realm: the resource realm (e.g. 'ticket' or 'wiki')
    :param category: the kind of event that happened to the resource
                     (e.g. 'created', 'changed' or 'deleted')
    :param target: the resource model (e.g. Ticket or WikiPage) or `None`
    :param time: the `datetime` when the event happened
    """

    def __init__(self, realm, category, target, time, author=""):
        self.realm = realm
        self.category = category
        self.target = target
        self.time = time
        self.author = author


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
            """)

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
        """)

    use_public_cc = BoolOption('notification', 'use_public_cc', 'false',
        """Addresses in the To and Cc fields are visible to all recipients.

        If this option is disabled, recipients are put in the Bcc list.
        """)

    use_short_addr = BoolOption('notification', 'use_short_addr', 'false',
        """Permit email address without a host/domain (i.e. username only).

        The SMTP server should accept those addresses, and either append
        a FQDN or use local delivery. See also `smtp_default_domain`. Do not
        use this option with a public SMTP server.
        """)

    smtp_subject_prefix = Option('notification', 'smtp_subject_prefix',
                                 '__default__',
        """Text to prepend to subject line of notification emails.

        If the setting is not defined, then `[$project_name]` is used as the
        prefix. If no prefix is desired, then specifying an empty option
        will disable it.
        """)

    message_id_hash = Option('notification', 'message_id_hash', 'md5',
        """Hash algorithm to create unique Message-ID header.
        ''(since 1.0.13)''""")

    notification_subscriber_section = ConfigSection('notification-subscriber',
        """The notifications subscriptions are controlled by plugins. All
        `INotificationSubscriber` components are in charge. These components
        may allow to be configured via this section in the `trac.ini` file.

        See TracNotification for more details.

        Available subscribers:
        [[SubscriberList]]
        """)

    distributors = ExtensionPoint(INotificationDistributor)
    subscribers = ExtensionPoint(INotificationSubscriber)

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

    @lazy
    def subscriber_defaults(self):
        rawsubscriptions = self.notification_subscriber_section.options()
        return parse_subscriber_config(rawsubscriptions)

    def default_subscriptions(self, klass):
        for d in self.subscriber_defaults[klass]:
            yield (klass, d['distributor'], d['format'], d['priority'],
                   d['adverb'])

    def get_default_format(self, transport):
        return self.config.get('notification',
                               'default_format.' + transport) or 'text/plain'

    def get_preferred_format(self, sid, authenticated, transport):
        from trac.notification.prefs import get_preferred_format
        return get_preferred_format(self.env, sid, authenticated,
                                    transport) or \
               self.get_default_format(transport)

    def send_email(self, from_addr, recipients, message):
        """Send message to recipients via e-mail."""
        self.email_sender.send(from_addr, recipients, message)

    def notify(self, event):
        """Distribute an event to all subscriptions.

        :param event: a `NotificationEvent`
        """
        self.distribute_event(event, self.subscriptions(event))

    def distribute_event(self, event, subscriptions):
        """Distribute a event to all subscriptions.

        :param event: a `NotificationEvent`
        :param subscriptions: a list of tuples (sid, authenticated, address,
                              transport, format) where either sid or
                              address can be `None`
        """
        packages = {}
        for sid, authenticated, address, transport, format in subscriptions:
            package = packages.setdefault(transport, {})
            key = (sid, authenticated, address)
            if key in package:
                continue
            package[key] = format or self.get_preferred_format(
                                                sid, authenticated, transport)
        for distributor in self.distributors:
            for transport in distributor.transports():
                if transport in packages:
                    recipients = [(k[0], k[1], k[2], format)
                                  for k, format
                                  in packages[transport].iteritems()]
                    distributor.distribute(transport, recipients, event)

    def subscriptions(self, event):
        """Return all subscriptions for a given event.

        :return: a list of (sid, authenticated, address, transport, format)
        """
        subscriptions = []
        for subscriber in self.subscribers:
            if event.category == 'batchmodify':
                for ticket_event in event.get_ticket_change_events(self.env):
                    subscriptions.extend(x for x in subscriber.matches(ticket_event) if x)
            else:
                subscriptions.extend(x for x in subscriber.matches(event) if x)

        # For each (transport, sid, authenticated) combination check the
        # subscription with the highest priority:
        # If it is "always" keep it. If it is "never" drop it.

        # sort by (transport, sid, authenticated, priority)
        ordered = sorted(subscriptions, key=itemgetter(1,2,3,6))
        previous_combination = None
        for rule, transport, sid, auth, addr, fmt, prio, adverb in ordered:
            if (transport, sid, auth) == previous_combination:
                continue
            if adverb == 'always':
                self.log.debug("Adding (%s [%s]) for 'always' on rule (%s) "
                               "for (%s)", sid, auth, rule, transport)
                yield (sid, auth, addr, transport, fmt)
            else:
                self.log.debug("Ignoring (%s [%s]) for 'never' on rule (%s) "
                               "for (%s)", sid, auth, rule, transport)
            # Also keep subscriptions without sid (raw email subscription)
            if sid:
                previous_combination = (transport, sid, auth)
