# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2005 Edgewall Software
# Copyright (C) 2004 Daniel Lundin <daniel@edgewall.com>
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2006 Jonas Borgström <jonas@edgewall.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Daniel Lundin <daniel@edgewall.com>
#         Christopher Lenz <cmlenz@gmx.de>

import time

from trac.core import TracError
from trac.util import hex_entropy, Markup

UPDATE_INTERVAL = 3600*24 # Update session last_visit time stamp after 1 day
PURGE_AGE = 3600*24*90 # Purge session after 90 days idle
COOKIE_KEY = 'trac_session'


class Session(dict):
    """Basic session handling and per-session storage."""

    def __init__(self, env, req):
        dict.__init__(self)
        self.env = env
        self.req = req
        self.sid = None
        self.last_visit = 0
        self._new = True
        self._old = {}
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
        self.req.outcookie[COOKIE_KEY]['path'] = self.req.base_path
        self.req.outcookie[COOKIE_KEY]['expires'] = expires

    def get_session(self, sid, authenticated=False):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        self.sid = sid
        cursor.execute("SELECT last_visit FROM session "
                       "WHERE sid=%s AND authenticated=%s",
                       (sid, int(authenticated)))
        row = cursor.fetchone()
        if not row:
            return
        self._new = False
        self.last_visit = int(row[0])
        cursor.execute("SELECT name,value FROM session_attribute "
                       "WHERE sid=%s and authenticated=%s",
                       (sid, int(authenticated)))
        for name, value in cursor:
            self[name] = value
        self._old.update(self)

        # Refresh the session cookie if this is the first visit since over a day
        if not authenticated and self.last_visit:
            if time.time() - self.last_visit > UPDATE_INTERVAL:
                self.bake_cookie()

    def change_sid(self, new_sid):
        assert self.req.authname == 'anonymous', \
               'Cannot change ID of authenticated session'
        assert new_sid, 'Session ID cannot be empty'
        if new_sid == self.sid:
            return
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT sid FROM session WHERE sid=%s", (new_sid,))
        if cursor.fetchone():
            raise TracError(Markup('Session "%s" already exists.<br />'
                                   'Please choose a different session ID.',
                                   new_sid), 'Error renaming session')
        self.env.log.debug('Changing session ID %s to %s' % (self.sid, new_sid))
        cursor.execute("UPDATE session SET sid=%s WHERE sid=%s "
                       "AND authenticated=0", (new_sid, self.sid))
        cursor.execute("UPDATE session_attribute SET sid=%s "
                       "WHERE sid=%s and authenticated=0",
                       (new_sid, self.sid))
        db.commit()
        self.sid = new_sid
        self.bake_cookie()

    def promote_session(self, sid):
        """Promotes an anonymous session to an authenticated session, if there
        is no preexisting session data for that user name.
        """
        assert self.req.authname != 'anonymous', \
               'Cannot promote session of anonymous user'

        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM session WHERE sid=%s "
                       "AND authenticated=1", (self.req.authname,))
        if cursor.fetchone()[0]:
            # If there's already an authenticated session for the user, we
            # simply delete the anonymous session
            cursor.execute("DELETE FROM session WHERE sid=%s "
                           "AND authenticated=0", (sid,))
            cursor.execute("DELETE FROM session_attribute WHERE sid=%s "
                           "AND authenticated=0", (sid,))
        else:
            # Otherwise, update the session records so that the session ID is
            # the user name, and the authenticated flag is set
            self.env.log.debug('Promoting anonymous session %s to '
                               'authenticated session for user %s', sid,
                               self.req.authname)
            cursor.execute("UPDATE session SET sid=%s,authenticated=1 "
                           "WHERE sid=%s AND authenticated=0",
                           (self.req.authname, sid))
            cursor.execute("UPDATE session_attribute SET sid=%s,"
                           "authenticated=1 WHERE sid=%s",
                           (self.req.authname, sid))
        self._new = False
        db.commit()

        self.sid = sid
        self.bake_cookie(0) # expire the cookie

    def save(self):
        if not self._old and not self.items():
            # The session doesn't have associated data, so there's no need to
            # persist it
            return

        db = self.env.get_db_cnx()
        cursor = db.cursor()
        authenticated = int(self.req.authname != 'anonymous')

        if self._new:
            self._new = False
            cursor.execute("INSERT INTO session (sid,last_visit,authenticated) "
                           "VALUES(%s,%s,%s)", (self.sid,
                                                self.last_visit,
                                                authenticated))
        if self._old.items() != self.items():
            attrs = [(self.sid, authenticated, k, v) for k, v in self.items()]
            cursor.execute("DELETE FROM session_attribute WHERE sid=%s",
                           (self.sid,))
            self._old = dict(self.items())
            if attrs:
                cursor.executemany("INSERT INTO session_attribute "
                                   "(sid,authenticated,name,value) "
                                   "VALUES(%s,%s,%s,%s)", attrs)
            elif not authenticated:
                # No need to keep around empty unauthenticated sessions
                cursor.execute("DELETE FROM session "
                               "WHERE sid=%s AND authenticated=0" % (self.sid,))
                return

        now = int(time.time())
        # Update the session last visit time if it is over an hour old,
        # so that session doesn't get purged
        if now - self.last_visit > UPDATE_INTERVAL:
            self.last_visit = now
            self.env.log.info("Refreshing session %s" % self.sid)
            cursor.execute('UPDATE session SET last_visit=%s '
                           'WHERE sid=%s AND authenticated=%s',
                           (self.last_visit, self.sid, authenticated))
            # Purge expired sessions. We do this only when the session was
            # changed as to minimize the purging.
            mintime = now - PURGE_AGE
            self.env.log.debug('Purging old, expired, sessions.')
            cursor.execute("DELETE FROM session_attribute "
                           "WHERE authenticated=0 AND sid "
                           "IN (SELECT sid FROM session WHERE "
                           "authenticated=0 AND last_visit < %s)",
                           (mintime,))
            cursor.execute("DELETE FROM session WHERE "
                           "authenticated=0 AND last_visit < %s",
                           (mintime,))
        db.commit()
