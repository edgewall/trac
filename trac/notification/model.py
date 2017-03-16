# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 Edgewall Software
# Copyright (C) 2010 Robert Corsaro
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from trac.util.datefmt import datetime_now, utc, to_utimestamp

__all__ = ['Subscription', 'Watch']


class Subscription(object):

    __slots__ = ('env', 'values')

    fields = ('id', 'sid', 'authenticated', 'distributor', 'format',
              'priority', 'adverb', 'class')

    def __init__(self, env):
        self.env = env
        self.values = {}

    def __repr__(self):
        values = ' '.join('%s=%r' % (name, self.values.get(name))
                          for name in self.fields)
        return '<%s %s>' % (self.__class__.__name__, values)

    def __getitem__(self, name):
        if name not in self.fields:
            raise KeyError(name)
        return self.values.get(name)

    def __setitem__(self, name, value):
        if name not in self.fields:
            raise KeyError(name)
        self.values[name] = value

    def _from_database(self, id, sid, authenticated, distributor, format,
                       priority, adverb, class_):
        self['id'] = id
        self['sid'] = sid
        self['authenticated'] = int(authenticated)
        self['distributor'] = distributor
        self['format'] = format or None
        self['priority'] = int(priority)
        self['adverb'] = adverb
        self['class'] = class_

    @classmethod
    def add(cls, env, subscription):
        """id and priority overwritten."""
        with env.db_transaction as db:
            priority = len(cls.find_by_sid_and_distributor(
                env, subscription['sid'], subscription['authenticated'],
                subscription['distributor'])) + 1
            now = to_utimestamp(datetime_now(utc))
            cursor = db.cursor()
            cursor.execute("""
                INSERT INTO
                notify_subscription (time, changetime, sid, authenticated,
                                     distributor, format, priority, adverb,
                                     class)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (now, now, subscription['sid'], int(subscription['authenticated']),
             subscription['distributor'], subscription['format'] or None,
             int(priority), subscription['adverb'],
             subscription['class']))
            return db.get_last_id(cursor, 'notify_subscription')

    @classmethod
    def delete(cls, env, rule_id, sid=None, authenticated=None):
        with env.db_transaction as db:
            kwargs = {'id': rule_id}
            if sid is not None or authenticated is not None:
                kwargs['sid'] = sid
                kwargs['authenticated'] = 1 if authenticated else 0
            for sub in cls._find(env, **kwargs):
                break
            else:
                return
            db("DELETE FROM notify_subscription WHERE id=%s", (sub['id'],))
            subs = cls.find_by_sid_and_distributor(
                env, sub['sid'], sub['authenticated'], sub['distributor'])
            now = to_utimestamp(datetime_now(utc))
            values = [(new_priority, now, sub['id'])
                      for new_priority, sub in enumerate(subs, 1)
                      if new_priority != sub['priority']]
            db.executemany("""
                UPDATE notify_subscription
                SET priority=%s, changetime=%s WHERE id=%s
                """, values)

    @classmethod
    def move(cls, env, rule_id, priority, sid=None, authenticated=None):
        with env.db_transaction as db:
            kwargs = {'id': rule_id}
            if sid is not None or authenticated is not None:
                kwargs['sid'] = sid
                kwargs['authenticated'] = 1 if authenticated else 0
            for sub in cls._find(env, **kwargs):
                break
            else:
                return
            subs = cls.find_by_sid_and_distributor(
                env, sub['sid'], sub['authenticated'], sub['distributor'])
            if not (1 <= priority <= len(subs)):
                return
            for idx, sub in enumerate(subs):
                if sub['id'] == rule_id:
                    break
            else:
                return
            subs.insert(priority - 1, subs.pop(idx))
            now = to_utimestamp(datetime_now(utc))
            values = [(new_priority, now, sub['id'])
                      for new_priority, sub in enumerate(subs, 1)
                      if new_priority != sub['priority']]
            db.executemany("""
                UPDATE notify_subscription
                SET priority=%s, changetime=%s WHERE id=%s
                """, values)

    @classmethod
    def replace_all(cls, env, sid, authenticated, subscriptions):
        authenticated = int(authenticated)
        with env.db_transaction as db:
            ids_map = {}
            for id_, distributor, class_ in db("""\
                    SELECT id, distributor, class FROM notify_subscription
                    WHERE sid=%s AND authenticated=%s""",
                    (sid, authenticated)):
                ids_map.setdefault((distributor, class_), []).append(id_)
            for ids in ids_map.itervalues():
                ids.sort(reverse=True)

            priorities = {}
            now = to_utimestamp(datetime_now(utc))
            for sub in subscriptions:
                distributor = sub['distributor']
                priorities.setdefault(distributor, 0)
                priorities[distributor] += 1
                prio = priorities[distributor]
                key = (distributor, sub['class'])
                if ids_map.get(key):
                    id_ = ids_map[key].pop()
                    db("""\
                        UPDATE notify_subscription
                        SET changetime=%s,distributor=%s,format=%s,priority=%s,
                            adverb=%s,class=%s
                        WHERE id=%s""",
                        (now, sub['distributor'], sub['format'] or None, prio,
                         sub['adverb'], sub['class'], id_))
                else:
                    db("""\
                        INSERT INTO notify_subscription (
                            time,changetime,sid,authenticated,distributor,
                            format,priority,adverb,class)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (now, now, sid, authenticated, sub['distributor'],
                         sub['format'] or None, prio, sub['adverb'],
                         sub['class']))

            delete_ids = []
            for ids in ids_map.itervalues():
                delete_ids.extend(ids)
            if delete_ids:
                db("DELETE FROM notify_subscription WHERE id IN (%s)" %
                   ','.join(('%s',) * len(delete_ids)), delete_ids)


    @classmethod
    def update_format_by_distributor_and_sid(cls, env, distributor, sid,
                                             authenticated, format):
        with env.db_transaction as db:
            db("""
                UPDATE notify_subscription
                   SET format=%s
                 WHERE distributor=%s
                   AND sid=%s
                   AND authenticated=%s
            """, (format or None, distributor, sid, int(authenticated)))

    @classmethod
    def _find(cls, env, order=None, **kwargs):
        with env.db_query as db:
            conditions = []
            args = []
            for name, value in sorted(kwargs.iteritems()):
                if name.endswith('_'):
                    name = name[:-1]
                if name == 'authenticated':
                    value = int(value)
                conditions.append(db.quote(name) + '=%s')
                args.append(value)
            query = 'SELECT id, sid, authenticated, distributor, format, ' \
                    'priority, adverb, class FROM notify_subscription'
            if conditions:
                query += ' WHERE ' + ' AND '.join(conditions)
            if order:
                if not isinstance(order, (tuple, list)):
                    order = (order,)
                query += ' ORDER BY ' + \
                         ', '.join(db.quote(name) for name in order)
            cursor = db.cursor()
            cursor.execute(query, args)
            for row in cursor:
                sub = Subscription(env)
                sub._from_database(*row)
                yield sub

    @classmethod
    def find_by_sid_and_distributor(cls, env, sid, authenticated, distributor):
        return list(cls._find(env, sid=sid, authenticated=authenticated,
                              distributor=distributor, order='priority'))

    @classmethod
    def find_by_sids_and_class(cls, env, uids, class_):
        """uids should be a collection to tuples (sid, auth)"""
        subs = []
        for sid, authenticated in uids:
            subs.extend(cls._find(env, class_=class_, sid=sid,
                                  authenticated=authenticated,
                                  order='priority'))
        return subs

    @classmethod
    def find_by_class(cls, env, class_):
        return list(cls._find(env, class_=class_))

    def subscription_tuple(self):
        return (
            self.values['class'],
            self.values['distributor'],
            self.values['sid'],
            self.values['authenticated'],
            None,
            self.values['format'] or None,
            int(self.values['priority']),
            self.values['adverb']
        )

    def _update_priority(self):
        with self.env.db_transaction as db:
            cursor = db.cursor()
            now = to_utimestamp(datetime_now(utc))
            cursor.execute("""
                UPDATE notify_subscription
                   SET changetime=%s, priority=%s
                 WHERE id=%s
            """, (now, int(self.values['priority']), self.values['id']))


