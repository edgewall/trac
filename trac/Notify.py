# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004 Edgewall Software
# Copyright (C) 2003, 2004 Daniel Lundin <daniel@edgewall.com>
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

import md5
import sys
import time
import smtplib
import os.path

import neo_cgi
import neo_cs
import neo_util

from __init__ import __version__
from util import add_dict_to_hdf, CRLF, TRUE, FALSE, TracError
import Environment
import core
import Ticket


def wrap(t, cols=75, initial_indent='', subsequent_indent=''):
    try:
        import textwrap
        t = t.strip().replace('\r\n', '\n').replace('\r', '\n')
        wrapper = textwrap.TextWrapper(cols, replace_whitespace = 0,
                                       break_long_words = 0,
                                       initial_indent = initial_indent,
                                       subsequent_indent = subsequent_indent)
        wrappedLines = []
        for line in t.split('\n'):
            wrappedLines += wrapper.wrap(line.rstrip()) or ['']
        return CRLF.join(wrappedLines)

    except ImportError:
        return t


class Notify:
    """Generic notification class for Trac. Subclass this to implement
    different methods."""

    db = None
    hdf = None
    cs = None

    def __init__(self, env, msg_template):
        self.env = env
        self.db = env.get_db_cnx()
        self.hdf = neo_util.HDF()
        core.populate_hdf(self.hdf, env, self.db, None)
        tmpl = os.path.join(env.get_config('general','templates_dir'), msg_template)
        self.cs = neo_cs.CS(self.hdf)
        self.cs.parseFile(tmpl)

    def notify(self,resid):
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
        raise Exception, "Notify::get_recipients not implemented"

    def begin_send(self):
        """Prepare to send messages. Called before sending begins."""
        pass

    def send(self, rcpt):
        """Send message to a recipient 'rcpt'. Called once for each recipient."""
        raise Exception, "Notify::send not implemented"

    def finish_send(self):
        """Clean up after sending all messages. Called after sending all messages."""
        pass



