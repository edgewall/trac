# svntrac
#
# Copyright (C) 2003 Xyche Software
# Copyright (C) 2003 Jonas Borgström <jonas@xyche.com>
#
# svntrac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# svntrac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Jonas Borgström <jonas@xyche.com>

import time
import string
import StringIO

from util import *
from Module import Module
import perm
import auth
import db
from Wiki import wiki_to_html

fields = ['time', 'component', 'severity', 'priority', 'milestone', 'reporter',
          'owner', 'cc', 'url', 'version', 'status', 'resolution',
          'summary', 'description']

class Newticket (Module):
    template_name = 'newticket.template'
    def render (self):
        default_component = self.config['ticket']['default_component']
        default_milestone = self.config['ticket']['default_milestone']
        default_priority  = self.config['ticket']['default_priority']
        default_severity  = self.config['ticket']['default_severity']
        default_version   = self.config['ticket']['default_version']
        
        self.namespace['title'] = 'create a new ticket'
        self.namespace['component_select'] = enum_selector ('SELECT name FROM component ORDER by name',
                                                            'component',
                                                            default_component)
        self.namespace['milestone_select'] = enum_selector ('SELECT name FROM milestone ORDER BY name',
                                                            'milestone',
                                                            default_milestone)
        self.namespace['severity_select'] = enum_selector ('SELECT name FROM enum WHERE type=\'severity\' ORDER BY name',
                                                           'severity',
                                                           default_severity)
        self.namespace['priority_select'] = enum_selector ('SELECT name FROM enum WHERE type=\'priority\' ORDER BY name',
                                                           'priority',
                                                           default_priority)
        self.namespace['version_select'] = enum_selector ('SELECT name FROM version ORDER BY name',
                                                          'version')
        if auth.get_authname() == 'anonymous':
            self.namespace['reporter'] = ''
        else:
            self.namespace['reporter'] = auth.get_authname()
            

