#!/usr/bin/env python
# -*- coding: iso8859-1 -*-
__version__ = '0.1'
__author__ = 'Daniel Lundin <daniel@edgewall.com>, Jonas Borgström <jonas@edgewall.com>'
__copyright__ = 'Copyright (c) 2004 Edgewall Research & Development'
__license__ = """
 Copyright (C) 2003, 2004 Edgewall Research & Development
 Copyright (C) 2003, 2004 Jonas Borgström <jonas@edgewall.com>
 Copyright (C) 2003, 2004 Daniel Lundin <daniel@edgewall.com>

 Trac is free software; you can redistribute it and/or
 modify it under the terms of the GNU General Public License as
 published by the Free Software Foundation; either version 2 of
 the License, or (at your option) any later version.

 Trac is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with this program; if not, write to the Free Software
 Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA."""

import os.path
import sys
import cmd
import shlex
import sqlite

class TracAdmin(cmd.Cmd):
    intro = ''
    license = __license__
    credits = '\n Visit the Trac Project at http://trac.edgewall.com/ \n'		\
              '\n Trac is brought to you by: \n' 				\
              '----------------------------------------------------------------- \n' 	\
              '                 Edgewall Research & Development \n' 			\
              '        Professional Linux and software development services \n'		\
              '              Read more at http://www.edgewall.com/ \n' 			\
              '----------------------------------------------------------------- \n' 

    doc_header = 'Trac Admin Console %(ver)s\n' \
                 'Available Commands:\n' \
                 % {'ver':__version__ }

    
    ruler = ''
    prompt = "Trac> "

    def __init__(self,dbfile=None):
        cmd.Cmd.__init__(self)
        self._intro_done = 0
        if dbfile:
            self.db_set(dbfile)

    def run(self):
        print 'Welcome to trac-admin %(ver)s,' 			\
              'the Trac adminstration console.\n' 		\
              '%(copy)s\n\n' 					\
              "Type:  '?' or 'help' for help on commands.\n" % 	\
              {'ver':__version__,'copy':__copyright__}
        while 1:
            try:
                self.cmdloop()
                break
            except KeyboardInterrupt:
                print "\n** Interrupt. Use 'quit' to exit **"


    ##
    ## Database methods
    ##

    def db_set(self, dbfile):
        self.dbname = dbfile
        self.prompt = "Trac [%s]> " % self.dbname

    def db_check(self):
        if os.path.isfile(self.dbname):
            f = file (self.dbname)
            data = f.read (50)
            if -1 == data.find("This file contains an SQLite"):
                return False
            f.close()
            return True
        return False
           
        
    def db_open(self):
        try:
            if not self.db_check():
                raise Exception
            return sqlite.connect (self.dbname)
        except Exception, e:
            print 'Failed to open/create database.'
            sys.exit()

    def db_execsql (self, sql):
        cnx=self.db_open()
        cursor = cnx.cursor()
        cursor.execute(sql)
        data = []
        while 1:
            row = cursor.fetchone()
            if row == None:
                break
            data.append(row)
        cnx.commit()
        return data

    ##
    ## Utility methods
    ##

    def arg_tokenize (self, argstr):
        return shlex.split(argstr) or ['']

    def word_complete (self, text, words):
        return [a for a in words if a.startswith (text)]

    def print_listing(self, headers, data, sep=' ',decor=1):
        ldata = data
        if decor:
            ldata.insert (0, headers)
        print
        colw=[]
        ncols = len(ldata[0]) # assumes all rows are of equal length
        for cnum in xrange(0, ncols):
            mw = 0
            for cell in [d[cnum] for d in ldata]:
                if len(cell) > mw:
                    mw = len(cell)
            colw.append(mw)
        for rnum in xrange(0, len(ldata)):
            for cnum in xrange(0, ncols):
                if decor and rnum == 0:
                    sp = ('%%%ds' % len(sep)) % ' '  # No separator in header
                else:
                    sp = sep
                if cnum+1 == ncols: sp = '' # No separator after last column
                print ("%%-%ds%s" % (colw[cnum], sp)) % ldata[rnum][cnum],
            print
            if rnum == 0 and decor:
                print ''.join(['-' for x in xrange(0,(1+len(sep))*cnum+sum(colw))])
        print

    def print_doc(self,doc,decor=False):
        if not doc: return
        self.print_listing (['Command','Description'], doc, '  --', decor) 

    def get_component_list (self):
        data = self.db_execsql ("SELECT name FROM component")
        return [r[0] for r in data]

    def get_config_list (self):
        data = self.db_execsql ("SELECT section||'.'||name FROM config")
        return [r[0] for r in data]

    def get_user_list (self):
        data = self.db_execsql ("SELECT DISTINCT user FROM permission")
        return [r[0] for r in data]


    ##
    ## Available Commands
    ##

    ## Help
    _help_help = [('help', 'Show documentation')]

    def do_help(self, line=None):
        arg = self.arg_tokenize(line)
        if arg[0]:
            try:
                doc = getattr(self, "_help_" + arg[0])
                self.print_doc (doc)
            except AttributeError:
                print "No documentation found for '%s'" % arg[0]
        else:
            docs = (self._help_about + self._help_help + self._help_initdb +
                    self._help_config +self._help_component)
            print 'trac-admin - The Trac Administration Console %s' % __version__
            self.print_doc (docs)
            print self.credits

    
    ## About / Version
    _help_about = [('about', 'Shows information about trac-admin')]
    _help_version = _help_about

    def do_about(self, line):
        print
        print 'Trac Admin Console %s' % __version__
        print '================================================================='
        print self.license
        print self.credits

    do_version = do_about # Alias


    ## Quit / EOF
    _help_quit = [['quit', 'Exit the program']]
    _help_EOF = _help_quit

    def do_quit(self,line):
        print
        sys.exit()

    do_EOF = do_quit # Alias


    ## Config
    _help_config = [('config list', 'Show current configuration'),
                     ('config set <option> <value>', 'Set config')]

    def complete_config (self, text, line, begidx, endidx):
        if begidx > 10 and line.startswith('config set'):
            comp = self.get_config_list()
        else:
            comp = ['list','show','set']
        return self.word_complete(text, comp)

    def do_config(self, line):
        arg = self.arg_tokenize(line)        
        try:
            if arg[0] in ['list', 'show']:
                self._do_config_list()
            elif arg[0] == 'set' and len(arg)==3:
                name = arg[1]
                value = arg[2]
                self._do_config_set(name, value)
            else:    
                self.do_help('config')
        except Exception, e:
            print "Config %s failed:" % arg[0], e

    def _do_config_list(self):
        data = self.db_execsql ('SELECT section, name, value FROM config')
        ldata = [[r[0]+'.'+r[1],r[2]] for r in data]
        self.print_listing(['Name', 'Value'], ldata)

    def _do_config_set(self, name, value):
        try:
            cfsection, cfname = name.split('.')
        except ValueError, e:
            raise Exception, "No such config option '%s'" % name
        data = self.db_execsql ("SELECT value FROM config WHERE "
                                    "section='%s' AND name='%s'" % (cfsection, cfname))
        if not data:
            raise Exception, "No such config option '%s'" % name
        self.db_execsql("UPDATE config SET value='%s' WHERE "
                        "section='%s' AND name='%s'" % (value, cfsection, cfname))
        

    ## Component
    _help_component = [('component list', 'Show available components'),
                       ('component add <name> <owner>', 'Add a new component'),
                       ('component remove <name>', 'Remove/uninstall component'),
                       ('component chown <name> <owner>', 'Change component ownership')]

    def complete_component (self, text, line, begidx, endidx):
        if begidx in [16,17]:
            comp = self.get_component_list()
        elif begidx > 15 and line.startswith('component chown '):
            comp = self.get_user_list()
        else:
            comp = ['list','add','remove','chown']
        return self.word_complete(text, comp)

    def do_component(self, line):
        arg = self.arg_tokenize(line)
        try:
            if arg[0]  == 'list':
                self._do_component_list()
            elif arg[0] == 'add' and len(arg)==3:
                name = arg[1]
                owner = arg[2]
                self._do_component_add(name, owner)
            elif arg[0] == 'remove'  and len(arg)==2:
                name = arg[1]
                self._do_component_remove(name)
            elif arg[0] == 'chown' and len(arg)==3:
                name = arg[1]
                owner = arg[2]
                self._do_component_set_owner(name, owner)
            else:    
                self.do_help ('component')
        except Exception, e:
            print 'Component %s failed:' % arg[0], e

    def _do_component_list(self):
        data = self.db_execsql('SELECT name, owner FROM component') 
        self.print_listing(['Name', 'Owner'], data)

    def _do_component_add(self, name, owner):
            data = self.db_execsql("INSERT INTO component VALUES('%s', '%s')"
                                   % (name, owner))

    def _do_component_remove(self, name):
            data = self.db_execsql("DELETE FROM component WHERE name='%s'"
                                   % (name))

    def _do_component_set_owner(self, name, owner):
            data = self.db_execsql("UPDATE component SET owner='%s' WHERE name='%s'"
                                   % (owner,name))


    ## Permission
    _help_permission = [('permission list', 'List permission rules'),
                       ('permission add <user> <action>', 'Add a new permission rule'),
                       ('permission remove <user> <action>', 'Remove permission rule')]

    def do_permission(self, line):
        arg = self.arg_tokenize(line)
        try:
            if arg[0]  == 'list':
                self._do_permission_list()
            elif arg[0] == 'add' and len(arg)==3:
                user = arg[1]
                action = arg[2]
                self._do_permission_add(user, action)
            elif arg[0] == 'remove'  and len(arg)==3:
                user = arg[1]
                action = arg[2]
                self._do_permission_remove(user, action)
            else:    
                self.do_help ('permission')
        except Exception, e:
            print 'Permission %s failed:' % arg[0], e

    def _do_permission_list(self):
        data = self.db_execsql('SELECT user, action FROM permission') 
        self.print_listing(['User', 'Action'], data)
        print
        print 'Available actions:'
        print ' LOG_VIEW, FILE_VIEW, CHANGESET_VIEW, BROWSER_VIEW, '
        print ' TICKET_VIEW, TICKET_CREATE, TICKET_MODIFY, TICKET_ADMIN, '
        print ' REPORT_VIEW, REPORT_CREATE, REPORT_MODIFY, REPORT_DELETE, REPORT_ADMIN, '
        print ' WIKI_VIEW, WIKI_CREATE, WIKI_MODIFY, WIKI_DELETE, WIKI_ADMIN, '
        print ' TIMELINE_VIEW and SEARCH_VIEW.'
        print ' CONFIG_VIEW, TRAC_ADMIN.'
        print
        
    def _do_permission_add(self, user, action):
        self.db_execsql("INSERT INTO permission VALUES('%s', '%s')" % (user, action))

    def _do_permission_remove(self, user, action):
        self.db_execsql("DELETE FROM permission WHERE user='%s' AND action='%s'" %
                        (user, action))

    ## Initdb
    _help_initdb = [('initdb', 'Create and initializes a new database')]

    def do_initdb(self, line):
        print "initializing..."
        if self.db_check():
            print "Initdb for '%s' failed.\nDoes a database already exist?" % self.dbname
            sys.exit(1)
        try:
            cnx = sqlite.connect (self.dbname)
            cursor = cnx.cursor ()
            self.initdb_create_tables(cursor)
            self.initdb_insert_default_values (cursor)
            cnx.commit()
        except Exception, e:
            print 'Failed to initialize database.', e
            cnx.rollback()
            sys.exit(1)

    def initdb_create_tables (self, cursor):
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

    def initdb_insert_default_values (self, cursor):
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



##
## Main
##
def main():
    tracadm = TracAdmin()
    if len (sys.argv) > 1:
        if sys.argv[1] in ['-h','--help','help']:
            tracadm.onecmd ("help")
        elif sys.argv[1] in ['-v','--version','version','about']:
            tracadm.onecmd ("version")
        else:
            tracadm.db_set(sys.argv[1])
            if len (sys.argv) > 2:
                s_args = ' '.join(["'%s'" % c for c in sys.argv[3:]])
                command = sys.argv[2] + ' ' +s_args
                tracadm.onecmd (command)
            else:
                while 1:
                    tracadm.run()
    else:
        tracadm.onecmd ("help")

if __name__ == '__main__':
    main()
