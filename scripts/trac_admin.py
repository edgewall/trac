#!/usr/bin/env python
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

# TODO:
# o Verify database version before modifying the database

import os
import sys
import sqlite

def usage():
    print '\nUsage: %s <database> <command>' % sys.argv[0]
    print '\n Available commands:'
    print '   initdb'
    print '   config list'
    print '   config set <name> <value>'
    print '   component list'
    print '   component add <name> <owner>'
    print '   component remove <name>'
    print '   component set owner <name> <new_owner>'
    print '   permission list'
    print '   permission add <user> <action>'
    print '   permission remove <user> <action>'
    print

def open_db(name):
    try:
        return sqlite.connect (name)
    except Exception, e:
        print 'Failed to open/create database.'
        sys.exit(1)

def create_tables (cursor):
    cursor.execute ("""
CREATE TABLE revision (
	rev 		integer PRIMARY KEY,
	time		integer,
	author		text,
	message		text
);
CREATE TABLE node_change (
	rev 		integer,
	name		text,
	change		char(1),
	UNIQUE(rev, name, change)
);
CREATE TABLE auth_cookie (
	cookie		text,
	name		text,
	ipnr		text,
	time		integer,
	UNIQUE(cookie, name, ipnr)
);
CREATE TABLE enum (
	type		text,
	name		text,
	value		text,
	UNIQUE(name,type)
);
CREATE TABLE config (
	section		text,
	name		text,
	value		text,
	UNIQUE(section, name)
);
CREATE TABLE ticket (
	id		integer PRIMARY KEY,
	time		integer,	-- the time it was created
	changetime	integer,
	component	text,
	severity	text,
	priority	text,
	owner		text,		-- who is this ticket assigned to
	reporter	text,
	cc		text,		-- email addresses to notify
	url		text,		-- url related to this ticket
	version		text,		-- 
	milestone	text,		-- 
	status		text,
	resolution	text,
	summary		text,		-- one-line summary
	description	text		-- problem description (long)
);
CREATE TABLE ticket_change (
	ticket		integer,
	time		integer,
	author		text,
	field		text,
	oldvalue	text,
	newvalue	text
);
CREATE TABLE report (
	id		integer PRIMARY KEY,
	author		text,
	title		text,
	sql		text
);
CREATE TABLE permission (
	user		text,		-- 
	action		text		-- allowable activity
);
CREATE TABLE component (
	 name		 text PRIMARY KEY,
	 owner		 text
);
CREATE TABLE milestone (
	 name		 text PRIMARY KEY,
	 time		 integer
);
CREATE TABLE version (
	 name		 text PRIMARY KEY,
	 time		 integer
);
CREATE TABLE wiki (
	 name		 text,
	 version		 integer,
	 time		 integer,
	 author		 text,
	 ipnr		 text,
	 locked		 integer,
	 text		 text,
	 UNIQUE(name,version)
);
""")

