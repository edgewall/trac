# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004, 2005 Edgewall Software
# Copyright (C) 2003, 2004, 2005 Jonas Borgström <jonas@edgewall.com>
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

from trac import perm, util
from trac.Module import Module
from trac.WikiFormatter import wiki_to_html
from trac.Notify import TicketNotifyEmail

import time
import string
from types import ListType
from UserDict import UserDict

__all__ = ['Ticket', 'NewticketModule', 'TicketModule']


class Ticket(UserDict):
    std_fields = ['time', 'component', 'severity', 'priority', 'milestone',
                  'reporter', 'owner', 'cc', 'url', 'version', 'status',
                  'resolution', 'keywords', 'summary', 'description',
                  'changetime']

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
        # Fetch the standard ticket fields
        cursor = db.cursor()
        cursor.execute("SELECT %s FROM ticket WHERE id=%%s"
                       % ','.join(Ticket.std_fields), (id,))
        row = cursor.fetchone()
        if not row:
            raise util.TracError('Ticket %d does not exist.' % id,
                                 'Invalid Ticket Number')

        self['id'] = id
        for i in range(len(Ticket.std_fields)):
            self[Ticket.std_fields[i]] = row[i] or ''

        # Fetch custom fields if available
        cursor.execute("SELECT name,value FROM ticket_custom WHERE ticket=%s",
                       (id,))
        rows = cursor.fetchall()
        if rows:
            for row in rows:
                self['custom_' + row[0]] = row[1]
        self._forget_changes()

    def populate(self, dict):
        """Populate the ticket with 'suitable' values from a dictionary"""
        def is_field(name):
            return name in Ticket.std_fields or name[:7] == 'custom_'
        for name in filter(is_field, dict.keys()):
            self[name] = dict.get(name, '')

        # We have to do an extra trick to catch unchecked checkboxes
        checkboxes = filter(lambda n: n[:9] == 'checkbox_', dict.keys())
        for name in ['custom_' + n[9:] for n in checkboxes]:
            if not dict.has_key(name):
                self[name] = '0'

    def insert(self, db):
        """Add ticket to database"""
        assert not self.has_key('id')

        # Add a timestamp
        now = int(time.time())
        self['time'] = now
        self['changetime'] = now

        cursor = db.cursor()

        std_fields = filter(lambda n: n in Ticket.std_fields, self.keys())
        cursor.execute("INSERT INTO ticket (%s) VALUES (%s)"
                       % (','.join(std_fields),
                          ','.join(['%s'] * len(std_fields))),
                       map(lambda n, self=self: self[n], std_fields))
        id = db.get_last_id()

        custom_fields = filter(lambda n: n[:7] == 'custom_', self.keys())
        for name in custom_fields:
            cursor.execute("INSERT INTO ticket_custom(ticket,name,value) "
                           "VALUES(%s,%s,%s)", (id, name[7:], self[name]))
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
            cursor.execute("SELECT owner FROM component "
                           "WHERE name=%s", (self._old['component'],))
            row = cursor.fetchone()
            # If the old component has been removed from the database
            # then we just leave the owner as is.
            if row:
                old_owner = row[0]
                if self['owner'] == old_owner:
                    cursor.execute("SELECT owner FROM component "
                                   "WHERE name=%s", (self['component'],))
                    self['owner'] = cursor.fetchone()[0]

        for name in self._old.keys():
            if name[:7] == 'custom_':
                fname = name[7:]
                cursor.execute("SELECT * FROM ticket_custom " 
                               "WHERE ticket=%s and name=%s", (id, fname))
                if cursor.fetchone():
                    cursor.execute("UPDATE ticket_custom SET value=%s "
                                   "WHERE ticket=%s AND name=%s",
                                   (self[name], id, fname))
                else:
                    cursor.execute("INSERT INTO ticket_custom (ticket,name,"
                                   "value) VALUES(%s,%s,%s)",
                                   (id, fname, self[name]))
            else:
                fname = name
                cursor.execute("UPDATE ticket SET %s=%s WHERE id=%s",
                               (fname, self[name], id))
            cursor.execute("INSERT INTO ticket_change "
                           "(ticket,time,author,field,oldvalue,newvalue) "
                           "VALUES (%s, %s, %s, %s, %s, %s)",
                           (id, when, author, fname, self._old[name],
                            self[name]))
        if comment:
            cursor.execute("INSERT INTO ticket_change "
                           "(ticket,time,author,field,oldvalue,newvalue) "
                           "VALUES (%s,%s,%s,'comment','',%s)",
                           (id, when, author, comment))

        cursor.execute("UPDATE ticket SET changetime=%s WHERE id=%s",
                       (when, id))
        db.commit()
        self._forget_changes()

    def get_changelog(self, db, when=0):
        """
        Returns the changelog as a list of tuples of the form
        (time, author, field, oldvalue, newvalue).
        """
        cursor = db.cursor()
        if when:
            cursor.execute("SELECT time,author,field,oldvalue,newvalue "
                           "FROM ticket_change "
                           "WHERE ticket=%s AND time=%s "
                           "UNION "
                           "SELECT time, author, 'attachment', null, filename "
                           "FROM attachment "
                           "WHERE id=%s AND time=%s "
                           "ORDER BY time",
                           (self['id'], when, self['id'], when))
        else:
            cursor.execute("SELECT time,author,field,oldvalue,newvalue "
                           "FROM ticket_change WHERE ticket=%s "
                           "UNION "
                           "SELECT time, author, 'attachment', null,filename "
                           "FROM attachment WHERE id = %s "
                           "ORDER BY time", (self['id'],  self['id']))
        log = []
        while 1:
            row = cursor.fetchone()
            if not row:
                break
            log.append((int(row[0]), row[1], row[2], row[3] or '', row[4] or ''))
        return log


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

    fields.sort(cmp_by_order)
    return fields


