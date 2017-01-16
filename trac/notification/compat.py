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

import re
from abc import ABCMeta, abstractmethod
from email.utils import formatdate

from genshi.builder import tag

from trac.core import *
from trac.notification.api import NotificationSystem
from trac.notification.mail import (create_charset, create_header,
                                    create_mime_text, RecipientMatcher)
from trac.util.html import to_fragment
from trac.util.text import CRLF
from trac.util.translation import _, deactivate, reactivate, tag_


__all__ = ['Notify', 'NotifyEmail']


class Notify(object):
    """Generic notification class for Trac.

    Subclass this to implement different methods.

    :since 1.1.3: deprecated and will be removed in 1.3.1
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
    """Baseclass for notification by email.

    :since 1.1.3: deprecated and will be removed in 1.3.1
    """

    from_email = 'trac+tickets@localhost'
    subject = ''
    template_name = None
    nodomaddr_re = RecipientMatcher.nodomaddr_re
    addrsep_re = re.compile(r'[;\s,]+')

    def __init__(self, env):
        super(NotifyEmail, self).__init__(env)

        self.recipient_matcher = RecipientMatcher(env)
        self.shortaddr_re = self.recipient_matcher.shortaddr_re
        self.longaddr_re = self.recipient_matcher.longaddr_re
        self._ignore_domains = self.recipient_matcher.ignore_domains
        self.name_map = {}
        self.email_map = {}
        for username, name, email in self.env.get_known_users():
            if name:
                self.name_map[username] = name
            if email:
                self.email_map[username] = email

        notify_sys = NotificationSystem(self.env)
        self._charset = create_charset(notify_sys.mime_encoding)

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

    def format_header(self, key, name, email=None):
        header = create_header(key, name, self._charset)
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
        recipient = self.recipient_matcher.match_recipient(address)
        if not recipient:
            return None
        return recipient[2]

    def encode_header(self, key, value):
        if isinstance(value, tuple):
            return self.format_header(key, value[0], value[1])
        mo = self.longaddr_re.match(value)
        if mo:
            return self.format_header(key, mo.group(1), mo.group(2))
        return self.format_header(key, value)

    def _format_body(self):
        stream = self.template.generate(**self.data)
        # don't translate the e-mail stream
        t = deactivate()
        try:
            return stream.render('text', encoding='utf-8')
        finally:
            reactivate(t)

    def send(self, torcpts, ccrcpts, mime_headers={}):
        body = self._format_body()
        public_cc = self.config.getbool('notification', 'use_public_cc')
        headers = {
            'X-Mailer': 'Trac %s, by Edgewall Software'
                        % self.env.trac_version,
            'X-Trac-Version': self.env.trac_version,
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
        msg = create_mime_text(body, 'plain', self._charset)
        self.add_headers(msg, headers)
        self.add_headers(msg, mime_headers)
        NotificationSystem(self.env).send_email(self.from_email, recipients,
                                                msg.as_string())
