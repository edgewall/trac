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

from util import *

class Session:
    """Basic session handling and per-session storage."""

    sid = None
    req = None
    env = None
    db = None
    vars = {}

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

    def populate_hdf(self):
        add_dict_to_hdf(self.vars, self.req.hdf, 'trac.session.var')
        self.req.hdf.setValue('trac.session.id', self.sid)

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
        currval =  self.vars.get(key)
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
        self.env.log.debug('Setting session variable: %s::%s = %s' % (self.sid,
                                                                     key,val))
        self.db.commit()
        self.vars[key] = val

    def create_new_sid(self):
        self.sid = hex_entropy()
        self.env.log.debug('Creating new session: %s' % self.sid)
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
        self.env.log.debug('Renamed session %s => %s' % (self.sid, newsid))