class NotifyEmail(Notify):
    """Baseclass for notification by email."""

    smtp_server = 'localhost'
    from_email = 'trac+tickets@localhost'
    subject = ''
    server = None

    def notify(self, resid, subject):
        self.subject = subject

        enabled = self.env.get_config('notification', 'smtp_enabled', '0')
        if not enabled.lower() in TRUE:
            return
        self.smtp_server = self.env.get_config('notification',
                                               'smtp_server',
                                               self.smtp_server)
        self.from_email = self.env.get_config('notification',
                                              'smtp_from', '')
        self.replyto_email = self.env.get_config('notification',
                                                 'smtp_replyto',
                                                 self.from_email)
        self.from_email = self.from_email or self.replyto_email
        if not self.from_email and not self.replyto_email:
            raise TracError('Unable to send email due to identity crisis. <br />'
                            'Both <b>notification.from</b> and'
                            ' <b>notification.reply_to</b> are unspecified'
                            ' in configuration.',
                            'SMTP Notification Error')
        Notify.notify(self, resid)

    def get_email_addresses(self, txt):
        import email.Utils
        emails = [x[1] for x in  email.Utils.getaddresses([str(txt)])]
        return filter(lambda x: x.find('@') > -1, emails)

    def begin_send(self):
        self.server = smtplib.SMTP(self.smtp_server)

    def send(self, rcpt, mime_headers={}):
        from email.MIMEText import MIMEText
        from email.Header import Header
        body = self.cs.render()
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['X-Mailer'] = 'Trac %s, by Edgewall Software' % __version__
        msg['X-Trac-Version'] =  __version__
        projname = self.env.get_config('project','name')
        msg['X-Trac-Project'] =  projname
        msg['X-URL'] =  self.env.get_config('project','url')
        msg['Subject'] = Header(self.subject, 'utf-8')
        msg['From'] = '%s <%s>' % (projname, self.from_email)
        msg['Sender'] = self.from_email
        msg['Reply-To'] = self.replyto_email
        msg['To'] = rcpt
        for hdr in mime_headers.keys():
            msg[hdr] = mime_headers[hdr]
        self.server.sendmail(self.from_email, rcpt, msg.as_string())

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
        NotifyEmail.__init__(self, env, self.template_name)

    def notify(self, ticket, newticket=1, modtime=0):
        self.ticket = ticket
        self.modtime = modtime
        self.newticket = newticket
        self.ticket['description'] = wrap(self.ticket.get('description',''),
                                          self.COLS,
                                          initial_indent=' ',
                                          subsequent_indent=' ')
        self.ticket['link'] = self.env.abs_href.ticket(ticket['id'])
        add_dict_to_hdf(self.ticket, self.hdf, 'ticket')
        self.hdf.setValue('email.ticket_props', self.format_props())
        self.hdf.setValue('email.ticket_body_hdr', self.format_hdr())
        self.hdf.setValue('ticket.link', self.ticket['link'])
        self.hdf.setValue('ticket.new', self.newticket and '1' or '0')
        subject = self.format_subj()
        if not self.newticket:
            subject = 'Re: ' + subject
        self.hdf.setValue('email.subject', subject)
        changes=''
        if not self.newticket and modtime:  # Ticketchange
            changelog = ticket.get_changelog(self.db, modtime)
            for date, author, field, old, new in changelog:
                self.hdf.setValue('ticket.change.author', author)
                pfx='ticket.change.%s' % field
                newv = ''
                if field == 'comment':
                    newv = wrap(new, self.COLS, ' ', ' ')
                elif field == 'description':
                    new_descr = wrap(new, self.COLS, ' ', ' ')
                    old_descr = wrap(old, self.COLS, '> ', '> ')
                    old_descr = old_descr.replace(2*CRLF, CRLF + '>' + CRLF)
                    cdescr = CRLF
                    cdescr += 'Old description:' + 2*CRLF + old_descr + 2*CRLF
                    cdescr += 'New description:' + 2*CRLF + new_descr + CRLF
                    self.hdf.setValue('email.changes_descr', cdescr)
                else:
                    newv = new
                    l = 7 + len(field)
                    chg = wrap('%s => %s' % (old, new), self.COLS-l,'', l*' ')
                    changes += '  * %s:  %s%s' % (field, chg, CRLF)
                if newv:
                    self.hdf.setValue('%s.oldvalue' % pfx, old)
                    self.hdf.setValue('%s.newvalue' % pfx, newv)
                self.hdf.setValue('%s.author' % pfx, author)
            if changes:
                self.hdf.setValue('email.changes_body', changes)
        NotifyEmail.notify(self, ticket['id'], subject)

    def format_props(self):
        tkt = self.ticket
        tkt['id'] = '%s' % tkt['id']
        t = self.modtime or tkt['time']
        tkt['modified'] = time.strftime('%c', time.localtime(t))
        fields = ['id',        'status',
                  'component', 'modified',
                  'severity',  'milestone',
                  'priority',  'version',
                  'owner',     'reporter']
        i = 1
        width = [0,0,0,0]
        for f in fields:
            if not tkt.has_key(f): continue
            idx = 2*(i % 2)
            if len(f) > width[idx]:
                width[idx] = len(f)
            if len(tkt[f]) > width[idx+1]:
                width[idx+1] = len(tkt[f])
            i += 1
        format = (' %%%is:  %%-%is%s' % (width[0], width[1], CRLF),
                  '%%%is:  %%-%is  |  ' % (width[2], width[3]))
        i = 1
        l = (width[2] + width[3] + 5)
        sep = l*'-' + '+' + (self.COLS-l)*'-'
        txt = sep + CRLF
        for f in fields:
            if not tkt.has_key(f): continue
            txt += format[i%2] % (f.capitalize(), tkt[f])
            i += 1
        txt += sep
        return txt

    def format_hdr(self):
        return '#%s: %s' % (self.ticket['id'],
                               wrap(self.ticket['summary'], self.COLS))

    def format_subj(self):
        projname = self.env.get_config('project', 'name')
        return '[%s] #%s: %s' % (projname, self.ticket['id'],
                                     self.ticket['summary'])

    def get_recipients(self, tktid):
        emails = []
        cursor = self.db.cursor()
        # Harvest email addresses from the cc field
        cursor.execute('SELECT cc FROM ticket WHERE id=%s', tktid)
        row = cursor.fetchone()
        if row:
            emails += row[0] and self.get_email_addresses(row[0]) or []

        # Add smtp_always_cc address
        acc = self.env.get_config('notification', 'smtp_always_cc', '')
        if acc:
            emails += self.get_email_addresses(acc)

        # Remove duplicates
        result = []
        for e in emails:
            if e not in result:
                result.append(e)
        return result

    def get_message_id(self, rcpt, modtime=0):
        """Generate a predictable, but sufficiently unique message ID."""
        s = '%s.%08d.%d.%s' % (self.env.get_config('project','url'),
                            int(self.ticket['id']), modtime, rcpt)
        dig = md5.new(s).hexdigest()
        host = self.from_email[self.from_email.find('@')+1:]
        msgid = '<%03d.%s@%s>' % (len(s), dig, host)
        return msgid

    def send(self, rcpt):
        hdrs = {}
        hdrs['Message-ID'] = self.get_message_id(rcpt, self.modtime)
        hdrs['X-Trac-Ticket-ID'] = self.ticket['id']
        hdrs['X-Trac-Ticket-URL'] = self.ticket['link']
        if not self.newticket:
            hdrs['In-Reply-To'] = self.get_message_id(rcpt)
            hdrs['References'] = self.get_message_id(rcpt)
        NotifyEmail.send(self, rcpt, hdrs)


# A simple test 
if __name__ == '__main__':
    import db
    env = Environment.Environment('/home/daniel/trac/db/tracenv')
    try:
        tktid = int(sys.argv[1])
    except IndexError:
        tktid = 223
    tn = TicketNotifyEmail(env)
#    tn.notify(tktid, 1)
#    tn.notify(223,0,1081476135)
#    tn.notify(223,0,1081476765)
    tn.notify(224,0,1081528294)
#    tn.display_hdf()
