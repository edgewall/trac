# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004, 2005 Edgewall Software
# Copyright (C) 2003, 2004, 2005 Daniel Lundin <daniel@edgewall.com>
#
# Trac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Trac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Daniel Lundin <daniel@edgewall.com>

from trac.__init__ import __version__
from trac.core import TracError
from trac.util import CRLF, TRUE, FALSE, enum, wrap
from trac.web.clearsilver import HDFWrapper
from trac.web.main import populate_hdf

import md5
import sys
import time
import smtplib


class Notify:
    """Generic notification class for Trac. Subclass this to implement
    different methods."""

    db = None
    hdf = None

    def __init__(self, env):
        self.env = env
        self.config = env.config
        self.db = env.get_db_cnx()
        self.hdf = HDFWrapper(loadpaths=[env.get_templates_dir(),
                                         self.config.get('trac', 'templates_dir')])
        populate_hdf(self.hdf, env)

    def notify(self, resid):
        if sys.version_info[0] == 2 and (sys.version_info[1] < 2 or
                                         sys.version_info[1] == 2 and
                                         sys.version_info[2] < 2):
            raise TracError, "Email notifications require Python >= 2.2.2"
        rcpts = self.get_recipients(resid)
        self.begin_send()
        for to in rcpts:
            self.send(to)
        self.finish_send()

    def get_recipients(self, resid):
        """Return a list of subscribers to the resource 'resid'."""
        raise NotImplementedError

    def begin_send(self):
        """Prepare to send messages. Called before sending begins."""
        pass

    def send(self, rcpt):
        """Send message to a recipient 'rcpt'. Called once for each recipient."""
        raise NotImplementedError

    def finish_send(self):
        """Clean up after sending all messages. Called after sending all messages."""
        pass


