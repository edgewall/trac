# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004 Edgewall Software
# Copyright (C) 2003, 2004 Jonas Borgström <jonas@edgewall.com>
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
# Author: Jonas Borgström <jonas@edgewall.com>

import re
import time
import string
from types import *

from util import *
from Module import Module
import perm
from Wiki import wiki_to_html
from Notify import TicketNotifyEmail

fields = ['time', 'component', 'severity', 'priority', 'milestone', 'reporter',
          'owner', 'cc', 'url', 'version', 'status', 'resolution',
          'keywords', 'summary', 'description']

def get_ticket (db, id, escape_values=1):
    global fields
    cursor = db.cursor ()

    fetch = string.join(fields, ',')
    cursor.execute(('SELECT %s FROM ticket ' % fetch) + 'WHERE id=%s', id)
    row = cursor.fetchone ()
    cursor.close ()

    if not row:
        raise TracError('Ticket %d does not exist.' % id,
                        'Invalid Ticket Number')

    info = {'id': id }
    # Escape the values so that they are safe to have as html parameters
    for i in range(len(fields)):
        # We shouldn't escape the description
        # wiki_to_html will take care of that
        if fields[i] == 'description':
            info[fields[i]] = row[i] or ''
        elif escape_values:
            info[fields[i]] = escape(row[i])
        else:
            info[fields[i]] = row[i]

    cursor = db.cursor ()
    cursor.execute('SELECT name,value FROM ticket_custom WHERE ticket=%i', id)
    rows = cursor.fetchall()
    if rows:
        info['custom'] = {}
        for r in rows:
            info['custom'][r[0]] = r[1]
    cursor.close ()
    return info


def insert_custom_fields(env, hdf, vals = {}):
    cfg = env.get_config_items('ticket-custom')
    if not cfg: return None,None
    allvars = {}
    vnames = []
    for k,v in cfg:
        allvars[k] = v
        if '.' not in k:
            vnames.append(k)
    if not allvars: return
    i = 0
    for name in vnames:
        vtype = allvars[name]
        vval = vals.get(name, allvars.get(name + '.value', ''))
        pfx = 'ticket.custom.%i' % i
        hdf.setValue('%s.name' % pfx, name)
        hdf.setValue('%s.type' % pfx, vtype)
        hdf.setValue('%s.label' % pfx, allvars.get(name + '.label', ''))
        hdf.setValue('%s.value' % pfx, vval)
        if vtype == 'select' or vtype == 'radio':
            opts = allvars.get(name + '.options', '').split('|')
            j = 0
            for o in opts:
                hdf.setValue('%s.option.%d' % (pfx, j), o)
                if vval and (o == vval or str(j) == vval):
                    hdf.setValue('%s.option.%d.selected' % (pfx, j), '1')
                j += 1
        elif vtype == 'checkbox':
            if vval in TRUE:
                hdf.setValue('%s.selected' % pfx, '1')
        i += 1


