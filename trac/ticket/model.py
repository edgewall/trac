# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004, 2005 Edgewall Software
# Copyright (C) 2003, 2004, 2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
#         Christopher Lenz <cmlenz@gmx.de>

import time

from trac.core import TracError
from trac.ticket import TicketSystem

__all__ = ['Ticket', 'Type', 'Status', 'Resolution', 'Priority', 'Severity',
           'Component', 'Version']


class Ticket(object):

    def __init__(self, env, tkt_id=None, db=None):
        self.env = env
        self.fields = TicketSystem(self.env).get_ticket_fields()
        self.values = {}
        if tkt_id:
            self._fetch_ticket(tkt_id, db)
        else:
            self._init_defaults(db)
            self.id = self.time_created = self.time_changed = None
        self._old = {}

    exists = property(fget=lambda self: self.id is not None)

    def _init_defaults(self, db=None):
        for field in self.fields:
            default = None
            if not field.get('custom'):
                default = self.env.config.get('ticket',
                                              'default_' + field['name'])
            else:
                default = field.get('value')
                options = field.get('options', [])
                if default and default not in field.get('options', []):
                    try:
                        default_idx = int(default)
                        if default_idx > len(options):
                            raise ValueError
                        default = options[default_idx]
                    except ValueError:
                        self.env.log.warning('Invalid default value for '
                                             'custom field "%s"'
                                             % field['name'])
            if default:
                self.values.setdefault(field['name'], default)

    def _fetch_ticket(self, tkt_id, db=None):
        if not db:
            db = self.env.get_db_cnx()

        # Fetch the standard ticket fields
        std_fields = [f['name'] for f in self.fields if not f.get('custom')]
        cursor = db.cursor()
        cursor.execute("SELECT %s,time,changetime FROM ticket WHERE id=%%s"
                       % ','.join(std_fields), (tkt_id,))
        row = cursor.fetchone()
        if not row:
            raise TracError('Ticket %d does not exist.' % tkt_id,
                            'Invalid Ticket Number')

        self.id = tkt_id
        for i in range(len(std_fields)):
            self.values[std_fields[i]] = row[i] or ''
        self.time_created = row[len(std_fields)]
        self.time_changed = row[len(std_fields) + 1]

        # Fetch custom fields if available
        custom_fields = [f['name'] for f in self.fields if f.get('custom')]
        cursor.execute("SELECT name,value FROM ticket_custom WHERE ticket=%s",
                       (tkt_id,))
        for name, value in cursor:
            if name in custom_fields:
                self.values[name] = value

    def __getitem__(self, name):
        return self.values[name]

    def __setitem__(self, name, value):
        """Log ticket modifications so the table ticket_change can be updated"""
        if name in self.values.keys() and self.values[name] == value:
            return
        if name not in self._old.keys(): # Changed field
            self._old[name] = self.values.get(name)
        elif self._old[name] == value: # Change of field reverted
            del self._old[name]
        self.values[name] = value

    def populate(self, values):
        """Populate the ticket with 'suitable' values from a dictionary"""
        field_names = [f['name'] for f in self.fields]
        for name in [name for name in values.keys() if name in field_names]:
            self[name] = values.get(name, '')

        # We have to do an extra trick to catch unchecked checkboxes
        for name in [name for name in values.keys() if name[9:] in field_names
                     and name.startswith('checkbox_')]:
            if name[9:] not in values.keys():
                self[name[9:]] = '0'

    def insert(self, db=None):
        """Add ticket to database"""
        assert not self.exists, 'Cannot insert an existing ticket'
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        # Add a timestamp
        now = int(time.time())
        self.time_created = self.time_changed = now

        cursor = db.cursor()

        # The owner field defaults to the component owner
        if self.values.get('component') and not self.values.get('owner'):
            try:
                component = Component(self.env, self['component'], db=db)
                if component.owner:
                    self['owner'] = component.owner
            except TracError, e:
                # Assume that no such component exists
                pass

        # Insert ticket record
        std_fields = [f['name'] for f in self.fields if not f.get('custom')
                      and f['name'] in self.values.keys()]
        cursor.execute("INSERT INTO ticket (%s,time,changetime) VALUES (%s)"
                       % (','.join(std_fields),
                          ','.join(['%s'] * (len(std_fields) + 2))),
                       [self[name] for name in std_fields] +
                       [self.time_created, self.time_changed])
        tkt_id = db.get_last_id('ticket')

        # Insert custom fields
        custom_fields = [f['name'] for f in self.fields if f.get('custom')
                         and f['name'] in self.values.keys()]
        cursor.executemany("INSERT INTO ticket_custom (ticket,name,value) "
                           "VALUES (%s,%s,%s)", [(tkt_id, name, self[name])
                                                 for name in custom_fields])

        if handle_ta:
            db.commit()
        self.id = tkt_id
        self._old = {}
        return self.id

    def save_changes(self, author, comment, when=0, db=None):
        """
        Store ticket changes in the database. The ticket must already exist in
        the database.
        """
        assert self.exists, 'Cannot update a new ticket'
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False
        cursor = db.cursor()
        if not when:
            when = int(time.time())

        if not self._old and not comment:
            return # Not modified

        if 'component' in self.values.keys():
            # If the component is changed on a 'new' ticket then owner field
            # is updated accordingly. (#623).
            if self.values.get('status') == 'new' \
                    and 'component' in self._old.keys() \
                    and 'owner' not in self._old.keys():
                try:
                    old_comp = Component(self.env, self._old['component'], db)
                    if old_comp.owner == self.values.get('owner'):
                        new_comp = Component(self.env, self['component'],
                                             db)
                        self['owner'] = new_comp.owner
                except TracError, e:
                    # If the old component has been removed from the database we
                    # just leave the owner as is.
                    pass

        custom_fields = [f['name'] for f in self.fields if f.get('custom')]
        for name in self._old.keys():
            if name in custom_fields:
                cursor.execute("SELECT * FROM ticket_custom " 
                               "WHERE ticket=%s and name=%s", (self.id, name))
                if cursor.fetchone():
                    cursor.execute("UPDATE ticket_custom SET value=%s "
                                   "WHERE ticket=%s AND name=%s",
                                   (self[name], self.id, name))
                else:
                    cursor.execute("INSERT INTO ticket_custom (ticket,name,"
                                   "value) VALUES(%s,%s,%s)",
                                   (self.id, name, self[name]))
            else:
                cursor.execute("UPDATE ticket SET %s=%%s WHERE id=%%s" % name,
                               (self[name], self.id))
            cursor.execute("INSERT INTO ticket_change "
                           "(ticket,time,author,field,oldvalue,newvalue) "
                           "VALUES (%s, %s, %s, %s, %s, %s)",
                           (self.id, when, author, name, self._old[name],
                            self[name]))
        if comment:
            cursor.execute("INSERT INTO ticket_change "
                           "(ticket,time,author,field,oldvalue,newvalue) "
                           "VALUES (%s,%s,%s,'comment','',%s)",
                           (self.id, when, author, comment))

        cursor.execute("UPDATE ticket SET changetime=%s WHERE id=%s",
                       (when, self.id))
        if handle_ta:
            db.commit()
        self._old = {}
        self.time_changed = when

    def get_changelog(self, when=0, db=None):
        """Return the changelog as a list of tuples of the form
        (time, author, field, oldvalue, newvalue).
        """
        if not db:
            db = self.env.get_db_cnx()
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
                           (self.id, when, self.id, when, self.id, when))
        else:
            cursor.execute("SELECT time,author,field,oldvalue,newvalue "
                           "FROM ticket_change WHERE ticket=%s "
                           "UNION "
                           "SELECT time,author,'attachment',null,filename "
                           "FROM attachment WHERE id=%s "
                           "UNION "
                           "SELECT time,author,'comment',null,description "
                           "FROM attachment WHERE id=%s "
                           "ORDER BY time", (self.id,  self.id, self.id))
        log = []
        for t, author, field, oldvalue, newvalue in cursor:
            log.append((int(t), author, field, oldvalue or '', newvalue or ''))
        return log


