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
from types import ListType
from UserDict import UserDict

import perm
import util
from Module import Module
from WikiFormatter import wiki_to_html
from Notify import TicketNotifyEmail

__all__ = ['Ticket', 'NewticketModule', 'TicketModule']


class Ticket(UserDict):
    std_fields = ['time', 'component', 'severity', 'priority', 'milestone',
                  'reporter', 'owner', 'cc', 'url', 'version', 'status', 'resolution',
                  'keywords', 'summary', 'description']

    def __init__(self, *args):
        UserDict.__init__(self)
        self._old = {}
        if len(args) == 2:
            self._fetch_ticket(*args)

    def __setitem__(self, name, value):
        """Log ticket modifications so the table ticket_change can be updated"""
        if self.has_key(name) and self[name] == value:
            return
        if not self._old.has_key(name):
            self._old[name] = self.get(name, None)
        self.data[name] = value

    def _forget_changes(self):
        self._old = {}

    def _fetch_ticket(self, db, id):
        cursor = db.cursor ()
        fetch = string.join(Ticket.std_fields, ',')
        cursor.execute(('SELECT %s FROM ticket ' % fetch) + 'WHERE id=%s', id)
        row = cursor.fetchone ()
        cursor.close ()

        if not row:
            raise util.TracError('Ticket %d does not exist.' % id,
                                 'Invalid Ticket Number')

        self['id'] = id
        # Escape the values so that they are safe to have as html parameters
        for i in range(len(Ticket.std_fields)):
            self[Ticket.std_fields[i]] = row[i] or ''

        cursor = db.cursor ()
        cursor.execute('SELECT name,value FROM ticket_custom WHERE ticket=%i', id)
        rows = cursor.fetchall()
        if rows:
            for r in rows:
                self['custom_' + r[0]] = r[1]
        self._forget_changes()

    def populate(self, dict):
        """Populate the ticket with 'suitable' values from a dictionary"""
        names = filter(lambda n: n in Ticket.std_fields or \
                       n[:7] == 'custom_', dict.keys())
        for name in names:
            self[name] = dict.get(name, '')

        # We have to do an extra trick to catch unchecked checkboxes
        checkboxes = filter(lambda n: n[:9] == 'checkbox_', dict.keys())
        for name in ['custom_' + n[9:] for n in checkboxes]:
            if not dict.has_key(name):
                self[name] = '0'

    def insert(self, db):
        """Add ticket to database"""
        cursor = db.cursor()
        assert not self.has_key('id')

        # Add a timestamp
        now = int(time.time())
        self['time'] = now
        self['changetime'] = now

        std_fields = filter(lambda n: n[:7] != 'custom_', self.keys())
        custom_fields = filter(lambda n: n[:7] == 'custom_', self.keys())
        std_values = map(lambda n, self=self: self[n], std_fields)
        nstr = string.join(std_fields, ',')
        vstr = ('%s,' * len(std_fields))[:-1]
        cursor.execute('INSERT INTO ticket (%s) VALUES(%s)' % (nstr, vstr),
                       *std_values)
        id = db.db.sqlite_last_insert_rowid()
        for name in custom_fields:
            cursor.execute('INSERT INTO ticket_custom(ticket,name,value)'
                           ' VALUES(%d, %s, %s)', id, name[7:], self[name])
        db.commit()
        self['id'] = id
        self._forget_changes()
        return id

    def save_changes(self, db, author, comment, when = 0):
        """Store ticket changes in the database.
        The ticket must already exist in the database."""
        assert self.has_key('id')
        cursor = db.cursor()
        if not when:
            when = int(time.time())
        id = self['id']

        if not self._old and not comment: return # Not modified

        # If the component is changed on a 'new' ticket then owner field
        # is updated accordingly. (#623).
        if self['status'] == 'new' and self._old.has_key('component') and \
               not self._old.has_key('owner'):
            cursor.execute('SELECT owner FROM component '
                           'WHERE name=%s', self._old['component'])
            row = cursor.fetchone()
            # If the old component has been removed from the database
            # then we just leave the owner as is.
            if row:
                old_owner = row[0]
                if self['owner'] == old_owner:
                    cursor.execute('SELECT owner FROM component '
                                   'WHERE name=%s', self['component'])
                    self['owner'] = cursor.fetchone()[0]

        for name in self._old.keys():
            if name[:7] == 'custom_':
                fname = name[7:]
                cursor.execute('REPLACE INTO ticket_custom(ticket,name,value)'
                               ' VALUES(%s, %s, %s)', id, fname, self[name])
            else:
                fname = name
                cursor.execute ('UPDATE ticket SET %s=%s WHERE id=%s',
                                fname, self[name], id)

            cursor.execute ('INSERT INTO ticket_change '
                            '(ticket, time, author, field, oldvalue, newvalue) '
                            'VALUES (%s, %s, %s, %s, %s, %s)',
                            id, when, author, fname, self._old[name], self[name])
        if comment:
            cursor.execute ('INSERT INTO ticket_change '
                            '(ticket,time,author,field,oldvalue,newvalue) '
                            "VALUES (%s, %s, %s, 'comment', '', %s)",
                            id, when, author, comment)

        cursor.execute ('UPDATE ticket SET changetime=%s WHERE id=%s', when, id)
        db.commit()
        self._forget_changes()

    def get_changelog(self, db, when=0):
        """Returns the changelog as a list of dictionaries"""
        cursor = db.cursor()
        if when:
            cursor.execute('SELECT time, author, field, oldvalue, newvalue '
                           'FROM ticket_change '
                           'WHERE ticket=%s AND time=%s'
                           'UNION '
                           'SELECT time, author, "attachment", null, filename '
                           'FROM attachment '
                           'WHERE id=%s AND time=%s '
                           'ORDER BY time',  self['id'], when, self['id'], when)
        else:
            cursor.execute('SELECT time, author, field, oldvalue, newvalue '
                           'FROM ticket_change '
                           'WHERE ticket=%s '
                           'UNION '
                           'SELECT time, author, "attachment", null,filename '
                           'FROM attachment '
                           'WHERE id = %s '
                           'ORDER BY time', self['id'],  self['id'])
        log = []
        while 1:
            row = cursor.fetchone()
            if not row: break
            log.append((int(row[0]), row[1], row[2], row[3] or '', row[4] or ''))
        return log