class Newticket (Module):
    template_name = 'newticket.cs'

    def create_ticket(self):
        """
        Insert a new ticket into the database.

        The values are taken from the html form
        """
        self.perm.assert_permission(perm.TICKET_CREATE)

        global fields
        data = {}
        for field in fields:
            if self.args.has_key(field):
                data[field] = self.args.get(field)
        now = int(time.time())
        data['time'] = now
        data['changetime'] = now
        data.setdefault('reporter',self.req.authname)

        cursor = self.db.cursor()

        # The owner field defaults to the component owner
        if data.has_key('component') and \
               (not data.has_key('owner') or data['owner'] == ''):
            # Assign it to the default owner
            cursor.execute('SELECT owner FROM component '
                           'WHERE name=%s', data['component'])
            owner = cursor.fetchone()[0]
            data['owner'] = owner

        nstr = string.join(data.keys(), ',')
        vstr = ('%s,' * len(data.keys()))[:-1]

        cursor.execute('INSERT INTO ticket (%s) VALUES(%s)' % (nstr, vstr),
                       *data.values())
        tktid = self.db.db.sqlite_last_insert_rowid()

        # Handle custom fields
        cfields = filter(lambda n: n[:7] == 'custom_', self.args.keys())
        for cname in cfields:
            name = cname[7:]
            val = self.args.get(cname)
            cursor.execute('INSERT INTO ticket_custom(ticket,name,value)'
                           ' VALUES(%d, %s, %s)', tktid, name, val)
        checkboxes = filter(lambda n: n[:9] == 'checkbox_', self.args.keys())
        for cb in [n[9:] for n in checkboxes]:
            if not 'custom_'+cb in cfields:
                cursor.execute('INSERT INTO ticket_custom(ticket,name,value)'
                               ' VALUES(%d, %s, 0)', tktid, cb)
        self.db.commit()

        # Notify
        tn = TicketNotifyEmail(self.env)
        tn.notify(tktid, newticket=1)

        # redirect to the Ticket module to get a GET request
        self.req.redirect(self.env.href.ticket(tktid))

    def render (self):
        if self.args.has_key('create'):
            self.create_ticket()

        default_component = self.env.get_config('ticket', 'default_component')
        default_milestone = self.env.get_config('ticket', 'default_milestone')
        default_priority  = self.env.get_config('ticket', 'default_priority')
        default_severity  = self.env.get_config('ticket', 'default_severity')
        default_version   = self.env.get_config('ticket', 'default_version')
        default_reporter  = get_reporter_id(self.req)

        component = self.args.get('component', default_component)
        milestone = self.args.get('milestone', default_milestone)
        priority = self.args.get('priority', default_priority)
        severity = self.args.get('severity', default_severity)
        version = self.args.get('version', default_version)
        reporter = self.args.get('reporter', default_reporter)

        cc = self.args.get('cc', '')
        owner = self.args.get('owner', '')
        summary = self.args.get('summary', '')
        keywords = self.args.get('keywords', '')
        description = self.args.get('description', '')

        if description:
            self.req.hdf.setValue('newticket.description_preview',
                                  wiki_to_html(description, self.req.hdf, self.env))
        self.req.hdf.setValue('title', 'New Ticket')
        self.req.hdf.setValue('newticket.component', component)
        self.req.hdf.setValue('newticket.milestone', milestone)
        self.req.hdf.setValue('newticket.priority', priority)
        self.req.hdf.setValue('newticket.severity', severity)
        self.req.hdf.setValue('newticket.version', version)
        self.req.hdf.setValue('newticket.summary', escape(summary))
        self.req.hdf.setValue('newticket.description', escape(description))
        self.req.hdf.setValue('newticket.cc', escape(cc))
        self.req.hdf.setValue('newticket.owner', escape(owner))
        self.req.hdf.setValue('newticket.keywords', escape(keywords))
        self.req.hdf.setValue('newticket.reporter', escape(reporter))

        sql_to_hdf(self.db, 'SELECT name FROM component ORDER BY name',
                   self.req.hdf, 'newticket.components')
        sql_to_hdf(self.db, 'SELECT name FROM milestone ORDER BY name',
                   self.req.hdf, 'newticket.milestones')
        sql_to_hdf(self.db, 'SELECT name FROM version ORDER BY name',
                   self.req.hdf, 'newticket.versions')

        insert_custom_fields(self.env, self.req.hdf)


