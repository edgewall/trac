# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2009 Edgewall Software
# Copyright (C) 2004 Daniel Lundin <daniel@edgewall.com>
# Copyright (C) 2004-2006 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2006 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2008 Matt Good <matt@matt-good.net>
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
# Author: Daniel Lundin <daniel@edgewall.com>
#         Christopher Lenz <cmlenz@gmx.de>

import time

from trac.admin.api import console_date_format
from trac.core import TracError, Component, implements
from trac.util import hex_entropy
from trac.util.text import print_table
from trac.util.translation import _
from trac.util.datefmt import format_date, parse_date, to_datetime, \
                              to_timestamp
from trac.admin.api import IAdminCommandProvider, AdminCommandError

UPDATE_INTERVAL = 3600 * 24 # Update session last_visit time stamp after 1 day
PURGE_AGE = 3600 * 24 * 90 # Purge session after 90 days idle
COOKIE_KEY = 'trac_session'

# Note: as we often manipulate both the `session` and the
#       `session_attribute` tables, there's a possibility of table
#       deadlocks (#9705). We try to prevent them to happen by always
#       accessing the tables in the same order within the transaction,
#       first `session`, then `session_attribute`.

class DetachedSession(dict):
    def __init__(self, env, sid):
        dict.__init__(self)
        self.env = env
        self.sid = None
        if sid:
            self.get_session(sid, authenticated=True)
        else:
            self.authenticated = False
            self.last_visit = 0
            self._new = True
            self._old = {}

    def __setitem__(self, key, value):
        dict.__setitem__(self, key, unicode(value))

    def get_session(self, sid, authenticated=False):
        self.env.log.debug('Retrieving session for ID %r', sid)

        db = self.env.get_db_cnx()
        cursor = db.cursor()

        self.sid = sid
        self.authenticated = authenticated
        self.clear()

        cursor.execute("""
            SELECT last_visit FROM session WHERE sid=%s AND authenticated=%s
            """, (sid, int(authenticated)))
        row = cursor.fetchone()
        if not row:
            self.last_visit = 0
            self._new = True
            self._old = {}
            return
        self._new = False
        self.last_visit = int(row[0] or 0)

        cursor.execute("""
            SELECT name,value FROM session_attribute
            WHERE sid=%s and authenticated=%s
            """, (sid, int(authenticated)))
        self.update(cursor)
        self._old = self.copy()

    def save(self):
        items = self.items()
        if not self._old and not items:
            # The session doesn't have associated data, so there's no need to
            # persist it
            return

        authenticated = int(self.authenticated)
        now = int(time.time())

        # We can't do the session management in one big transaction,
        # as the intertwined changes to both the session and
        # session_attribute tables are prone to deadlocks (#9705).
        # Therefore we first we save the current session, then we
        # eventually purge the tables.
        
        session_saved = [False]

        @self.env.with_transaction()
        def save_session(db):
            cursor = db.cursor()

            # Try to save the session if it's a new one. A failure to
            # do so is not critical but we nevertheless skip the
            # following steps.

            if self._new:
                self.last_visit = now
                self._new = False
                # The session might already exist even if _new is True since
                # it could have been created by a concurrent request (#3563).
                try:
                    cursor.execute("""
                        INSERT INTO session (sid,last_visit,authenticated)
                        VALUES (%s,%s,%s)
                        """, (self.sid, self.last_visit, authenticated))
                except Exception:
                    self.env.log.warning('Session %s already exists', self.sid)
                    db.rollback()
                    return

            # Remove former values for session_attribute and save the
            # new ones. The last concurrent request to do so "wins".

            if self._old != self:
                if not items and not authenticated:
                    # No need to keep around empty unauthenticated sessions
                    cursor.execute("""
                        DELETE FROM session WHERE sid=%s AND authenticated=0
                        """, (self.sid,))
                cursor.execute("""
                    DELETE FROM session_attribute
                    WHERE sid=%s AND authenticated=%s
                    """, (self.sid, authenticated))
                self._old = dict(self.items())
                # The session variables might already have been updated by a
                # concurrent request.
                try:
                    cursor.executemany("""
                        INSERT INTO session_attribute
                          (sid,authenticated,name,value)
                        VALUES (%s,%s,%s,%s)
                        """, [(self.sid, authenticated, k, v)
                              for k, v in items])
                except Exception:
                    self.env.log.warning('Attributes for session %s already '
                                         'updated', self.sid)
                    db.rollback()
                    return
                session_saved[0] = True

        # Purge expired sessions. We do this only when the session was
        # changed as to minimize the purging.

        if session_saved[0] and now - self.last_visit > UPDATE_INTERVAL:
            self.last_visit = now
            mintime = now - PURGE_AGE

            @self.env.with_transaction()
            def purge_session_attributes(db):
                cursor = db.cursor()
                # Update the session last visit time if it is over an
                # hour old, so that session doesn't get purged
                self.env.log.info("Refreshing session %s", self.sid)
                cursor.execute("""
                    UPDATE session SET last_visit=%s
                    WHERE sid=%s AND authenticated=%s
                    """, (self.last_visit, self.sid, authenticated))
                self.env.log.debug('Purging old, expired, sessions.')
                cursor.execute("""
                    DELETE FROM session_attribute
                    WHERE authenticated=0 AND sid IN (
                      SELECT sid FROM session 
                      WHERE authenticated=0 AND last_visit < %s
                    )
                    """, (mintime,))

            # Avoid holding locks on lot of rows on both session_attribute
            # and session tables
            @self.env.with_transaction()
            def purge_sessions(db):
                cursor = db.cursor()
                cursor.execute("""
                    DELETE FROM session
                    WHERE authenticated=0 AND last_visit < %s
                    """, (mintime,))


