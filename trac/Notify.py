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

import sys
import os.path
import md5

import neo_cgi
import neo_cs
import neo_util

from __init__ import __version__
from util import *
import Environment
import core
import Ticket


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


# >=2.2 modules
try: 
    import email.Utils
    from email.MIMEText import MIMEText
    import smtplib
except ImportError:
    raise TracError, "Email notifications require Python >= 2.2"
else:
    # >=2.3 modules
    try:
        import textwrap
        def wrap(t, cols=75, initial_indent='', subsequent_indent=''):
            return '\n'.join(textwrap.wrap(t, replace_whitespace=0,
                                           width=cols, break_long_words=0,
                                           initial_indent=initial_indent,
                                           subsequent_indent=subsequent_indent))
    except ImportError:
        def wrap(t, *args, **kwords):
            return t

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
                                                  'smtp_replyto',
                                                  self.from_email)
            Notify.notify(self, resid)
                 
        def get_email_addresses(self, txt):
            emails = [x[1] for x in  email.Utils.getaddresses([str(txt)])]
            return filter(lambda x: x.find('@') > -1, emails)

        def begin_send(self):
            self.server = smtplib.SMTP(self.smtp_server)

        def send(self, rcpt, mime_headers={}):
            body = self.cs.render()
            msg = MIMEText (body)
            msg['X-Mailer'] = 'Trac %s, by Edgewall Software' % __version__
            msg['X-Trac-Version'] =  __version__
            projname = self.env.get_config('project','name')
            msg['X-Trac-Project'] =  projname
            msg['X-URL'] =  self.env.get_config('project','url')
            msg['Subject'] = self.subject
            msg['From'] = '%s <%s>' % (projname, self.from_email)
            msg['Sender'] = msg['Reply-To'] = self.from_email
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

        def notify(self, tktid, newticket=1, modtime=0):
            self.ticket = Ticket.get_ticket(self.db, tktid)
            self.modtime = modtime
            self.newticket = newticket
            self.ticket['description'] = wrap(self.ticket['description'],
                                              self.COLS)
            self.ticket['link'] = self.env.abs_href.ticket(tktid)
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
                cursor = self.db.cursor()
                cursor.execute('SELECT author, field, oldvalue, newvalue '
                               ' FROM ticket_change WHERE ticket=%s ANd time=%s' %
                               (tktid, modtime))
                rows=cursor.fetchall()
                for r in rows:
                    self.hdf.setValue('ticket.change.author', str(r[0]))
                    pfx='ticket.change.%s' % r[1]
                    if r[1] == 'comment':
                        newv = wrap(r[3], initial_indent=' ',
                                    subsequent_indent=' ').strip()
                    else:
                        newv = r[3]
                        l = 7 + len(r[1])
                        chg = wrap('%s => %s' % (r[2], r[3]), self.COLS-l,'', l*' ')
                        changes += '  * %s:  %s\n' % (r[1], chg)
                    self.hdf.setValue('%s.author' % pfx, str(r[0]))
                    self.hdf.setValue('%s.oldvalue' % pfx, str(r[2]))
                    self.hdf.setValue('%s.newvalue' % pfx, newv)
                if changes:
                    self.hdf.setValue('email.changes_body', changes)
            NotifyEmail.notify(self, tktid, subject)

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
                idx = 2*(i % 2)
                if len(f) > width[idx]:
                    width[idx] = len(f)
                if len(tkt[f]) > width[idx+1]:
                    width[idx+1] = len(tkt[f])
                i += 1
            format = (' %%%is:  %%-%is\n' % (width[0], width[1]),
                      '%%%is:  %%-%is  |  ' % (width[2], width[3]))
            i = 1
            l = (width[2] + width[3] + 5)
            sep = l*'-' + '+' + (self.COLS-l)*'-'
            txt = sep + '\n'
            for f in fields:
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
            cursor.execute('SELECT reporter,cc FROM ticket WHERE id=%s', tktid)
            row = cursor.fetchone()
            if row:
                emails += row[0] and self.get_email_addresses(row[0]) or []
                emails += row[1] and self.get_email_addresses(row[1]) or []
            cursor.execute('SELECT DISTINCT author,ticket FROM ticket_change '
                           ' WHERE ticket=%s', tktid)
            rows = cursor.fetchall()
            for row in rows:
                emails += row[0] and self.get_email_addresses(row[0]) or []

            # Add smtp_always_cc address
            acc = self.env.get_config('notification', 'smtp_always_cc', '')
            if acc:
                emails += self.get_email_addresses(acc)
                    
            result = []
            for e in emails:        # Remove duplicates
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