def insert_default_values (cursor):
    cursor.execute ("""
CREATE INDEX node_change_idx	ON node_change(rev);
CREATE INDEX ticket_change_idx	ON ticket_change(ticket, time);
CREATE INDEX wiki_idx		ON wiki(name,version);

INSERT INTO component (name, owner) VALUES('component1', 'somebody');
INSERT INTO component (name, owner) VALUES('component2', 'somebody');

INSERT INTO milestone (name, time) VALUES('', 0);
INSERT INTO milestone (name, time) VALUES('milestone1', 0);
INSERT INTO milestone (name, time) VALUES('milestone2', 0);
INSERT INTO milestone (name, time) VALUES('milestone3', 0);
INSERT INTO milestone (name, time) VALUES('milestone4', 0);

INSERT INTO version (name, time) VALUES('', 0);
INSERT INTO version (name, time) VALUES('1.0', 0);
INSERT INTO version (name, time) VALUES('2.0', 0);

INSERT INTO enum (type, name, value) VALUES('status', 'new', 1);
INSERT INTO enum (type, name, value) VALUES('status', 'assigned', 2);
INSERT INTO enum (type, name, value) VALUES('status', 'reopened', 3);
INSERT INTO enum (type, name, value) VALUES('status', 'closed', 4);

INSERT INTO enum (type, name, value) VALUES('resolution', 'fixed', 1);
INSERT INTO enum (type, name, value) VALUES('resolution', 'invalid', 2);
INSERT INTO enum (type, name, value) VALUES('resolution', 'wontfix', 3);
INSERT INTO enum (type, name, value) VALUES('resolution', 'duplicate', 4);
INSERT INTO enum (type, name, value) VALUES('resolution', 'worksforme', 5);

INSERT INTO enum (type, name, value) VALUES('severity', 'blocker', 1);
INSERT INTO enum (type, name, value) VALUES('severity', 'critical', 2);
INSERT INTO enum (type, name, value) VALUES('severity', 'major', 3);
INSERT INTO enum (type, name, value) VALUES('severity', 'normal', 4);
INSERT INTO enum (type, name, value) VALUES('severity', 'minor', 5);
INSERT INTO enum (type, name, value) VALUES('severity', 'trivial', 6);
INSERT INTO enum (type, name, value) VALUES('severity', 'enhancement', 7);

INSERT INTO enum (type, name, value) VALUES('priority', 'p1', 1);
INSERT INTO enum (type, name, value) VALUES('priority', 'p2', 2);
INSERT INTO enum (type, name, value) VALUES('priority', 'p3', 3);
INSERT INTO enum (type, name, value) VALUES('priority', 'p4', 4);
INSERT INTO enum (type, name, value) VALUES('priority', 'p5', 5);

INSERT INTO permission (user, action) VALUES('anonymous', 'LOG_VIEW');
INSERT INTO permission (user, action) VALUES('anonymous', 'FILE_VIEW');
INSERT INTO permission (user, action) VALUES('anonymous', 'WIKI_VIEW');
INSERT INTO permission (user, action) VALUES('anonymous', 'SEARCH_VIEW');
INSERT INTO permission (user, action) VALUES('anonymous', 'REPORT_VIEW');
INSERT INTO permission (user, action) VALUES('anonymous', 'TICKET_VIEW');
INSERT INTO permission (user, action) VALUES('anonymous', 'TICKET_CREATE');
INSERT INTO permission (user, action) VALUES('anonymous', 'BROWSER_VIEW');
INSERT INTO permission (user, action) VALUES('anonymous', 'TIMELINE_VIEW');
INSERT INTO permission (user, action) VALUES('anonymous', 'CHANGESET_VIEW');

INSERT INTO config (section, name, value)
VALUES('trac', 'database_version', '1');
INSERT INTO config (section, name, value)
VALUES('general', 'htdocs_location', '/trac/');
INSERT INTO config (section, name, value)
VALUES('general', 'repository_dir', '/var/svn/myrep');
INSERT INTO config (section, name, value)
VALUES('general', 'templates_dir', '/usr/lib/trac/templates');
INSERT INTO config (section, name, value)
VALUES('ticket', 'default_version', '');
INSERT INTO config (section, name, value)
VALUES('ticket', 'default_severity', 'normal');
INSERT INTO config (section, name, value)
VALUES('ticket', 'default_priority', 'p2');
INSERT INTO config (section, name, value)
VALUES('ticket', 'default_milestone', '');
INSERT INTO config (section, name, value)
VALUES('ticket', 'default_component', 'general');
INSERT INTO config (section, name, value)
VALUES('header_logo', 'link', 'http://trac.edgewall.com/');
INSERT INTO config (section, name, value)
VALUES('header_logo', 'src', 'trac_banner.png');
INSERT INTO config (section, name, value)
VALUES('header_logo', 'alt', 'Trac');
INSERT INTO config (section, name, value)
VALUES('header_logo', 'width', '199');
INSERT INTO config (section, name, value)
VALUES('header_logo', 'height', '38');

INSERT INTO report (id, author, title, sql) 
	VALUES (1, NULL, 'Active tickets', 
"SELECT id AS ticket, status, 
severity, priority, owner, time as created, summary 
FROM ticket 
WHERE status IN ('new', 'assigned', 'reopened')
ORDER BY priority, time"
);
""")

def cmd_initdb():
    dbname = sys.argv[1]
    if os.access(dbname, os.R_OK):
        print 'database %s already exists' % dbname
        sys.exit(1)
    try:
        cnx = sqlite.connect (dbname)
    except Exception, e:
        print 'Failed to create database %s.' % dbname
        sys.exit(1)
    try:
        cursor = cnx.cursor ()
        create_tables (cursor)
        insert_default_values (cursor)
        cnx.commit()
    except Exception, e:
        print 'Failed to initialize database.', e
        cnx.rollback()
        sys.exit(1)

def cmd_config_list():
    cnx = open_db(sys.argv[1])
    cursor = cnx.cursor()
    cursor.execute('SELECT section, name, value FROM config')
    print 'Name                           Value'
    print '============================================================'
    while 1:
        row = cursor.fetchone()
        if row == None:
            break
        print '%-30s %-30s' % (row[0] + '.' + row[1], row[2])
    
