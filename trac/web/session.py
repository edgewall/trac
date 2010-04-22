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
from datetime import date

from trac.core import TracError, Component, implements
from trac.util import hex_entropy
from trac.util.text import print_table, printout
from trac.util.translation import _
from trac.util.html import Markup
from trac.util.datefmt import parse_date, to_timestamp
from trac.admin.api import IAdminCommandProvider, AdminCommandError

UPDATE_INTERVAL = 3600 * 24 # Update session last_visit time stamp after 1 day
PURGE_AGE = 3600 * 24 * 90 # Purge session after 90 days idle
COOKIE_KEY = 'trac_session'


class DetachedSession(dict):
    def __init__(self, env, sid):
        dict.__init__(self)
        self.env = env
        self.sid = None
        self.last_visit = 0
        self._new = True
        self._old = {}
        if sid:
            self.get_session(sid, authenticated=True)
        else:
            self.authenticated = False

    def __setitem__(self, key, value):
        dict.__setitem__(self, key, unicode(value))

    def get_session(self, sid, authenticated=False):
        self.env.log.debug('Retrieving session for ID %r', sid)

        db = self.env.get_db_cnx()
        cursor = db.cursor()

        self.sid = sid
        self.authenticated = authenticated

        cursor.execute("""
            SELECT last_visit FROM session WHERE sid=%s AND authenticated=%s
            """, (sid, int(authenticated)))
        row = cursor.fetchone()
        if not row:
            return
        self._new = False
        self.last_visit = int(row[0] or 0)

        cursor.execute("""
            SELECT name,value FROM session_attribute
            WHERE sid=%s and authenticated=%s
            """, (sid, int(authenticated)))
        for name, value in cursor:
            self[name] = value
        self._old.update(self)

    def save(self):
        if not self._old and not self.items():
            # The session doesn't have associated data, so there's no need to
            # persist it
            return

        authenticated = int(self.authenticated)
        now = int(time.time())

        @self.env.with_transaction()
        def delete_session_cookie(db):
            cursor = db.cursor()
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
            if self._old != self:
                attrs = [(self.sid, authenticated, k, v) 
                         for k, v in self.items()]
                cursor.execute("""
                    DELETE FROM session_attribute WHERE sid=%s
                    """, (self.sid,))
                self._old = dict(self.items())
                if attrs:
                    cursor.executemany("""
                       INSERT INTO session_attribute
                         (sid,authenticated,name,value)
                       VALUES (%s,%s,%s,%s)
                       """, attrs)
                elif not authenticated:
                    # No need to keep around empty unauthenticated sessions
                    cursor.execute("""
                        DELETE FROM session WHERE sid=%s AND authenticated=0
                        """, (self.sid,))
                    return
            # Update the session last visit time if it is over an hour old,
            # so that session doesn't get purged
            if now - self.last_visit > UPDATE_INTERVAL:
                self.last_visit = now
                self.env.log.info("Refreshing session %s", self.sid)
                cursor.execute("""
                    UPDATE session SET last_visit=%s
                    WHERE sid=%s AND authenticated=%s
                    """, (self.last_visit, self.sid, authenticated))
                # Purge expired sessions. We do this only when the session was
                # changed as to minimize the purging.
                mintime = now - PURGE_AGE
                self.env.log.debug('Purging old, expired, sessions.')
                cursor.execute("""
                    DELETE FROM session_attribute
                    WHERE authenticated=0 AND sid IN (
                      SELECT sid FROM session 
                      WHERE authenticated=0 AND last_visit < %s
                    )
                    """, (mintime,))
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
                raise TracError(Markup(
                    _("Session '%(id)s' already exists.<br />"
                      "Please choose a different session ID.",
                      id=new_sid), _("Error renaming session")))
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
                # we didn't have an anonymous session for this sid
                cursor.execute("""
                    INSERT INTO session (sid,last_visit,authenticated)
                    VALUES (%s,%s,1)
                    """, (self.req.authname, int(time.time())))
        self._new = False

        self.sid = sid
        self.bake_cookie(0) # expire the cookie


