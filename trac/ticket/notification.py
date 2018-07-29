# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2018 Edgewall Software
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
#
# Author: Daniel Lundin <daniel@edgewall.com>
#

from genshi.template.text import NewTextTemplate

from trac.attachment import IAttachmentChangeListener
from trac.core import *
from trac.config import *
from trac.env import IEnvironmentSetupParticipant
from trac.notification.api import (IEmailDecorator, INotificationFormatter,
                                   INotificationSubscriber,
                                   NotificationEvent, NotificationSystem)
from trac.notification.compat import NotifyEmail
from trac.notification.mail import (RecipientMatcher, create_message_id,
                                    get_from_author, set_header)
from trac.notification.model import Subscription
from trac.ticket.api import translation_deactivated
from trac.ticket.model import Ticket
from trac.util.datefmt import (datetime_now, format_date_or_datetime,
                               get_timezone, utc)
from trac.util.text import exception_to_unicode, obfuscate_email_address, \
                           shorten_line, text_width, wrap
from trac.util.translation import _
from trac.web.chrome import Chrome


class TicketNotificationSystem(Component):

    implements(IEnvironmentSetupParticipant)

    def environment_created(self):
        section = 'notification-subscriber'
        if section not in self.config.sections():
            self.config.set(section, 'always_notify_cc',
                            'CarbonCopySubscriber')
            self.config.set(section, 'always_notify_updater',
                            'TicketUpdaterSubscriber')
            self.config.set(section, 'always_notify_previous_updater',
                            'TicketPreviousUpdatersSubscriber')
            self.config.save()

    def environment_needs_upgrade(self):
        return False

    def upgrade_environment(self):
        pass

    ticket_subject_template = Option('notification', 'ticket_subject_template',
                                     '${prefix} #${ticket.id}: ${summary}',
        """A Genshi text template snippet used to get the notification
        subject.

        The template variables are documented on the
        [TracNotification#Customizingthee-mailsubject TracNotification] page.
        """)

    batch_subject_template = Option('notification', 'batch_subject_template',
                                    '${prefix} Batch modify: ${tickets_descr}',
        """Like `ticket_subject_template` but for batch modifications.
        (''since 1.0'')""")

    ambiguous_char_width = Option('notification', 'ambiguous_char_width',
                                  'single',
        """Width of ambiguous characters that should be used in the table
        of the notification mail.

        If `single`, the same width as characters in US-ASCII. This is
        expected by most users. If `double`, twice the width of
        US-ASCII characters.  This is expected by CJK users. (''since
        0.12.2'')""")


def get_ticket_notification_recipients(env, config, tktid, prev_cc=None,
                                       modtime=None):
    """Returns notifications recipients.

    :since 1.0.2: the `config` parameter is no longer used.
    :since 1.0.2: the `prev_cc` parameter is deprecated.
    :since 1.1.3: deprecated and will be removed in 1.3.1.
    """
    section = env.config['notification']
    always_notify_reporter = section.getbool('always_notify_reporter')
    always_notify_owner = section.getbool('always_notify_owner')
    always_notify_updater = section.getbool('always_notify_updater')

    cc_recipients = set(prev_cc or [])
    to_recipients = set()
    tkt = Ticket(env, tktid)

    # CC field is stored as comma-separated string. Parse to list.
    to_list = lambda cc: cc.replace(',', ' ').split()

    # Backward compatibility
    if not modtime:
        modtime = tkt['changetime']

    # Harvest email addresses from the author field of ticket_change(s)
    if always_notify_updater:
        for author, ticket in env.db_query("""
                SELECT DISTINCT author, ticket FROM ticket_change
                WHERE ticket=%s
                """, (tktid, )):
            to_recipients.add(author)

    # Harvest previous owner and cc list
    author = None
    for changelog in tkt.get_changelog(modtime):
        author, field, old = changelog[1:4]
        if field == 'owner' and always_notify_owner:
            to_recipients.add(old)
        elif field == 'cc':
            cc_recipients.update(to_list(old))

    # Harvest email addresses from the cc, reporter, and owner fields
    updater = author or tkt['reporter']
    if tkt['cc']:
        cc_recipients.update(to_list(tkt['cc']))
    if always_notify_reporter:
        to_recipients.add(tkt['reporter'])
    if always_notify_owner:
        to_recipients.add(tkt['owner'])
    if always_notify_updater and updater:
        to_recipients.add(updater)

    # Suppress the updater from the recipients if necessary
    if not always_notify_updater:
        filter_out = True
        if always_notify_reporter and updater == tkt['reporter']:
            filter_out = False
        if always_notify_owner and updater == tkt['owner']:
            filter_out = False
        if filter_out:
            to_recipients.discard(updater)

    return list(to_recipients), list(cc_recipients), \
           tkt['reporter'], tkt['owner']


