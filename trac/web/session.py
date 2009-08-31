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

from trac.core import TracError
from trac.util import hex_entropy
from trac.util.html import Markup

UPDATE_INTERVAL = 3600*24 # Update session last_visit time stamp after 1 day
PURGE_AGE = 3600*24*90 # Purge session after 90 days idle
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

    def save(self):
        if not self._old and not self.items():
            # The session doesn't have associated data, so there's no need to
            # persist it
            return

        authenticated = int(self.authenticated)
        now = int(time.time())
        db = self.env.get_db_cnx()
        cursor = db.cursor()

        if self._new:
            self.last_visit = now
            self._new = False
            # The session might already exist even if _new is True since
            # it could have been created by a concurrent request (#3563).
            try:
                cursor.execute("INSERT INTO session (sid,last_visit,authenticated)"
                               " VALUES(%s,%s,%s)",
                               (self.sid, self.last_visit, authenticated))
            except Exception, e:
                db.rollback()
                self.env.log.warning('Session %s already exists: %s' % 
                                     (self.sid, e))
        if self._old != self:
            attrs = [(self.sid, authenticated, k, v) for k, v in self.items()]
            cursor.execute("DELETE FROM session_attribute WHERE sid=%s",
                           (self.sid,))
            self._old = dict(self.items())
            if attrs:
                # The session variables might already have been updated by a 
                # concurrent request.
                try:
                    cursor.executemany("INSERT INTO session_attribute "
                                       "(sid,authenticated,name,value) "
                                       "VALUES(%s,%s,%s,%s)", attrs)
                except Exception, e:
                    db.rollback()
                    self.env.log.warning('Attributes for session %s already '
                                         'updated: %s' % (self.sid, e))
            elif not authenticated:
                # No need to keep around empty unauthenticated sessions
                cursor.execute("DELETE FROM session "
                               "WHERE sid=%s AND authenticated=0", (self.sid,))
                db.commit()
                return

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

        # Refresh the session cookie if this is the first visit since over a day
        if not authenticated and refresh_cookie:
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
                                   'Please choose a different session ID.')
                            % new_sid, 'Error renaming session')
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
        cursor.execute("SELECT authenticated FROM session "
                       "WHERE sid=%s OR sid=%s ", (sid, self.req.authname))
        authenticated_flags = [row[0] for row in cursor.fetchall()]
        
        if len(authenticated_flags) == 2:
            # There's already an authenticated session for the user, we
            # simply delete the anonymous session
            cursor.execute("DELETE FROM session WHERE sid=%s "
                           "AND authenticated=0", (sid,))
            cursor.execute("DELETE FROM session_attribute WHERE sid=%s "
                           "AND authenticated=0", (sid,))
        elif len(authenticated_flags) == 1:
            if not authenticated_flags[0]:
                # Update the anomymous session records so that the session ID
                # becomes the user name, and set the authenticated flag.
                self.env.log.debug('Promoting anonymous session %s to '
                                   'authenticated session for user %s',
                                   sid, self.req.authname)
                cursor.execute("UPDATE session SET sid=%s,authenticated=1 "
                               "WHERE sid=%s AND authenticated=0",
                               (self.req.authname, sid))
                cursor.execute("UPDATE session_attribute "
                               "SET sid=%s,authenticated=1 WHERE sid=%s",
                               (self.req.authname, sid))
        else:
            # we didn't have an anonymous session for this sid
            cursor.execute("INSERT INTO session (sid,last_visit,authenticated)"
                           " VALUES(%s,%s,1)",
                           (self.req.authname, int(time.time())))
        self._new = False
        db.commit()

        self.sid = sid
        self.bake_cookie(0) # expire the cookie
