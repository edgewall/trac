# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
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

from __future__ import with_statement

from hashlib import md5

from genshi.template.text import NewTextTemplate

from trac.core import *
from trac.config import *
from trac.notification import NotifyEmail
from trac.ticket.api import TicketSystem
from trac.ticket.model import Ticket
from trac.util.datefmt import to_utimestamp
from trac.util.text import obfuscate_email_address, shorten_line, \
                           text_width, wrap
from trac.util.translation import deactivate, reactivate


class TicketNotificationSystem(Component):

    always_notify_owner = BoolOption('notification', 'always_notify_owner',
                                     'false',
        """Always send notifications to the ticket owner (''since 0.9'').""")

    always_notify_reporter = BoolOption('notification',
                                        'always_notify_reporter',
                                        'false',
        """Always send notifications to any address in the ''reporter''
        field.""")

    always_notify_updater = BoolOption('notification', 'always_notify_updater',
                                       'true',
        """Always send notifications to the person who causes the ticket
        property change and to any previous updater of that ticket.""")

    ticket_subject_template = Option('notification', 'ticket_subject_template',
                                     '$prefix #$ticket.id: $summary',
        """A Genshi text template snippet used to get the notification subject.

        By default, the subject template is `$prefix #$ticket.id: $summary`.
        `$prefix` being the value of the `smtp_subject_prefix` option.
        ''(since 0.11)''""")

    batch_subject_template = Option('notification', 'batch_subject_template',
                                    '$prefix Batch modify: $tickets_descr',
        """Like ticket_subject_template but for batch modifications.

        By default, the template is `$prefix Batch modify: $tickets_descr`.
        ''(since 1.0)''""")

    ambiguous_char_width = Option('notification', 'ambiguous_char_width',
                                  'single',
        """Which width of ambiguous characters (e.g. 'single' or
        'double') should be used in the table of notification mail.

        If 'single', the same width as characters in US-ASCII. This is
        expected by most users. If 'double', twice the width of
        US-ASCII characters.  This is expected by CJK users. ''(since
        0.12.2)''""")