def cmp_by_order(a, b):
    try:
        return int(a['order']) - int(b['order'])
    except:
        if a['order'] < b['order']:
            return -1
        elif a['order'] > b['order']:
            return 1
        else:
            return 0

def get_custom_fields(env):
    cfg = env.get_config_items('ticket-custom')
    if not cfg:
        return []
    names = []
    items = {}
    for k, v in cfg:
        items[k] = v
        if '.' not in k:
            names.append(k)
    fields = []
    for name in names:
        field = {
            'name': name,
            'type': items[name],
            'order': items.get(name + '.order', '0'),
            'label': items.get(name + '.label', ''),
            'value': items.get(name + '.value', '')
        }
        if field['type'] == 'select' or field['type'] == 'radio':
            field['options'] = items.get(name + '.options', '').split('|')
        elif field['type'] == 'textarea':
            field['width'] = items.get(name + '.cols', '')
            field['height'] = items.get(name + '.rows', '')
        fields.append(field)

    fields.sort(cmp_by_order)
    return fields


def insert_custom_fields(env, hdf, vals = {}):
    fields = get_custom_fields(env)
    i = 0
    for f in fields:
        name = f['name']
        val = vals.get('custom_' + name, f['value'])
        pfx = 'ticket.custom.%i' % i
        hdf.setValue('%s.name' % pfx, f['name'])
        hdf.setValue('%s.type' % pfx, f['type'])
        hdf.setValue('%s.label' % pfx, f['label'])
        hdf.setValue('%s.value' % pfx, val)
        if f['type'] == 'select' or f['type'] == 'radio':
            j = 0
            for option in f['options']:
                hdf.setValue('%s.option.%d' % (pfx, j), option)
                if val and (option == val or str(j) == val):
                    hdf.setValue('%s.option.%i.selected' % (pfx, j), '1')
                j += 1
        elif f['type'] == 'checkbox':
            if val in util.TRUE:
                hdf.setValue('%s.selected' % pfx, '1')
        elif f['type'] == 'textarea':
            hdf.setValue('%s.width' % pfx, f['width'])
            hdf.setValue('%s.height' % pfx, f['height'])
        i += 1


