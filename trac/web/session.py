# -*- coding: iso-8859-1 -*-
#
# Copyright (C) 2004-2005 Edgewall Software
# Copyright (C) 2004 Daniel Lundin <daniel@edgewall.com>
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
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
        cursor.execute("SELECT var_name,var_value FROM session "
                       "WHERE sid=%s AND authenticated=%s",
                       (sid, int(authenticated)))
        for name, value in cursor:
            self[name] = value
        self._old.update(self)

        # Refresh the session cookie if this is the first visit since over a day
        if not authenticated and self.has_key('last_visit'):
            if time.time() - int(self['last_visit']) > UPDATE_INTERVAL:
                self.bake_cookie()

    def change_sid(self, new_sid):
        assert self.req.authname == 'anonymous', \
               'Cannot change ID of authenticated session'
        assert new_sid, 'Session ID cannot be empty'
        if new_sid == self.sid:
            return
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT sid FROM session WHERE sid=%s "
                       "AND authenticated=0", (new_sid,))
        if cursor.fetchone():
            raise TracError(Markup('Session "%s" already exists.<br />'
                                   'Please choose a different session ID.',
                                   new_sid), 'Error renaming session')
        self.env.log.debug('Changing session ID %s to %s' % (self.sid, new_sid))
        cursor.execute("UPDATE session SET sid=%s WHERE sid=%s "
                       "AND authenticated=0", (new_sid, self.sid))
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
        else:
            # Otherwise, update the session records so that the session ID is
            # the user name, and the authenticated flag is set
            self.env.log.debug('Promoting anonymous session %s to '
                               'authenticated session for user %s', sid,
                               self.req.authname)
            cursor.execute("UPDATE session SET sid=%s,authenticated=1 "
                           "WHERE sid=%s AND authenticated=0",
                           (self.req.authname, sid))
        db.commit()

        self.sid = sid
        self.bake_cookie(0) # expire the cookie

    def save(self):
        if not self._old and not self.items():
            # The session doesn't have associated data, so there's no need to
            # persist it
            return

        changed = False
        now = int(time.time())

        if self.req.authname == 'anonymous':
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

        db = self.env.get_db_cnx()
        cursor = db.cursor()
        authenticated = int(self.req.authname != 'anonymous')

        # Find all new or modified session variables and persist their values to
        # the database
        for k,v in self.items():
            if not self._old.has_key(k):
                self.env.log.debug('Adding variable %s with value "%s" to '
                                   'session %s' % (k, v,
                                   self.sid or self.req.authname))
                cursor.execute("INSERT INTO session VALUES(%s,%s,%s,%s)",
                               (self.sid, authenticated, k, v))
                changed = True
            elif v != self._old[k]:
                self.env.log.debug('Changing variable %s from "%s" to "%s" in '
                                   'session %s' % (k, self._old[k], v,
                                   self.sid))
                cursor.execute("UPDATE session SET var_value=%s "
                               "WHERE sid=%s AND authenticated=%s "
                               "AND var_name=%s", (v, self.sid, authenticated,
                               k))
                changed = True

        # Find all variables that have been deleted and also remove them from
        # the database
        for k in [k for k in self._old.keys() if not self.has_key(k)]:
            self.env.log.debug('Deleting variable %s from session %s'
                               % (k, self.sid or self.req.authname))
            cursor.execute("DELETE FROM session WHERE sid=%s AND "
                           "authenticated=%s AND var_name=%s",
                           (self.sid, authenticated, k))
            changed = True

        if changed:
            # Purge expired sessions. We do this only when the session was
            # changed as to minimize the purging.
            mintime = now - PURGE_AGE
            self.env.log.debug('Purging old, expired, sessions.')
            cursor.execute("DELETE FROM session WHERE authenticated=0 AND "
                           "sid IN (SELECT sid FROM session WHERE "
                           "var_name='last_visit' AND var_value < %s)",
                           (mintime,))

            db.commit()