class Watch(object):

    __slots__ = ('env', 'values')

    fields = ('id', 'sid', 'authenticated', 'class', 'realm', 'target')

    def __init__(self, env):
        self.env = env
        self.values = {}

    def __getitem__(self, name):
        if name not in self.fields:
            raise KeyError(name)
        return self.values.get(name)

    def __setitem__(self, name, value):
        if name not in self.fields:
            raise KeyError(name)
        self.values[name] = value

    def _from_database(self, id, sid, authenticated, class_, realm, target):
        self['id'] = id
        self['sid'] = sid
        self['authenticated'] = int(authenticated)
        self['class'] = class_
        self['realm'] = realm
        self['target'] = target

    @classmethod
    def add(cls, env, sid, authenticated, class_, realm, targets):
        with env.db_transaction as db:
            for target in targets:
                db("""
                    INSERT INTO notify_watch (sid, authenticated, class,
                                              realm, target)
                    VALUES (%s, %s, %s, %s, %s)
                """, (sid, int(authenticated), class_, realm, target))

    @classmethod
    def delete(cls, env, watch_id):
        with env.db_transaction as db:
            db("DELETE FROM notify_watch WHERE id = %s", (watch_id,))

    @classmethod
    def delete_by_sid_and_class(cls, env, sid, authenticated, class_):
        with env.db_transaction as db:
            db("""
                DELETE FROM notify_watch
                WHERE sid = %s AND authenticated = %s AND class = %s
            """, (sid, int(authenticated), class_))

    @classmethod
    def delete_by_class_realm_and_target(cls, env, class_, realm, target):
        with env.db_transaction as db:
            db("""
                DELETE FROM notify_watch
                WHERE class = %s AND realm = %s AND target = %s
            """, (realm, class_, target))

    @classmethod
    def _find(cls, env, order=None, **kwargs):
        with env.db_query as db:
            conditions = []
            args = []
            for name, value in sorted(kwargs.iteritems()):
                if name.endswith('_'):
                    name = name[:-1]
                if name == 'authenticated':
                    value = int(value)
                conditions.append(db.quote(name) + '=%s')
                if name == 'authenticated':
                    value = int(value)
                args.append(value)
            query = 'SELECT id, sid, authenticated, class, realm, target ' \
                    'FROM notify_watch'
            if conditions:
                query += ' WHERE ' + ' AND '.join(conditions)
            if order:
                if not isinstance(order, (tuple, list)):
                    order = (order,)
                query += ' ORDER BY ' + \
                         ', '.join(db.quote(name) for name in order)
            cursor = db.cursor()
            cursor.execute(query, args)
            for row in cursor:
                watch = Watch(env)
                watch._from_database(*row)
                yield watch

    @classmethod
    def find_by_sid_and_class(cls, env, sid, authenticated, class_):
        return list(cls._find(env, sid=sid, authenticated=authenticated,
                              class_=class_, order='target'))

    @classmethod
    def find_by_sid_class_realm_and_target(cls, env, sid, authenticated,
                                           class_, realm, target):
        return list(cls._find(env, sid=sid, authenticated=authenticated,
                              class_=class_, realm=realm, order='target'))

    @classmethod
    def find_by_class_realm_and_target(cls, env, class_, realm, target):
        return list(cls._find(env, class_=class_, realm=realm, target=target))

    @classmethod
    def find_by_class_and_realm(cls, env, class_, realm):
        return list(cls._find(env, class_=class_, realm=realm))