def insert_custom_fields(env, hdf, vals = {}):
    fields = get_custom_fields(env)
    i = 0
    for f in fields:
        name = f['name']
        val = vals.get('custom_' + name, f['value'])
        pfx = 'ticket.custom.%i' % i
        hdf['%s.name' % pfx] = f['name']
        hdf['%s.type' % pfx] = f['type']
        hdf['%s.label' % pfx] = f['label']
        hdf['%s.value' % pfx] = val
        if f['type'] == 'select' or f['type'] == 'radio':
            j = 0
            for option in f['options']:
                hdf['%s.option.%d' % (pfx, j)] = option
                if val and (option == val or str(j) == val):
                    hdf['%s.option.%i.selected' % (pfx, j)] = 1
                j += 1
        elif f['type'] == 'checkbox':
            if val in util.TRUE:
                hdf['%s.selected' % pfx] = 1
        elif f['type'] == 'textarea':
            hdf['%s.width' % pfx] = f['width']
            hdf['%s.height' % pfx] = f['height']
        i += 1


class NewticketModule(Module):
    template_name = 'newticket.cs'

    def create_ticket(self, req):
        if not req.args.get('summary'):
            raise util.TracError('Tickets must contain a summary.')

        ticket = Ticket()
        ticket.populate(req.args)
        ticket.setdefault('reporter', req.authname)

        # The owner field defaults to the component owner
        cursor = self.db.cursor()
        if ticket.get('component') and ticket.get('owner', '') == '':
            cursor.execute('SELECT owner FROM component '
                           'WHERE name=%s', ticket['component'])
            owner = cursor.fetchone()[0]
            ticket['owner'] = owner

        tktid = ticket.insert(self.db)

        # Notify
        try:
            tn = TicketNotifyEmail(self.env)
            tn.notify(ticket, newticket=1)
        except Exception, e:
            self.log.exception("Failure sending notification on creation of "
                               "ticket #%d: %s" % (tktid, e))

        req.redirect(self.env.href.ticket(tktid))

    def render(self, req):
        self.perm.assert_permission(perm.TICKET_CREATE)

        if req.args.has_key('create'):
            self.create_ticket(req)

        ticket = Ticket()
        ticket.populate(req.args)
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
        ticket.setdefault('reporter', util.get_reporter_id(req))

        if ticket.has_key('description'):
            req.hdf['newticket.description_preview'] = wiki_to_html(ticket['description'],
                                                                    req.hdf, self.env,
                                                                    self.db)

        req.hdf['title'] = 'New Ticket'
        evals = dict(zip(ticket.keys(),
                         map(lambda x: util.escape(x), ticket.values())))
        req.hdf['newticket'] = evals

        util.sql_to_hdf(self.db, "SELECT name FROM component ORDER BY name",
                        req.hdf, 'newticket.components')
        util.sql_to_hdf(self.db, "SELECT name FROM milestone WHERE completed=0 "
                                 "ORDER BY name",
                        req.hdf, 'newticket.milestones')
        util.sql_to_hdf(self.db, "SELECT name FROM version ORDER BY name",
                        req.hdf, 'newticket.versions')
        util.sql_to_hdf(self.db, "SELECT name FROM enum WHERE type='priority' "
                                 "ORDER BY value",
                        req.hdf, 'enums.priority')
        util.sql_to_hdf(self.db, "SELECT name FROM enum WHERE type='severity' "
                                 "ORDER BY value",
                        req.hdf, 'enums.severity')

        restrict_owner = self.env.get_config('ticket', 'restrict_owner')
        if restrict_owner.lower() in util.TRUE:
            users = []
            for username,name,email in self.env.get_known_users(self.db):
                label = username
                if name:
                    label = '%s (%s)' % (util.escape(username),
                                         util.escape(name))
                users.append({'name': username,'label': label})
            req.hdf['newticket.users'] = users

        insert_custom_fields(self.env, req.hdf, ticket)


