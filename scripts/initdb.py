#!/usr/bin/env python
#
# svntrac
#
# Copyright (C) 2002, 2003 Jonas Borgström <jonas@codefactory.se>
#
# svntrac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# svntrac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Jonas Borgström <jonas@codefactory.se>

import sys
import sqlite

def usage():
    print
    print 'Initializes/creates a new (empty) svntrac database'
    print
    print 'usage: %s <dbfilename>' % sys.argv[0]
    print
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

INSERT INTO component (name, owner) VALUES('general', 'jonas');
INSERT INTO component (name, owner) VALUES('report system', 'jonas');
INSERT INTO component (name, owner) VALUES('browser', 'jonas');
INSERT INTO component (name, owner) VALUES('timeline', 'jonas');
INSERT INTO component (name, owner) VALUES('ticket system', 'jonas');

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
INSERT INTO permission (user, action) VALUES('anonymous', 'REPORT_VIEW');
INSERT INTO permission (user, action) VALUES('anonymous', 'TICKET_VIEW');
INSERT INTO permission (user, action) VALUES('anonymous', 'BROWSER_VIEW');
INSERT INTO permission (user, action) VALUES('anonymous', 'TIMELINE_VIEW');
INSERT INTO permission (user, action) VALUES('anonymous', 'CHANGESET_VIEW');

INSERT INTO report (id, author, title, sql) 
	VALUES (1, NULL, 'active tickets', 
"SELECT id AS ticket, status, 
severity, priority, owner, time as created, summary 
FROM ticket 
WHERE status IN ('new', 'assigned', 'reopened')
ORDER BY priority, time"
);
""")

def initialize_db (name):
    print 'Initializing "%s"...' % name,
    try:
        cnx = sqlite.connect (name)
    except Exception, e:
        print 'Failed to open/create database.'
        sys.exit(1)
    try:
        cursor = cnx.cursor ()
        create_tables (cursor)
        insert_default_values (cursor)
        cnx.commit()
    except Exception, e:
        print 'Failed to initialize database.'
        cnx.rollback()
        sys.exit(1)
    print 'done\n'

def main():
    if len(sys.argv) != 2:
        usage()
        
    initialize_db (sys.argv[1])

if __name__ == '__main__':
    main()