class TicketChangeEvent(NotificationEvent):
    """Represent a ticket change `NotificationEvent`."""

    def __init__(self, category, target, time, author, comment=None,
                 changes=None, attachment=None):
        super(TicketChangeEvent, self).__init__('ticket', category, target,
                                                time, author)
        self.comment = comment
        if changes is None and time is not None:
            changes = target.get_change(cdate=time)
        self.changes = changes  or {}
        self.attachment = attachment


class BatchTicketChangeEvent(NotificationEvent):
    """Represent a ticket batch modify `NotificationEvent`."""

    def __init__(self, targets, time, author, comment, new_values, action):
        super(BatchTicketChangeEvent, self).__init__('ticket', 'batchmodify',
                                                     targets, time, author)
        self.comment = comment
        self.new_values = new_values
        self.action = action

    def get_ticket_change_events(self, env):
        for id in self.target:
            model = Ticket(env, id)
            yield TicketChangeEvent('changed', model, self.time, self.author,
                                    self.comment)


class TicketFormatter(Component):
    """Format `TicketChangeEvent` notifications."""

    implements(INotificationFormatter, IEmailDecorator)

    def get_supported_styles(self, transport):
        yield 'text/plain', 'ticket'

    def format(self, transport, style, event):
        if event.realm != 'ticket':
            return
        if event.category == 'batchmodify':
            return self._format_plaintext_batchmodify(event)
        if event.category in ('attachment added', 'attachment deleted'):
            return self._format_plaintext_attachment(event)
        else:
            return self._format_plaintext(event)

    def _format_plaintext(self, event):
        notify = TicketNotifyEmail(self.env)
        return notify.format(event.target, event.category == 'created',
                             event.time)

    def _format_plaintext_attachment(self, event):
        notify = TicketNotifyEmail(self.env)
        return notify.format_attachment(event.target, event.attachment,
                                        event.category == 'attachment added')

    def _format_plaintext_batchmodify(self, event):
        notify = BatchTicketNotifyEmail(self.env)
        return notify.format(event.target, event.new_values, event.comment,
                             event.action, event.author, event.time)

    def _get_message_id(self, event, newticket=None):
        ticket = event.target
        from_email = get_from_author(self.env, event)
        if from_email and isinstance(from_email, tuple):
            from_email = from_email[1]
        if not from_email:
            from_email = self.config.get('notification', 'smtp_from') or \
                         self.config.get('notification', 'smtp_replyto')
        modtime = None if newticket else event.time
        return create_message_id(self.env, '%08d' % ticket.id, from_email,
                                 modtime, ticket['reporter'] or '')

    def decorate_message(self, event, message, charset):
        if event.realm != 'ticket':
            return
        if event.category == 'batchmodify':
            notify = BatchTicketNotifyEmail(self.env)
            tickets = event.target
            tickets_descr = ', '.join(['#%s' % t for t in tickets])
            subject = notify.format_subj(tickets_descr)
        else:
            notify = TicketNotifyEmail(self.env)
            ticket = event.target
            notify.ticket = ticket
            summary = ticket['summary']
            from trac.ticket.web_ui import TicketModule
            for change in TicketModule(self.env) \
                          .grouped_changelog_entries(ticket, when=event.time):
                if 'summary' in change['fields']:
                    values = change['fields']['summary']
                    summary = "%s (was: %s)" % (values['new'], values['old'])
            subject = notify.format_subj(summary, event.category == 'created')
            msgid = self._get_message_id(event, newticket=True)
            url = self.env.abs_href.ticket(ticket.id)
            if event.category == 'created':
                set_header(message, 'Message-ID', msgid, charset)
            else:
                set_header(message, 'Message-ID', self._get_message_id(event),
                           charset)
                set_header(message, 'In-Reply-To', msgid, charset)
                set_header(message, 'References', msgid, charset)
                cnum = ticket.get_comment_number(event.time)
                if cnum is not None:
                    url += '#comment:%d' % cnum
            set_header(message, 'X-Trac-Ticket-ID', ticket.id, charset)
            set_header(message, 'X-Trac-Ticket-URL', url, charset)
        set_header(message, 'Subject', subject, charset)