class Ticket (Module):
    template_name = 'ticket.template'

    def get_ticket (self, id):
        global fields
        cnx = db.get_connection ()
        cursor = cnx.cursor ()

        fetch = string.join(fields, ',')

        cursor.execute(('SELECT %s FROM ticket ' % fetch) + 'WHERE id=%s', id)
        row = cursor.fetchone ()
        cursor.close ()

        info = {'ticket': id }
        for i in range(len(fields)):
            info[fields[i]] = row[i] or ''
        return info

    def save_changes (self, id, old, new): 
        global fields
        
        if new.has_key('action'):
            if new['action'] == 'accept':
                new['status'] = 'assigned'
                new['owner'] = auth.get_authname()
            if new['action'] == 'resolve':
                new['status'] = 'closed'
                new['resolution'] = new['resolve_resolution']
            elif new['action'] == 'reassign':
                new['owner'] = new['reassign_owner']
                new['status'] = 'assigned'
            elif new['action'] == 'reopen':
                new['status'] = 'reopened'
                new['resolution'] = ''

        changed = 0
        change = ''
        cnx = db.get_connection ()
        cursor = cnx.cursor()
        now = int(time.time())
        authname = auth.get_authname ()
        for name in fields:
            if new.has_key(name) and (not old.has_key(name) or old[name] != new[name]):
                cursor.execute ('INSERT INTO ticket_change '
                                '(ticket, time, author, field, oldvalue, newvalue) '
                                'VALUES (%s, %s, %s, %s, %s, %s)',
                                id, now, authname, name, old[name], new[name])
                cursor.execute ('UPDATE ticket SET %s=%s WHERE id=%s',
                                name, new[name], id)
                changed = 1
        if new.has_key('comment') and len(new['comment']) > 0:
            cursor.execute ('INSERT INTO ticket_change '
                            '(ticket,time,author,field,oldvalue,newvalue) '
                            "VALUES (%s, %s, %s, 'comment', '', %s)",
                            id, now, authname, new['comment'])
            changed = 1
        if changed:
            cursor.execute ('UPDATE ticket SET changetime=%s WHERE id=%s',
                            now, id)
            cnx.commit()

    def create_ticket (self):
        perm.assert_permission (perm.TICKET_CREATE)
        
        cnx = db.get_connection ()
        cursor = cnx.cursor()
        global fields
        data = {}
        for field in fields:
            if self.args.has_key(field):
                data[field] = self.args[field]
        now = int(time.time())
        data['time']       = now
        data['changetime'] = now

        if not data.has_key('owner') or data['owner'] == '':
            # Assign it to the default owner
            cursor.execute('SELECT owner FROM component '
                           'WHERE name=%s', data['component'])
            owner = cursor.fetchone()[0]
            data['owner']      = owner
        
        nstr  = string.join (data.keys(), ',')
        vstr = ('%s,' * len(data.keys()))[:-1]
        
        cursor.execute ('INSERT INTO ticket (%s) VALUES(%s)' % (nstr, vstr),
                        *data.values())
        id = cnx.db.sqlite_last_insert_rowid ()
        cnx.commit()
        
        # redirect to the Ticket module to get a GET request
        redirect (ticket_href(id))
        
    def get_changes(self, id):
        cnx = db.get_connection ()
        cursor = cnx.cursor()
        cursor.execute('SELECT time, author, field, oldvalue, newvalue '
                       'FROM ticket_change '
                       'WHERE ticket=%s ORDER BY time', id)
        
        out = StringIO.StringIO()
        curr_author = None
        curr_date   = 0
        comment = None
	while 1:
	    row = cursor.fetchone()
	    if row == None:
		break

            date   = int(row[0])
            author = row[1]
            field  = row[2]
            old    = row[3]
            new    = row[4]
            if date != curr_date or author != curr_author:
                if comment:
                    out.write ('<p>comment:%s</p>' % wiki_to_html(comment))
                    comment = None
                curr_date = date
                curr_author = author
                out.write('<div class="ticket-modified">modified by %s %s:</div>'
                          % (curr_author,
                             time.strftime('%F %H:%M', time.localtime(curr_date))))
            if field == 'comment':
                comment = new
                continue
            if new == '':
                out.write ("<p>cleared <b>%s</b></p>" %
                           (field))
            elif old == '':
                out.write ("<p><b>%s</b> set to <b>%s</b></p>" %
                           (field, new))
            else:
                out.write ("<p><b>%s</b> changed from <b>%s</b> to <b>%s</b></p>" %
                           (field, old, new))
        if comment:
            out.write ('<p>comment:%s</p>' % wiki_to_html(comment))
            comment = None
            
        return out.getvalue()

    def get_actions(self, info):
        out = StringIO.StringIO()
        out.write ('<input type="radio" name="action" value="leave" '
                   'checked="checked">&nbsp;leave as %s<br>' % info['status'])
        
        if info['status'] == 'new':
            out.write ('<input type="radio" name="action" value="accept">'
                       '&nbsp;accept ticket<br>')
        if info['status'] == 'closed':
            out.write ('<input type="radio" name="action" value="reopen">'
                       '&nbsp;reopen ticket<br>')
        if info['status'] in ['new', 'assigned', 'reopened']:
            out.write ('<input type="radio" name="action" value="resolve">'
                       '&nbsp;resolve as: '
                       '<select name="resolve_resolution">'
                       '<option selected>fixed</option>'
                       '<option>invalid</option>'
                       '<option>wontfix</option>'
                       '<option>duplicate</option>'
                       '<option>worksforme</option>'
                       '</select><br>')
            out.write ('<input type="radio" name="action" value="reassign">'
                       '&nbsp;reassign ticket to:'
                       '&nbsp<input type="text" name="reassign_owner" '
                       'value="%s">' % info['owner'])
        return out.getvalue()
    
    def render (self):

        if self.args.has_key('action'):
            action = self.args['action']
        else:
            action = 'view'
            
        if action == 'create':
            self.create_ticket ()
        try:
            id = int(self.args['id'])
        except:
            redirect (menu_href ())

        if action in ['leave', 'accept', 'reopen', 'resolve', 'reassign']:
            # save changes and redirect to avoid the POST request
            old = self.get_ticket(id)
            perm.assert_permission (perm.TICKET_MODIFY)
            self.save_changes (id, old, self.args)
            redirect (ticket_href (id))
        
        perm.assert_permission (perm.TICKET_VIEW)
        
        info = self.get_ticket(id)
	for key in info.keys():
	    self.namespace[key] = info[key]

        self.namespace['title'] = 'Ticket #%d' % id
        
        self.namespace['component_select'] = enum_selector ('SELECT name FROM component ORDER BY name',
                                                            'component',
                                                            info['component'])
        self.namespace['milestone_select'] = enum_selector ('SELECT name FROM milestone ORDER BY name',
                                                            'milestone',
                                                            info['milestone'])
        self.namespace['severity_select'] = enum_selector ('SELECT name FROM enum WHERE type=\'severity\' ORDER BY name',
                                                           'severity',
                                                           info['severity'])
        self.namespace['priority_select'] = enum_selector ('SELECT name FROM enum WHERE type=\'priority\' ORDER BY name',
                                                           'priority',
                                                           info['priority'])
        self.namespace['version_select'] = enum_selector ('SELECT name FROM version ORDER BY name',
                                                          'version',
                                                          info['version'])

        self.namespace['actions'] = self.get_actions(info)
        self.namespace['changes'] = self.get_changes(id)
        self.namespace['description'] = wiki_to_html(info['description'])
        
        self.namespace['opened']  = time.strftime('%F %H:%M',
                                                  time.localtime(int(info['time'])))
       
