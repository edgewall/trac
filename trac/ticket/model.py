# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2006 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2006 Christian Boos <cboos@neuf.fr>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Jonas Borgström <jonas@edgewall.com>
#         Christopher Lenz <cmlenz@gmx.de>

import re
import sys
import time
from datetime import date, datetime

from trac.attachment import Attachment
from trac.core import TracError
from trac.resource import Resource, ResourceNotFound
from trac.ticket.api import TicketSystem
from trac.util import embedded_numbers, partition, sorted
from trac.util.datefmt import utc, utcmax, to_timestamp
from trac.util.translation import _

__all__ = ['Ticket', 'Type', 'Status', 'Resolution', 'Priority', 'Severity',
           'Component', 'Milestone', 'Version', 'group_milestones']


class Ticket(object):

    id_is_valid = staticmethod(lambda num: 0 < int(num) <= 1L << 31)

    def __init__(self, env, tkt_id=None, db=None, version=None):
        self.env = env
        self.resource = Resource('ticket', tkt_id, version)
        self.fields = TicketSystem(self.env).get_ticket_fields()
        self.values = {}
        if tkt_id is not None:
            self._fetch_ticket(tkt_id, db)
        else:
            self._init_defaults(db)
            self.id = self.time_created = self.time_changed = None
        self._old = {}

    def _get_db(self, db):
        return db or self.env.get_db_cnx()

    def _get_db_for_write(self, db):
        if db:
            return (db, False)
        else:
            return (self.env.get_db_cnx(), True)

    exists = property(fget=lambda self: self.id is not None)

    def _init_defaults(self, db=None):
        for field in self.fields:
            default = None
            if field['name'] in ['resolution', 'status']:
                # Ignore for new - only change through workflow
                pass
            elif not field.get('custom'):
                default = self.env.config.get('ticket',
                                              'default_' + field['name'])
            else:
                default = field.get('value')
                options = field.get('options')
                if default and options and default not in options:
                    try:
                        default = options[int(default)]
                    except (ValueError, IndexError):
                        self.env.log.warning('Invalid default value "%s" '
                                             'for custom field "%s"'
                                             % (default, field['name']))
            if default:
                self.values.setdefault(field['name'], default)

    def _fetch_ticket(self, tkt_id, db=None):
        row = None
        if self.id_is_valid(tkt_id):
            db = self._get_db(db)

            # Fetch the standard ticket fields
            std_fields = [f['name'] for f in self.fields if not f.get('custom')]
            cursor = db.cursor()
            cursor.execute("SELECT %s,time,changetime FROM ticket WHERE id=%%s"
                           % ','.join(std_fields), (tkt_id,))
            row = cursor.fetchone()
        if not row:
            raise ResourceNotFound('Ticket %s does not exist.' % tkt_id,
                                   'Invalid Ticket Number')

        self.id = tkt_id
        for i in range(len(std_fields)):
            if row[i] is not None:
                self.values[std_fields[i]] = row[i]
        self.time_created = datetime.fromtimestamp(row[len(std_fields)], utc)
        self.time_changed = datetime.fromtimestamp(row[len(std_fields) + 1], utc)

        # Fetch custom fields if available
        custom_fields = [f['name'] for f in self.fields if f.get('custom')]
        cursor.execute("SELECT name,value FROM ticket_custom WHERE ticket=%s",
                       (tkt_id,))
        for name, value in cursor:
            if name in custom_fields and value is not None:
                self.values[name] = value

    def __getitem__(self, name):
        return self.values.get(name)

    def __setitem__(self, name, value):
        """Log ticket modifications so the table ticket_change can be updated"""
        if name in self.values and self.values[name] == value:
            return
        if name not in self._old: # Changed field
            self._old[name] = self.values.get(name)
        elif self._old[name] == value: # Change of field reverted
            del self._old[name]
        if value:
            if isinstance(value, list):
                raise TracError(_("Multi-values fields not supported yet"))
            field = [field for field in self.fields if field['name'] == name]
            if field and field[0].get('type') != 'textarea':
                value = value.strip()
        self.values[name] = value

    def get_value_or_default(self, name):
        """Return the value of a field or the default value if it is
        undefined"""
        try:
            return self.values[name]
        except KeyError:
            field = [field for field in self.fields if field['name'] == name]
            if field:
                return field[0].get('value')
            return None
        
    def populate(self, values):
        """Populate the ticket with 'suitable' values from a dictionary"""
        field_names = [f['name'] for f in self.fields]
        for name in [name for name in values.keys() if name in field_names]:
            self[name] = values.get(name, '')

        # We have to do an extra trick to catch unchecked checkboxes
        for name in [name for name in values.keys() if name[9:] in field_names
                     and name.startswith('checkbox_')]:
            if name[9:] not in values:
                self[name[9:]] = '0'

    def insert(self, when=None, db=None):
        """Add ticket to database"""
        assert not self.exists, 'Cannot insert an existing ticket'
        db, handle_ta = self._get_db_for_write(db)

        # Add a timestamp
        if when is None:
            when = datetime.now(utc)
        self.time_created = self.time_changed = when

        cursor = db.cursor()

        # The owner field defaults to the component owner
        if self.values.get('component') and not self.values.get('owner'):
            try:
                component = Component(self.env, self['component'], db=db)
                if component.owner:
                    self['owner'] = component.owner
            except ResourceNotFound, e:
                # No such component exists
                pass

        # Insert ticket record
        created = to_timestamp(self.time_created)
        changed = to_timestamp(self.time_changed)
        std_fields = []
        custom_fields = []
        for f in self.fields:
            fname = f['name']
            if fname in self.values:
                if f.get('custom'):
                    custom_fields.append(fname)
                else:
                    std_fields.append(fname)
        cursor.execute("INSERT INTO ticket (%s,time,changetime) VALUES (%s)"
                       % (','.join(std_fields),
                          ','.join(['%s'] * (len(std_fields) + 2))),
                       [self[name] for name in std_fields] + [created, changed])
        tkt_id = db.get_last_id(cursor, 'ticket')

        # Insert custom fields
        if custom_fields:
            cursor.executemany("INSERT INTO ticket_custom (ticket,name,value) "
                               "VALUES (%s,%s,%s)", [(tkt_id, name, self[name])
                                                     for name in custom_fields])
        if handle_ta:
            db.commit()

        self.id = tkt_id
        self.resource = self.resource(id=tkt_id)
        self._old = {}

        for listener in TicketSystem(self.env).change_listeners:
            listener.ticket_created(self)

        return self.id

    def save_changes(self, author, comment, when=None, db=None, cnum=''):
        """
        Store ticket changes in the database. The ticket must already exist in
        the database.  Returns False if there were no changes to save, True
        otherwise.
        """
        assert self.exists, 'Cannot update a new ticket'

        if not self._old and not comment:
            return False # Not modified

        db, handle_ta = self._get_db_for_write(db)
        cursor = db.cursor()
        if when is None:
            when = datetime.now(utc)
        when_ts = to_timestamp(when)

        if 'component' in self.values:
            # If the component is changed on a 'new' ticket then owner field
            # is updated accordingly. (#623).
            if self.values.get('status') == 'new' \
                    and 'component' in self._old \
                    and 'owner' not in self._old:
                try:
                    old_comp = Component(self.env, self._old['component'], db)
                    old_owner = old_comp.owner or ''
                    current_owner = self.values.get('owner') or ''
                    if old_owner == current_owner:
                        new_comp = Component(self.env, self['component'], db)
                        if new_comp.owner:
                            self['owner'] = new_comp.owner
                except TracError, e:
                    # If the old component has been removed from the database we
                    # just leave the owner as is.
                    pass

        # Fix up cc list separators and remove duplicates
        if 'cc' in self.values:
            cclist = []
            for cc in re.split(r'[;,\s]+', self.values['cc']):
                if cc not in cclist:
                    cclist.append(cc)
            self.values['cc'] = ', '.join(cclist)

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
                           (self.id, when_ts, author, name, self._old[name],
                            self[name]))
        # always save comment, even if empty (numbering support for timeline)
        cursor.execute("INSERT INTO ticket_change "
                       "(ticket,time,author,field,oldvalue,newvalue) "
                       "VALUES (%s,%s,%s,'comment',%s,%s)",
                       (self.id, when_ts, author, cnum, comment))

        cursor.execute("UPDATE ticket SET changetime=%s WHERE id=%s",
                       (when_ts, self.id))

        if handle_ta:
            db.commit()
        old_values = self._old
        self._old = {}
        self.time_changed = when

        for listener in TicketSystem(self.env).change_listeners:
            listener.ticket_changed(self, comment, author, old_values)
        return True

    def get_changelog(self, when=None, db=None):
        """Return the changelog as a list of tuples of the form
        (time, author, field, oldvalue, newvalue, permanent).

        While the other tuple elements are quite self-explanatory,
        the `permanent` flag is used to distinguish collateral changes
        that are not yet immutable (like attachments, currently).
        """
        db = self._get_db(db)
        cursor = db.cursor()
        when_ts = when and to_timestamp(when) or 0
        if when_ts:
            cursor.execute("SELECT time,author,field,oldvalue,newvalue,1 "
                           "FROM ticket_change WHERE ticket=%s AND time=%s "
                           "UNION "
                           "SELECT time,author,'attachment',null,filename,0 "
                           "FROM attachment WHERE id=%s AND time=%s "
                           "UNION "
                           "SELECT time,author,'comment',null,description,0 "
                           "FROM attachment WHERE id=%s AND time=%s "
                           "ORDER BY time",
                           (self.id, when_ts, str(self.id), when_ts, 
                           str(self.id), when_ts))
        else:
            cursor.execute("SELECT time,author,field,oldvalue,newvalue,1 "
                           "FROM ticket_change WHERE ticket=%s "
                           "UNION "
                           "SELECT time,author,'attachment',null,filename,0 "
                           "FROM attachment WHERE id=%s "
                           "UNION "
                           "SELECT time,author,'comment',null,description,0 "
                           "FROM attachment WHERE id=%s "
                           "ORDER BY time", (self.id,  str(self.id), 
                           str(self.id)))
        log = []
        for t, author, field, oldvalue, newvalue, permanent in cursor:
            log.append((datetime.fromtimestamp(int(t), utc), author, field,
                       oldvalue or '', newvalue or '', permanent))
        return log

    def delete(self, db=None):
        db, handle_ta = self._get_db_for_write(db)
        Attachment.delete_all(self.env, 'ticket', self.id, db)
        cursor = db.cursor()
        cursor.execute("DELETE FROM ticket WHERE id=%s", (self.id,))
        cursor.execute("DELETE FROM ticket_change WHERE ticket=%s", (self.id,))
        cursor.execute("DELETE FROM ticket_custom WHERE ticket=%s", (self.id,))

        if handle_ta:
            db.commit()

        for listener in TicketSystem(self.env).change_listeners:
            listener.ticket_deleted(self)