class SessionAdmin(Component):
    """trac-admin command provider for session management"""

    implements(IAdminCommandProvider)

    def get_admin_commands(self):
        yield ('session list', '<sid> [...]',
               """List the name and email for the sids specified

               Specifying the sid \'anonymous\' will list all of the
               unauthenticated sessions.  \'*\' may be used to list all
               sessions regardless of authenticated status.""",
               self._complete_sids, self._do_list)

        yield ('session add', '<sid> [name] [email]',
               """Create a session for the given sid

               Populates the name and email attributes and sets the session 
               as authenticated.""",
               None, self._do_add)

        yield ('session set', '<name|email> <sid> <value>',
               'Set the name or email attribute of the given sid',
               self._complete_set, self._do_set)

        yield ('session delete', '<sid> [...]',
               """Delete the session of the specified sid

               Specifying the sid 'anonymous' will delete all anonymous
               sessions.  Using '*' will delete all sessions, regardless.""",
               self._complete_sids, self._do_delete)

        yield ('session purge', '<age>',
               """Purge all anonymous sessions older than the given age

               Age may be specified as a relative time like "90 days ago", or
               in YYYYMMDD format.""",
               None, self._do_purge)

    def _do_list(self, *sids):
        rows = list(self._get_list(*sids))
        if not rows:
            printout(_('No SID found'))
        else:
            print_table(rows, [_('SID'), _('Name'), _('Email')]) 
        
    def _do_add(self, sid, *args):
        if list(self._get_list(sid)):
            raise AdminCommandError(_("Session already exists. Unable to add "
                                      "a duplicate session."))
        self._add_session(sid, *args)

    def _do_set(self, attr, sid, val):
        exists = [r for r in self._get_list(sid)]
        if not exists:
            raise AdminCommandError(_("Unable to set session attribute on a "
                                      "non-existent SID"))
        self._set_attr(sid, attr, val) 

    def _complete_set(self, args):
        if len(args) == 1:
            return ['name', 'email']
        elif len(args) == 2:
            return self._get_authenticated_sids()

    def _do_delete(self, *sids):
        for sid in sids:
            self._delete_session(sid) 

    def _do_purge(self, age):
        self._purge_sessions(parse_date(age))

    def _complete_sids(self, *args):
        sids = self._get_authenticated_sids()
        sids.append('authenticated')
        sids.append('anonymous')
        return sids

    # Internal helper methods
    def _get_list(self, *sids):
        if not sids:
            return
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        check_auth = True
        check_sid = False
        if sids[0].lower() == 'anonymous':
            authenticated = 0
        elif sids[0].lower() == 'authenticated':
            authenticated = 1
        elif sids[0] == '*':
            check_auth = False
        else:
            check_auth = False
            check_sid = True

        if check_auth:
            cursor.execute("""
                SELECT DISTINCT s.sid, n.value, e.value 
                FROM session AS s 
                  LEFT JOIN session_attribute AS n
                    ON (n.sid=s.sid AND n.authenticated=%s AND n.name='name')
                  LEFT JOIN session_attribute AS e
                    ON (e.sid=s.sid AND e.authenticated=%s AND e.name='email')
                WHERE s.authenticated=%s ORDER BY s.sid
                """, (authenticated,) * 3)
        elif check_sid:
            cursor.execute("""
                SELECT DISTINCT s.sid, n.value, e.value 
                FROM session AS s 
                  LEFT JOIN session_attribute AS n
                    ON (n.sid=s.sid AND n.name='name') 
                  LEFT JOIN session_attribute AS e
                    ON (e.sid=s.sid AND e.name='email') 
                WHERE s.sid IN (%s)
                """ % ','.join("%s" for i in range(len(sids))), sids)
        else:
            cursor.execute("""
                SELECT DISTINCT s.sid, n.value, e.value 
                FROM session AS s 
                  LEFT JOIN session_attribute AS n
                    ON (n.sid=s.sid AND n.name='name') 
                  LEFT JOIN session_attribute AS e
                    ON (e.sid=s.sid  AND e.name='email') ORDER BY s.sid
                """)

        for sid, name, email in cursor:
            yield (sid, name, email)

    def _add_session(self, sid, name=None, email=None):
        @self.env.with_transaction()
        def add_session(db):
            cursor = db.cursor()
            cursor.execute("INSERT INTO session VALUES (%s, 1, %s)",
                           (sid, time.time()))
            if name is not None:
                cursor.execute("""
                    INSERT INTO session_attribute VALUES (%s, 1, 'name', %s)
                    """, (sid, name))
            if email is not None:
                cursor.execute("""
                    INSERT INTO session_attribute VALUES (%s, 1, 'email', %s)
                    """, (sid, email))

    def _set_attr(self, sid, attr, val):
        @self.env.with_transaction()
        def set_attr(db):
            cursor = db.cursor()
            cursor.execute("""
                SELECT authenticated FROM session WHERE sid = %s
                """, (sid,))
            for authenticated, in cursor:
                cursor.execute("""
                    SELECT name, value FROM session_attribute
                    WHERE sid = %s AND authenticated = %s AND name = %s
                    """, (sid, authenticated, attr))
                for row in cursor:
                    cursor.execute("""
                        UPDATE session_attribute SET value = %s
                        WHERE sid = %s AND authenticated = %s AND name = %s
                        """, (val, sid, authenticated, attr))
                    break
                else:
                    cursor.execute("""
                        INSERT INTO session_attribute VALUES (%s, %s, %s, %s)
                        """, (sid, authenticated, attr, val))
                break
            else:
                raise TracError(_("Session id %(sid)s not found", sid=sid))

    def _delete_session(self, sid):
        @self.env.with_transaction()
        def delete_session(db):
            cursor = db.cursor()
            if sid.lower() == 'anonymous':
                cursor.execute("""
                    DELETE FROM session_attribute WHERE authenticated = 0
                    """)
                cursor.execute("""
                    DELETE FROM session WHERE authenticated = 0
                    """)
            elif sid == '*':
                cursor.execute("""
                    DELETE FROM session_attribute WHERE name <> 'password'
                    """)
                cursor.execute("""
                    DELETE FROM session
                    """)
            else:
                cursor.execute("""
                    DELETE FROM session_attribute WHERE sid = %s
                    """, (sid,))
                cursor.execute("""
                    DELETE FROM session WHERE sid = %s
                    """, (sid,))

    def _purge_sessions(self, age=None):
        """Purge anonymous sessions older than [age].

        If `age` is None, then purge all anonymous sessions.
        """
        @self.env.with_transaction()
        def purge_session(db):
            cursor = db.cursor()
            if age:
                ts = to_timestamp(age)
                cursor.execute("""
                    DELETE FROM session_attribute
                    WHERE authenticated=0
                      AND sid IN (SELECT sid FROM session
                                  WHERE authenticated=0 AND last_visit < %s)
                    """, (ts,))
                cursor.execute("""
                    DELETE FROM session
                    WHERE authenticated=0 AND last_visit < %s
                    """, (ts,))
            else:
                cursor.execute("""
                    DELETE FROM session_attribute WHERE authenticated=0
                    """)
                cursor.execute("""
                    DELETE FROM session WHERE authenticated=0
                    """)

    def _get_authenticated_sids(self):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT sid FROM session WHERE authenticated = 1")
        return [r[0] for r in cursor]