class TicketOwnerSubscriber(Component):
    """Allows ticket owners to subscribe to their tickets."""

    implements(INotificationSubscriber)

    def matches(self, event):
        if event.realm != 'ticket':
            return
        if event.category not in ('created', 'changed', 'attachment added',
                                  'attachment deleted'):
            return
        ticket = event.target

        owners = [ticket['owner']]

        # Harvest previous owner
        if 'fields' in event.changes and 'owner' in event.changes['fields']:
            owners.append(event.changes['fields']['owner']['old'])

        matcher = RecipientMatcher(self.env)
        klass = self.__class__.__name__
        sids = set()
        for owner in owners:
            recipient = matcher.match_recipient(owner)
            if not recipient:
                continue
            sid, auth, addr = recipient

            # Default subscription
            for s in self.default_subscriptions():
                yield s[0], s[1], sid, auth, addr, s[2], s[3], s[4]
            if sid:
                sids.add((sid,auth))

        for s in Subscription.find_by_sids_and_class(self.env, sids, klass):
            yield s.subscription_tuple()

    def description(self):
        return _("Ticket that I own is created or modified")

    def default_subscriptions(self):
        klass = self.__class__.__name__
        return NotificationSystem(self.env).default_subscriptions(klass)

    def requires_authentication(self):
        return True


class TicketUpdaterSubscriber(Component):
    """Allows updaters to subscribe to their own updates."""

    implements(INotificationSubscriber)

    def matches(self, event):
        if event.realm != 'ticket':
            return
        if event.category not in ('created', 'changed', 'attachment added',
                                  'attachment deleted'):
            return

        matcher = RecipientMatcher(self.env)
        recipient = matcher.match_recipient(event.author)
        if not recipient:
            return
        sid, auth, addr = recipient

        # Default subscription
        for s in self.default_subscriptions():
            yield s[0], s[1], sid, auth, addr, s[2], s[3], s[4]

        if sid:
            klass = self.__class__.__name__
            for s in Subscription.find_by_sids_and_class(self.env,
                    ((sid,auth),), klass):
                yield s.subscription_tuple()

    def description(self):
        return _("I update a ticket")

    def default_subscriptions(self):
        klass = self.__class__.__name__
        return NotificationSystem(self.env).default_subscriptions(klass)

    def requires_authentication(self):
        return True


class TicketPreviousUpdatersSubscriber(Component):
    """Allows subscribing to future changes simply by updating a ticket."""

    implements(INotificationSubscriber)

    def matches(self, event):
        if event.realm != 'ticket':
            return
        if event.category not in ('created', 'changed', 'attachment added',
                                  'attachment deleted'):
            return

        updaters = [row[0] for row in self.env.db_query("""
            SELECT DISTINCT author FROM ticket_change
            WHERE ticket=%s
            """, (event.target.id, ))]

        matcher = RecipientMatcher(self.env)
        klass = self.__class__.__name__
        sids = set()
        for previous_updater in updaters:
            if previous_updater == event.author:
                continue

            recipient = matcher.match_recipient(previous_updater)
            if not recipient:
                continue
            sid, auth, addr = recipient

            # Default subscription
            for s in self.default_subscriptions():
                yield s[0], s[1], sid, auth, addr, s[2], s[3], s[4]
            if sid:
                sids.add((sid,auth))

        for s in Subscription.find_by_sids_and_class(self.env, sids, klass):
            yield s.subscription_tuple()

    def description(self):
        return _("Ticket that I previously updated is modified")

    def default_subscriptions(self):
        klass = self.__class__.__name__
        return NotificationSystem(self.env).default_subscriptions(klass)

    def requires_authentication(self):
        return True


class TicketReporterSubscriber(Component):
    """Allows the users to subscribe to tickets that they report."""

    implements(INotificationSubscriber)

    def matches(self, event):
        if event.realm != 'ticket':
            return
        if event.category not in ('created', 'changed', 'attachment added',
                                  'attachment deleted'):
            return

        ticket = event.target

        matcher = RecipientMatcher(self.env)
        recipient = matcher.match_recipient(ticket['reporter'])
        if not recipient:
            return
        sid, auth, addr = recipient

        # Default subscription
        for s in self.default_subscriptions():
            yield s[0], s[1], sid, auth, addr, s[2], s[3], s[4]

        if sid:
            klass = self.__class__.__name__
            for s in Subscription.find_by_sids_and_class(self.env,
                    ((sid,auth),), klass):
                yield s.subscription_tuple()

    def description(self):
        return _("Ticket that I reported is modified")

    def default_subscriptions(self):
        klass = self.__class__.__name__
        return NotificationSystem(self.env).default_subscriptions(klass)

    def requires_authentication(self):
        return True