def simplify_whitespace(name):
    """Strip spaces and remove duplicate spaces within names"""
    return ' '.join(name.split())
        

class AbstractEnum(object):
    type = None
    ticket_col = None

    def __init__(self, env, name=None, db=None):
        if not self.ticket_col:
            self.ticket_col = self.type
        self.env = env
        if name:
            name = simplify_whitespace(name)
        if name:
            if not db:
                db = self.env.get_db_cnx()
            cursor = db.cursor()
            cursor.execute("SELECT value FROM enum WHERE type=%s AND name=%s",
                           (self.type, name))
            row = cursor.fetchone()
            if not row:
                raise ResourceNotFound(_('%(type)s %(name)s does not exist.',
                                  type=self.type, name=name))
            self.value = self._old_value = row[0]
            self.name = self._old_name = name
        else:
            self.value = self._old_value = None
            self.name = self._old_name = None

    exists = property(fget=lambda self: self._old_value is not None)

    def delete(self, db=None):
        assert self.exists, 'Cannot delete non-existent %s' % self.type
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        cursor = db.cursor()
        self.env.log.info('Deleting %s %s' % (self.type, self.name))
        cursor.execute("DELETE FROM enum WHERE type=%s AND value=%s",
                       (self.type, self._old_value))
        # Re-order any enums that have higher value than deleted (close gap)
        for enum in list(self.select(self.env)):
            try:
                if int(enum.value) > int(self._old_value):
                    enum.value = unicode(int(enum.value) - 1)
                    enum.update(db=db)
            except ValueError:
                pass # Ignore cast error for this non-essential operation

        if handle_ta:
            db.commit()
        self.value = self._old_value = None
        self.name = self._old_name = None
        TicketSystem(self.env).reset_ticket_fields()

    def insert(self, db=None):
        assert not self.exists, 'Cannot insert existing %s' % self.type
        self.name = simplify_whitespace(self.name)
        assert self.name, 'Cannot create %s with no name' % self.type
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        cursor = db.cursor()
        self.env.log.debug("Creating new %s '%s'" % (self.type, self.name))
        if not self.value:
            cursor.execute(("SELECT COALESCE(MAX(%s),0) FROM enum "
                            "WHERE type=%%s") % db.cast('value', 'int'),
                           (self.type,))
            self.value = int(float(cursor.fetchone()[0])) + 1
        cursor.execute("INSERT INTO enum (type,name,value) VALUES (%s,%s,%s)",
                       (self.type, self.name, self.value))

        if handle_ta:
            db.commit()
        self._old_name = self.name
        self._old_value = self.value
        TicketSystem(self.env).reset_ticket_fields()

    def update(self, db=None):
        assert self.exists, 'Cannot update non-existent %s' % self.type
        self.name = simplify_whitespace(self.name)
        assert self.name, 'Cannot update %s with no name' % self.type
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        cursor = db.cursor()
        self.env.log.info('Updating %s "%s"' % (self.type, self.name))
        cursor.execute("UPDATE enum SET name=%s,value=%s "
                       "WHERE type=%s AND name=%s",
                       (self.name, self.value, self.type, self._old_name))
        if self.name != self._old_name:
            # Update tickets
            cursor.execute("UPDATE ticket SET %s=%%s WHERE %s=%%s" %
                           (self.ticket_col, self.ticket_col),
                           (self.name, self._old_name))

        if handle_ta:
            db.commit()
        self._old_name = self.name
        self._old_value = self.value
        TicketSystem(self.env).reset_ticket_fields()

    def select(cls, env, db=None):
        if not db:
            db = env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT name,value FROM enum WHERE type=%s "
                       "ORDER BY " + db.cast('value', 'int'),
                       (cls.type,))
        for name, value in cursor:
            obj = cls(env)
            obj.name = obj._old_name = name
            obj.value = obj._old_value = value
            yield obj
    select = classmethod(select)


