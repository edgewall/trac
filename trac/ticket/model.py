# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2006 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2006 Christian Boos <cboos@edgewall.org>
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

from __future__ import with_statement

import re

from trac.attachment import Attachment
from trac import core
from trac.cache import cached
from trac.core import TracError
from trac.resource import Resource, ResourceNotFound
from trac.ticket.api import TicketSystem
from trac.util import embedded_numbers, partition
from trac.util.text import empty
from trac.util.datefmt import datetime_now, from_utimestamp, to_utimestamp, \
                              utc, utcmax
from trac.util.translation import _

__all__ = ['Ticket', 'Type', 'Status', 'Resolution', 'Priority', 'Severity',
           'Component', 'Milestone', 'Version', 'group_milestones']


def _fixup_cc_list(cc_value):
    """Fix up cc list separators and remove duplicates."""
    cclist = []
    for cc in re.split(r'[;,\s]+', cc_value):
        if cc and cc not in cclist:
            cclist.append(cc)
    return ', '.join(cclist)


class Ticket(object):

    # Fields that must not be modified directly by the user
    protected_fields = ('resolution', 'status', 'time', 'changetime')

    @staticmethod
    def id_is_valid(num):
        try:
            return 0 < int(num) <= 1L << 31
        except (ValueError, TypeError):
            return False

    # 0.11 compatibility
    time_created = property(lambda self: self.values.get('time'))
    time_changed = property(lambda self: self.values.get('changetime'))

    def __init__(self, env, tkt_id=None, db=None, version=None):
        """
        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        self.env = env
        self.fields = TicketSystem(self.env).get_ticket_fields()
        self.editable_fields = \
            set(f['name'] for f in self.fields
                          if f['name'] not in self.protected_fields)
        self.std_fields, self.custom_fields, self.time_fields = [], [], []
        for f in self.fields:
            if f.get('custom'):
                self.custom_fields.append(f['name'])
            else:
                self.std_fields.append(f['name'])
            if f['type'] == 'time':
                self.time_fields.append(f['name'])
        self.values = {}
        if tkt_id is not None:
            self._fetch_ticket(tkt_id)
        else:
            self._init_defaults()
            self.id = None
        self.resource = Resource('ticket', self.id, version)
        self._old = {}

    exists = property(lambda self: self.id is not None)

    def _init_defaults(self):
        for field in self.fields:
            default = None
            if field['name'] in self.protected_fields:
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
                                             'for custom field "%s"',
                                             default, field['name'])
            if default:
                self.values.setdefault(field['name'], default)

    def _fetch_ticket(self, tkt_id):
        row = None
        if self.id_is_valid(tkt_id):
            # Fetch the standard ticket fields
            tkt_id = int(tkt_id)
            for row in self.env.db_query("SELECT %s FROM ticket WHERE id=%%s" %
                                         ','.join(self.std_fields), (tkt_id,)):
                break
        if not row:
            raise ResourceNotFound(_("Ticket %(id)s does not exist.",
                                     id=tkt_id), _("Invalid ticket number"))

        self.id = tkt_id
        for i, field in enumerate(self.std_fields):
            value = row[i]
            if field in self.time_fields:
                self.values[field] = from_utimestamp(value)
            elif value is None:
                self.values[field] = empty
            else:
                self.values[field] = value

        # Fetch custom fields if available
        for name, value in self.env.db_query("""
                SELECT name, value FROM ticket_custom WHERE ticket=%s
                """, (tkt_id,)):
            if name in self.custom_fields:
                if value is None:
                    self.values[name] = empty
                else:
                    self.values[name] = value

    def __getitem__(self, name):
        return self.values.get(name)

    def __setitem__(self, name, value):
        """Log ticket modifications so the table ticket_change can be updated
        """
        if value:
            if isinstance(value, list):
                raise TracError(_("Multi-values fields not supported yet"))
            field = [field for field in self.fields if field['name'] == name]
            if field and field[0].get('type') != 'textarea':
                value = value.strip()
        if name in self.values and self.values[name] == value:
            return
        if name not in self._old: # Changed field
            self._old[name] = self.values.get(name)
        elif self._old[name] == value: # Change of field reverted
            del self._old[name]
        self.values[name] = value

    def get_value_or_default(self, name):
        """Return the value of a field or the default value if it is undefined
        """
        try:
            value = self.values[name]
            return value if value is not empty else self.get_default(name)
        except KeyError:
            pass

    def get_default(self, name):
        """Return the default value of a field."""
        field = [field for field in self.fields if field['name'] == name]
        if field:
            return field[0].get('value', '')

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
        """Add ticket to database.

        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        assert not self.exists, 'Cannot insert an existing ticket'

        if 'cc' in self.values:
            self['cc'] = _fixup_cc_list(self.values['cc'])

        # Add a timestamp
        if when is None:
            when = datetime_now(utc)
        self.values['time'] = self.values['changetime'] = when

        # The owner field defaults to the component owner
        if self.values.get('owner') == '< default >':
            default_to_owner = ''
            if self.values.get('component'):
                try:
                    component = Component(self.env, self['component'])
                    default_to_owner = component.owner # even if it's empty
                except ResourceNotFound:
                    # No such component exists
                    pass
            # If the current owner is "< default >", we need to set it to
            # _something_ else, even if that something else is blank.
            self['owner'] = default_to_owner

        # Perform type conversions
        db_values = self._to_db_types(self.values)

        # Insert ticket record
        std_fields = []
        custom_fields = []
        for f in self.fields:
            fname = f['name']
            if fname in self.values:
                if f.get('custom'):
                    custom_fields.append(fname)
                else:
                    std_fields.append(fname)
        with self.env.db_transaction as db:
            cursor = db.cursor()
            cursor.execute("INSERT INTO ticket (%s) VALUES (%s)"
                           % (','.join(std_fields),
                              ','.join(['%s'] * len(std_fields))),
                           [db_values.get(name) for name in std_fields])
            tkt_id = db.get_last_id(cursor, 'ticket')

            # Insert custom fields
            if custom_fields:
                db.executemany(
                    """INSERT INTO ticket_custom (ticket, name, value)
                       VALUES (%s, %s, %s)
                    """, [(tkt_id, c, db_values.get(c)) for c in custom_fields])

        self.id = tkt_id
        self.resource = self.resource(id=tkt_id)
        self._old = {}

        for listener in TicketSystem(self.env).change_listeners:
            listener.ticket_created(self)

        return self.id

    def save_changes(self, author=None, comment=None, when=None, db=None,
                     cnum='', replyto=None):
        """
        Store ticket changes in the database. The ticket must already exist in
        the database.  Returns False if there were no changes to save, True
        otherwise.

        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        :since 1.0: the `cnum` parameter is deprecated, and threading should
        be controlled with the `replyto` argument
        """
        assert self.exists, "Cannot update a new ticket"

        if 'cc' in self.values:
            self['cc'] = _fixup_cc_list(self.values['cc'])

        props_unchanged = all(self.values.get(k) == v
                              for k, v in self._old.iteritems())
        if (not comment or not comment.strip()) and props_unchanged:
            return False # Not modified

        if when is None:
            when = datetime_now(utc)
        when_ts = to_utimestamp(when)

        if 'component' in self.values:
            # If the component is changed on a 'new' ticket
            # then owner field is updated accordingly. (#623).
            if self.values.get('status') == 'new' \
                    and 'component' in self._old \
                    and 'owner' not in self._old:
                try:
                    old_comp = Component(self.env, self._old['component'])
                    old_owner = old_comp.owner or ''
                    current_owner = self.values.get('owner') or ''
                    if old_owner == current_owner:
                        new_comp = Component(self.env, self['component'])
                        if new_comp.owner:
                            self['owner'] = new_comp.owner
                except TracError:
                    # If the old component has been removed from the database
                    # we just leave the owner as is.
                    pass

        # Perform type conversions
        db_values = self._to_db_types(self.values)
        old_db_values = self._to_db_types(self._old)

        with self.env.db_transaction as db:
            db("UPDATE ticket SET changetime=%s WHERE id=%s",
               (when_ts, self.id))

            # find cnum if it isn't provided
            if not cnum:
                num = 0
                for ts, old in db("""
                        SELECT DISTINCT tc1.time, COALESCE(tc2.oldvalue,'')
                        FROM ticket_change AS tc1
                        LEFT OUTER JOIN ticket_change AS tc2
                        ON tc2.ticket=%s AND tc2.time=tc1.time
                           AND tc2.field='comment'
                        WHERE tc1.ticket=%s ORDER BY tc1.time DESC
                        """, (self.id, self.id)):
                    # Use oldvalue if available, else count edits
                    try:
                        num += int(old.rsplit('.', 1)[-1])
                        break
                    except ValueError:
                        num += 1
                cnum = str(num + 1)
                if replyto:
                    cnum = '%s.%s' % (replyto, cnum)

            # store fields
            for name in self._old.keys():
                if name in self.custom_fields:
                    for row in db("""SELECT * FROM ticket_custom
                                     WHERE ticket=%s and name=%s
                                     """, (self.id, name)):
                        db("""UPDATE ticket_custom SET value=%s
                              WHERE ticket=%s AND name=%s
                              """, (db_values.get(name), self.id, name))
                        break
                    else:
                        db("""INSERT INTO ticket_custom (ticket,name,value)
                              VALUES(%s,%s,%s)
                              """, (self.id, name, db_values.get(name)))
                else:
                    db("UPDATE ticket SET %s=%%s WHERE id=%%s"
                       % name, (db_values.get(name), self.id))
                db("""INSERT INTO ticket_change
                        (ticket,time,author,field,oldvalue,newvalue)
                      VALUES (%s, %s, %s, %s, %s, %s)
                      """, (self.id, when_ts, author, name,
                            old_db_values.get(name), db_values.get(name)))

            # always save comment, even if empty
            # (numbering support for timeline)
            db("""INSERT INTO ticket_change
                    (ticket,time,author,field,oldvalue,newvalue)
                  VALUES (%s,%s,%s,'comment',%s,%s)
                  """, (self.id, when_ts, author, cnum, comment))

        old_values = self._old
        self._old = {}
        self.values['changetime'] = when

        for listener in TicketSystem(self.env).change_listeners:
            listener.ticket_changed(self, comment, author, old_values)
        return int(cnum.rsplit('.', 1)[-1])

    def _to_db_types(self, values):
        values = values.copy()
        for field, value in values.iteritems():
            if field in self.time_fields:
                values[field] = to_utimestamp(values[field])
            else:
                values[field] = value if value else None
        return values

    def get_changelog(self, when=None, db=None):
        """Return the changelog as a list of tuples of the form
        (time, author, field, oldvalue, newvalue, permanent).

        While the other tuple elements are quite self-explanatory,
        the `permanent` flag is used to distinguish collateral changes
        that are not yet immutable (like attachments, currently).

        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        sid = str(self.id)
        when_ts = to_utimestamp(when)
        if when_ts:
            sql = """
                SELECT time, author, field, oldvalue, newvalue, 1 AS permanent
                FROM ticket_change WHERE ticket=%s AND time=%s
                  UNION
                SELECT time, author, 'attachment', null, filename,
                  0 AS permanent
                FROM attachment WHERE type='ticket' AND id=%s AND time=%s
                  UNION
                SELECT time, author, 'comment', null, description,
                  0 AS permanent
                FROM attachment WHERE type='ticket' AND id=%s AND time=%s
                ORDER BY time,permanent,author
                """
            args = (self.id, when_ts, sid, when_ts, sid, when_ts)
        else:
            sql = """
                SELECT time, author, field, oldvalue, newvalue, 1 AS permanent
                FROM ticket_change WHERE ticket=%s
                  UNION
                SELECT time, author, 'attachment', null, filename,
                  0 AS permanent
                FROM attachment WHERE type='ticket' AND id=%s
                  UNION
                SELECT time, author, 'comment', null, description,
                  0 AS permanent
                FROM attachment WHERE type='ticket' AND id=%s
                ORDER BY time,permanent,author
                """
            args = (self.id, sid, sid)
        return [(from_utimestamp(t), author, field, oldvalue or '',
                 newvalue or '', permanent)
                for t, author, field, oldvalue, newvalue, permanent in
                self.env.db_query(sql, args)]

    def delete(self, db=None):
        """Delete the ticket.

        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        with self.env.db_transaction as db:
            Attachment.delete_all(self.env, 'ticket', self.id, db)
            db("DELETE FROM ticket WHERE id=%s", (self.id,))
            db("DELETE FROM ticket_change WHERE ticket=%s", (self.id,))
            db("DELETE FROM ticket_custom WHERE ticket=%s", (self.id,))

        for listener in TicketSystem(self.env).change_listeners:
            listener.ticket_deleted(self)

    def get_change(self, cnum=None, cdate=None, db=None):
        """Return a ticket change by its number or date.

        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        if cdate is None:
            row = self._find_change(cnum)
            if not row:
                return
            cdate = from_utimestamp(row[0])
        ts = to_utimestamp(cdate)
        fields = {}
        change = {'date': cdate, 'fields': fields}
        for field, author, old, new in self.env.db_query("""
                SELECT field, author, oldvalue, newvalue
                FROM ticket_change WHERE ticket=%s AND time=%s
                """, (self.id, ts)):
            fields[field] = {'author': author, 'old': old, 'new': new}
            if field == 'comment':
                change['author'] = author
            elif not field.startswith('_'):
                change.setdefault('author', author)
        if fields:
            return change

    def delete_change(self, cnum=None, cdate=None, when=None):
        """Delete a ticket change identified by its number or date."""
        if cdate is None:
            row = self._find_change(cnum)
            if not row:
                return
            cdate = from_utimestamp(row[0])
        ts = to_utimestamp(cdate)
        if when is None:
            when = datetime_now(utc)
        when_ts = to_utimestamp(when)

        with self.env.db_transaction as db:
            # Find modified fields and their previous value
            fields = [(field, old, new)
                      for field, old, new in db("""
                        SELECT field, oldvalue, newvalue FROM ticket_change
                        WHERE ticket=%s AND time=%s
                        """, (self.id, ts))
                      if field != 'comment' and not field.startswith('_')]
            for field, oldvalue, newvalue in fields:
                # Find the next change
                for next_ts, in db("""SELECT time FROM ticket_change
                                      WHERE ticket=%s AND time>%s AND field=%s
                                      LIMIT 1
                                      """, (self.id, ts, field)):
                    # Modify the old value of the next change if it is equal
                    # to the new value of the deleted change
                    db("""UPDATE ticket_change SET oldvalue=%s
                          WHERE ticket=%s AND time=%s AND field=%s
                          AND oldvalue=%s
                          """, (oldvalue, self.id, next_ts, field, newvalue))
                    break
                else:
                    # No next change, edit ticket field
                    if field in self.std_fields:
                        db("UPDATE ticket SET %s=%%s WHERE id=%%s"
                           % field, (oldvalue, self.id))
                    else:
                        db("""UPDATE ticket_custom SET value=%s
                              WHERE ticket=%s AND name=%s
                              """, (oldvalue, self.id, field))

            # Delete the change
            db("DELETE FROM ticket_change WHERE ticket=%s AND time=%s",
               (self.id, ts))

            # Update last changed time
            db("UPDATE ticket SET changetime=%s WHERE id=%s",
               (when_ts, self.id))

        self._fetch_ticket(self.id)

        changes = dict((field, (oldvalue, newvalue))
                       for field, oldvalue, newvalue in fields)
        for listener in TicketSystem(self.env).change_listeners:
            if hasattr(listener, 'ticket_change_deleted'):
                listener.ticket_change_deleted(self, cdate, changes)

    def modify_comment(self, cdate, author, comment, when=None):
        """Modify a ticket comment specified by its date, while keeping a
        history of edits.
        """
        ts = to_utimestamp(cdate)
        if when is None:
            when = datetime_now(utc)
        when_ts = to_utimestamp(when)

        with self.env.db_transaction as db:
            # Find the current value of the comment
            old_comment = False
            for old_comment, in db("""
                    SELECT newvalue FROM ticket_change
                    WHERE ticket=%s AND time=%s AND field='comment'
                    """, (self.id, ts)):
                break
            if comment == (old_comment or ''):
                return

            # Comment history is stored in fields named "_comment%d"
            # Find the next edit number
            fields = db("""SELECT field FROM ticket_change
                           WHERE ticket=%%s AND time=%%s AND field %s
                           """ % db.prefix_match(),
                           (self.id, ts, db.prefix_match_value('_comment')))
            rev = max(int(field[8:]) for field, in fields) + 1 if fields else 0
            db("""INSERT INTO ticket_change
                    (ticket,time,author,field,oldvalue,newvalue)
                  VALUES (%s,%s,%s,%s,%s,%s)
                  """, (self.id, ts, author, '_comment%d' % rev,
                        old_comment or '', str(when_ts)))
            if old_comment is False:
                # There was no comment field, add one, find the
                # original author in one of the other changed fields
                old_author = None
                for old_author, in db("""
                        SELECT author FROM ticket_change
                        WHERE ticket=%%s AND time=%%s AND NOT field %s LIMIT 1
                        """ % db.prefix_match(),
                        (self.id, ts, db.prefix_match_value('_'))):
                    db("""INSERT INTO ticket_change
                            (ticket,time,author,field,oldvalue,newvalue)
                          VALUES (%s,%s,%s,'comment','',%s)
                          """, (self.id, ts, old_author, comment))
            else:
                db("""UPDATE ticket_change SET newvalue=%s
                      WHERE ticket=%s AND time=%s AND field='comment'
                      """, (comment, self.id, ts))

            # Update last changed time
            db("UPDATE ticket SET changetime=%s WHERE id=%s",
               (when_ts, self.id))

        self.values['changetime'] = when

        old_comment = old_comment or ''
        for listener in TicketSystem(self.env).change_listeners:
            if hasattr(listener, 'ticket_comment_modified'):
                listener.ticket_comment_modified(self, cdate, author, comment,
                                                 old_comment)

    def get_comment_history(self, cnum=None, cdate=None, db=None):
        """Retrieve the edit history of a comment identified by its number or
        date.

        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        if cdate is None:
            row = self._find_change(cnum)
            if not row:
                return
            ts0, author0, last_comment = row
        else:
            ts0, author0, last_comment = to_utimestamp(cdate), None, None
        with self.env.db_query as db:
            # Get last comment and author if not available
            if last_comment is None:
                last_comment = ''
                for author0, last_comment in db("""
                        SELECT author, newvalue FROM ticket_change
                        WHERE ticket=%s AND time=%s AND field='comment'
                        """, (self.id, ts0)):
                    break
            if author0 is None:
                for author0, last_comment in db("""
                        SELECT author, newvalue FROM ticket_change
                        WHERE ticket=%%s AND time=%%s AND NOT field %s LIMIT 1
                        """ % db.prefix_match(),
                        (self.id, ts0, db.prefix_match_value('_'))):
                    break
                else:
                    return

            # Get all fields of the form "_comment%d"
            rows = db("""SELECT field, author, oldvalue, newvalue
                         FROM ticket_change
                         WHERE ticket=%%s AND time=%%s AND field %s
                         """ % db.prefix_match(),
                         (self.id, ts0, db.prefix_match_value('_comment')))
            rows = sorted((int(field[8:]), author, old, new)
                          for field, author, old, new in rows)
            history = []
            for rev, author, comment, ts in rows:
                history.append((rev, from_utimestamp(long(ts0)), author0,
                                comment))
                ts0, author0 = ts, author
            history.sort()
            rev = history[-1][0] + 1 if history else 0
            history.append((rev, from_utimestamp(long(ts0)), author0,
                            last_comment))
            return history

    def _find_change(self, cnum):
        """Find a comment by its number."""
        scnum = unicode(cnum)
        with self.env.db_query as db:
            for row in db("""
                    SELECT time, author, newvalue FROM ticket_change
                    WHERE ticket=%%s AND field='comment'
                    AND (oldvalue=%%s OR oldvalue %s)
                    """ % db.like(),
                    (self.id, scnum, '%' + db.like_escape('.' + scnum))):
                return row

            # Fallback when comment number is not available in oldvalue
            num = 0
            for ts, old, author, comment in db("""
                    SELECT DISTINCT tc1.time, COALESCE(tc2.oldvalue,''),
                                    tc2.author, COALESCE(tc2.newvalue,'')
                    FROM ticket_change AS tc1
                    LEFT OUTER JOIN ticket_change AS tc2
                    ON tc2.ticket=%s AND tc2.time=tc1.time
                       AND tc2.field='comment'
                    WHERE tc1.ticket=%s ORDER BY tc1.time
                    """, (self.id, self.id)):
                # Use oldvalue if available, else count edits
                try:
                    num = int(old.rsplit('.', 1)[-1])
                except ValueError:
                    num += 1
                if num == cnum:
                    break
            else:
                return

            # Find author if NULL
            if author is None:
                for author, in db("""
                        SELECT author FROM ticket_change
                        WHERE ticket=%%s AND time=%%s AND NOT field %s LIMIT 1
                        """ % db.prefix_match(),
                        (self.id, ts, db.prefix_match_value('_'))):
                    break
            return (ts, author, comment)


