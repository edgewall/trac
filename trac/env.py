# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004, 2005 Edgewall Software
# Copyright (C) 2003, 2004, 2005 Jonas Borgström <jonas@edgewall.com>
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
# 

from __future__ import generators

from trac import db, db_default, util
from trac.config import Configuration
from trac.core import ComponentManager

import os
import shutil
import sys
import time
import urllib
import unicodedata

db_version = db_default.db_version


class Environment(ComponentManager):
    """
    Trac stores project information in a Trac environment.

    A Trac environment consists of a directory structure containing
    among other things:
     * a configuration file.
     * a sqlite database (stores tickets, wiki pages...)
     * Project specific templates and wiki macros.
     * wiki and ticket attachments.
    """
    __cnx_pool = None

    def __init__(self, path, create=False, db_str=None):
        ComponentManager.__init__(self)
        self.path = path
        if create:
            self.create(db_str)
        self.verify()
        self.load_config()

        try: # Use binary I/O on Windows
            import msvcrt
            msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
            msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
        except ImportError:
            pass

        self.setup_log()

        from trac.loader import load_components
        load_components(self)

    def component_activated(self, component):
        component.env = self
        component.config = self.config
        component.log = self.log

    def is_component_enabled(self, cls):
        component_name = (cls.__module__ + '.' + cls.__name__).lower()
        for name,value in self.config.options('disabled_components'):
            if value in util.TRUE and component_name.startswith(name):
                return False
        return True

    def verify(self):
        """Verifies that self.path is a compatible trac environment"""
        fd = open(os.path.join(self.path, 'VERSION'), 'r')
        assert fd.read(26) == 'Trac Environment Version 1'
        fd.close()

    def get_db_cnx(self):
        if not self.__cnx_pool:
            self.__cnx_pool = db.get_cnx_pool(self)
        return self.__cnx_pool.get_cnx()

    def get_repository(self, authname=None):
        from trac.versioncontrol.cache import CachedRepository
        from trac.versioncontrol.svn_authz import SubversionAuthorizer
        from trac.versioncontrol.svn_fs import SubversionRepository
        repos_dir = self.config.get('trac', 'repository_dir')
        if not repos_dir:
            raise EnvironmentError, 'Path to repository not configured'
        authz = None
        if authname:
            authz = SubversionAuthorizer(self, authname)
        repos = SubversionRepository(repos_dir, authz, self.log)
        return CachedRepository(self.get_db_cnx(), repos, authz, self.log)

    def create(self, db_str=None):
        def _create_file(fname, data=None):
            fd = open(fname, 'w')
            if data: fd.write(data)
            fd.close()
        # Create the directory structure
        os.mkdir(self.path)
        os.mkdir(os.path.join(self.path, 'conf'))
        os.mkdir(self.get_log_dir())
        os.mkdir(self.get_attachments_dir())
        os.mkdir(self.get_templates_dir())
        os.mkdir(os.path.join(self.path, 'wiki-macros'))
        # Create a few static files
        _create_file(os.path.join(self.path, 'VERSION'),
                     'Trac Environment Version 1\n')
        _create_file(os.path.join(self.path, 'README'),
                    'This directory contains a Trac project.\n'
                    'Visit http://trac.edgewall.com/ for more information.\n')
        _create_file(os.path.join(self.path, 'conf', 'trac.ini'))
        _create_file(os.path.join(self.get_templates_dir(), 'README'),
                     'This directory contains project-specific custom templates and style sheet.\n')
        _create_file(os.path.join(self.get_templates_dir(), 'site_header.cs'),
                     """<?cs
####################################################################
# Site header - Contents are automatically inserted above Trac HTML
?>
""")
        _create_file(os.path.join(self.get_templates_dir(), 'site_footer.cs'),
                     """<?cs
#########################################################################
# Site footer - Contents are automatically inserted after main Trac HTML
?>
""")
        _create_file(os.path.join(self.get_templates_dir(), 'site_css.cs'),
                     """<?cs
##################################################################
# Site CSS - Place custom CSS, including overriding styles here.
?>
""")

        # Setup the default configuration
        self.load_config()
        for section,name,value in db_default.default_config:
            self.config.set(section, name, value)
        self.config.set('trac', 'database', db_str)
        self.config.save()

        # Create the database
        cnx = db.init_db(self.path, db_str)
        self._insert_default_data(cnx)

    def _insert_default_data(self, db=None):
        if not db:
            db = self.get_db_cnx()
        cursor = db.cursor()
        for table, cols, vals in db_default.data:
            cursor.executemany("INSERT INTO %s (%s) VALUES (%s)" % (table,
                               ','.join(cols), ','.join(['%s' for c in cols])),
                               vals)
        db.commit()

    def get_version(self):
        cnx = self.get_db_cnx()
        cursor = cnx.cursor()
        cursor.execute("SELECT value FROM system WHERE name='database_version'")
        row = cursor.fetchone()
        return row and int(row[0])

    def load_config(self):
        self.config = Configuration(os.path.join(self.path, 'conf', 'trac.ini'))
        for section,name,value in db_default.default_config:
            self.config.setdefault(section, name, value)

    def get_templates_dir(self):
        return os.path.join(self.path, 'templates')

    def get_log_dir(self):
        return os.path.join(self.path, 'log')

    def setup_log(self):
        from trac.log import logger_factory
        logtype = self.config.get('logging', 'log_type')
        loglevel = self.config.get('logging', 'log_level')
        logfile = self.config.get('logging', 'log_file')
        logfile = os.path.join(self.get_log_dir(), logfile)
        logid = self.path # Env-path provides process-unique ID
        self.log = logger_factory(logtype, logfile, loglevel, logid)

    def get_attachments_dir(self):
        return os.path.join(self.path, 'attachments')

    def get_known_users(self, cnx=None):
        """
        Generator that yields information about all known users, i.e. users that
        have logged in to this Trac environment and possibly set their name and
        email.

        This function generates one tuple for every user, of the form
        (username, name, email) ordered alpha-numerically by username.
        """
        if not cnx:
            cnx = self.get_db_cnx()
        cursor = cnx.cursor()
        cursor.execute("SELECT DISTINCT s.sid, n.var_value, e.var_value "
                       "FROM session AS s "
                       " LEFT JOIN session AS n ON (n.sid=s.sid "
                       "  AND n.authenticated=1 AND n.var_name = 'name') "
                       " LEFT JOIN session AS e ON (e.sid=s.sid "
                       "  AND e.authenticated=1 AND e.var_name = 'email') "
                       "WHERE s.authenticated=1 ORDER BY s.sid")
        for username,name,email in cursor:
            yield username, name, email

    def backup(self, dest=None):
        """Simple SQLite-specific backup. Copy the database file."""
        db_str = self.config.get('trac', 'database')
        if db_str[:7] != 'sqlite:':
            raise EnvironmentError, 'Can only backup sqlite databases'
        db_name = os.path.join(self.path, db_str[7:])
        if not dest:
            dest = '%s.%i.bak' % (db_name, self.get_version())
        shutil.copy (db_name, dest)

    def upgrade(self, backup=None,backup_dest=None):
        """Upgrade database. Each db version should have its own upgrade
        module, names upgrades/dbN.py, where 'N' is the version number (int)."""
        dbver = self.get_version()
        if dbver == db_default.db_version:
            return 0
        elif dbver > db_default.db_version:
            raise EnvironmentError, 'Database newer than Trac version'
        else:
            if backup:
                self.backup(backup_dest)
            cnx = self.get_db_cnx()
            cursor = cnx.cursor()
            import upgrades
            for i in xrange(dbver + 1, db_default.db_version + 1):
                try:
                    upg  = 'db%i' % i
                    __import__('upgrades', globals(), locals(),[upg])
                    d = getattr(upgrades, upg)
                except AttributeError:
                    err = 'No upgrade module for version %i (%s.py)' % (i, upg)
                    raise EnvironmentError, err
                d.do_upgrade(self, i, cursor)
            cursor.execute("UPDATE system SET value=%s WHERE "
                           "name='database_version'", (db_default.db_version))
            self.log.info('Upgraded db version from %d to %d',
                          dbver, db_default.db_version)
            cnx.commit()
            return 1


def open_environment(env_path=None):
    if not env_path:
        env_path = os.getenv('TRAC_ENV')
    if not env_path:
        raise EnvironmentError, \
              'Missing environment variable "TRAC_ENV". Trac requires this ' \
              'variable to point to a valid Trac Environment.'

    env = Environment(env_path)
    version = env.get_version()
    if version < db_version:
        raise EnvironmentError, \
              'The Trac Environment needs to be upgraded. Run "trac-admin %s ' \
              'upgrade"' % env_path
    elif version > db_version:
        raise EnvironmentError, \
              'Unknown Trac Environment version (%d).' % version
    return env