class Type(AbstractEnum):
    type = 'ticket_type'
    ticket_col = 'type'


class Status(object):
    def __init__(self, env):
        self.env = env
    def select(cls, env, db=None):
        for state in TicketSystem(env).get_all_status():
            status = cls(env)
            status.name = state
            yield status
    select = classmethod(select)


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
            name = simplify_whitespace(name)
        if name:
            if not db:
                db = self.env.get_db_cnx()
            cursor = db.cursor()
            cursor.execute("SELECT owner,description FROM component "
                           "WHERE name=%s", (name,))
            row = cursor.fetchone()
            if not row:
                raise ResourceNotFound(_('Component %(name)s does not exist.',
                                  name=name))
            self.name = self._old_name = name
            self.owner = row[0] or None
            self.description = row[1] or ''
        else:
            self.name = self._old_name = None
            self.owner = None
            self.description = None

    exists = property(fget=lambda self: self._old_name is not None)

    def delete(self, db=None):
        assert self.exists, 'Cannot delete non-existent component'
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
        TicketSystem(self.env).reset_ticket_fields()

    def insert(self, db=None):
        assert not self.exists, 'Cannot insert existing component'
        self.name = simplify_whitespace(self.name)
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
        self._old_name = self.name

        if handle_ta:
            db.commit()
        TicketSystem(self.env).reset_ticket_fields()

    def update(self, db=None):
        assert self.exists, 'Cannot update non-existent component'
        self.name = simplify_whitespace(self.name)
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
        TicketSystem(self.env).reset_ticket_fields()

    def select(cls, env, db=None):
        if not db:
            db = env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT name,owner,description FROM component "
                       "ORDER BY name")
        for name, owner, description in cursor:
            component = cls(env)
            component.name = component._old_name = name
            component.owner = owner or None
            component.description = description or ''
            yield component
    select = classmethod(select)