class NewTicketSubscriber(Component):
    """Allows the users to subscribe to new tickets."""

    implements(INotificationSubscriber)

    # INotificationSubscriber methods

    def matches(self, event):
        if event.realm != 'ticket' or event.category != 'created':
            return

        klass = self.__class__.__name__
        for s in Subscription.find_by_class(self.env, klass):
            yield s.subscription_tuple()

    def description(self):
        return _("Any ticket is created")

    def default_subscriptions(self):
        return []

    def requires_authentication(self):
        return False


class CarbonCopySubscriber(Component):
    """Carbon copy subscriber for cc ticket field."""

    implements(INotificationSubscriber)

    def matches(self, event):
        if event.realm != 'ticket':
            return
        if event.category not in ('created', 'changed', 'attachment added',
                                  'attachment deleted'):
            return

        # CC field is stored as comma-separated string. Parse to set.
        chrome = Chrome(self.env)
        to_set = lambda cc: set(chrome.cc_list(cc))
        cc_set = to_set(event.target['cc'] or '')

        # Harvest previous CC field
        if 'fields' in event.changes and 'cc' in event.changes['fields']:
            cc_set.update(to_set(event.changes['fields']['cc']['old']))

        matcher = RecipientMatcher(self.env)
        klass = self.__class__.__name__
        sids = set()
        for cc in cc_set:
            recipient = matcher.match_recipient(cc)
            if not recipient:
                continue
            sid, auth, addr = recipient

            # Default subscription
            for s in self.default_subscriptions():
                yield s[0], s[1], sid, auth, addr, s[2], s[3], s[4]
            if sid:
                sids.add((sid,auth))

        for s in Subscription.find_by_sids_and_class(self.env, sids, klass):
            yield s.subscription_tuple()

    def description(self):
        return _("Ticket that I'm listed in the CC field is modified")

    def default_subscriptions(self):
        klass = self.__class__.__name__
        return NotificationSystem(self.env).default_subscriptions(klass)

    def requires_authentication(self):
        return True