class Ticket (Module):
    template_name = 'ticket.cs'

    _custom_rule = re.compile('(text|checkbox|select|radio)\(([^,\)]*)[ ,]*([^,\)]*)\)')

    def get_ticket (self, id, escape_values=1):
        return get_ticket(self.db, id, escape_values)

    def save_changes (self, id, old, new): 
        global fields

        action = new.get('action', None)
        if action == 'accept':
            new['status'] = 'assigned'
            new['owner'] = self.req.authname
        if action == 'resolve':
            new['status'] = 'closed'
            new['resolution'] = new['resolve_resolution']
        elif action == 'reassign':
            new['owner'] = new['reassign_owner']
            new['status'] = 'assigned'
        elif action == 'reopen':
            new['status'] = 'reopened'
            new['resolution'] = ''

        changed = 0
        change = ''
        cursor = self.db.cursor()
        now = int(time.time())
        if new.has_key('reporter'):
            author = new['reporter']
            del new['reporter']
        else:
            author = self.req.authname
        for name in fields:
            # Make sure to only log changes of interest. For example
            # we consider field values of '' and NULL to be identical
            if new.has_key(name) and \
               ((not old[name] and new[name]) or \
                (old[name] and not new[name]) or \
                (old[name] and new[name] and old[name] != new[name])):

                cursor.execute ('INSERT INTO ticket_change '
                                '(ticket, time, author, field, oldvalue, newvalue) '
                                'VALUES (%s, %s, %s, %s, %s, %s)',
                                id, now, author, name, old[name], new[name])
                cursor.execute ('UPDATE ticket SET %s=%s WHERE id=%s',
                                name, new[name], id)
                changed = 1
        comment = new.get('comment')
        if comment:
            cursor.execute ('INSERT INTO ticket_change '
                            '(ticket,time,author,field,oldvalue,newvalue) '
                            "VALUES (%s, %s, %s, 'comment', '', %s)",
                            id, now, author, comment)
            changed = 1
        if changed:
            cursor.execute ('UPDATE ticket SET changetime=%s WHERE id=%s',
                            now, id)
            self.db.commit()

        custom = new.get('custom')
        if custom:
            cursor = self.db.cursor()
            for name in custom.keys():
                val = custom[name]
                oldval = old.get('custom', {}).get(name)
                if val == oldval:
                    continue
                cursor.execute('REPLACE INTO ticket_custom(ticket,name,value)'
                               ' VALUES(%s, %s, %s)', id, name, val)
                cursor.execute ('INSERT INTO ticket_change '
                                '(ticket, time, author, field, oldvalue, newvalue) '
                                'VALUES (%s, %s, %s, %s, %s, %s)',
                                id, now, author, name, oldval, val)
            self.db.commit()

        tn = TicketNotifyEmail(self.env)
        tn.notify(id, newticket=0, modtime=now)

    def insert_ticket_data(self, hdf, id, info, reporter_id):
        """Inserts ticket data into the hdf"""
        add_dict_to_hdf(info, self.req.hdf, 'ticket')

        sql_to_hdf(self.db, 'SELECT name FROM component ORDER BY name',
                   self.req.hdf, 'ticket.components')
        sql_to_hdf(self.db, 'SELECT name FROM milestone ORDER BY name',
                   self.req.hdf, 'ticket.milestones')
        sql_to_hdf(self.db, 'SELECT name FROM version ORDER BY name',
                   self.req.hdf, 'ticket.versions')
        hdf_add_if_missing(self.req.hdf, 'ticket.components', info['component'])
        hdf_add_if_missing(self.req.hdf, 'ticket.milestones', info['milestone'])
        hdf_add_if_missing(self.req.hdf, 'ticket.versions', info['version'])
        hdf_add_if_missing(self.req.hdf, 'enums.priority', info['priority'])
        hdf_add_if_missing(self.req.hdf, 'enums.severity', info['severity'])

        self.req.hdf.setValue('ticket.reporter_id', escape(reporter_id))
        self.req.hdf.setValue('title', '#%d (ticket)' % id)
        self.req.hdf.setValue('ticket.description',
                              wiki_to_html(info['description'], self.req.hdf,
                                           self.env))
        self.req.hdf.setValue('ticket.opened',
                              time.strftime('%c', time.localtime(int(info['time']))))

        cursor = self.db.cursor()
        cursor.execute('SELECT time, author, field, oldvalue, newvalue '
                       'FROM ticket_change '
                       'WHERE ticket=%s ORDER BY time', id)

        curr_author = None
        curr_date   = 0
        comment = None
        idx = 0
        while 1:
            row = cursor.fetchone()
            if row == None:
                break

            date   = int(row[0])
            author = row[1] or ''
            field  = row[2] or ''
            old    = row[3] or ''
            new    = row[4] or ''

            hdf.setValue('ticket.changes.%d.date' % idx,
                         time.strftime('%c', time.localtime(date)))
            hdf.setValue('ticket.changes.%d.time' % idx, str(date))
            hdf.setValue('ticket.changes.%d.author' % idx, author)
            hdf.setValue('ticket.changes.%d.field' % idx, field)
            hdf.setValue('ticket.changes.%d.old' % idx, old)
            if field == 'comment':
                hdf.setValue('ticket.changes.%d.new' % idx,
                             wiki_to_html(new, self.req.hdf, self.env))
            else:
                hdf.setValue('ticket.changes.%d.new' % idx, new)
            idx = idx + 1

        cursor = self.db.cursor()
        cursor.execute('SELECT name, value FROM ticket_custom'
                       ' WHERE ticket=%i', id)
        rows = cursor.fetchall()
        customvals = {}
        for k,v in rows:
            customvals[k] = v
        insert_custom_fields(self.env, hdf, customvals)

        # List attached files
        self.env.get_attachments_hdf(self.db, 'ticket', str(id), self.req.hdf,
                                     'ticket.attachments')


    def render (self):
        action = self.args.get('action', 'view')
        preview = self.args.has_key('preview')

        if not self.args.has_key('id'):
            self.req.redirect(self.env.href.wiki())

        id = int(self.args.get('id'))

        if not preview \
               and action in ['leave', 'accept', 'reopen', 'resolve', 'reassign']:
            # save changes and redirect to avoid the POST request
            self.perm.assert_permission (perm.TICKET_MODIFY)
            old = self.get_ticket(id, 0)
            new = {}
            checkboxes = []
            for name in self.args.keys():
                new[name] = self.args[name].value
                if name[:9] == 'checkbox_':
                    checkboxes.append(self.args[name].value)
                if name[:7] == 'custom_':
                    cname = name[7:]
                    if not new.has_key('custom'):
                        new['custom'] = {}
                    new['custom'][cname] = self.args[name].value
            for cb in checkboxes:
                new['custom'][cb[7:]] = str(self.args.has_key(cb) and 1 or 0)
            self.save_changes (id, old, new)
            self.req.redirect(self.env.href.ticket(id))
        self.perm.assert_permission (perm.TICKET_VIEW)

        info = self.get_ticket(id)
        reporter_id = get_reporter_id(self.req)

        if preview:
            # Use user supplied values
            for field in fields:
                if self.args.has_key(field) and field != 'reporter':
                    info[field] = self.args.get(field)
            self.req.hdf.setValue('ticket.comment', self.args.get('comment'))
            reporter_id = self.args.get('reporter')
            # Wiki format a preview of comment
            self.req.hdf.setValue('ticket.comment_preview',
                                  wiki_to_html(self.args.get('comment'),
                                               self.req.hdf, self.env))

        self.insert_ticket_data(self.req.hdf, id, info, reporter_id)

