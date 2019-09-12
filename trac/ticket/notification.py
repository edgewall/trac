# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2019 Edgewall Software
# Copyright (C) 2003-2005 Daniel Lundin <daniel@edgewall.com>
# Copyright (C) 2005-2006 Emmanuel Blot <emmanuel.blot@free.fr>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.
#
# Author: Daniel Lundin <daniel@edgewall.com>
#

import re

from trac.api import IEnvironmentSetupParticipant
from trac.attachment import IAttachmentChangeListener
from trac.core import *
from trac.config import *
from trac.notification.api import (IEmailDecorator, INotificationFormatter,
                                   INotificationSubscriber,
                                   NotificationEvent, NotificationSystem)
from trac.notification.mail import (RecipientMatcher, create_header,
                                    create_message_id, get_from_author,
                                    get_message_addresses, set_header)
from trac.notification.model import Subscription
from trac.perm import PermissionSystem
from trac.ticket.api import translation_deactivated
from trac.ticket.model import Ticket, sort_tickets_by_priority
from trac.util import lazy
from trac.util.datefmt import format_date_or_datetime, get_timezone
from trac.util.text import (CRLF, exception_to_unicode, jinja2template,
                            shorten_line, text_width, wrap)
from trac.util.translation import _
from trac.web.chrome import Chrome


class TicketNotificationSystem(Component):

    implements(IEnvironmentSetupParticipant)

    def environment_created(self):
        section = 'notification-subscriber'
        if section not in self.config:
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