class NewticketModule(Module):
    template_name = 'newticket.cs'

    def create_ticket(self):
        if not self.args.get('summary'):
            raise util.TracError('Tickets must contain Summary.')

        ticket = Ticket()
        ticket.populate(self.args)
        ticket.setdefault('reporter',self.req.authname)

        # The owner field defaults to the component owner
        cursor = self.db.cursor()
        if ticket.get('component') and ticket.get('owner', '') == '':
            cursor.execute('SELECT owner FROM component '
                           'WHERE name=%s', ticket['component'])
            owner = cursor.fetchone()[0]
            ticket['owner'] = owner

        tktid = ticket.insert(self.db)

        # Notify
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=1)
        self.req.redirect(self.env.href.ticket(tktid))


    def render (self):
        self.perm.assert_permission(perm.TICKET_CREATE)

        if self.args.has_key('create'):
            self.create_ticket()

        ticket = Ticket()
        ticket.populate(self.args)
        ticket.setdefault('component',
                          self.env.get_config('ticket', 'default_component'))
        ticket.setdefault('milestone',
                          self.env.get_config('ticket', 'default_milestone'))
        ticket.setdefault('priority',
                          self.env.get_config('ticket', 'default_priority'))
        ticket.setdefault('severity',
                          self.env.get_config('ticket', 'default_severity'))
        ticket.setdefault('version',
                          self.env.get_config('ticket', 'default_version'))
        ticket.setdefault('reporter', util.get_reporter_id(self.req))

        if ticket.has_key('description'):
            self.req.hdf.setValue('newticket.description_preview',
                                  wiki_to_html(ticket['description'],
                                               self.req.hdf, self.env, self.db))

        self.req.hdf.setValue('title', 'New Ticket')
        evals = util.mydict(zip(ticket.keys(),
                                map(lambda x: util.escape(x), ticket.values())))
        util.add_to_hdf(evals, self.req.hdf, 'newticket')

        util.sql_to_hdf(self.db, 'SELECT name FROM component ORDER BY name',
                        self.req.hdf, 'newticket.components')
        util.sql_to_hdf(self.db, 'SELECT name FROM milestone ORDER BY name',
                        self.req.hdf, 'newticket.milestones')
        util.sql_to_hdf(self.db, 'SELECT name FROM version ORDER BY name',
                        self.req.hdf, 'newticket.versions')
        util.sql_to_hdf(self.db, "SELECT name FROM enum WHERE type='priority'"
                                 " ORDER BY value",
                        self.req.hdf, 'enums.priority')
        util.sql_to_hdf(self.db, "SELECT name FROM enum WHERE type='severity'"
                                 " ORDER BY value",
                        self.req.hdf, 'enums.severity')

        insert_custom_fields(self.env, self.req.hdf, ticket)


