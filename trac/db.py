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
import sqlite

class Database(sqlite.Connection):
    def __init__(self, db_name):
        if not os.access(db_name, os.F_OK):
            raise EnvironmentError, 'Database "%s" not found.' % db_name
        
        directory = os.path.dirname(db_name)
        if not os.access(db_name, os.R_OK + os.W_OK) or \
               not os.access(directory, os.R_OK + os.W_OK):
            tmp = db_name
            db_name = None
            raise EnvironmentError, \
                  'The web server user requires read _and_ write permission\n' \
                  'to the database %s and the directory this file is located in.' % tmp
        sqlite.Connection.__init__(self, db_name, timeout=10000)
        
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