class Milestone(object):

    def __init__(self, env, name=None, db=None):
        self.env = env
        if name:
            self._fetch(name, db)
            self._old_name = name
        else:
            self.name = self._old_name = None
            self.due = self.completed = None
            self.description = ''

    def _get_resource(self):
        return Resource('milestone', self.name) ### .version !!!
    resource = property(_get_resource)

    def _fetch(self, name, db=None):
        if not db:
            db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT name,due,completed,description "
                       "FROM milestone WHERE name=%s", (name,))
        row = cursor.fetchone()
        if not row:
            raise ResourceNotFound('Milestone %s does not exist.' % name,
                                   'Invalid Milestone Name')
        self._from_database(row)

    exists = property(fget=lambda self: self._old_name is not None)
    is_completed = property(fget=lambda self: self.completed is not None)
    is_late = property(fget=lambda self: self.due and \
                                         self.due.date() < date.today())

    def _from_database(self, row):
        name, due, completed, description = row
        self.name = self._old_name = name
        self.due = due and datetime.fromtimestamp(int(due), utc) or None
        self.completed = completed and \
                         datetime.fromtimestamp(int(completed), utc) or None
        self.description = description or ''

    def delete(self, retarget_to=None, author=None, db=None):
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        cursor = db.cursor()
        self.env.log.info('Deleting milestone %s' % self.name)
        cursor.execute("DELETE FROM milestone WHERE name=%s", (self.name,))

        # Retarget/reset tickets associated with this milestone
        now = datetime.now(utc)
        cursor.execute("SELECT id FROM ticket WHERE milestone=%s", (self.name,))
        tkt_ids = [int(row[0]) for row in cursor]
        for tkt_id in tkt_ids:
            ticket = Ticket(self.env, tkt_id, db)
            ticket['milestone'] = retarget_to
            ticket.save_changes(author, 'Milestone %s deleted' % self.name,
                                now, db=db)
        self.name = self._old_name = None

        if handle_ta:
            db.commit()
        TicketSystem(self.env).reset_ticket_fields()

    def insert(self, db=None):
        assert self.name, 'Cannot create milestone with no name'
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        self.name = simplify_whitespace(self.name)
        cursor = db.cursor()
        self.env.log.debug("Creating new milestone '%s'" % self.name)
        cursor.execute("INSERT INTO milestone (name,due,completed,description) "
                       "VALUES (%s,%s,%s,%s)",
                       (self.name, to_timestamp(self.due), to_timestamp(self.completed),
                        self.description))
        self._old_name = self.name

        if handle_ta:
            db.commit()
        TicketSystem(self.env).reset_ticket_fields()

    def update(self, db=None):
        assert self.name, 'Cannot update milestone with no name'
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        self.name = simplify_whitespace(self.name)
        cursor = db.cursor()
        self.env.log.info('Updating milestone "%s"' % self.name)
        cursor.execute("UPDATE milestone SET name=%s,due=%s,"
                       "completed=%s,description=%s WHERE name=%s",
                       (self.name, to_timestamp(self.due), to_timestamp(self.completed),
                        self.description,
                        self._old_name))
        self.env.log.info('Updating milestone field of all tickets '
                          'associated with milestone "%s"' % self.name)
        cursor.execute("UPDATE ticket SET milestone=%s WHERE milestone=%s",
                       (self.name, self._old_name))
        self._old_name = self.name

        if handle_ta:
            db.commit()
        TicketSystem(self.env).reset_ticket_fields()

    def select(cls, env, include_completed=True, db=None):
        if not db:
            db = env.get_db_cnx()
        sql = "SELECT name,due,completed,description FROM milestone "
        if not include_completed:
            sql += "WHERE COALESCE(completed,0)=0 "
        cursor = db.cursor()
        cursor.execute(sql)
        milestones = []
        for row in cursor:
            milestone = Milestone(env)
            milestone._from_database(row)
            milestones.append(milestone)
        def milestone_order(m):
            return (m.completed or utcmax,
                    m.due or utcmax,
                    embedded_numbers(m.name))
        return sorted(milestones, key=milestone_order)
    select = classmethod(select)