class Session(DetachedSession):
    """Basic session handling and per-session storage."""

    def __init__(self, env, req):
        super(Session, self).__init__(env, None)
        self.req = req
        if req.authname == 'anonymous':
            if not req.incookie.has_key(COOKIE_KEY):
                self.sid = hex_entropy(24)
                self.bake_cookie()
            else:
                sid = req.incookie[COOKIE_KEY].value
                self.get_session(sid)
        else:
            if req.incookie.has_key(COOKIE_KEY):
                sid = req.incookie[COOKIE_KEY].value
                self.promote_session(sid)
            self.get_session(req.authname, authenticated=True)

    def bake_cookie(self, expires=PURGE_AGE):
        assert self.sid, 'Session ID not set'
        self.req.outcookie[COOKIE_KEY] = self.sid
        self.req.outcookie[COOKIE_KEY]['path'] = self.req.base_path or '/'
        self.req.outcookie[COOKIE_KEY]['expires'] = expires
        if self.env.secure_cookies:
            self.req.outcookie[COOKIE_KEY]['secure'] = True

    def get_session(self, sid, authenticated=False):
        refresh_cookie = False

        if self.sid and sid != self.sid:
            refresh_cookie = True

        super(Session, self).get_session(sid, authenticated)
        if self.last_visit and time.time() - self.last_visit > UPDATE_INTERVAL:
            refresh_cookie = True

        # Refresh the session cookie if this is the first visit after a day
        if not authenticated and refresh_cookie:
            self.bake_cookie()

    def change_sid(self, new_sid):
        assert self.req.authname == 'anonymous', \
               'Cannot change ID of authenticated session'
        assert new_sid, 'Session ID cannot be empty'
        if new_sid == self.sid:
            return
        @self.env.with_transaction()
        def update_session_id(db):
            cursor = db.cursor()
            cursor.execute("SELECT sid FROM session WHERE sid=%s", (new_sid,))
            if cursor.fetchone():
                raise TracError(_("Session '%(id)s' already exists. "
                                  "Please choose a different session ID.",
                                  id=new_sid),
                                _("Error renaming session"))
            self.env.log.debug('Changing session ID %s to %s', self.sid,
                               new_sid)
            cursor.execute("""
                UPDATE session SET sid=%s WHERE sid=%s AND authenticated=0
                  """, (new_sid, self.sid))
            cursor.execute("""
                UPDATE session_attribute SET sid=%s 
                WHERE sid=%s and authenticated=0
                """, (new_sid, self.sid))
        self.sid = new_sid
        self.bake_cookie()

    def promote_session(self, sid):
        """Promotes an anonymous session to an authenticated session, if there
        is no preexisting session data for that user name.
        """
        assert self.req.authname != 'anonymous', \
               'Cannot promote session of anonymous user'

        @self.env.with_transaction()
        def update_session_id(db):
            cursor = db.cursor()
            cursor.execute("""
                SELECT authenticated FROM session WHERE sid=%s OR sid=%s
                """, (sid, self.req.authname))
            authenticated_flags = [row[0] for row in cursor.fetchall()]
            
            if len(authenticated_flags) == 2:
                # There's already an authenticated session for the user,
                # we simply delete the anonymous session
                cursor.execute("""
                    DELETE FROM session WHERE sid=%s AND authenticated=0
                    """, (sid,))
                cursor.execute("""
                    DELETE FROM session_attribute
                    WHERE sid=%s AND authenticated=0
                    """, (sid,))
            elif len(authenticated_flags) == 1:
                if not authenticated_flags[0]:
                    # Update the anomymous session records so the session ID
                    # becomes the user name, and set the authenticated flag.
                    self.env.log.debug('Promoting anonymous session %s to '
                                       'authenticated session for user %s',
                                       sid, self.req.authname)
                    cursor.execute("""
                        UPDATE session SET sid=%s,authenticated=1
                        WHERE sid=%s AND authenticated=0
                        """, (self.req.authname, sid))
                    cursor.execute("""
                        UPDATE session_attribute SET sid=%s,authenticated=1
                        WHERE sid=%s
                        """, (self.req.authname, sid))
            else:
                # We didn't have an anonymous session for this sid. The
                # authenticated session might have been inserted between the
                # SELECT above and here, so we catch the error.
                try:
                    cursor.execute("""
                        INSERT INTO session (sid,last_visit,authenticated)
                        VALUES (%s,%s,1)
                        """, (self.req.authname, int(time.time())))
                except Exception:
                    self.env.log.warning('Authenticated session for %s '
                                         'already exists', self.req.authname)
                    db.rollback()
        self._new = False

        self.sid = sid
        self.bake_cookie(0) # expire the cookie