def cmd_config_set():
    name = sys.argv[4]
    section, name = name.split('.')
    value = sys.argv[5]
    cnx = open_db(sys.argv[1])
    cursor = cnx.cursor()
    try:
        cursor.execute('UPDATE config SET value=%s WHERE '
                       'section=%s AND name=%s', value, section, name)
        cnx.commit()
    except Exception, e:
        print 'Config change failed:', e

def cmd_component_list():
    cnx = open_db(sys.argv[1])
    cursor = cnx.cursor()
    cursor.execute('SELECT name, owner FROM component')
    print 'Name                           Owner'
    print '============================================================'
    while 1:
        row = cursor.fetchone()
        if row == None:
            break
        print '%-30s %-30s' % (row[0], row[1])

def cmd_component_add():
    name = sys.argv[4]
    owner = sys.argv[5]
    cnx = open_db(sys.argv[1])
    cursor = cnx.cursor()
    try:
        cursor.execute('INSERT INTO component VALUES(%s, %s)',
                       name, owner)
        cnx.commit()
    except:
        print 'Component addition failed'
        sys.exit(1)

def cmd_component_remove():
    name = sys.argv[4]
    cnx = open_db(sys.argv[1])
    cursor = cnx.cursor()
    try:
        cursor.execute('DELETE FROM component WHERE name=%s',
                       name)
        cnx.commit()
    except:
        print 'Component removal failed'
        sys.exit(1)

def cmd_component_set_owner():
    name = sys.argv[5]
    owner = sys.argv[6]
    cnx = open_db(sys.argv[1])
    cursor = cnx.cursor()
    try:
        cursor.execute('UPDATE component SET owner=%s WHERE name=%s',
                       owner, name)
        cnx.commit()
    except:
        print 'Owner change failed'
        sys.exit(1)

def cmd_permission_list():
    cnx = open_db(sys.argv[1])
    cursor = cnx.cursor()
    cursor.execute('SELECT user, action FROM permission')
    print 'User                           Action'
    print '============================================================'
    while 1:
        row = cursor.fetchone()
        if row == None:
            break
        print '%-30s %-30s' % (row[0], row[1])
    print
    print 'Available action:'
    print ' LOG_VIEW, FILE_VIEW, CHANGESET_VIEW, BROWSER_VIEW, '
    print ' TICKET_VIEW, TICKET_CREATE, TICKET_MODIFY, TICKET_ADMIN, '
    print ' REPORT_VIEW, REPORT_CREATE, REPORT_MODIFY, REPORT_DELETE, REPORT_ADMIN, '
    print ' WIKI_VIEW, WIKI_CREATE, WIKI_MODIFY, WIKI_DELETE, WIKI_ADMIN, '
    print ' TIMELINE_VIEW and SEARCH_VIEW.'
    print ' CONFIG_VIEW, TRAC_ADMIN.'
    
def cmd_permission_add():
    user = sys.argv[4]
    action = sys.argv[5]
    cnx = open_db(sys.argv[1])
    cursor = cnx.cursor()
    try:
        cursor.execute('INSERT INTO permission VALUES(%s, %s)',
                       user, action)
        cnx.commit()
    except:
        print 'Permission addition failed.'
        sys.exit(1)

def cmd_permission_remove():
    user = sys.argv[4]
    action = sys.argv[5]
    cnx = open_db(sys.argv[1])
    cursor = cnx.cursor()
    try:
        cursor.execute('DELETE FROM permission WHERE user=%s AND action=%s',
                       user, action)
        cnx.commit()
    except:
        print 'Permission removal failed'
        sys.exit(1)

def main():
    if sys.argv[2:] == ['initdb']:
        cmd_initdb()
    elif sys.argv[2:] == ['config', 'list']:
        cmd_config_list()
    elif sys.argv[2:4] == ['config', 'set'] and len(sys.argv) == 6:
        cmd_config_set()
    elif sys.argv[2:] == ['component', 'list']:
        cmd_component_list()
    elif sys.argv[2:4] == ['component', 'add'] and len(sys.argv) == 6:
        cmd_component_add()
    elif sys.argv[2:4] == ['component', 'remove'] and len(sys.argv) == 5:
        cmd_component_remove()
    elif sys.argv[2:5] == ['component', 'set', 'owner'] and len(sys.argv) == 7:
        cmd_component_set_owner()
    elif sys.argv[2:] == ['permission', 'list']:
        cmd_permission_list()
    elif sys.argv[2:4] == ['permission', 'add'] and len(sys.argv) == 6:
        cmd_permission_add()
    elif sys.argv[2:4] == ['permission', 'remove'] and len(sys.argv) == 6:
        cmd_permission_remove()
    else:
        usage()

if __name__ == '__main__':
    main()