def group_milestones(milestones, include_completed):
    """Group milestones into "open with due date", "open with no due date",
    and possibly "completed". Return a list of (label, milestones) tuples."""
    def category(m):
        return m.is_completed and 1 or m.due and 2 or 3
    open_due_milestones, open_not_due_milestones, \
        closed_milestones = partition([(m, category(m))
            for m in milestones], (2, 3, 1))
    groups = [
        (_('Open (by due date)'), open_due_milestones),
        (_('Open (no due date)'), open_not_due_milestones),
    ]
    if include_completed:
        groups.append((_('Closed'), closed_milestones))
    return groups


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
                raise ResourceNotFound(_('Version %(name)s does not exist.',
                                  name=name))
            self.name = self._old_name = name
            self.time = row[0] and datetime.fromtimestamp(int(row[0]), utc) or None
            self.description = row[1] or ''
        else:
            self.name = self._old_name = None
            self.time = None
            self.description = None

    exists = property(fget=lambda self: self._old_name is not None)

    def delete(self, db=None):
        assert self.exists, 'Cannot delete non-existent version'
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
        TicketSystem(self.env).reset_ticket_fields()

    def insert(self, db=None):
        assert not self.exists, 'Cannot insert existing version'
        self.name = simplify_whitespace(self.name)
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
                       (self.name, to_timestamp(self.time), self.description))
        self._old_name = self.name

        if handle_ta:
            db.commit()
        TicketSystem(self.env).reset_ticket_fields()

    def update(self, db=None):
        assert self.exists, 'Cannot update non-existent version'
        self.name = simplify_whitespace(self.name)
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
                       (self.name, to_timestamp(self.time), self.description,
                        self._old_name))
        if self.name != self._old_name:
            # Update tickets
            cursor.execute("UPDATE ticket SET version=%s WHERE version=%s",
                           (self.name, self._old_name))
            self._old_name = self.name

        if handle_ta:
            db.commit()
        TicketSystem(self.env).reset_ticket_fields()

    def select(cls, env, db=None):
        if not db:
            db = env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT name,time,description FROM version")
        versions = []
        for name, time, description in cursor:
            version = cls(env)
            version.name = version._old_name = name
            version.time = time and datetime.fromtimestamp(int(time), utc) or None
            version.description = description or ''
            versions.append(version)
        def version_order(v):
            return (v.time or utcmax, embedded_numbers(v.name))
        return sorted(versions, key=version_order, reverse=True)
    select = classmethod(select)