class TicketModule (Module):
    template_name = 'ticket.cs'

    def save_changes(self, req, id):
        self.perm.assert_permission (perm.TICKET_MODIFY)
        ticket = Ticket(self.db, id)

        if not req.args.get('summary'):
            raise util.TracError('Tickets must contain Summary.')

        if req.args.has_key('description'):
            self.perm.assert_permission (perm.TICKET_ADMIN)

        if req.args.has_key('reporter'):
            self.perm.assert_permission (perm.TICKET_ADMIN)

        # TODO: this should not be hard-coded like this
        action = req.args.get('action', None)
        if action == 'accept':
            ticket['status'] =  'assigned'
            ticket['owner'] = req.authname
        if action == 'resolve':
            ticket['status'] = 'closed'
            ticket['resolution'] = req.args.get('resolve_resolution')
        elif action == 'reassign':
            ticket['owner'] = req.args.get('reassign_owner')
            ticket['status'] = 'new'
        elif action == 'reopen':
            ticket['status'] = 'reopened'
            ticket['resolution'] = ''

        ticket.populate(req.args)

        now = int(time.time())
        ticket.save_changes(self.db, req.args.get('author', req.authname),
                            req.args.get('comment'), when=now)

        try:
            tn = TicketNotifyEmail(self.env)
            tn.notify(ticket, newticket=0, modtime=now)
        except Exception, e:
            self.log.exception("Failure sending notification on change to "
                               "ticket #%d: %s" % (id, e))

        req.redirect(self.env.href.ticket(id))

    def insert_ticket_data(self, req, id, ticket, reporter_id):
        """Insert ticket data into the hdf"""
        evals = dict(zip(ticket.keys(),
                         map(lambda x: util.escape(x), ticket.values())))
        req.hdf['ticket'] = evals

        util.sql_to_hdf(self.db, "SELECT name FROM component ORDER BY name",
                        req.hdf, 'ticket.components')
        util.sql_to_hdf(self.db, "SELECT name FROM milestone ORDER BY name",
                        req.hdf, 'ticket.milestones')
        util.sql_to_hdf(self.db, "SELECT name FROM version ORDER BY name",
                        req.hdf, 'ticket.versions')
        util.sql_to_hdf(self.db, "SELECT name FROM enum WHERE type='priority'"
                                 " ORDER BY value",
                        req.hdf, 'enums.priority')
        util.sql_to_hdf(self.db, "SELECT name FROM enum WHERE type='severity'"
                                 " ORDER BY value",
                        req.hdf, 'enums.severity')
        util.sql_to_hdf(self.db, "SELECT name FROM enum WHERE type='resolution'"
                                 " ORDER BY value",
                        req.hdf, 'enums.resolution')
        util.hdf_add_if_missing(req.hdf, 'ticket.components', ticket['component'])
        util.hdf_add_if_missing(req.hdf, 'ticket.milestones', ticket['milestone'])
        util.hdf_add_if_missing(req.hdf, 'ticket.versions', ticket['version'])
        util.hdf_add_if_missing(req.hdf, 'enums.priority', ticket['priority'])
        util.hdf_add_if_missing(req.hdf, 'enums.severity', ticket['severity'])
        util.hdf_add_if_missing(req.hdf, 'enums.resolution', 'fixed')

        req.hdf['ticket.reporter_id'] = util.escape(reporter_id)
        req.hdf['title'] = '#%d (%s)' % (id, util.escape(ticket['summary']))
        req.hdf['ticket.description.formatted'] = wiki_to_html(ticket['description'],
                                                               req.hdf, self.env,
                                                               self.db)

        opened = int(ticket['time'])
        req.hdf['ticket.opened'] = time.strftime('%c', time.localtime(opened))
        req.hdf['ticket.opened_delta'] = util.pretty_timedelta(opened)
        lastmod = int(ticket['changetime'])
        if lastmod != opened:
            req.hdf['ticket.lastmod'] = time.strftime('%c', time.localtime(lastmod))
            req.hdf['ticket.lastmod_delta'] = util.pretty_timedelta(lastmod)

        restrict_owner = self.env.get_config('ticket', 'restrict_owner')
        if restrict_owner.lower() in util.TRUE:
            users = []
            for username,name,email in self.env.get_known_users(self.db):
                label = username
                if name:
                    label = '%s (%s)' % (util.escape(username),
                                         util.escape(name))
                users.append({'name': username,'label': label})
            req.hdf['ticket.users'] = users

        changelog = ticket.get_changelog(self.db)
        curr_author = None
        curr_date   = 0
        changes = []
        for date, author, field, old, new in changelog:
            if date != curr_date or author != curr_author:
                changes.append({
                    'date': time.strftime('%c', time.localtime(date)),
                    'author': util.escape(author),
                    'fields': {}
                })
                curr_date = date
                curr_author = author
            if field == 'comment':
                changes[-1]['comment'] = wiki_to_html(new, req.hdf, self.env,
                                                      self.db)
            elif field == 'description':
                changes[-1]['fields'][field] = ''
            else:
                changes[-1]['fields'][field] = {'old': old, 'new': new}
        req.hdf['ticket.changes'] = changes

        insert_custom_fields(self.env, req.hdf, ticket)
        # List attached files
        self.env.get_attachments_hdf(self.db, 'ticket', str(id), req.hdf,
                                     'ticket.attachments')
        req.hdf['ticket.attach_href'] = self.env.href.attachment('ticket',
                                                                 str(id), None)

    def render(self, req):
        self.perm.assert_permission (perm.TICKET_VIEW)

        action = req.args.get('action', 'view')
        preview = req.args.has_key('preview')

        if not req.args.has_key('id'):
            req.redirect(self.env.href.wiki())

        id = int(req.args.get('id'))

        if not preview \
           and action in ('leave', 'accept', 'reopen', 'resolve', 'reassign'):
            self.save_changes(req, id)

        ticket = Ticket(self.db, id)
        reporter_id = util.get_reporter_id(req)

        if preview:
            # Use user supplied values
            ticket.populate(req.args)
            req.hdf['ticket.action'] = action
            req.hdf['ticket.reassign_owner'] = req.args.get('reassign_owner')
            reporter_id = req.args.get('author')
            comment = req.args.get('comment')
            if comment:
                req.hdf['ticket.comment'] = util.escape(comment)
                # Wiki format a preview of comment
                req.hdf['ticket.comment_preview'] = wiki_to_html(comment,
                                                                 req.hdf,
                                                                 self.env,
                                                                 self.db)
        else:
            req.hdf['ticket.reassign_owner'] = req.authname

        self.insert_ticket_data(req, id, ticket, reporter_id)

        # If the ticket is being shown in the context of a query, add
        # links to help navigate in the query result set
        if 'query_tickets' in req.session:
            tickets = req.session['query_tickets'].split()
            if str(id) in tickets:
                idx = int(tickets.index(str(id)))
                if idx > 0:
                    self.add_link('first', self.env.href.ticket(tickets[0]),
                                  'Ticket #%s' % tickets[0])
                    self.add_link('prev', self.env.href.ticket(tickets[idx - 1]),
                                  'Ticket #%s' % tickets[idx - 1])
                if idx < len(tickets) - 1:
                    self.add_link('next', self.env.href.ticket(tickets[idx + 1]),
                                  'Ticket #%s' % tickets[idx + 1])
                    self.add_link('last', self.env.href.ticket(tickets[-1]),
                                  'Ticket #%s' % tickets[-1])
            self.add_link('up', req.session['query_href'])