class AbstractEnum(object):
    type = None

    def __init__(self, env, name=None, db=None):
        self.env = env
        if name:
            if not db:
                db = self.env.get_db_cnx()
            cursor = db.cursor()
            cursor.execute("SELECT value FROM enum WHERE type=%s AND name=%s",
                           (self.type, name))
            row = cursor.fetchone()
            if not row:
                raise TracError, '%s %s does not exist.' % (self.type, name)
            self.value = self._old_value = row[0]
            self.name = self._old_name = name
        else:
            self.value = self._old_value = None
            self.name = self._old_name = None

    exists = property(fget=lambda self: self._old_value is not None)

    def delete(self, db=None):
        assert self.exists, 'Cannot deleting non-existent %s' % self.type
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        cursor = db.cursor()
        self.env.log.info('Deleting %s %s' % (self.type, self.name))
        cursor.execute("DELETE FROM enum WHERE type=%s AND value=%s",
                       (self.type, self._old_value))
        self.value = self._old_value = None
        self.name = None

        if handle_ta:
            db.commit()

    def insert(self, db=None):
        assert self.name, 'Cannot create %s with no name' % self.type
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        cursor = db.cursor()
        self.env.log.debug("Creating new %s '%s'" % (self.type, self.name))
        value = self.value
        if not value:
            cursor.execute("SELECT COALESCE(MAX(value)) FROM enum "
                           "WHERE type=%s", (self.type,))
            value = int(cursor.fetchone()[0])
        cursor.execute("INSERT INTO enum (name,value) VALUES (%s,%s)",
                       (self.name, self.value))

        if handle_ta:
            db.commit()

    def update(self, db=None):
        assert self.exists, 'Cannot update non-existent %s' % self.type
        assert self.name, 'Cannot update %s with no name' % self.type
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        cursor = db.cursor()
        self.env.log.info('Updating %s "%s"' % (self.type, self.name))
        cursor.execute("UPDATE enum SET name=%s,value=%s "
                       "WHERE type=%s AND value=%s",
                       (self.name, self.value, self.type, self._old_value))
        if self.name != self._old_name:
            # Update tickets
            cursor.execute("UPDATE ticket SET %s=%%s WHERE %s=%%s" %
                           (self.type, self.type), (self.name, self._old_name))
            self._old_name = self.name
            self._old_value = self.value

        if handle_ta:
            db.commit()

    def select(cls, env, db=None):
        if not db:
            db = env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT name,value FROM enum WHERE type=%s "
                       "ORDER BY value", (cls.type,))
        for name, value in cursor:
            obj = cls(env)
            obj.name = name
            obj.value = value
            yield obj
    select = classmethod(select)