class TicketChangeEvent(NotificationEvent):
    """Represent a ticket change `NotificationEvent`."""

    def __init__(self, category, target, time, author, comment=None,
                 changes=None, attachment=None):
        super(TicketChangeEvent, self).__init__('ticket', category, target,
                                                time, author)
        self.comment = comment
        if changes is None and time is not None:
            changes = target.get_change(cdate=time)
        self.changes = changes or {}
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

    COLS = 75
    addrsep_re = re.compile(r'[;\s,]+')

    ambiguous_char_width = Option('notification', 'ambiguous_char_width',
                                  'single',
        """Width of ambiguous characters that should be used in the table
        of the notification mail.

        If `single`, the same width as characters in US-ASCII. This is
        expected by most users. If `double`, twice the width of
        US-ASCII characters.  This is expected by CJK users.
        """)

    batch_subject_template = Option('notification', 'batch_subject_template',
                                    '${prefix} Batch modify: ${tickets_descr}',
        """Like `ticket_subject_template` but for batch modifications.
        (''since 1.0'')""")

    ticket_subject_template = Option('notification', 'ticket_subject_template',
                                     '${prefix} #${ticket.id}: ${summary}',
        """A Jinja2 text template snippet used to get the notification
        subject.

        The template variables are documented on the
        [TracNotification#Customizingthee-mailsubject TracNotification] page.
        """)

    @lazy
    def ambiwidth(self):
        return 2 if self.ambiguous_char_width == 'double' else 1

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
        """Format ticket change notification e-mail (untranslated)"""
        ticket = event.target
        newticket = event.category == 'created'
        with translation_deactivated(ticket):
            link = self.env.abs_href.ticket(ticket.id)

            changes_body = ''
            changes_descr = ''
            change_data = {}
            if not newticket and event.time:  # Ticket change
                from trac.ticket.web_ui import TicketModule
                for change in TicketModule(self.env) \
                              .grouped_changelog_entries(ticket,
                                                         when=event.time):
                    if not change['permanent']:  # attachment with same time...
                        continue
                    author = change['author']
                    change_data.update({
                        'author': self._format_author(author),
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
                        elif field == 'cc':
                            addcc, delcc = self._diff_cc(old, new)
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
                                old = self._format_author(old)
                                new = self._format_author(new)
                            elif field in ticket.time_fields:
                                format = ticket.fields.by_name(field) \
                                                      .get('format')
                                old = self._format_time_field(old, format)
                                new = self._format_time_field(new, format)
                            newv = new
                            length = 7 + len(field)
                            spacer_old, spacer_new = ' ', ' '
                            if len(old + new) + length > self.COLS:
                                length = 5
                                if len(old) + length > self.COLS:
                                    spacer_old = '\n'
                                if len(new) + length > self.COLS:
                                    spacer_new = '\n'
                            chg = '* %s: %s%s%s=>%s%s' \
                                  % (field, spacer_old, old,
                                     spacer_old, spacer_new, new)
                            chg = chg.replace('\n', '\n' + length * ' ')
                            chg = wrap(chg, self.COLS, '', length * ' ', '\n',
                                       self.ambiwidth)
                            changes_body += ' %s%s' % (chg, '\n')
                        if newv:
                            change_data[field] = {'oldvalue': old,
                                                  'newvalue': new}

            ticket_values = ticket.values.copy()
            ticket_values['id'] = ticket.id
            ticket_values['description'] = wrap(
                ticket_values.get('description', ''), self.COLS,
                initial_indent=' ', subsequent_indent=' ', linesep='\n',
                ambiwidth=self.ambiwidth)
            ticket_values['new'] = newticket
            ticket_values['link'] = link

            data = Chrome(self.env).populate_data(None, {
                'CRLF': CRLF,
                'ticket_props': self._format_props(ticket),
                'ticket_body_hdr': self._format_hdr(ticket),
                'ticket': ticket_values,
                'changes_body': changes_body,
                'changes_descr': changes_descr,
                'change': change_data
            })
            return self._format_body(data, 'ticket_notify_email.txt')

    def _format_plaintext_attachment(self, event):
        """Format ticket attachment notification e-mail (untranslated)"""
        ticket = event.target
        added = event.category == 'attachment added'
        newticket = False
        link = self.env.abs_href.ticket(ticket.id)
        author = event.attachment.author
        with translation_deactivated(ticket):
            changes_body = wrap(" * Attachment \"%s\" %s."
                                % (event.attachment.filename,
                                   "added" if added else "removed"),
                                self.COLS, ' ', ' ', '\n',
                                self.ambiwidth) + "\n"
            if event.attachment.description:
                changes_body += "\n" + wrap(event.attachment.description,
                                            self.COLS, ' ', ' ', '\n',
                                            self.ambiwidth)

            ticket_values = ticket.values.copy()
            ticket_values['id'] = ticket.id
            ticket_values['description'] = wrap(
                ticket_values.get('description', ''), self.COLS,
                initial_indent=' ', subsequent_indent=' ', linesep='\n',
                ambiwidth=self.ambiwidth)
            ticket_values['new'] = newticket
            ticket_values['link'] = link

            data = Chrome(self.env).populate_data(None, {
                'CRLF': CRLF,
                'ticket_props': self._format_props(ticket),
                'ticket_body_hdr': self._format_hdr(ticket),
                'ticket': ticket_values,
                'changes_body': changes_body,
                'changes_descr': '',
                'change': {'author': self._format_author(author)},
            })
            return self._format_body(data, 'ticket_notify_email.txt')

    def _format_plaintext_batchmodify(self, event):
        """Format batch ticket change notification e-mail (untranslated)"""
        with translation_deactivated():
            tickets = sort_tickets_by_priority(self.env, event.target)
            changes_descr = '\n'.join('%s to %s' % (prop, val)
                                      for prop, val
                                      in event.new_values.iteritems())
            tickets_descr = ', '.join('#%s' % t for t in tickets)
            link = self.env.abs_href.query(id=','.join(str(t) for t in tickets))
            data = Chrome(self.env).populate_data(None, {
                'CRLF': CRLF,
                'tickets_descr': tickets_descr,
                'changes_descr': changes_descr,
                'comment': event.comment,
                'action': event.action,
                'author': event.author,
                'ticket_query_link': link,
            })
            return self._format_body(data, 'batch_ticket_notify_email.txt')

    def _format_author(self, author):
        return Chrome(self.env).format_author(None, author)

    def _format_body(self, data, template_name):
        chrome = Chrome(self.env)
        template = chrome.load_template(template_name, text=True)
        with translation_deactivated():  # don't translate the e-mail stream
            body = chrome.render_template_string(template, data, text=True)
            return body.encode('utf-8')

    def _format_subj(self, event):
        is_newticket = event.category == 'created'
        ticket = event.target

        summary = ticket['summary']
        if event.changes and 'summary' in event.changes['fields']:
            change = event.changes['fields']['summary']
            summary = "%s (was: %s)" % (change['new'], change['old'])

        prefix = self.config.get('notification', 'smtp_subject_prefix')
        if prefix == '__default__':
            prefix = '[%s]' % self.env.project_name

        data = {
            'prefix': prefix,
            'summary': summary,
            'ticket': ticket,
            'changes': event.changes,
            'env': self.env,
        }

        template = jinja2template(self.ticket_subject_template, text=True)
        subj = template.render(**data).strip()
        if not is_newticket:
            subj = "Re: " + subj
        return subj

    def _format_subj_batchmodify(self, tickets):
        tickets_descr = ', '.join('#%s' % t for t in tickets)

        template = jinja2template(self.batch_subject_template, text=True)

        prefix = self.config.get('notification', 'smtp_subject_prefix')
        if prefix == '__default__':
            prefix = '[%s]' % self.env.project_name

        data = {
            'prefix': prefix,
            'tickets_descr': tickets_descr,
            'env': self.env,
        }
        subj = template.render(**data).strip()
        return shorten_line(subj)

    def _format_hdr(self, ticket):
        return '#%s: %s' % (ticket.id, wrap(ticket['summary'], self.COLS,
                                            linesep='\n',
                                            ambiwidth=self.ambiwidth))

    def _format_props(self, ticket):
        fields = [f for f in ticket.fields
                  if f['name'] not in ('summary', 'cc', 'time', 'changetime')]
        width = [0, 0, 0, 0]
        i = 0
        for f in fields:
            if f['type'] == 'textarea':
                continue
            fname = f['name']
            if fname not in ticket.values:
                continue
            fval = ticket[fname] or ''
            if fname in ticket.time_fields:
                format = ticket.fields.by_name(fname).get('format')
                fval = self._format_time_field(fval, format)
            if fval.find('\n') != -1:
                continue
            if fname in ['owner', 'reporter']:
                fval = self._format_author(fval)
            idx = 2 * (i % 2)
            width[idx] = max(self._get_text_width(f['label']), width[idx])
            width[idx + 1] = max(self._get_text_width(fval), width[idx + 1])
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
            if fname not in ticket.values:
                continue
            fval = ticket[fname] or ''
            if fname in ticket.time_fields:
                format = ticket.fields.by_name(fname).get('format')
                fval = self._format_time_field(fval, format)
            if fname in ['owner', 'reporter']:
                fval = self._format_author(fval)
            if f['type'] == 'textarea' or '\n' in unicode(fval):
                big.append((f['label'], '\n'.join(fval.splitlines())))
            else:
                # Note: f['label'] is a Babel's LazyObject, make sure its
                # __str__ method won't be called.
                str_tmp = u'%s:  %s' % (f['label'], unicode(fval))
                idx = i % 2
                initial_indent = ' ' * (width[2 * idx] -
                                        self._get_text_width(f['label']) +
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

        for i in xrange(max(len(cell_l), len(cell_r))):
            if i >= len(cell_l):
                cell_l.append(width_l * ' ')
            elif i >= len(cell_r):
                cell_r.append('')
            fmt_width = width_l - self._get_text_width(cell_l[i]) \
                        + len(cell_l[i])
            txt += u'%-*s|%s%s' % (fmt_width, cell_l[i], cell_r[i], '\n')
        if big:
            txt += sep
            for name, value in big:
                txt += '\n'.join(['', name + ':', value, '', ''])
        txt += sep
        return txt

    def _format_time_field(self, value, format):
        tzinfo = get_timezone(self.config.get('trac', 'default_timezone'))
        return format_date_or_datetime(format, value, tzinfo=tzinfo) \
               if value else ''

    def _diff_cc(self, old, new):
        oldcc = self.addrsep_re.split(old)
        newcc = self.addrsep_re.split(new)
        added = [self._format_author(x)
                 for x in newcc if x and x not in oldcc]
        removed = [self._format_author(x)
                   for x in oldcc if x and x not in newcc]
        return added, removed

    def _get_text_width(self, text):
        return text_width(text, ambiwidth=self.ambiwidth)

    def _get_from_email(self, event):
        from_email = get_from_author(self.env, event)
        if from_email and isinstance(from_email, tuple):
            from_email = from_email[1]
        if not from_email:
            from_email = self.config.get('notification', 'smtp_from') or \
                         self.config.get('notification', 'smtp_replyto')
        return from_email

    def _get_message_id(self, targetid, from_email, modtime, more=None):
        return create_message_id(self.env, targetid, from_email, modtime, more)

    def decorate_message(self, event, message, charset):
        if event.realm != 'ticket':
            return
        from_email = self._get_from_email(event)
        if event.category == 'batchmodify':
            tickets = sort_tickets_by_priority(self.env, event.target)
            subject = self._format_subj_batchmodify(tickets)
            targetid = ','.join(map(str, tickets))
            msgid = self._get_message_id(targetid, from_email, event.time)
        else:
            subject = self._format_subj(event)
            ticket = event.target
            targetid = '%08d' % ticket.id
            more = ticket['reporter'] or ''
            msgid = self._get_message_id(targetid, from_email, None, more)
            url = self.env.abs_href.ticket(ticket.id)
            if event.category != 'created':
                set_header(message, 'In-Reply-To', msgid, charset)
                set_header(message, 'References', msgid, charset)
                msgid = self._get_message_id(targetid, from_email, event.time,
                                             more)
                cnum = ticket.get_comment_number(event.time)
                if cnum is not None:
                    url += '#comment:%d' % cnum
            set_header(message, 'X-Trac-Ticket-ID', ticket.id, charset)
            set_header(message, 'X-Trac-Ticket-URL', url, charset)
            # When owner, reporter and updater are listed in the Cc header,
            # move the address to To header.
            if NotificationSystem(self.env).use_public_cc:
                to_addrs = set()
                matcher = RecipientMatcher(self.env)
                for rcpt in ticket['owner'], ticket['reporter'], event.author:
                    rcpt = matcher.match_recipient(rcpt)
                    if not rcpt:
                        continue
                    addr = rcpt[2]
                    if addr:
                        to_addrs.add(addr)
                if to_addrs:
                    cc_addrs = get_message_addresses(message, 'Cc')
                    to_addrs &= set(addr for name, addr in cc_addrs)
                if to_addrs:
                    cc_header = ', '.join(create_header('Cc', (name, addr),
                                                        charset)
                                          for name, addr in cc_addrs
                                          if addr not in to_addrs)
                    if cc_header:
                        set_header(message, 'Cc', cc_header, charset)
                    elif 'Cc' in message:
                        del message['Cc']
                    to_header = ', '.join(sorted(to_addrs))
                    set_header(message, 'To', to_header, charset)
        set_header(message, 'Subject', subject, charset)
        set_header(message, 'Message-ID', msgid, charset)


class TicketOwnerSubscriber(Component):
    """Allows ticket owners to subscribe to their tickets."""

    implements(INotificationSubscriber)

    def matches(self, event):
        owners = None
        if _is_ticket_change_event(event):
            owners = [event.target['owner']]
            # Harvest previous owner
            if 'fields' in event.changes and 'owner' in event.changes['fields']:
                owners.append(event.changes['fields']['owner']['old'])
        return _ticket_change_subscribers(self, owners)

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
        updater = None
        if _is_ticket_change_event(event):
            updater = event.author
        return _ticket_change_subscribers(self, updater)

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
        updaters = None
        if _is_ticket_change_event(event):
            updaters = [author for author, in self.env.db_query("""
                SELECT DISTINCT author FROM ticket_change
                WHERE ticket=%s
                """, (event.target.id,))
                        if author != event.author]
        return _ticket_change_subscribers(self, updaters)

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
        reporter = None
        if _is_ticket_change_event(event):
            reporter = event.target['reporter']
        return _ticket_change_subscribers(self, reporter)

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
        cc_users = None
        if _is_ticket_change_event(event):
            # CC field is stored as comma-separated string. Parse to set.
            chrome = Chrome(self.env)
            to_set = lambda cc: set(chrome.cc_list(cc))
            cc_users = to_set(event.target['cc'] or '')

            # Harvest previous CC field
            if 'fields' in event.changes and 'cc' in event.changes['fields']:
                cc_users.update(to_set(event.changes['fields']['cc']['old']))
        return _ticket_change_subscribers(self, cc_users)

    def description(self):
        return _("Ticket that I'm listed in the CC field is modified")

    def default_subscriptions(self):
        klass = self.__class__.__name__
        return NotificationSystem(self.env).default_subscriptions(klass)

    def requires_authentication(self):
        return True


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
            self.log.error("Failure sending notification when %s for "
                           "attachment '%s' to ticket #%s: %s",
                           category, attachment.filename, ticket.id,
                           exception_to_unicode(e))


def _is_ticket_change_event(event):
    return event.realm == 'ticket' and \
           event.category in ('created', 'changed', 'attachment added',
                              'attachment deleted')


def _ticket_change_subscribers(subscriber, candidates):
    if not candidates:
        return
    if not isinstance(candidates, (list, set, tuple)):
        candidates = [candidates]

    # Get members of permission groups
    groups = PermissionSystem(subscriber.env).get_groups_dict()
    for cc in set(candidates):
        if cc in groups:
            candidates.remove(cc)
            candidates.update(groups[cc])

    matcher = RecipientMatcher(subscriber.env)
    klass = subscriber.__class__.__name__
    sids = set()
    for candidate in candidates:
        recipient = matcher.match_recipient(candidate)
        if not recipient:
            continue
        sid, auth, addr = recipient

        # Default subscription
        for s in subscriber.default_subscriptions():
            yield s[0], s[1], sid, auth, addr, s[2], s[3], s[4]
        if sid:
            sids.add((sid, auth))

    for s in Subscription.find_by_sids_and_class(subscriber.env, sids, klass):
        yield s.subscription_tuple()