class SessionAdmin(Component):
    """trac-admin command provider for session management"""

    implements(IAdminCommandProvider)

    def get_admin_commands(self):
        yield ('session list', '[sid[:0|1]] [...]',
               """List the name and email for the given sids

               Specifying the sid 'anonymous' lists all unauthenticated
               sessions, and 'authenticated' all authenticated sessions.
               '*' lists all sessions, and is the default if no sids are
               given.
               
               An sid suffix ':0' operates on an unauthenticated session with
               the given sid, and a suffix ':1' on an authenticated session
               (the default).""",
               self._complete_list, self._do_list)

        yield ('session add', '<sid[:0|1]> [name] [email]',
               """Create a session for the given sid

               Populates the name and email attributes for the given session.
               Adding a suffix ':0' to the sid makes the session
               unauthenticated, and a suffix ':1' makes it authenticated (the
               default if no suffix is specified).""",
               None, self._do_add)

        yield ('session set', '<name|email> <sid[:0|1]> <value>',
               """Set the name or email attribute of the given sid
               
               An sid suffix ':0' operates on an unauthenticated session with
               the given sid, and a suffix ':1' on an authenticated session
               (the default).""",
               self._complete_set, self._do_set)

        yield ('session delete', '<sid[:0|1]> [...]',
               """Delete the session of the specified sid

               An sid suffix ':0' operates on an unauthenticated session with
               the given sid, and a suffix ':1' on an authenticated session
               (the default). Specifying the sid 'anonymous' will delete all
               anonymous sessions.""",
               self._complete_delete, self._do_delete)

        yield ('session purge', '<age>',
               """Purge all anonymous sessions older than the given age

               Age may be specified as a relative time like "90 days ago", or
               in YYYYMMDD format.""",
               None, self._do_purge)

    def _split_sid(self, sid):
        if sid.endswith(':0'):
            return (sid[:-2], 0)
        elif sid.endswith(':1'):
            return (sid[:-2], 1)
        else:
            return (sid, 1)

    def _get_sids(self):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT sid, authenticated FROM session")
        return ['%s:%d' % (sid, auth) for sid, auth in cursor]

    def _get_list(self, sids):
        all_anon = 'anonymous' in sids or '*' in sids
        all_auth = 'authenticated' in sids or '*' in sids
        sids = set(self._split_sid(sid) for sid in sids
                   if sid not in ('anonymous', 'authenticated', '*'))
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("""
            SELECT DISTINCT s.sid, s.authenticated, s.last_visit,
                            n.value, e.value
            FROM session AS s
              LEFT JOIN session_attribute AS n
                ON (n.sid=s.sid AND n.authenticated=s.authenticated
                    AND n.name='name')
              LEFT JOIN session_attribute AS e
                ON (e.sid=s.sid AND e.authenticated=s.authenticated
                    AND e.name='email')
            ORDER BY s.sid, s.authenticated
            """)
        for sid, authenticated, last_visit, name, email in cursor:
            if all_anon and not authenticated or all_auth and authenticated \
                    or (sid, authenticated) in sids:
                yield (sid, authenticated, last_visit, name, email)

    def _complete_list(self, args):
        all_sids = self._get_sids() + ['*', 'anonymous', 'authenticated']
        return set(all_sids) - set(args)

    def _complete_set(self, args):
        if len(args) == 1:
            return ['name', 'email']
        elif len(args) == 2:
            return self._get_sids()

    def _complete_delete(self, args):
        all_sids = self._get_sids() + ['anonymous']
        return set(all_sids) - set(args)

    def _do_list(self, *sids):
        if not sids:
            sids = ['*']
        print_table([(r[0], r[1], format_date(to_datetime(r[2]),
                                              console_date_format),
                      r[3], r[4])
                     for r in self._get_list(sids)],
                    [_('SID'), _('Auth'), _('Last Visit'), _('Name'),
                     _('Email')])
        
    def _do_add(self, sid, name=None, email=None):
        sid, authenticated = self._split_sid(sid)
        @self.env.with_transaction()
        def add_session(db):
            cursor = db.cursor()
            try:
                cursor.execute("INSERT INTO session VALUES (%s, %s, %s)",
                               (sid, authenticated, int(time.time())))
            except Exception:
                raise AdminCommandError(_("Session '%(sid)s' already exists",
                                          sid=sid))
            if name is not None:
                cursor.execute("""
                    INSERT INTO session_attribute VALUES (%s, %s, 'name', %s)
                    """, (sid, authenticated, name))
            if email is not None:
                cursor.execute("""
                    INSERT INTO session_attribute VALUES (%s, %s, 'email', %s)
                    """, (sid, authenticated, email))

    def _do_set(self, attr, sid, val):
        if attr not in ('name', 'email'):
            raise AdminCommandError(_("Invalid attribute '%(attr)s'",
                                      attr=attr))
        sid, authenticated = self._split_sid(sid)
        @self.env.with_transaction()
        def set_attr(db):
            cursor = db.cursor()
            cursor.execute("""
                SELECT sid FROM session WHERE sid=%s AND authenticated=%s
                """, (sid, authenticated))
            if not cursor.fetchone():
                raise AdminCommandError(_("Session '%(sid)s' not found",
                                          sid=sid))
            cursor.execute("""
                DELETE FROM session_attribute
                WHERE sid=%s AND authenticated=%s AND name=%s
                """, (sid, authenticated, attr))
            cursor.execute("""
                INSERT INTO session_attribute VALUES (%s, %s, %s, %s)
                """, (sid, authenticated, attr, val))

    def _do_delete(self, *sids):
        @self.env.with_transaction()
        def delete_session(db):
            cursor = db.cursor()
            for sid in sids:
                sid, authenticated = self._split_sid(sid)
                if sid == 'anonymous':
                    cursor.execute("""
                        DELETE FROM session WHERE authenticated=0
                        """)
                    cursor.execute("""
                        DELETE FROM session_attribute WHERE authenticated=0
                        """)
                else:
                    cursor.execute("""
                        DELETE FROM session
                        WHERE sid=%s AND authenticated=%s
                        """, (sid, authenticated))
                    cursor.execute("""
                        DELETE FROM session_attribute
                        WHERE sid=%s AND authenticated=%s
                        """, (sid, authenticated))

    def _do_purge(self, age):
        when = parse_date(age)
        @self.env.with_transaction()
        def purge_session(db):
            cursor = db.cursor()
            ts = to_timestamp(when)
            cursor.execute("""
                DELETE FROM session
                WHERE authenticated=0 AND last_visit<%s
                """, (ts,))
            cursor.execute("""
                DELETE FROM session_attribute
                WHERE authenticated=0
                      AND sid NOT IN (SELECT sid FROM session
                                      WHERE authenticated=0)
                """)