class Type(AbstractEnum):
    type = 'ticket_type'


class Status(AbstractEnum):
    type = 'status'


class Resolution(AbstractEnum):
    type = 'resolution'


class Priority(AbstractEnum):
    type = 'priority'


class Severity(AbstractEnum):
    type = 'severity'


class Component(object):

    def __init__(self, env, name=None, db=None):
        self.env = env
        if name:
            if not db:
                db = self.env.get_db_cnx()
            cursor = db.cursor()
            cursor.execute("SELECT owner,description FROM component "
                           "WHERE name=%s", (name,))
            row = cursor.fetchone()
            if not row:
                raise TracError, 'Component %s does not exist.' % name
            self.name = self._old_name = name
            self.owner = row[0] or None
            self.description = row[1] or ''
        else:
            self.name = self._old_name = None
            self.owner = None
            self.description = None

    exists = property(fget=lambda self: self._old_name is not None)

    def delete(self, db=None):
        assert self.exists, 'Cannot deleting non-existent component'
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        cursor = db.cursor()
        self.env.log.info('Deleting component %s' % self.name)
        cursor.execute("DELETE FROM component WHERE name=%s", (self.name,))

        self.name = self._old_name = None

        if handle_ta:
            db.commit()

    def insert(self, db=None):
        assert self.name, 'Cannot create component with no name'
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        cursor = db.cursor()
        self.env.log.debug("Creating new component '%s'" % self.name)
        cursor.execute("INSERT INTO component (name,owner,description) "
                       "VALUES (%s,%s,%s)",
                       (self.name, self.owner, self.description))

        if handle_ta:
            db.commit()

    def update(self, db=None):
        assert self.exists, 'Cannot update non-existent component'
        assert self.name, 'Cannot update component with no name'
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        cursor = db.cursor()
        self.env.log.info('Updating component "%s"' % self.name)
        cursor.execute("UPDATE component SET name=%s,owner=%s,description=%s "
                       "WHERE name=%s",
                       (self.name, self.owner, self.description,
                        self._old_name))
        if self.name != self._old_name:
            # Update tickets
            cursor.execute("UPDATE ticket SET component=%s WHERE component=%s",
                           (self.name, self._old_name))
            self._old_name = self.name

        if handle_ta:
            db.commit()

    def select(cls, env, db=None):
        if not db:
            db = env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT name,owner,description FROM component "
                       "ORDER BY name")
        for name, owner, description in cursor:
            component = cls(env)
            component.name = name
            component.owner = owner or None
            component.description = description or ''
            yield component
    select = classmethod(select)


