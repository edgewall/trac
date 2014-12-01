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

from trac.config import BoolOption, ExtensionOption, ListOption, Option
from trac.core import *


__all__ = ['IEmailSender', 'NotificationSystem']


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
