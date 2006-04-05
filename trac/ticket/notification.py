# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# Copyright (C) 2003-2005 Daniel Lundin <daniel@edgewall.com>
# Copyright (C) 2005-2006 Emmanuel Blot <emmanuel.blot@free.fr>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Daniel Lundin <daniel@edgewall.com>
#

import md5

from trac import __version__
from trac.core import *
from trac.config import *
from trac.util import CRLF, wrap
from trac.notification import NotifyEmail


class TicketNotificationSystem(Component):

    implements(IConfigurable)

    # IConfigurable methods

    def get_config_sections(self):
        yield ConfigSection('notification', [
            ConfigOption('always_notify_owner', 'false',
                         """Always send notifications to the ticket owner
                         (''since 0.9'')
                         """),
            ConfigOption('always_notify_reporter', 'false',
                         """Always send notifications to any address in the
                         ''reporter'' field
                         """),
            ConfigOption('smtp_always_cc', '',
                         "Email address(es) to always send notifications to"),
            ])


class TicketNotifyEmail(NotifyEmail):
    """Notification of ticket changes."""

    template_name = "ticket_notify_email.cs"
    ticket = None
    newticket = None
    modtime = 0
    from_email = 'trac+ticket@localhost'
    COLS = 75

    def __init__(self, env):
        NotifyEmail.__init__(self, env)
        self.prev_cc = []

    def notify(self, ticket, newticket=True, modtime=0):
        self.ticket = ticket
        self.modtime = modtime
        self.newticket = newticket
        self.ticket['description'] = wrap(self.ticket.values.get('description', ''),
                                          self.COLS, initial_indent=' ',
                                          subsequent_indent=' ', linesep=CRLF)
        self.ticket['link'] = self.env.abs_href.ticket(ticket.id)
        self.hdf.set_unescaped('email.ticket_props', self.format_props())
        self.hdf.set_unescaped('email.ticket_body_hdr', self.format_hdr())
        self.hdf.set_unescaped('ticket', self.ticket.values)
        self.hdf['ticket.new'] = self.newticket
        subject = self.format_subj()
        if not self.newticket:
            subject = 'Re: ' + subject
        self.hdf.set_unescaped('email.subject', subject)
        changes = ''
        if not self.newticket and modtime:  # Ticket change
            changelog = ticket.get_changelog(modtime)
            for date, author, field, old, new in changelog:
                self.hdf.set_unescaped('ticket.change.author', author)
                pfx = 'ticket.change.%s' % field
                newv = ''
                if field == 'comment':
                    newv = wrap(new, self.COLS, ' ', ' ', CRLF)
                elif field == 'description':
                    new_descr = wrap(new, self.COLS, ' ', ' ', CRLF)
                    old_descr = wrap(old, self.COLS, '> ', '> ', CRLF)
                    old_descr = old_descr.replace(2*CRLF, CRLF + '>' + CRLF)
                    cdescr = CRLF
                    cdescr += 'Old description:' + 2*CRLF + old_descr + 2*CRLF
                    cdescr += 'New description:' + 2*CRLF + new_descr + CRLF
                    self.hdf.set_unescaped('email.changes_descr', cdescr)
                else:
                    newv = new
                    l = 7 + len(field)
                    chg = wrap('%s => %s' % (old, new), self.COLS - l, '',
                               l * ' ', CRLF)
                    changes += '  * %s:  %s%s' % (field, chg, CRLF)
                if newv:
                    self.hdf.set_unescaped('%s.oldvalue' % pfx, old)
                    self.hdf.set_unescaped('%s.newvalue' % pfx, newv)
                if field == 'cc':
                    self.prev_cc += old and self.parse_cc(old) or []
                self.hdf.set_unescaped('%s.author' % pfx, author)
            if changes:
                self.hdf.set_unescaped('email.changes_body', changes)
        NotifyEmail.notify(self, ticket.id, subject)

    def format_props(self):
        tkt = self.ticket
        fields = [f for f in tkt.fields if f['name'] not in ('summary', 'cc')]
        width = [0, 0, 0, 0]
        i = 0
        for f in [f['name'] for f in fields if f['type'] != 'textarea']:
            if not tkt.values.has_key(f):
                continue
            fval = tkt[f]
            if fval.find('\n') != -1:
                continue
            idx = 2 * (i % 2)
            if len(f) > width[idx]:
                width[idx] = len(f)
            if len(fval) > width[idx + 1]:
                width[idx + 1] = len(fval)
            i += 1
        format = ('%%%is:  %%-%is  |  ' % (width[0], width[1]),
                  ' %%%is:  %%-%is%s' % (width[2], width[3], CRLF))
        l = (width[0] + width[1] + 5)
        sep = l * '-' + '+' + (self.COLS - l) * '-'
        txt = sep + CRLF
        big = []
        i = 0
        for f in [f for f in fields if f['name'] != 'description']:
            fname = f['name']
            if not tkt.values.has_key(fname):
                continue
            fval = tkt[fname]
            if f['type'] == 'textarea' or '\n' in unicode(fval):
                big.append((fname.capitalize(), CRLF.join(fval.splitlines())))
            else:
                txt += format[i % 2] % (fname.capitalize(), fval)
                i += 1
        if i % 2:
            txt += CRLF
        if big:
            txt += sep
            for name, value in big:
                txt += CRLF.join(['', name + ':', value, '', ''])
        txt += sep
        return txt

    def parse_cc(self, txt):
        return filter(lambda x: '@' in x, txt.replace(',', ' ').split())

    def format_hdr(self):
        return '#%s: %s' % (self.ticket.id, wrap(self.ticket['summary'],
                                                 self.COLS, linesep=CRLF))

    def format_subj(self):
        projname = self.config.get('project', 'name')
        return '[%s] #%s: %s' % (projname, self.ticket.id,
                                 self.ticket['summary'])

    def get_recipients(self, tktid):
        notify_reporter = self.config.getbool('notification',
                                              'always_notify_reporter')
        notify_owner = self.config.getbool('notification',
                                           'always_notify_owner')

        ccrecipients = self.prev_cc
        torecipients = []
        cursor = self.db.cursor()

        # Harvest email addresses from the cc, reporter, and owner fields
        cursor.execute("SELECT cc,reporter,owner FROM ticket WHERE id=%s",
                       (tktid,))
        row = cursor.fetchone()
        if row:
            ccrecipients += row[0] and row[0].replace(',', ' ').split() or []
            if notify_reporter:
                torecipients.append(row[1])
            if notify_owner:
                torecipients.append(row[2])

        # Harvest email addresses from the author field of ticket_change(s)
        if notify_reporter:
            cursor.execute("SELECT DISTINCT author,ticket FROM ticket_change "
                           "WHERE ticket=%s", (tktid,))
            for author,ticket in cursor:
                torecipients.append(author)

        # Add smtp_always_cc address
        acc = self.config.get('notification', 'smtp_always_cc')
        if acc:
            ccrecipients += acc.replace(',', ' ').split()
            
        return (torecipients, ccrecipients)

    def get_message_id(self, rcpt, modtime=0):
        """Generate a predictable, but sufficiently unique message ID."""
        s = '%s.%08d.%d.%s' % (self.config.get('project', 'url'),
                               int(self.ticket.id), modtime, rcpt)
        dig = md5.new(s).hexdigest()
        host = self.from_email[self.from_email.find('@') + 1:]
        msgid = '<%03d.%s@%s>' % (len(s), dig, host)
        return msgid

    def send(self, torcpts, ccrcpts):
        hdrs = {}
        dest = torcpts or ccrcpts
        if not dest:
            self.env.log.info('no recipient for a ticket notification')
            return 
        hdrs['Message-ID'] = self.get_message_id(dest[0], self.modtime)
        hdrs['X-Trac-Ticket-ID'] = str(self.ticket.id)
        hdrs['X-Trac-Ticket-URL'] = self.ticket['link']
        if not self.newticket:
            hdrs['In-Reply-To'] = self.get_message_id(dest[0])
            hdrs['References'] = self.get_message_id(dest[0])
        NotifyEmail.send(self, torcpts, ccrcpts, hdrs)

