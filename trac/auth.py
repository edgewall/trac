# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004 Edgewall Software
# Copyright (C) 2003, 2004 Jonas Borgström <jonas@edgewall.com>
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
# Author: Jonas Borgström <jonas@edgewall.com>

import os
import Cookie
import time
import util
import random

AUTH_TIMEOUT = 60*60*24*30 # 30 days

authname = 'anonymous'

def get_authname ():
    return authname

def flush_auth_cookies (db):
    """
    Delete auth cookies which are older then AUTH_TIMEOUT seconds.
    """
    cursor = db.cursor ()
    cursor.execute ('DELETE FROM auth_cookie WHERE time < %d'
                    % int(time.time() - AUTH_TIMEOUT))
    db.commit ()

def validate_auth_cookie (db, auth_cookie, ipnr):
    """
    Makes sure the auth_cookie is valid and that it comes from the correct host.
    """
    cursor = db.cursor ()
    cursor.execute ("SELECT name FROM auth_cookie WHERE cookie='%s' AND ipnr='%s'"
                    % (auth_cookie, ipnr))
    if cursor.rowcount >= 1:
        global authname
        authname = cursor.fetchone()[0]
        return 1
    else:
        return 0

def update_auth_cookie (db, auth_cookie, ipnr):
    """
    Update the timeout value for an auth cookie.
    """
    cursor = db.cursor ()
    cursor.execute ("UPDATE auth_cookie SET time=%d WHERE cookie='%s' AND ipnr='%s'" % (int(time.time()), auth_cookie, ipnr))
    db.commit ()

def create_auth_cookie (db, name, ipnr):
    """
    Create a new auth_cookie which is stored in the db and sent to the user
    """
    global authname
    cursor = db.cursor ()
    # TODO: authenticate here
    cookie = str(random.random())
    cursor.execute ("INSERT INTO auth_cookie (cookie, name, ipnr, time)" +
                    "VALUES ('%s', '%s', '%s', %d)"
                    % (cookie, name, ipnr, int(time.time())));
    db.commit ()
    authname = name
    return cookie

def authenticate_user (db):
    flush_auth_cookies (db)
    cookie = Cookie.SimpleCookie(os.getenv('HTTP_COOKIE'))
    auth_cookie = create_auth_cookie (os.getenv('REMOTE_USER'),
                                      os.getenv('REMOTE_ADDR'))
    cookie['trac_auth'] = auth_cookie
    cookie['trac_auth']['path'] = os.getenv('SCRIPT_NAME')
    #cookie['trac_auth']['secure'] = 'true'
    # send the cookie to the browser as a http header
    print cookie.output()

def login(db):
    authenticate_user(db)
    if os.getenv('PATH_INFO') == '/login':
        uri = os.getenv('HTTP_REFERER')
        if not uri:
            import Href
            uri = Href.href.wiki()
        util.redirect (uri)

def logout (db, auth_cookie):
    cursor = db.cursor ()
    cursor.execute ("DELETE FROM auth_cookie WHERE cookie='%s'" % auth_cookie)
    db.commit ()
    if os.getenv('PATH_INFO') == '/logout':
        uri = os.getenv('HTTP_REFERER')
        if not uri:
            import Href
            uri = Href.href.wiki()
        util.redirect (uri)

def verify_authentication (db, args):
    cookie = Cookie.SimpleCookie(os.getenv('HTTP_COOKIE'))
    remote_addr = os.getenv ('REMOTE_ADDR')
    
    if cookie.has_key('trac_auth'):
        auth_cookie = cookie['trac_auth'].value
        if os.getenv('PATH_INFO') == '/logout':
            logout (db, auth_cookie)
        else:
            if not validate_auth_cookie (db, auth_cookie, remote_addr)  \
                   and os.getenv('REMOTE_USER'):
                login(db)
    elif os.getenv('REMOTE_USER'):
        login(db)
        