class TicketModule (Module):
    template_name = 'ticket.cs'

    def save_changes (self, id):
        self.perm.assert_permission (perm.TICKET_MODIFY)
        ticket = Ticket(self.db, id)

        if not self.args.get('summary'):
            raise util.TracError('Tickets must contain Summary.')

        if self.args.has_key('description'):
            self.perm.assert_permission (perm.TICKET_ADMIN)

        if self.args.has_key('reporter'):
            self.perm.assert_permission (perm.TICKET_ADMIN)

        # TODO: this should not be hard-coded like this
        action = self.args.get('action', None)
        if action == 'accept':
            ticket['status'] =  'assigned'
            ticket['owner'] = self.req.authname
        if action == 'resolve':
            ticket['status'] = 'closed'
            ticket['resolution'] = self.args.get('resolve_resolution')
        elif action == 'reassign':
            ticket['owner'] = self.args.get('reassign_owner')
            ticket['status'] = 'new'
        elif action == 'reopen':
            ticket['status'] = 'reopened'
            ticket['resolution'] = ''

        ticket.populate(self.args)

        now = int(time.time())

        ticket.save_changes(self.db,
                            self.args.get('author', self.req.authname),
                            self.args.get('comment'),
                            when=now)

        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=0, modtime=now)
        self.req.redirect(self.env.href.ticket(id))

    def insert_ticket_data(self, hdf, id, ticket, reporter_id):
        """Insert ticket data into the hdf"""
        evals = util.mydict(zip(ticket.keys(),
                                map(lambda x: util.escape(x), ticket.values())))
        util.add_to_hdf(evals, self.req.hdf, 'ticket')

        util.sql_to_hdf(self.db, 'SELECT name FROM component ORDER BY name',
                        self.req.hdf, 'ticket.components')
        util.sql_to_hdf(self.db, 'SELECT name FROM milestone ORDER BY name',
                        self.req.hdf, 'ticket.milestones')
        util.sql_to_hdf(self.db, 'SELECT name FROM version ORDER BY name',
                        self.req.hdf, 'ticket.versions')
        util.sql_to_hdf(self.db, "SELECT name FROM enum WHERE type='priority'"
                                 " ORDER BY value",
                        self.req.hdf, 'enums.priority')
        util.sql_to_hdf(self.db, "SELECT name FROM enum WHERE type='severity'"
                                 " ORDER BY value",
                        self.req.hdf, 'enums.severity')
        util.sql_to_hdf(self.db, "SELECT name FROM enum WHERE type='resolution'"
                                 " ORDER BY value",
                        self.req.hdf, 'enums.resolution')
        util.hdf_add_if_missing(self.req.hdf, 'ticket.components', ticket['component'])
        util.hdf_add_if_missing(self.req.hdf, 'ticket.milestones', ticket['milestone'])
        util.hdf_add_if_missing(self.req.hdf, 'ticket.versions', ticket['version'])
        util.hdf_add_if_missing(self.req.hdf, 'enums.priority', ticket['priority'])
        util.hdf_add_if_missing(self.req.hdf, 'enums.severity', ticket['severity'])
        util.hdf_add_if_missing(self.req.hdf, 'enums.resolution', 'fixed')

        self.req.hdf.setValue('ticket.reporter_id', util.escape(reporter_id))
        self.req.hdf.setValue('title', '#%d (%s)' % (id, util.escape(ticket['summary'])))
        self.req.hdf.setValue('ticket.description.formatted',
                              wiki_to_html(ticket['description'], self.req.hdf,
                                           self.env, self.db))
        self.req.hdf.setValue('ticket.opened', time.strftime('%c', time.localtime(int(ticket['time']))))

        changelog = ticket.get_changelog(self.db)
        curr_author = None
        curr_date   = 0
        comment = None
        idx = 0
        for date, author, field, old, new in changelog:
            hdf.setValue('ticket.changes.%d.date' % idx,
                         time.strftime('%c', time.localtime(date)))
            hdf.setValue('ticket.changes.%d.time' % idx, str(date))
            hdf.setValue('ticket.changes.%d.author' % idx, util.escape(author))
            hdf.setValue('ticket.changes.%d.field' % idx, field)
            hdf.setValue('ticket.changes.%d.old' % idx, util.escape(old))
            if field == 'comment':
                hdf.setValue('ticket.changes.%d.new' % idx,
                             wiki_to_html(new, self.req.hdf, self.env, self.db))
            else:
                hdf.setValue('ticket.changes.%d.new' % idx, util.escape(new))
            idx = idx + 1

        insert_custom_fields(self.env, hdf, ticket)
        # List attached files
        self.env.get_attachments_hdf(self.db, 'ticket', str(id), self.req.hdf,
                                     'ticket.attachments')

    def render (self):
        self.perm.assert_permission (perm.TICKET_VIEW)

        action = self.args.get('action', 'view')
        preview = self.args.has_key('preview')

        if not self.args.has_key('id'):
            self.req.redirect(self.env.href.wiki())

        id = int(self.args.get('id'))

        if not preview \
               and action in ['leave', 'accept', 'reopen', 'resolve', 'reassign']:
            self.save_changes (id)

        ticket = Ticket(self.db, id)
        reporter_id = util.get_reporter_id(self.req)

        if preview:
            # Use user supplied values
            for field in Ticket.std_fields:
                if self.args.has_key(field) and field != 'reporter':
                    ticket[field] = self.args.get(field)
            self.req.hdf.setValue('ticket.action', action)
            reporter_id = self.args.get('author')
            comment = self.args.get('comment')
            if comment:
                self.req.hdf.setValue('ticket.comment', util.escape(comment))
                # Wiki format a preview of comment
                self.req.hdf.setValue('ticket.comment_preview',
                                  wiki_to_html(comment,
                                               self.req.hdf, self.env, self.db))

        self.insert_ticket_data(self.req.hdf, id, ticket, reporter_id)

        cursor = self.db.cursor()
        cursor.execute("SELECT max(id) FROM ticket")
        row = cursor.fetchone()
        if row:
            max_id = int(row[0])
            if id > 1:
                self.add_link('first', self.env.href.ticket(1), 'Ticket #1')
                self.add_link('prev', self.env.href.ticket(id - 1),
                              'Ticket #%d' % (id - 1))
            if id < max_id:
                self.add_link('next', self.env.href.ticket(id + 1),
                              'Ticket #%d' % (id + 1))
                self.add_link('last', self.env.href.ticket(max_id),
                              'Ticket #%d' % (max_id))