class TicketNotifyEmail(NotifyEmail):
    """Notification of ticket changes.

    :since 1.1.3: deprecated and will be removed in 1.3.1
    """

    template_name = "ticket_notify_email.txt"
    from_email = 'trac+ticket@localhost'
    COLS = 75

    def __init__(self, env):
        super(TicketNotifyEmail, self).__init__(env)
        ambiguous_char_width = env.config.get('notification',
                                              'ambiguous_char_width',
                                              'single')
        self.ambiwidth = 2 if ambiguous_char_width == 'double' else 1
        self.ticket = None
        self.modtime = 0
        self.newticket = None
        self.reporter = None
        self.owner = None

    def notify(self, ticket, newticket=True, modtime=None):
        """Send ticket change notification e-mail (untranslated)"""
        with translation_deactivated(ticket):
            author = self._prepare_body(ticket, newticket, modtime)
            subject = self.data['subject']
            super(TicketNotifyEmail, self).notify(ticket.id, subject, author)

    def notify_attachment(self, ticket, attachment, added=True):
        """Send ticket attachment notification (untranslated)"""
        with translation_deactivated(ticket):
            self._prepare_body_attachment(ticket, attachment, added)
            author = attachment.author
            subject = self.data['subject']
            super(TicketNotifyEmail, self).notify(ticket.id, subject, author)

    def format(self, ticket, newticket=True, modtime=None):
        """Format ticket change notification e-mail (untranslated)"""
        with translation_deactivated(ticket):
            self._prepare_body(ticket, newticket, modtime)
            return self._format_body()

    def format_attachment(self, ticket, attachment, added=True):
        """Format ticket attachment notification e-mail (untranslated)"""
        with translation_deactivated(ticket):
            self._prepare_body_attachment(ticket, attachment, added)
            return self._format_body()

    def _prepare_body(self, ticket, newticket, modtime):
        self.ticket = ticket
        self.modtime = modtime
        self.newticket = newticket
        self.reporter = ''
        self.owner = ''
        link = self.env.abs_href.ticket(ticket.id)
        summary = self.ticket['summary']
        author = None

        changes_body = ''
        changes_descr = ''
        change_data = {}
        if not self.newticket and modtime:  # Ticket change
            from trac.ticket.web_ui import TicketModule
            for change in TicketModule(self.env) \
                          .grouped_changelog_entries(ticket, when=modtime):
                if not change['permanent']:  # attachment with same time...
                    continue
                author = change['author']
                change_data.update({
                    'author': self.format_author(author),
                    'comment': wrap(change['comment'], self.COLS, ' ', ' ',
                                    '\n', self.ambiwidth)
                })
                link += '#comment:%s' % str(change.get('cnum', ''))
                for field, values in change['fields'].iteritems():
                    old = values['old']
                    new = values['new']
                    newv = ''
                    if field == 'description':
                        new_descr = wrap(new, self.COLS, ' ', ' ', '\n',
                                         self.ambiwidth)
                        old_descr = wrap(old, self.COLS, '> ', '> ', '\n',
                                         self.ambiwidth)
                        old_descr = old_descr.replace(2 * '\n', '\n' + '>' +
                                                      '\n')
                        cdescr = '\n'
                        cdescr += 'Old description:' + 2 * '\n' + old_descr + \
                                  2 * '\n'
                        cdescr += 'New description:' + 2 * '\n' + new_descr + \
                                  '\n'
                        changes_descr = cdescr
                    elif field == 'summary':
                        summary = "%s (was: %s)" % (new, old)
                    elif field == 'cc':
                        addcc, delcc = self.diff_cc(old, new)
                        chgcc = ''
                        if delcc:
                            chgcc += wrap(" * cc: %s (removed)" %
                                          ', '.join(delcc),
                                          self.COLS, ' ', ' ', '\n',
                                          self.ambiwidth) + '\n'
                        if addcc:
                            chgcc += wrap(" * cc: %s (added)" %
                                          ', '.join(addcc),
                                          self.COLS, ' ', ' ', '\n',
                                          self.ambiwidth) + '\n'
                        if chgcc:
                            changes_body += chgcc
                    else:
                        if field in ['owner', 'reporter']:
                            old = self.format_author(old)
                            new = self.format_author(new)
                        elif field in ticket.time_fields:
                            format = ticket.fields.by_name(field).get('format')
                            old = self.format_time_field(old, format)
                            new = self.format_time_field(new, format)
                        newv = new
                        length = 7 + len(field)
                        spacer_old, spacer_new = ' ', ' '
                        if len(old + new) + length > self.COLS:
                            length = 5
                            if len(old) + length > self.COLS:
                                spacer_old = '\n'
                            if len(new) + length > self.COLS:
                                spacer_new = '\n'
                        chg = '* %s: %s%s%s=>%s%s' % (field, spacer_old, old,
                                                      spacer_old, spacer_new,
                                                      new)
                        chg = chg.replace('\n', '\n' + length * ' ')
                        chg = wrap(chg, self.COLS, '', length * ' ', '\n',
                                   self.ambiwidth)
                        changes_body += ' %s%s' % (chg, '\n')
                    if newv:
                        change_data[field] = {'oldvalue': old, 'newvalue': new}

        if newticket:
            author = ticket['reporter']

        ticket_values = ticket.values.copy()
        ticket_values['id'] = ticket.id
        ticket_values['description'] = wrap(
            ticket_values.get('description', ''), self.COLS,
            initial_indent=' ', subsequent_indent=' ', linesep='\n',
            ambiwidth=self.ambiwidth)
        ticket_values['new'] = self.newticket
        ticket_values['link'] = link

        subject = self.format_subj(summary, newticket)

        self.data.update({
            'ticket_props': self.format_props(),
            'ticket_body_hdr': self.format_hdr(),
            'subject': subject,
            'ticket': ticket_values,
            'changes_body': changes_body,
            'changes_descr': changes_descr,
            'change': change_data
        })
        return author

    def _prepare_body_attachment(self, ticket, attachment, added):
        self.ticket = ticket
        self.modtime = attachment.date or datetime_now(utc)
        self.newticket = False
        self.reporter = ''
        self.owner = ''
        link = self.env.abs_href.ticket(ticket.id)
        summary = self.ticket['summary']
        author = attachment.author

        # Note: no translation yet
        changes_body = wrap(" * Attachment \"%s\" %s."
                            % (attachment.filename,
                               "added" if added else "removed"),
                            self.COLS, ' ', ' ', '\n',
                            self.ambiwidth) + "\n"
        if attachment.description:
            changes_body += "\n" + wrap(attachment.description, self.COLS,
                                        ' ', ' ', '\n', self.ambiwidth)

        ticket_values = ticket.values.copy()
        ticket_values['id'] = ticket.id
        ticket_values['description'] = wrap(
            ticket_values.get('description', ''), self.COLS,
            initial_indent=' ', subsequent_indent=' ', linesep='\n',
            ambiwidth=self.ambiwidth)
        ticket_values['new'] = self.newticket
        ticket_values['link'] = link
        subject = self.format_subj(summary, False)

        self.data.update({
            'ticket_props': self.format_props(),
            'ticket_body_hdr': self.format_hdr(),
            'subject': subject,
            'ticket': ticket_values,
            'changes_body': changes_body,
            'changes_descr': '',
            'change': {'author': self.format_author(author)},
        })

    def format_props(self):
        tkt = self.ticket
        fields = [f for f in tkt.fields
                  if f['name'] not in ('summary', 'cc', 'time', 'changetime')]
        width = [0, 0, 0, 0]
        i = 0
        for f in fields:
            if f['type'] == 'textarea':
                continue
            fname = f['name']
            if fname not in tkt.values:
                continue
            fval = tkt[fname] or ''
            if fname in tkt.time_fields:
                format = tkt.fields.by_name(fname).get('format')
                fval = self.format_time_field(fval, format)
            if fval.find('\n') != -1:
                continue
            if fname in ['owner', 'reporter']:
                fval = self.format_author(fval)
            idx = 2 * (i % 2)
            width[idx] = max(self.get_text_width(f['label']), width[idx])
            width[idx + 1] = max(self.get_text_width(fval), width[idx + 1])
            i += 1
        width_l = width[0] + width[1] + 5
        width_r = width[2] + width[3] + 5
        half_cols = (self.COLS - 1) / 2
        if width_l + width_r + 1 > self.COLS:
            if ((width_l > half_cols and width_r > half_cols) or
                    (width[0] > half_cols / 2 or width[2] > half_cols / 2)):
                width_l = half_cols
                width_r = half_cols
            elif width_l > width_r:
                width_l = min((self.COLS - 1) * 2 / 3, width_l)
                width_r = self.COLS - width_l - 1
            else:
                width_r = min((self.COLS - 1) * 2 / 3, width_r)
                width_l = self.COLS - width_r - 1
        sep = width_l * '-' + '+' + width_r * '-'
        txt = sep + '\n'
        vals_lr = ([], [])
        big = []
        i = 0
        width_lr = [width_l, width_r]
        for f in [f for f in fields if f['name'] != 'description']:
            fname = f['name']
            if fname not in tkt.values:
                continue
            fval = tkt[fname] or ''
            if fname in tkt.time_fields:
                format = tkt.fields.by_name(fname).get('format')
                fval = self.format_time_field(fval, format)
            if fname in ['owner', 'reporter']:
                fval = self.format_author(fval)
            if f['type'] == 'textarea' or '\n' in unicode(fval):
                big.append((f['label'], '\n'.join(fval.splitlines())))
            else:
                # Note: f['label'] is a Babel's LazyObject, make sure its
                # __str__ method won't be called.
                str_tmp = u'%s:  %s' % (f['label'], unicode(fval))
                idx = i % 2
                initial_indent = ' ' * (width[2 * idx] -
                                        self.get_text_width(f['label']) +
                                        2 * idx)
                wrapped = wrap(str_tmp, width_lr[idx] - 2 + 2 * idx,
                               initial_indent, '  ', '\n', self.ambiwidth)
                vals_lr[idx].append(wrapped.splitlines())
                i += 1
        if len(vals_lr[0]) > len(vals_lr[1]):
            vals_lr[1].append([])

        cell_l = []
        cell_r = []
        for i in xrange(len(vals_lr[0])):
            vals_l = vals_lr[0][i]
            vals_r = vals_lr[1][i]
            vals_diff = len(vals_l) - len(vals_r)
            diff = len(cell_l) - len(cell_r)
            if diff > 0:
                # add padding to right side if needed
                if vals_diff < 0:
                    diff += vals_diff
                cell_r.extend([''] * max(diff, 0))
            elif diff < 0:
                # add padding to left side if needed
                if vals_diff > 0:
                    diff += vals_diff
                cell_l.extend([''] * max(-diff, 0))
            cell_l.extend(vals_l)
            cell_r.extend(vals_r)

        for i in range(max(len(cell_l), len(cell_r))):
            if i >= len(cell_l):
                cell_l.append(width_l * ' ')
            elif i >= len(cell_r):
                cell_r.append('')
            fmt_width = width_l - self.get_text_width(cell_l[i]) \
                        + len(cell_l[i])
            txt += u'%-*s|%s%s' % (fmt_width, cell_l[i], cell_r[i], '\n')
        if big:
            txt += sep
            for name, value in big:
                txt += '\n'.join(['', name + ':', value, '', ''])
        txt += sep
        return txt

    def parse_cc(self, txt):
        return filter(lambda x: '@' in x, txt.replace(',', ' ').split())

    def diff_cc(self, old, new):
        chrome = Chrome(self.env)
        oldcc = chrome.cc_list(old)
        newcc = chrome.cc_list(new)
        added = [self.format_author(x)
                 for x in newcc if x and x not in oldcc]
        rmved = [self.format_author(x)
                 for x in oldcc if x and x not in newcc]
        return added, rmved

    def format_author(self, author):
        return Chrome(self.env).format_author(None, author)

    def format_hdr(self):
        return '#%s: %s' % (self.ticket.id, wrap(self.ticket['summary'],
                                                 self.COLS, linesep='\n',
                                                 ambiwidth=self.ambiwidth))

    def format_subj(self, summary, newticket=True):
        template = self.config.get('notification', 'ticket_subject_template')
        template = NewTextTemplate(template.encode('utf8'))

        prefix = self.config.get('notification', 'smtp_subject_prefix')
        if prefix == '__default__':
            prefix = '[%s]' % self.env.project_name

        data = {
            'prefix': prefix,
            'summary': summary,
            'ticket': self.ticket,
            'env': self.env,
        }

        subj = template.generate(**data).render('text', encoding=None).strip()
        if not newticket:
            subj = "Re: " + subj
        return subj

    def format_time_field(self, value, format):
        tzinfo = get_timezone(self.config.get('trac', 'default_timezone'))
        return format_date_or_datetime(format, value, tzinfo=tzinfo) \
               if value else ''

    def get_recipients(self, tktid):
        to_recipients, cc_recipients, reporter, owner = \
            get_ticket_notification_recipients(self.env, self.config, tktid,
                                               modtime=self.modtime)
        self.reporter = reporter
        self.owner = owner
        return to_recipients, cc_recipients

    def get_message_id(self, rcpt, modtime=None):
        """Generate a predictable, but sufficiently unique message ID."""
        targetid = '%08d' % int(self.ticket.id)
        return create_message_id(self.env, targetid, self.from_email,
                                 modtime, rcpt)

    def send(self, torcpts, ccrcpts):
        dest = self.reporter or 'anonymous'
        hdrs = {
            'Message-ID': self.get_message_id(dest, self.modtime),
            'X-Trac-Ticket-ID': str(self.ticket.id),
            'X-Trac-Ticket-URL': self.data['ticket']['link']
        }
        if not self.newticket:
            msgid = self.get_message_id(dest)
            hdrs['In-Reply-To'] = msgid
            hdrs['References'] = msgid
        super(TicketNotifyEmail, self).send(torcpts, ccrcpts, hdrs)

    def get_text_width(self, text):
        return text_width(text, ambiwidth=self.ambiwidth)

    def obfuscate_email(self, text):
        """ Obfuscate text when `show_email_addresses` is disabled in config.
        Obfuscation happens once per email, regardless of recipients, so
        cannot use permission-based obfuscation.

        :since 1.2: Deprecated and will be removed in 1.3.1.
        """
        if self.env.config.getbool('trac', 'show_email_addresses'):
            return text
        else:
            return obfuscate_email_address(text)