def simplify_whitespace(name):
    """Strip spaces and remove duplicate spaces within names"""
    if name:
        return ' '.join(name.split())
    return name


class AbstractEnum(object):
    type = None
    ticket_col = None

    def __init__(self, env, name=None, db=None):
        if not self.ticket_col:
            self.ticket_col = self.type
        self.env = env
        if name:
            for value, in self.env.db_query("""
                    SELECT value FROM enum WHERE type=%s AND name=%s
                    """, (self.type, name)):
                self.value = self._old_value = value
                self.name = self._old_name = name
                break
            else:
                raise ResourceNotFound(_("%(type)s %(name)s does not exist.",
                                         type=self.type, name=name))
        else:
            self.value = self._old_value = None
            self.name = self._old_name = None

    exists = property(lambda self: self._old_value is not None)

    def delete(self, db=None):
        """Delete the enum value.

        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        assert self.exists, "Cannot delete non-existent %s" % self.type

        with self.env.db_transaction as db:
            self.env.log.info("Deleting %s %s", self.type, self.name)
            db("DELETE FROM enum WHERE type=%s AND value=%s",
               (self.type, self._old_value))
            # Re-order any enums that have higher value than deleted
            # (close gap)
            for enum in self.select(self.env):
                try:
                    if int(enum.value) > int(self._old_value):
                        enum.value = unicode(int(enum.value) - 1)
                        enum.update()
                except ValueError:
                    pass # Ignore cast error for this non-essential operation
            TicketSystem(self.env).reset_ticket_fields()
        self.value = self._old_value = None
        self.name = self._old_name = None

    def insert(self, db=None):
        """Add a new enum value.

        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        assert not self.exists, "Cannot insert existing %s" % self.type
        self.name = simplify_whitespace(self.name)
        if not self.name:
            raise TracError(_('Invalid %(type)s name.', type=self.type))

        with self.env.db_transaction as db:
            self.env.log.debug("Creating new %s '%s'", self.type, self.name)
            if not self.value:
                row = db("SELECT COALESCE(MAX(%s), 0) FROM enum WHERE type=%%s"
                         % db.cast('value', 'int'),
                         (self.type,))
                self.value = int(float(row[0][0])) + 1 if row else 0
            db("INSERT INTO enum (type, name, value) VALUES (%s, %s, %s)",
               (self.type, self.name, self.value))
            TicketSystem(self.env).reset_ticket_fields()

        self._old_name = self.name
        self._old_value = self.value

    def update(self, db=None):
        """Update the enum value.

        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        assert self.exists, "Cannot update non-existent %s" % self.type
        self.name = simplify_whitespace(self.name)
        if not self.name:
            raise TracError(_("Invalid %(type)s name.", type=self.type))

        with self.env.db_transaction as db:
            self.env.log.info("Updating %s '%s'", self.type, self.name)
            db("UPDATE enum SET name=%s,value=%s WHERE type=%s AND name=%s",
               (self.name, self.value, self.type, self._old_name))
            if self.name != self._old_name:
                # Update tickets
                db("UPDATE ticket SET %s=%%s WHERE %s=%%s"
                   % (self.ticket_col, self.ticket_col),
                   (self.name, self._old_name))
            TicketSystem(self.env).reset_ticket_fields()

        self._old_name = self.name
        self._old_value = self.value

    @classmethod
    def select(cls, env, db=None):
        """
        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        with env.db_query as db:
            for name, value in db("""
                    SELECT name, value FROM enum WHERE type=%s ORDER BY
                    """ + db.cast('value', 'int'),
                    (cls.type,)):
                obj = cls(env)
                obj.name = obj._old_name = name
                obj.value = obj._old_value = value
                yield obj