def get_ticket_notification_recipients(env, config, tktid, prev_cc=None,
                                       modtime=None):
    """Returns notifications recipients.

    :since 1.0.2: the `config` parameter is no longer used.
    :since 1.0.2: the `prev_cc` parameter is deprecated.
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

    # Harvest email addresses from the cc, reporter, and owner fields
    if tkt['cc']:
        cc_recipients.update(to_list(tkt['cc']))
    if always_notify_reporter:
        to_recipients.add(tkt['reporter'])
    if always_notify_owner:
        to_recipients.add(tkt['owner'])

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

    # Suppress the updater from the recipients if necessary
    updater = author or tkt['reporter']
    if not always_notify_updater:
        filter_out = True
        if always_notify_reporter and updater == tkt['reporter']:
            filter_out = False
        if always_notify_owner and updater == tkt['owner']:
            filter_out = False
        if filter_out:
            to_recipients.discard(updater)
    elif updater:
        to_recipients.add(updater)

    return list(to_recipients), list(cc_recipients), \
           tkt['reporter'], tkt['owner']


class TicketNotifyEmail(NotifyEmail):
    """Notification of ticket changes."""

    template_name = "ticket_notify_email.txt"
    ticket = None
    newticket = None
    modtime = 0
    from_email = 'trac+ticket@localhost'
    COLS = 75

    def __init__(self, env):
        NotifyEmail.__init__(self, env)
        ambiguous_char_width = env.config.get('notification',
                                              'ambiguous_char_width',
                                              'single')
        self.ambiwidth = 2 if ambiguous_char_width == 'double' else 1

    def notify(self, ticket, newticket=True, modtime=None):
        """Send ticket change notification e-mail (untranslated)"""
        t = deactivate()
        translated_fields = ticket.fields
        try:
            ticket.fields = TicketSystem(self.env).get_ticket_fields()
            self._notify(ticket, newticket, modtime)
        finally:
            ticket.fields = translated_fields
            reactivate(t)

    def _notify(self, ticket, newticket=True, modtime=None):
        self.ticket = ticket
        self.modtime = modtime
        self.newticket = newticket

        changes_body = ''
        self.reporter = ''
        self.owner = ''
        changes_descr = ''
        change_data = {}
        link = self.env.abs_href.ticket(ticket.id)
        summary = self.ticket['summary']
        author = None

        if not self.newticket and modtime:  # Ticket change
            from trac.ticket.web_ui import TicketModule
            for change in TicketModule(self.env).grouped_changelog_entries(
                                                ticket, when=modtime):
                if not change['permanent']: # attachment with same time...
                    continue
                author = change['author']
                change_data.update({
                    'author': self.obfuscate_email(author),
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
                        old_descr = old_descr.replace(2 * '\n', '\n' + '>' + \
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
                        (addcc, delcc) = self.diff_cc(old, new)
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
                            old = self.obfuscate_email(old)
                            new = self.obfuscate_email(new)
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

        subject = self.format_subj(summary)
        if not self.newticket:
            subject = 'Re: ' + subject
        self.data.update({
            'ticket_props': self.format_props(),
            'ticket_body_hdr': self.format_hdr(),
            'subject': subject,
            'ticket': ticket_values,
            'changes_body': changes_body,
            'changes_descr': changes_descr,
            'change': change_data
            })
        NotifyEmail.notify(self, ticket.id, subject, author)

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
            if not fname in tkt.values:
                continue
            fval = tkt[fname] or ''
            if fval.find('\n') != -1:
                continue
            if fname in ['owner', 'reporter']:
                fval = self.obfuscate_email(fval)
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
            if fname in ['owner', 'reporter']:
                fval = self.obfuscate_email(fval)
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
        oldcc = NotifyEmail.addrsep_re.split(old)
        newcc = NotifyEmail.addrsep_re.split(new)
        added = [self.obfuscate_email(x) \
                                for x in newcc if x and x not in oldcc]
        removed = [self.obfuscate_email(x) \
                                for x in oldcc if x and x not in newcc]
        return (added, removed)

    def format_hdr(self):
        return '#%s: %s' % (self.ticket.id, wrap(self.ticket['summary'],
                                                 self.COLS, linesep='\n',
                                                 ambiwidth=self.ambiwidth))

    def format_subj(self, summary):
        template = self.config.get('notification','ticket_subject_template')
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

        return template.generate(**data).render('text', encoding=None).strip()

    def get_recipients(self, tktid):
        torecipients, ccrecipients, reporter, owner = \
            get_ticket_notification_recipients(self.env, self.config, tktid,
                                               modtime=self.modtime)
        self.reporter = reporter
        self.owner = owner
        return (torecipients, ccrecipients)

    def get_message_id(self, rcpt, modtime=None):
        """Generate a predictable, but sufficiently unique message ID."""
        s = '%s.%08d.%d.%s' % (self.env.project_url.encode('utf-8'),
                               int(self.ticket.id), to_utimestamp(modtime),
                               rcpt.encode('ascii', 'ignore'))
        dig = md5(s).hexdigest()
        host = self.from_email[self.from_email.find('@') + 1:]
        msgid = '<%03d.%s@%s>' % (len(s), dig, host)
        return msgid

    def send(self, torcpts, ccrcpts):
        dest = self.reporter or 'anonymous'
        hdrs = {}
        hdrs['Message-ID'] = self.get_message_id(dest, self.modtime)
        hdrs['X-Trac-Ticket-ID'] = str(self.ticket.id)
        hdrs['X-Trac-Ticket-URL'] = self.data['ticket']['link']
        if not self.newticket:
            msgid = self.get_message_id(dest)
            hdrs['In-Reply-To'] = msgid
            hdrs['References'] = msgid
        NotifyEmail.send(self, torcpts, ccrcpts, hdrs)

    def get_text_width(self, text):
        return text_width(text, ambiwidth=self.ambiwidth)

    def obfuscate_email(self, text):
        """ Obfuscate text when `show_email_addresses` is disabled in config.
        Obfuscation happens once per email, regardless of recipients, so
        cannot use permission-based obfuscation.
        """
        if self.env.config.getbool('trac', 'show_email_addresses'):
            return text
        else:
            return obfuscate_email_address(text)


class BatchTicketNotifyEmail(NotifyEmail):
    """Notification of ticket batch modifications."""

    template_name = "batch_ticket_notify_email.txt"

    def __init__(self, env):
        NotifyEmail.__init__(self, env)

    def notify(self, tickets, new_values, comment, action, author):
        """Send batch ticket change notification e-mail (untranslated)"""
        t = deactivate()
        try:
            self._notify(tickets, new_values, comment, action, author)
        finally:
            reactivate(t)

    def _notify(self, tickets, new_values, comment, action, author):
        self.tickets = tickets
        self.reporter = ''
        self.owner = ''
        changes_descr = '\n'.join(['%s to %s' % (prop, val)
                                  for (prop, val) in new_values.iteritems()])
        tickets_descr = ', '.join(['#%s' % t for t in tickets])
        subject = self.format_subj(tickets_descr)
        link = self.env.abs_href.query(id=','.join([str(t) for t in tickets]))
        self.data.update({
            'tickets_descr': tickets_descr,
            'changes_descr': changes_descr,
            'comment': comment,
            'action': action,
            'author': author,
            'subject': subject,
            'ticket_query_link': link,
            })
        NotifyEmail.notify(self, tickets, subject, author)

    def format_subj(self, tickets_descr):
        template = self.config.get('notification','batch_subject_template')
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
        alltorecipients = set()
        allccrecipients = set()
        for t in tktids:
            torecipients, ccrecipients, reporter, owner = \
                get_ticket_notification_recipients(self.env, self.config, t)
            alltorecipients.update(torecipients)
            allccrecipients.update(ccrecipients)
        return list(alltorecipients), list(allccrecipients)
