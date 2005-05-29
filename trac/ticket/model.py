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

import time


class Ticket(dict):
    std_fields = ['type', 'time', 'component', 'severity', 'priority',
                  'milestone', 'reporter', 'owner', 'cc', 'version', 'status',
                  'resolution', 'keywords', 'summary', 'description',
                  'changetime']

    def __init__(self, db=None, tkt_id=None):
        dict.__init__(self)
        self._old = {}
        if db and tkt_id:
            self._fetch_ticket(db, tkt_id)

    def __setitem__(self, name, value):
        """Log ticket modifications so the table ticket_change can be updated"""
        if self.has_key(name) and self[name] == value:
            return
        if not self._old.has_key(name): # Changed field
            self._old[name] = self.get(name, None)
        elif self._old[name] == value: # Change of field reverted
            del self._old[name]
        dict.__setitem__(self, name, value)

    def _forget_changes(self):
        self._old = {}

    def _fetch_ticket(self, db, tkt_id):
        # Fetch the standard ticket fields
        cursor = db.cursor()
        cursor.execute("SELECT %s FROM ticket WHERE id=%%s"
                       % ','.join(Ticket.std_fields), (tkt_id,))
        row = cursor.fetchone()
        if not row:
            raise TracError('Ticket %d does not exist.' % tkt_id,
                            'Invalid Ticket Number')

        self['id'] = tkt_id
        for i in range(len(Ticket.std_fields)):
            self[Ticket.std_fields[i]] = row[i] or ''

        # Fetch custom fields if available
        cursor.execute("SELECT name,value FROM ticket_custom WHERE ticket=%s",
                       (tkt_id,))
        for name, value in cursor:
            self['custom_' + name] = value

        self._forget_changes()

    def populate(self, data):
        """Populate the ticket with 'suitable' values from a dictionary"""
        for name in [name for name in data.keys()
                     if name in self.std_fields or name.startswith('custom_')]:
            self[name] = data.get(name, '')

        # We have to do an extra trick to catch unchecked checkboxes
        for name in ['custom_' + name[9:] for name in data.keys()
                     if name.startswith('checkbox_')]:
            if not data.has_key(name):
                self[name] = '0'

    def insert(self, db):
        """Add ticket to database"""
        assert not self.has_key('id'), 'Cannot insert an existing ticket'

        # Add a timestamp
        now = int(time.time())
        self['time'] = self['changetime'] = now

        cursor = db.cursor()

        std_fields = [name for name in self.keys() if name in self.std_fields]
        cursor.execute("INSERT INTO ticket (%s) VALUES (%s)"
                       % (','.join(std_fields),
                          ','.join(['%s'] * len(std_fields))),
                       [self[name] for name in std_fields])
        tkt_id = db.get_last_id('ticket')

        for name in [name for name in self.keys() if name.startswith('custom_')]:
            cursor.execute("INSERT INTO ticket_custom (ticket,name,value) "
                           "VALUES (%s,%s,%s)", (tkt_id, name[7:], self[name]))

        db.commit()
        self['id'] = tkt_id
        self._forget_changes()
        return tkt_id

    def save_changes(self, db, author, comment, when=0):
        """
        Store ticket changes in the database. The ticket must already exist in
        the database.
        """
        assert self.has_key('id'), 'Cannot update a new ticket'
        cursor = db.cursor()
        if not when:
            when = int(time.time())
        tkt_id = self['id']

        if not self._old and not comment:
            return # Not modified

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
                               "WHERE ticket=%s and name=%s", (tkt_id, fname))
                if cursor.fetchone():
                    cursor.execute("UPDATE ticket_custom SET value=%s "
                                   "WHERE ticket=%s AND name=%s",
                                   (self[name], tkt_id, fname))
                else:
                    cursor.execute("INSERT INTO ticket_custom (ticket,name,"
                                   "value) VALUES(%s,%s,%s)",
                                   (tkt_id, fname, self[name]))
            else:
                fname = name
                cursor.execute("UPDATE ticket SET %s=%%s WHERE id=%%s" % fname,
                               (self[name], tkt_id))
            cursor.execute("INSERT INTO ticket_change "
                           "(ticket,time,author,field,oldvalue,newvalue) "
                           "VALUES (%s, %s, %s, %s, %s, %s)",
                           (tkt_id, when, author, fname, self._old[name],
                            self[name]))
        if comment:
            cursor.execute("INSERT INTO ticket_change "
                           "(ticket,time,author,field,oldvalue,newvalue) "
                           "VALUES (%s,%s,%s,'comment','',%s)",
                           (tkt_id, when, author, comment))

        cursor.execute("UPDATE ticket SET changetime=%s WHERE id=%s",
                       (when, tkt_id))
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
                           "FROM ticket_change WHERE ticket=%s AND time=%s "
                           "UNION "
                           "SELECT time,author,'attachment',null,filename "
                           "FROM attachment WHERE id=%s AND time=%s "
                           "UNION "
                           "SELECT time,author,'comment',null,description "
                           "FROM attachment WHERE id=%s AND time=%s "
                           "ORDER BY time",
                           (self['id'], when, self['id'], when,
                            self['id'], when))
        else:
            cursor.execute("SELECT time,author,field,oldvalue,newvalue "
                           "FROM ticket_change WHERE ticket=%s "
                           "UNION "
                           "SELECT time,author,'attachment',null,filename "
                           "FROM attachment WHERE id=%s "
                           "UNION "
                           "SELECT time,author,'comment',null,description "
                           "FROM attachment WHERE id=%s "
                           "ORDER BY time",
                           (self['id'],  self['id'], self['id']))
        log = []
        for t, author, field, oldvalue, newvalue in cursor:
            log.append((int(t), author, field, oldvalue or '', newvalue or ''))
        return log