class Version(object):

    def __init__(self, env, name=None, db=None):
        self.env = env
        if name:
            if not db:
                db = self.env.get_db_cnx()
            cursor = db.cursor()
            cursor.execute("SELECT time,description FROM version "
                           "WHERE name=%s", (name,))
            row = cursor.fetchone()
            if not row:
                raise TracError, 'Version %s does not exist.' % name
            self.name = self._old_name = name
            self.time = row[0] and int(row[0]) or None
            self.description = row[1] or ''
        else:
            self.name = self._old_name = None
            self.time = None
            self.description = None

    exists = property(fget=lambda self: self._old_name is not None)

    def delete(self, db=None):
        assert self.exists, 'Cannot deleting non-existent version'
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        cursor = db.cursor()
        self.env.log.info('Deleting version %s' % self.name)
        cursor.execute("DELETE FROM version WHERE name=%s", (self.name,))

        self.name = self._old_name = None

        if handle_ta:
            db.commit()

    def insert(self, db=None):
        assert self.name, 'Cannot create version with no name'
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        cursor = db.cursor()
        self.env.log.debug("Creating new version '%s'" % self.name)
        cursor.execute("INSERT INTO version (name,time,description) "
                       "VALUES (%s,%s,%s)",
                       (self.name, self.time, self.description))

        if handle_ta:
            db.commit()

    def update(self, db=None):
        assert self.exists, 'Cannot update non-existent version'
        assert self.name, 'Cannot update version with no name'
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        cursor = db.cursor()
        self.env.log.info('Updating version "%s"' % self.name)
        cursor.execute("UPDATE version SET name=%s,time=%s,description=%s "
                       "WHERE name=%s",
                       (self.name, self.time, self.description,
                        self._old_name))
        if self.name != self._old_name:
            # Update tickets
            cursor.execute("UPDATE ticket SET version=%s WHERE version=%s",
                           (self.name, self._old_name))
            self._old_name = self.name

        if handle_ta:
            db.commit()

    def select(cls, env, db=None):
        if not db:
            db = env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT name,time,description FROM version "
                       "ORDER BY COALESCE(time,0),name")
        for name, time, description in cursor:
            component = cls(env)
            component.name = name
            component.time = time and int(time) or None
            component.description = description or ''
            yield component
    select = classmethod(select)