class Type(AbstractEnum):
    type = 'ticket_type'
    ticket_col = 'type'


class Status(object):
    def __init__(self, env):
        self.env = env

    @classmethod
    def select(cls, env, db=None):
        for state in TicketSystem(env).get_all_status():
            status = cls(env)
            status.name = state
            yield status


class Resolution(AbstractEnum):
    type = 'resolution'


class Priority(AbstractEnum):
    type = 'priority'


class Severity(AbstractEnum):
    type = 'severity'


class Component(object):
    def __init__(self, env, name=None, db=None):
        """
        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        self.env = env
        self.name = self._old_name = self.owner = self.description = None
        if name:
            for owner, description in self.env.db_query("""
                    SELECT owner, description FROM component WHERE name=%s
                    """, (name,)):
                self.name = self._old_name = name
                self.owner = owner or None
                self.description = description or ''
                break
            else:
                raise ResourceNotFound(_("Component %(name)s does not exist.",
                                         name=name))

    exists = property(lambda self: self._old_name is not None)

    def delete(self, db=None):
        """Delete the component.

        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        assert self.exists, "Cannot delete non-existent component"

        with self.env.db_transaction as db:
            self.env.log.info("Deleting component %s", self.name)
            db("DELETE FROM component WHERE name=%s", (self.name,))
            self.name = self._old_name = None
            TicketSystem(self.env).reset_ticket_fields()

    def insert(self, db=None):
        """Insert a new component.

        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        assert not self.exists, "Cannot insert existing component"
        self.name = simplify_whitespace(self.name)
        if not self.name:
            raise TracError(_("Invalid component name."))

        with self.env.db_transaction as db:
            self.env.log.debug("Creating new component '%s'", self.name)
            db("""INSERT INTO component (name,owner,description)
                  VALUES (%s,%s,%s)
                  """, (self.name, self.owner, self.description))
            self._old_name = self.name
            TicketSystem(self.env).reset_ticket_fields()

    def update(self, db=None):
        """Update the component.

        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        assert self.exists, "Cannot update non-existent component"
        self.name = simplify_whitespace(self.name)
        if not self.name:
            raise TracError(_("Invalid component name."))

        with self.env.db_transaction as db:
            self.env.log.info("Updating component '%s'", self.name)
            db("""UPDATE component SET name=%s,owner=%s, description=%s
                  WHERE name=%s
                  """, (self.name, self.owner, self.description,
                        self._old_name))
            if self.name != self._old_name:
                # Update tickets
                db("UPDATE ticket SET component=%s WHERE component=%s",
                   (self.name, self._old_name))
                self._old_name = self.name
            TicketSystem(self.env).reset_ticket_fields()

    @classmethod
    def select(cls, env, db=None):
        """
        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        for name, owner, description in env.db_query("""
                SELECT name, owner, description FROM component ORDER BY name
            """):
            component = cls(env)
            component.name = component._old_name = name
            component.owner = owner or None
            component.description = description or ''
            yield component


class MilestoneCache(core.Component):
    """Cache for milestone data and factory for 'milestone' resources."""

    @cached
    def milestones(self):
        """Dictionary containing milestone data, indexed by name.

        Milestone data consist of a tuple containing the name, the
        datetime objects for due and completed dates and the
        description.
        """
        milestones = {}
        for name, due, completed, description in self.env.db_query("""
                SELECT name, due, completed, description FROM milestone
                """):
            milestones[name] = (name,
                    from_utimestamp(due) if due else None,
                    from_utimestamp(completed) if completed else None,
                    description or '')
        return milestones

    def fetchone(self, name, milestone=None):
        """Retrieve an existing milestone having the given `name`.

        If `milestone` is specified, fill that instance instead of creating
        a fresh one.

        :return: `None` if no such milestone exists
        """
        data = self.milestones.get(name)
        if data:
            return self.factory(data, milestone)

    def fetchall(self):
        """Iterator on all milestones."""
        for data in self.milestones.itervalues():
            yield self.factory(data)

    def factory(self, (name, due, completed, description), milestone=None):
        """Build a `Milestone` object from milestone data.

        That instance remains *private*, i.e. can't be retrieved by
        name by other processes or even by other threads in the same
        process, until its `~Milestone.insert` method gets called with
        success.
        """
        milestone = milestone or Milestone(self.env)
        milestone.name = name
        milestone.due = due
        milestone.completed = completed
        milestone.description = description
        milestone.checkin(invalidate=False)
        return milestone


class Milestone(object):
    def __init__(self, env, name=None, db=None):
        """Create an undefined milestone or fetch one from the database,
        if `name` is given.

        In the latter case however, raise `~trac.resource.ResourceNotFound`
        if a milestone of that name doesn't exist yet.
        """
        self.env = env
        if name:
            if not self.cache.fetchone(name, self):
                raise ResourceNotFound(
                    _("Milestone %(name)s does not exist.",
                      name=name), _("Invalid milestone name"))
        else:
            self.cache.factory((None, None, None, ''), self)

    @property
    def cache(self):
        return MilestoneCache(self.env)

    @property
    def resource(self):
        return Resource('milestone', self.name) ### .version !!!

    exists = property(lambda self: self._old['name'] is not None)
    is_completed = property(lambda self: self.completed is not None)
    is_late = property(lambda self: self.due and
                                    self.due < datetime_now(utc))

    def checkin(self, invalidate=True):
        self._old = {'name': self.name, 'due': self.due,
                     'completed': self.completed,
                     'description': self.description}
        if invalidate:
            del self.cache.milestones

    _to_old = checkin #: compatibility with hacks < 0.12.5 (remove in 1.1.1)

    def delete(self, retarget_to=None, author=None, db=None):
        """Delete the milestone.

        :since 1.0.2: the `retarget_to` and `author` parameters are
                      deprecated and will be removed in Trac 1.3.1. Tickets
                      should be moved to another milestone by calling
                      `move_tickets` before `delete`.

        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        with self.env.db_transaction as db:
            self.env.log.info("Deleting milestone %s", self.name)
            db("DELETE FROM milestone WHERE name=%s", (self.name,))
            Attachment.delete_all(self.env, 'milestone', self.name)
            # Don't translate ticket comment (comment:40:ticket:5658)
            self.move_tickets(retarget_to, author, "Milestone deleted")
            self._old['name'] = None
            del self.cache.milestones
            TicketSystem(self.env).reset_ticket_fields()

        for listener in TicketSystem(self.env).milestone_change_listeners:
            listener.milestone_deleted(self)

    def insert(self, db=None):
        """Insert a new milestone.

        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        self.name = simplify_whitespace(self.name)
        if not self.name:
            raise TracError(_("Invalid milestone name."))

        with self.env.db_transaction as db:
            self.env.log.debug("Creating new milestone '%s'", self.name)
            db("""INSERT INTO milestone (name, due, completed, description)
                  VALUES (%s,%s,%s,%s)
                  """, (self.name, to_utimestamp(self.due),
                        to_utimestamp(self.completed), self.description))
            self.checkin()
            TicketSystem(self.env).reset_ticket_fields()

        for listener in TicketSystem(self.env).milestone_change_listeners:
            listener.milestone_created(self)

    def update(self, db=None, author=None):
        """Update the milestone.

        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        self.name = simplify_whitespace(self.name)
        if not self.name:
            raise TracError(_("Invalid milestone name."))

        old = self._old.copy()
        with self.env.db_transaction as db:
            if self.name != old['name']:
                # Update milestone field in tickets
                self.move_tickets(self.name, author, "Milestone renamed")
                # Reparent attachments
                Attachment.reparent_all(self.env, 'milestone', old['name'],
                                        'milestone', self.name)

            self.env.log.info("Updating milestone '%s'", old['name'])
            db("""UPDATE milestone
                  SET name=%s, due=%s, completed=%s, description=%s
                  WHERE name=%s
                  """, (self.name, to_utimestamp(self.due),
                        to_utimestamp(self.completed),
                        self.description, old['name']))
            self.checkin()
        # Fields need reset if renamed or completed/due changed
        TicketSystem(self.env).reset_ticket_fields()

        old_values = dict((k, v) for k, v in old.iteritems()
                          if getattr(self, k) != v)
        for listener in TicketSystem(self.env).milestone_change_listeners:
            listener.milestone_changed(self, old_values)

    def move_tickets(self, new_milestone, author, comment=None,
                     exclude_closed=False):
        """Move tickets associated with this milestone to another
        milestone.

        :param new_milestone: milestone to which the tickets are moved
        :param author: author of the change
        :param comment: comment that is inserted into moved tickets. The
                        string should not be translated.
        :param exclude_closed: whether tickets with status closed should be
                               excluded

        :return: a list of ids of tickets that were moved
        """
        # Check if milestone exists, but if the milestone is being renamed
        # the new milestone won't exist in the cache yet so skip the test
        if new_milestone and new_milestone != self.name:
            if not self.cache.fetchone(new_milestone):
                raise ResourceNotFound(
                    _("Milestone %(name)s does not exist.",
                      name=new_milestone), _("Invalid milestone name"))
        now = datetime_now(utc)
        with self.env.db_transaction as db:
            sql = "SELECT id FROM ticket WHERE milestone=%s"
            if exclude_closed:
                sql += " AND status != 'closed'"
            tkt_ids = [int(row[0]) for row in db(sql, (self._old['name'],))]
            if tkt_ids:
                self.env.log.info("Moving tickets associated with milestone "
                                  "'%s' to milestone '%s'", self._old['name'],
                                  new_milestone)
                for tkt_id in tkt_ids:
                    ticket = Ticket(self.env, tkt_id)
                    ticket['milestone'] = new_milestone
                    ticket.save_changes(author, comment, now)
        return tkt_ids

    @classmethod
    def select(cls, env, include_completed=True, db=None):
        """
        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        milestones = MilestoneCache(env).fetchall()
        if not include_completed:
            milestones = [m for m in milestones if m.completed is None]
        def milestone_order(m):
            return (m.completed or utcmax,
                    m.due or utcmax,
                    embedded_numbers(m.name))
        return sorted(milestones, key=milestone_order)


def group_milestones(milestones, include_completed):
    """Group milestones into "open with due date", "open with no due date",
    and possibly "completed". Return a list of (label, milestones) tuples."""
    def category(m):
        return 1 if m.is_completed else 2 if m.due else 3
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
        self.name = self._old_name = self.time = self.description = None
        if name:
            for time, description in self.env.db_query("""
                    SELECT time, description FROM version WHERE name=%s
                    """, (name,)):
                self.name = self._old_name = name
                self.time = from_utimestamp(time) if time else None
                self.description = description or ''
                break
            else:
                raise ResourceNotFound(_("Version %(name)s does not exist.",
                                         name=name))

    exists = property(lambda self: self._old_name is not None)

    def delete(self, db=None):
        """Delete the version.

        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        assert self.exists, "Cannot delete non-existent version"

        with self.env.db_transaction as db:
            self.env.log.info("Deleting version %s", self.name)
            db("DELETE FROM version WHERE name=%s", (self.name,))
            self.name = self._old_name = None
            TicketSystem(self.env).reset_ticket_fields()

    def insert(self, db=None):
        """Insert a new version.

        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        assert not self.exists, "Cannot insert existing version"
        self.name = simplify_whitespace(self.name)
        if not self.name:
            raise TracError(_("Invalid version name."))

        with self.env.db_transaction as db:
            self.env.log.debug("Creating new version '%s'", self.name)
            db("INSERT INTO version (name,time,description) VALUES (%s,%s,%s)",
                (self.name, to_utimestamp(self.time), self.description))
            self._old_name = self.name
            TicketSystem(self.env).reset_ticket_fields()

    def update(self, db=None):
        """Update the version.

        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        assert self.exists, "Cannot update non-existent version"
        self.name = simplify_whitespace(self.name)
        if not self.name:
            raise TracError(_("Invalid version name."))

        with self.env.db_transaction as db:
            self.env.log.info("Updating version '%s'", self.name)
            db("""UPDATE version
                  SET name=%s, time=%s, description=%s WHERE name=%s
                  """, (self.name, to_utimestamp(self.time), self.description,
                        self._old_name))
            if self.name != self._old_name:
                # Update tickets
                db("UPDATE ticket SET version=%s WHERE version=%s",
                   (self.name, self._old_name))
                self._old_name = self.name
        # Fields need reset if renamed or if time is changed
        TicketSystem(self.env).reset_ticket_fields()

    @classmethod
    def select(cls, env, db=None):
        """
        :since 1.0: the `db` parameter is no longer needed and will be removed
        in version 1.1.1
        """
        versions = []
        for name, time, description in env.db_query("""
                SELECT name, time, description FROM version"""):
            version = cls(env)
            version.name = version._old_name = name
            version.time = from_utimestamp(time) if time else None
            version.description = description or ''
            versions.append(version)
        def version_order(v):
            return (v.time or utcmax, embedded_numbers(v.name))
        return sorted(versions, key=version_order, reverse=True)
