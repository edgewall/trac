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

import sys
from util import *

class Session:
    """Basic session handling and per-session storage."""

    sid = None
    req = None
    env = None
    db = None
    vars = {}

    DEPARTURE_INTERVAL = 3600 # If you're idle for an hour, you left
    UPDATE_INTERVAL = 300  # Update session every 5 mins
    COOKIE_KEY = 'trac_session'

    def __init__(self, env, req, newsession = 0):
        self.env = env
        self.db = self.env.get_db_cnx()
        self.req = req
        self.sid = None
        self.vars = {}
        if newsession:
            self.create_new_sid()
        else:
            try:
                sid = req.incookie[self.COOKIE_KEY].value
                self.get_session(sid)
            except KeyError:
                self.create_new_sid()

    def __getitem__(self, key):
        return self.vars[key]

    def __setitem__(self, key, val):
        return self.set_var(key, val)

    def __delitem__(self, key):
        return self.set_var(key, '')

    def get(self, *args):
        return apply(self.vars.get, args)

    def __repr__(self):
        s = "\n session id='%s'" % self.sid
        for k in self.vars.keys():
            s += "\n  %s='%s'" % (k, self.vars[k])
        return s

    def keys(self):
        return self.vars.keys()

    def bake_cookie(self):
        self.req.outcookie[self.COOKIE_KEY] = self.sid
        self.req.outcookie[self.COOKIE_KEY]['path'] = self.req.cgi_location
        self.req.outcookie[self.COOKIE_KEY]['expires'] = 420000000

    def populate_hdf(self):
        add_dict_to_hdf(self.vars, self.req.hdf, 'trac.session.var')
        self.req.hdf.setValue('trac.session.id', self.sid)
        last_visit =  float(self.get('last_visit', 0))
        if last_visit:
            self.req.hdf.setValue('trac.session.var.last_visit_txt',
                                  time.strftime('%x %X', time.localtime(last_visit)))
        mod_time =  float(self.get('mod_time', 0))
        if mod_time:
            self.req.hdf.setValue('trac.session.var.mod_time_txt',
                                  time.strftime('%x %X', time.localtime(mod_time)))

    def update_sess_time(self):
        sess_time = int(self.get('mod_time',0))
        last_visit = int(self.get('last_visit',0))
        now = int(time.time())
        idle = now - sess_time
        if idle > self.DEPARTURE_INTERVAL or not last_visit:
            self['last_visit'] = sess_time
        if idle > self.UPDATE_INTERVAL or not sess_time:
            self['mod_time'] = now

    def get_session(self, sid):
        self.sid = sid
        curs = self.db.cursor()
        curs.execute("SELECT username,var_name,var_value FROM session"
                    " WHERE sid=%s", self.sid)
        rows = curs.fetchall()
        if (not rows                              # No session data yet
            or rows[0][0] == 'anonymous'          # Anon session
            or rows[0][0] == self.req.authname):  # Session is mine
            for u,k,v in rows:
                self.vars[k] = v
            self.update_sess_time()
            self.bake_cookie()
            self.populate_hdf()
            return
        if self.req.authname == 'anonymous':
            err = ('Session cookie requires authentication. <p>'
                   'Please choose action:</p>'
                   '<ul><li><a href="%s">Log in and continue session</a></li>'
                   '<li><a href="%s?newsession=1">Create new session (no login required)</a></li>'
                   '</ul>'
                   % (self.env.href.login(), self.env.href.settings()))
        else:
            err = ('Session belongs to another authenticated user.'
                   '<p><a href="%s?newsession=1">'
                   'Create new session</a></p>' % self.env.href.settings())
        raise TracError(err, 'Error accessing authenticated session')

    def set_var(self, key, val):
        currval =  self.get(key)
        if currval == val:
            return
        curs = self.db.cursor()
        if currval == None:
            curs.execute('INSERT INTO session(sid,username,var_name,var_value)'
                         ' VALUES(%s,%s,%s,%s)',
                         self.sid, self.req.authname, key, val)
        else:
            curs.execute('UPDATE session SET username=%s,var_value=%s'
                         ' WHERE sid=%s AND var_name=%s',
                         self.req.authname, val, self.sid, key)
        self.db.commit()
        self.vars[key] = val

    def create_new_sid(self):
        self.sid = hex_entropy(24)
        self.bake_cookie()
        self.populate_hdf()

    def change_sid(self, newsid):
        if newsid == self.sid:
            return
        curs = self.db.cursor()
        curs.execute("SELECT sid FROM session WHERE sid=%s", newsid)
        if curs.fetchone():
            raise TracError("Session '%s' already exists.<br />"
                            "Please choose a different session id." % newsid,
                            "Error renaming session")
        curs.execute("UPDATE session SET sid=%s WHERE sid=%s",
                     newsid, self.sid)
        self.db.commit()
        self.sid = newsid
        self.bake_cookie()