class NotifyEmail(Notify):
    """Baseclass for notification by email."""

    smtp_server = 'localhost'
    smtp_port = 25
    from_email = 'trac+tickets@localhost'
    subject = ''
    server = None
    email_map = None
    template_name = None

    def __init__(self, env):
        Notify.__init__(self, env)

        # Get the email addresses of all known users
        self.email_map = {}
        for username,name,email in self.env.get_known_users(self.db):
            self.email_map[username] = email

    def notify(self, resid, subject):
        self.subject = subject

        enabled = self.config.get('notification', 'smtp_enabled')
        if not enabled.lower() in TRUE:
            return
        self.smtp_server = self.config.get('notification', 'smtp_server')
        self.smtp_port = int(self.config.get('notification', 'smtp_port'))
        self.from_email = self.config.get('notification', 'smtp_from')
        self.replyto_email = self.config.get('notification', 'smtp_replyto')
        self.from_email = self.from_email or self.replyto_email
        if not self.from_email and not self.replyto_email:
            raise TracError('Unable to send email due to identity crisis. <br />'
                            'Both <b>notification.from</b> and'
                            ' <b>notification.reply_to</b> are unspecified'
                            ' in configuration.',
                            'SMTP Notification Error')

        # Authentication info (optional)
        self.user_name = self.config.get('notification', 'smtp_user')
        self.password = self.config.get('notification', 'smtp_password')

        Notify.notify(self, resid)

    def get_email_addresses(self, txt):
        import email.Utils
        emails = [x[1] for x in  email.Utils.getaddresses([str(txt)])]
        return filter(lambda x: x.find('@') > -1, emails)

    def begin_send(self):
        self.server = smtplib.SMTP(self.smtp_server, self.smtp_port)
        if self.user_name:
            self.server.login(self.user_name, self.password)

    def send(self, rcpt, mime_headers={}):
        from email.MIMEText import MIMEText
        from email.Header import Header
        from email.Utils import formatdate
        body = self.hdf.render(self.template_name)
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['X-Mailer'] = 'Trac %s, by Edgewall Software' % __version__
        msg['X-Trac-Version'] =  __version__
        projname = self.config.get('project','name')
        msg['X-Trac-Project'] =  projname
        msg['X-URL'] =  self.config.get('project','url')
        msg['Subject'] = Header(self.subject, 'utf-8')
        msg['From'] = '%s <%s>' % (projname, self.from_email)
        msg['Sender'] = self.from_email
        msg['Reply-To'] = self.replyto_email
        msg['To'] = rcpt
        msg['Date'] = formatdate()
        for hdr in mime_headers.keys():
            msg[hdr] = mime_headers[hdr]
        self.env.log.debug("Sending SMTP notification to %s on port %d"
                           % (self.smtp_server, self.smtp_port))
        self.server.sendmail(self.from_email, [rcpt], msg.as_string())

    def finish_send(self):
        self.server.quit()


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
        self.hdf['email.ticket_props'] = self.format_props()
        self.hdf['email.ticket_body_hdr'] = self.format_hdr()
        self.hdf['ticket'] = self.ticket.values
        self.hdf['ticket.new'] = self.newticket
        subject = self.format_subj()
        if not self.newticket:
            subject = 'Re: ' + subject
        self.hdf['email.subject'] = subject
        changes = ''
        if not self.newticket and modtime:  # Ticket change
            changelog = ticket.get_changelog(modtime)
            for date, author, field, old, new in changelog:
                self.hdf['ticket.change.author'] = author
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
                    self.hdf['email.changes_descr'] = cdescr
                else:
                    newv = new
                    l = 7 + len(field)
                    chg = wrap('%s => %s' % (old, new), self.COLS-l,'', l*' ',
                               CRLF)
                    changes += '  * %s:  %s%s' % (field, chg, CRLF)
                if newv:
                    self.hdf['%s.oldvalue' % pfx] = old
                    self.hdf['%s.newvalue' % pfx] = newv
                if field == 'cc':
                    self.prev_cc += old and self.parse_cc(old) or []
                self.hdf['%s.author' % pfx] = author
            if changes:
                self.hdf['email.changes_body'] = changes
        NotifyEmail.notify(self, ticket.id, subject)

    def format_props(self):
        tkt = self.ticket
        fields = [f for f in tkt.fields if f['type'] != 'textarea'
                                       and f['name'] != 'summary']
        t = self.modtime or tkt.time_changed
        width = [0, 0, 0, 0]
        for i, f in enum([f['name'] for f in fields]):
            if not f in tkt.values.keys():
                continue
            fval = tkt[f]
            if fval.find('\n') > -1:
                continue
            idx = 2 * (i % 2)
            if len(f) > width[idx]:
                width[idx] = len(f)
            if len(fval) > width[idx + 1]:
                width[idx + 1] = len(fval)
        format = ('%%%is:  %%-%is  |  ' % (width[1], width[1]),
                  ' %%%is:  %%-%is%s' % (width[2], width[3], CRLF))
        i = 1
        l = (width[0] + width[1] + 5)
        sep = l*'-' + '+' + (self.COLS-l)*'-'
        txt = sep + CRLF
        big = []
        for i, f in enum([f['name'] for f in fields]):
            if not tkt.values.has_key(f): continue
            fval = tkt[f]
            if '\n' in str(fval):
                big.append((f.capitalize(), fval))
            else:
                txt += format[i % 2] % (f.capitalize(), fval)
        if not i % 2:
            txt += '\n'
        if big:
            txt += sep
            for k,v in big:
                txt += '\n%s:\n%s\n\n' % (k,v)
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
        val = self.config.get('notification', 'always_notify_reporter')
        notify_reporter = val.lower() in TRUE
        val = self.config.get('notification', 'always_notify_owner')
        notify_owner = val.lower() in TRUE

        recipients = self.prev_cc
        cursor = self.db.cursor()

        # Harvest email addresses from the cc, reporter, and owner fields
        cursor.execute("SELECT cc,reporter,owner FROM ticket WHERE id=%s",
                       (tktid,))
        row = cursor.fetchone()
        if row:
            recipients += row[0] and row[0].replace(',', ' ').split() or []
            if notify_reporter:
                recipients.append(row[1])
            if notify_owner:
                recipients.append(row[2])

        # Harvest email addresses from the author field of ticket_change(s)
        if notify_reporter:
            cursor.execute("SELECT DISTINCT author,ticket FROM ticket_change "
                           "WHERE ticket=%s", (tktid,))
            for author,ticket in cursor:
                recipients.append(row[0])

        # Add smtp_always_cc address
        acc = self.config.get('notification', 'smtp_always_cc')
        if acc:
            recipients += acc.replace(',', ' ').split()

        # now convert recipients into email addresses where necessary
        emails = []
        for recipient in recipients:
            if recipient.find('@') >= 0:
                emails.append(recipient)
            else:
                if self.email_map.has_key(recipient):
                    emails.append(self.email_map[recipient])

        # Remove duplicates
        result = []
        for e in emails:
            if e not in result:
                result.append(e)
        return result

    def get_message_id(self, rcpt, modtime=0):
        """Generate a predictable, but sufficiently unique message ID."""
        s = '%s.%08d.%d.%s' % (self.config.get('project', 'url'),
                               int(self.ticket.id), modtime, rcpt)
        dig = md5.new(s).hexdigest()
        host = self.from_email[self.from_email.find('@') + 1:]
        msgid = '<%03d.%s@%s>' % (len(s), dig, host)
        return msgid

    def send(self, rcpt):
        hdrs = {}
        hdrs['Message-ID'] = self.get_message_id(rcpt, self.modtime)
        hdrs['X-Trac-Ticket-ID'] = str(self.ticket.id)
        hdrs['X-Trac-Ticket-URL'] = self.ticket['link']
        if not self.newticket:
            hdrs['In-Reply-To'] = self.get_message_id(rcpt)
            hdrs['References'] = self.get_message_id(rcpt)
        NotifyEmail.send(self, rcpt, hdrs)
