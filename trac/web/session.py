# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004 Edgewall Software
# Copyright (C) 2004 Daniel Lundin <daniel@edgewall.com>
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
# Author: Daniel Lundin <daniel@edgewall.com>

from trac.util import hex_entropy, TracError

import sys
import time


UPDATE_INTERVAL = 3600*24 # Update session last_visit time stamp after 1 day
PURGE_AGE = 3600*24*90 # Purge session after 90 days idle
COOKIE_KEY = 'trac_session'


class Session(dict):
    """Basic session handling and per-session storage."""

    sid = None
    req = None
    env = None
    db = None
    _old = {}

    def __init__(self, env, db, req, newsession=0):
        dict.__init__(self)
        self.env = env
        self.db = db
        self.req = req
        self.sid = None
        self._old = {}
        if req.authname == 'anonymous':
            if newsession or not req.incookie.has_key(COOKIE_KEY):
                self.sid = hex_entropy(24)
                self.bake_cookie()
            else:
                sid = req.incookie[COOKIE_KEY].value
                self.get_session(sid)
        else:
            if req.incookie.has_key(COOKIE_KEY):
                sid = req.incookie[COOKIE_KEY].value
                self.promote_session(sid)
            self.get_session()

    def bake_cookie(self, expires=PURGE_AGE):
        self.req.outcookie[COOKIE_KEY] = self.sid
        self.req.outcookie[COOKIE_KEY]['path'] = self.req.cgi_location
        self.req.outcookie[COOKIE_KEY]['expires'] = expires

    def get_session(self, sid=None):
        cursor = self.db.cursor()
        if sid:
            self.sid = sid
            cursor.execute("SELECT var_name,var_value FROM session "
                           "WHERE sid=%s AND username='anonymous'", (sid,))
        else:
            cursor.execute("SELECT var_name,var_value FROM session "
                           "WHERE sid IS NULL AND username=%s",
                           (self.req.authname))
        for name, value in cursor:
            self[name] = value
        self._old.update(self)

        # Refresh the session cookie if this is the first visit since over a day
        if sid and self.has_key('last_visit'):
            if time.time() - int(self['last_visit']) > UPDATE_INTERVAL:
                self.bake_cookie()

    def change_sid(self, new_sid):
        assert self.sid, "Cannot change ID of authenticated session"
        assert new_sid, "Session ID cannot be empty"
        if new_sid == self.sid:
            return
        cursor = self.db.cursor()
        cursor.execute("SELECT sid FROM session WHERE sid=%s", (new_sid,))
        if cursor.fetchone():
            raise TracError("Session '%s' already exists.<br />"
                            "Please choose a different session id." % new_sid,
                            "Error renaming session")
        self.env.log.debug('Changing session ID %s to %s' % (self.sid, newsid))
        cursor.execute("UPDATE session SET sid=%s WHERE sid=%s",
                       (new_sid, self.sid))
        self.db.commit()
        self.sid = new_sid
        self.bake_cookie()

    def promote_session(self, sid):
        """
        Promotes an anonymous session to an authenticated session, if there is
        no preexisting session data for that user name.
        """
        assert self.req.authname != 'anonymous', \
               'Cannot promote session of anonymous user'

        self.env.log.debug('Promoting anonymous session %s to authenticated '
                           'session for user %s' % (sid, self.req.authname))
        cursor = self.db.cursor()
        cursor.execute("SELECT COUNT(*) FROM session WHERE username=%s",
                       (self.req.authname,))
        if cursor.fetchone()[0]:
            cursor.execute("DELETE FROM session WHERE sid=%s "
                           "AND username='anonymous'", (sid,))
        else:
            cursor.execute("UPDATE session SET sid=NULL,username=%s "
                           "WHERE sid=%s AND username='anonymous'",
                           (self.req.authname, sid))
        self.db.commit()
        self.bake_cookie(0) # expire the cookie

    def save(self):
        if not self._old and not self.items():
            # The session doesn't have associated data, so there's no need to
            # persist it
            return

        changed = 0
        now = int(time.time())

        if self.sid:
            # Update the session last visit time if it is over an hour old,
            # so that session doesn't get purged
            last_visit = int(self.get('last_visit', 0))
            if now - last_visit > UPDATE_INTERVAL:
                self.env.log.info("Refreshing session %s" % self.sid)
                self['last_visit'] = now

            # If the only data in the session is the last_visit time, it makes
            # no sense to keep the session around
            if len(self.items()) == 1:
                del self['last_visit']

        cursor = self.db.cursor()

        # Find all new or modified session variables and persist their values to
        # the database
        for k,v in self.items():
            if not self._old.has_key(k):
                self.env.log.debug('Adding variable %s with value "%s" to '
                                   'session %s' % (k, v,
                                   self.sid or self.req.authname))
                cursor.execute("INSERT INTO session (sid,username,var_name,"
                               "var_value) VALUES(%s,%s,%s,%s)",
                               (self.sid, self.req.authname, k, v))
                changed = 1
            elif v != self._old[k]:
                self.env.log.debug('Changing variable %s from "%s" to "%s" in '
                                   'session %s' % (k, self._old[k], v,
                                   self.sid or self.req.authname))
                cursor.execute("UPDATE session SET var_value=%s WHERE sid=%s "
                               "AND username=%s AND var_name=%s",
                               (v, self.sid, self.req.authname, k))
                changed = 1

        # Find all variables that have been deleted and also remove them from
        # the database
        for k in [k for k in self._old.keys() if not self.has_key(k)]:
            self.env.log.debug('Deleting variable %s from session %s'
                               % (k, self.sid or self.req.authname))
            cursor.execute("DELETE FROM session WHERE sid=%s AND username=%s "
                           "AND var_name=%s", (self.sid, self.req.authname, k))
            changed = 1

        if changed:
            # Purge expired sessions. We do this only when the session was
            # changed as to minimize the purging.
            mintime = now - PURGE_AGE
            self.env.log.debug('Purging old, expired, sessions.')
            cursor.execute("DELETE FROM session WHERE username='anonymous' AND "
                           "sid IN (SELECT sid FROM session WHERE "
                           "var_name='last_visit' AND var_value < %s)",
                           (mintime,))

            self.db.commit()
