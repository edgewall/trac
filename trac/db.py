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
import os.path
import shutil
import sqlite
import db_default

__db_version__ = db_default.db_version

class Database(sqlite.Connection):
    def __init__(self, db_name, create=0):
        if not create and not os.access(db_name, os.F_OK):
            raise EnvironmentError, 'Database "%s" not found.' % db_name
        
        directory = os.path.dirname(db_name) or os.curdir
        if not create and not os.access(db_name, os.R_OK + os.W_OK) or \
               not os.access(directory, os.R_OK + os.W_OK):
            tmp = db_name
            db_name = None
            raise EnvironmentError, \
                  'The web server user requires read _and_ write permission\n' \
                  'to the database %s and the directory this file is located in.' % tmp
        self.db_name = db_name
        sqlite.Connection.__init__(self, db_name, timeout=10000)

    def __del__(self):
        pass 
        
    def load_config(self):
        """
        load configuration from the config table.
        
        The configuration is returned as a section-dictionary containing
        name-value dictionaries.
        """
        cursor = self.cursor()
        cursor.execute('SELECT section, name, value FROM config')
        config = {}
        rows = cursor.fetchall()
        for row in rows:
            if not config.has_key(row[0]):
                config[row[0]] = {}
            config[row[0]][row[1]] = row[2]
        return config

    def get_version(self):
        cursor = self.cursor()
        cursor.execute("SELECT value FROM config"
                       " WHERE section='trac' AND name='database_version'")
        row = cursor.fetchone()
        return row and int(row[0])

    def initdb(self):
        cursor = self.cursor()
        try:
            if self.get_version():
                raise EnvironmentError, 'Trac database already exists.'
        except:
            pass
        cursor.execute (db_default.schema)
        self.commit()
        
    def insert_default_data (self):
        def prep_value(v):
            if v == None:
                return 'NULL'
            else:
                return '"%s"' % v

        if self.get_version():
            raise EnvironmentError, 'Database already has data.'
        cursor = self.cursor()
        
        for t in xrange(0, len(db_default.data)):
            table = db_default.data[t][0]
            cols = ','.join(db_default.data[t][1])
            for row in db_default.data[t][2]:
                values = ','.join(map(prep_value, row))
                sql = "INSERT INTO %s (%s) VALUES(%s);" % (table, cols, values)
                cursor.execute(sql)
        self.commit()

    def backup(self, dest=None):
        """Simple SQLite-specific backup. Copy the database file."""
        if not dest:
            dest = '%s.%i.bak' % (self.db_name, self.get_version())
        shutil.copy (self.db_name, dest)

    def upgrade(self, backup=None,backup_dest=None):
        """Upgrade database. Each db version should have its own upgrade
        module, names upgrades/dbN.py, where 'N' is the version number (int)."""
        dbver = self.get_version()
        if dbver == __db_version__:
            return 0
        elif dbver > __db_version__:
            raise EnvironmentError, 'Database newer than Trac version'
        else:
            if backup:
                self.backup(backup_dest)
            import upgrades
            for i in xrange(dbver + 1, __db_version__ + 1):
                try:
                    upg  = 'db%i' % i
                    __import__('upgrades', globals(), locals(),[upg])
                    d = getattr(upgrades, upg)
                except AttributeError:
                    err = 'No upgrade module for version %i (%s.py)' % (i, upg)
                    raise EnvironmentError, err
                d.do_upgrade(self, i)
                cursor = self.cursor()
                cursor.execute("UPDATE config SET value='%i' WHERE"
                             " section='trac' AND name='database_version'" % i)
                self.commit()
            return 1