class TicketAttachmentNotifier(Component):
    """Sends notification on attachment change."""

    implements(IAttachmentChangeListener)

    # IAttachmentChangeListener methods

    def attachment_added(self, attachment):
        self._notify_attachment(attachment, 'attachment added',
                                attachment.date)

    def attachment_deleted(self, attachment):
        self._notify_attachment(attachment, 'attachment deleted', None)

    def attachment_reparented(self, attachment, old_parent_realm,
                              old_parent_id):
        pass

    # Internal methods

    def _notify_attachment(self, attachment, category, time):
        resource = attachment.resource.parent
        if resource.realm != 'ticket':
            return
        ticket = Ticket(self.env, resource.id)
        event = TicketChangeEvent(category, ticket, time, ticket['reporter'],
                                  attachment=attachment)
        try:
            NotificationSystem(self.env).notify(event)
        except Exception as e:
            self.log.error("Failure sending notification when adding "
                           "attachment %s to ticket #%s: %s",
                           attachment.filename, ticket.id,
                           exception_to_unicode(e))


class BatchTicketNotifyEmail(NotifyEmail):
    """Notification of ticket batch modifications.

    :since 1.1.3: deprecated and will be removed in 1.3.1
    """

    template_name = "batch_ticket_notify_email.txt"

    def __init__(self, env):
        super(BatchTicketNotifyEmail, self).__init__(env)

    def notify(self, tickets, new_values, comment, action, author,
               modtime=None):
        """Send batch ticket change notification e-mail (untranslated)"""
        tickets = self._sort_tickets_by_priority(tickets)
        with translation_deactivated():
            self._notify(tickets, new_values, comment, action, author, modtime)

    def _notify(self, tickets, new_values, comment, action, author, modtime):
        self._prepare_body(tickets, new_values, comment, action, author,
                           modtime)
        subject = self.data['subject']
        super(BatchTicketNotifyEmail, self).notify(tickets, subject, author)

    def format(self, tickets, new_values, comment, action, author,
               modtime=None):
        """Format batch ticket change notification e-mail (untranslated)"""
        with translation_deactivated():
            self._prepare_body(tickets, new_values, comment, action, author,
                               modtime)
            return self._format_body()

    def _prepare_body(self, tickets, new_values, comment, action, author,
                      modtime):
        self.tickets = tickets
        self.reporter = ''
        self.owner = ''
        self.modtime = modtime
        changes_descr = '\n'.join('%s to %s' % (prop, val)
                                  for prop, val in new_values.iteritems())
        tickets_descr = ', '.join('#%s' % t for t in tickets)
        subject = self.format_subj(tickets_descr)
        link = self.env.abs_href.query(id=','.join(str(t) for t in tickets))
        self.data.update({
            'tickets_descr': tickets_descr,
            'changes_descr': changes_descr,
            'comment': comment,
            'action': action,
            'author': author,
            'subject': subject,
            'ticket_query_link': link,
        })

    def _sort_tickets_by_priority(self, tickets):
        with self.env.db_query as db:
            tickets = [int(id_) for id_ in tickets]
            holders = ','.join(['%s'] * len(tickets))
            rows = db("""
                SELECT id FROM ticket AS t
                LEFT OUTER JOIN enum p
                    ON p.type='priority' AND p.name=t.priority
                WHERE t.id IN (%s)
                ORDER BY COALESCE(p.value,'')='', %s, t.id
                """ % (holders, db.cast('p.value', 'int')),
                tickets)
            return [row[0] for row in rows]

    def format_subj(self, tickets_descr):
        template = self.config.get('notification', 'batch_subject_template')
        template = NewTextTemplate(template.encode('utf8'))

        prefix = self.config.get('notification', 'smtp_subject_prefix')
        if prefix == '__default__':
            prefix = '[%s]' % self.env.project_name

        data = {
            'prefix': prefix,
            'tickets_descr': tickets_descr,
            'env': self.env,
        }
        subj = template.generate(**data).render('text', encoding=None).strip()
        return shorten_line(subj)

    def get_recipients(self, tktids):
        all_to_recipients = set()
        all_cc_recipients = set()
        for t in tktids:
            to_recipients, cc_recipients, reporter, owner = \
                get_ticket_notification_recipients(self.env, self.config, t,
                                                   modtime=self.modtime)
            all_to_recipients.update(to_recipients)
            all_cc_recipients.update(cc_recipients)
        return list(all_to_recipients), list(all_cc_recipients)

    def get_message_id(self, modtime=None):
        targetid = ','.join(map(str, self.tickets))
        return create_message_id(self.env, targetid, self.from_email, modtime)

    def send(self, torcpts, ccrcpts):
        hdrs = {'Message-ID': self.get_message_id(self.modtime)}
        super(BatchTicketNotifyEmail, self).send(torcpts, ccrcpts, hdrs)
