# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2005 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
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
# Author: Jonas Borgström <jonas@edgewall.com>

import os

from trac import db_default, util
from trac.config import *
from trac.core import Component, ComponentManager, implements, Interface, \
                      ExtensionPoint, TracError
from trac.db import DatabaseManager
from trac.versioncontrol import RepositoryManager

__all__ = ['Environment', 'IEnvironmentSetupParticipant', 'open_environment']


class IEnvironmentSetupParticipant(Interface):
    """Extension point interface for components that need to participate in the
    creation and upgrading of Trac environments, for example to create
    additional database tables."""

    def environment_created():
        """Called when a new Trac environment is created."""

    def environment_needs_upgrade(db):
        """Called when Trac checks whether the environment needs to be upgraded.
        
        Should return `True` if this participant needs an upgrade to be
        performed, `False` otherwise.
        """

    def upgrade_environment(db):
        """Actually perform an environment upgrade.
        
        Implementations of this method should not commit any database
        transactions. This is done implicitly after all participants have
        performed the upgrades they need without an error being raised.
        """


class Environment(Component, ComponentManager):
    """Trac stores project information in a Trac environment.

    A Trac environment consists of a directory structure containing among other
    things:
     * a configuration file.
     * an SQLite database (stores tickets, wiki pages...)
     * Project specific templates and wiki macros.
     * wiki and ticket attachments.
    """   
    setup_participants = ExtensionPoint(IEnvironmentSetupParticipant)

    base_url = Option('trac', 'base_url', '',
        """Base URL of the Trac deployment.
        
        In most configurations, Trac will automatically reconstruct the URL
        that is used to access it automatically. However, in more complex
        setups, usually involving running Trac behind a HTTP proxy, you may
        need to use this option to force Trac to use the correct URL.""")

    project_name = Option('project', 'name', 'My Project',
        """Name of the project.""")

    project_description = Option('project', 'descr', 'My example project',
        """Short description of the project.""")

    project_url = Option('project', 'url', 'http://example.org/',
        """URL of the main project web site.""")

    project_footer = Option('project', 'footer',
                            'Visit the Trac open source project at<br />'
                            '<a href="http://trac.edgewall.com/">'
                            'http://trac.edgewall.com/</a>',
        """Page footer text (right-aligned).""")

    project_icon = Option('project', 'icon', 'common/trac.ico',
        """URL of the icon of the project.""")

    log_type = Option('logging', 'log_type', 'none',
        """Logging facility to use.
        
        Should be one of (`none`, `file`, `stderr`, `syslog`, `winlog`).""")

    log_file = Option('logging', 'log_file', 'trac.log',
        """If `log_type` is `file`, this should be a path to the log-file.""")

    log_level = Option('logging', 'log_level', 'DEBUG',
        """Level of verbosity in log.
        
        Should be one of (`CRITICAL`, `ERROR`, `WARN`, `INFO`, `DEBUG`).""")

    def __init__(self, path, create=False, options=[]):
        """Initialize the Trac environment.
        
        @param path:   the absolute path to the Trac environment
        @param create: if `True`, the environment is created and populated with
                       default data; otherwise, the environment is expected to
                       already exist.
        @param options: A list of `(section, name, value)` tuples that define
                        configuration options
        """
        ComponentManager.__init__(self)

        self.path = path
        self.setup_config(load_defaults=create)
        self.setup_log()

        from trac.loader import load_components
        load_components(self)

        if create:
            self.create(options)
        else:
            self.verify()

        if create:
            for setup_participant in self.setup_participants:
                setup_participant.environment_created()

    def component_activated(self, component):
        """Initialize additional member variables for components.
        
        Every component activated through the `Environment` object gets three
        member variables: `env` (the environment object), `config` (the
        environment configuration) and `log` (a logger object)."""
        component.env = self
        component.config = self.config
        component.log = self.log

    def is_component_enabled(self, cls):
        """Implemented to only allow activation of components that are not
        disabled in the configuration.
        
        This is called by the `ComponentManager` base class when a component is
        about to be activated. If this method returns false, the component does
        not get activated."""
        if not isinstance(cls, basestring):
            component_name = (cls.__module__ + '.' + cls.__name__).lower()
        else:
            component_name = cls.lower()

        rules = [(name.lower(), value.lower() in ('enabled', 'on'))
                 for name, value in self.config.options('components')]
        rules.sort(lambda a, b: -cmp(len(a[0]), len(b[0])))

        for pattern, enabled in rules:
            if component_name == pattern or pattern.endswith('*') \
                    and component_name.startswith(pattern[:-1]):
                return enabled

        # versioncontrol components are enabled if the repository is configured
        # FIXME: this shouldn't be hardcoded like this
        if component_name.startswith('trac.versioncontrol.'):
            return self.config.get('trac', 'repository_dir') != ''

        # By default, all components in the trac package are enabled
        return component_name.startswith('trac.')

    def verify(self):
        """Verify that the provided path points to a valid Trac environment
        directory."""
        fd = open(os.path.join(self.path, 'VERSION'), 'r')
        try:
            assert fd.read(26) == 'Trac Environment Version 1'
        finally:
            fd.close()

    def get_db_cnx(self):
        """Return a database connection from the connection pool."""
        return DatabaseManager(self).get_connection()

    def shutdown(self):
        """Close the environment."""
        DatabaseManager(self).shutdown()

    def get_repository(self, authname=None):
        """Return the version control repository configured for this
        environment.
        
        @param authname: user name for authorization
        """
        return RepositoryManager(self).get_repository(authname)

    def create(self, options=[]):
        """Create the basic directory structure of the environment, initialize
        the database and populate the configuration file with default values."""
        def _create_file(fname, data=None):
            fd = open(fname, 'w')
            if data: fd.write(data)
            fd.close()

        # Create the directory structure
        if not os.path.exists(self.path):
            os.mkdir(self.path)
        os.mkdir(self.get_log_dir())
        os.mkdir(self.get_htdocs_dir())
        os.mkdir(os.path.join(self.path, 'plugins'))
        os.mkdir(os.path.join(self.path, 'wiki-macros'))

        # Create a few files
        _create_file(os.path.join(self.path, 'VERSION'),
                     'Trac Environment Version 1\n')
        _create_file(os.path.join(self.path, 'README'),
                     'This directory contains a Trac environment.\n'
                     'Visit http://trac.edgewall.com/ for more information.\n')

        # Setup the default configuration
        os.mkdir(os.path.join(self.path, 'conf'))
        _create_file(os.path.join(self.path, 'conf', 'trac.ini'))
        self.setup_config(load_defaults=True)
        for section, name, value in options:
            self.config.set(section, name, value)
        self.config.save()

        # Create the database
        DatabaseManager(self).init_db()

    def get_version(self, db=None):
        """Return the current version of the database."""
        if not db:
            db = self.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT value FROM system WHERE name='database_version'")
        row = cursor.fetchone()
        return row and int(row[0])

    def setup_config(self, load_defaults=False):
        """Load the configuration file."""
        self.config = Configuration(os.path.join(self.path, 'conf', 'trac.ini'))
        if load_defaults:
            for section, default_options in self.config.defaults().iteritems():
                for name, value in default_options.iteritems():
                    self.config.set(section, name, value)

    def get_templates_dir(self):
        """Return absolute path to the templates directory."""
        return os.path.join(self.path, 'templates')

    def get_htdocs_dir(self):
        """Return absolute path to the htdocs directory."""
        return os.path.join(self.path, 'htdocs')

    def get_log_dir(self):
        """Return absolute path to the log directory."""
        return os.path.join(self.path, 'log')

    def setup_log(self):
        """Initialize the logging sub-system."""
        from trac.log import logger_factory
        logtype = self.log_type
        logfile = self.log_file
        if logtype == 'file' and not os.path.isabs(logfile):
            logfile = os.path.join(self.get_log_dir(), logfile)
        self.log = logger_factory(logtype, logfile, self.log_level, self.path)

    def get_known_users(self, cnx=None):
        """Generator that yields information about all known users, i.e. users
        that have logged in to this Trac environment and possibly set their name
        and email.

        This function generates one tuple for every user, of the form
        (username, name, email) ordered alpha-numerically by username.

        @param cnx: the database connection; if ommitted, a new connection is
                    retrieved
        """
        if not cnx:
            cnx = self.get_db_cnx()
        cursor = cnx.cursor()
        cursor.execute("SELECT DISTINCT s.sid, n.value, e.value "
                       "FROM session AS s "
                       " LEFT JOIN session_attribute AS n ON (n.sid=s.sid "
                       "  and n.authenticated=1 AND n.name = 'name') "
                       " LEFT JOIN session_attribute AS e ON (e.sid=s.sid "
                       "  AND e.authenticated=1 AND e.name = 'email') "
                       "WHERE s.authenticated=1 ORDER BY s.sid")
        for username,name,email in cursor:
            yield username, name, email

    def backup(self, dest=None):
        """Simple SQLite-specific backup of the database.

        @param dest: Destination file; if not specified, the backup is stored in
                     a file called db_name.trac_version.bak
        """
        import shutil

        db_str = self.config.get('trac', 'database')
        if not db_str.startswith('sqlite:'):
            raise EnvironmentError, 'Can only backup sqlite databases'
        db_name = os.path.join(self.path, db_str[7:])
        if not dest:
            dest = '%s.%i.bak' % (db_name, self.get_version())
        shutil.copy (db_name, dest)

    def needs_upgrade(self):
        """Return whether the environment needs to be upgraded."""
        db = self.get_db_cnx()
        for participant in self.setup_participants:
            if participant.environment_needs_upgrade(db):
                self.log.warning('Component %s requires environment upgrade',
                                 participant)
                return True
        return False

    def upgrade(self, backup=False, backup_dest=None):
        """Upgrade database.
        
        Each db version should have its own upgrade module, names
        upgrades/dbN.py, where 'N' is the version number (int).

        @param backup: whether or not to backup before upgrading
        @param backup_dest: name of the backup file
        @return: whether the upgrade was performed
        """
        db = self.get_db_cnx()

        upgraders = []
        for participant in self.setup_participants:
            if participant.environment_needs_upgrade(db):
                upgraders.append(participant)
        if not upgraders:
            return False

        if backup:
            self.backup(backup_dest)
        for participant in upgraders:
            participant.upgrade_environment(db)
        db.commit()

        # Database schema may have changed, so close all connections
        self.shutdown()

        return True


class EnvironmentSetup(Component):
    implements(IEnvironmentSetupParticipant)

    # IEnvironmentSetupParticipant methods

    def environment_created(self):
        """Insert default data into the database."""
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        for table, cols, vals in db_default.data:
            cursor.executemany("INSERT INTO %s (%s) VALUES (%s)" % (table,
                               ','.join(cols), ','.join(['%s' for c in cols])),
                               vals)
        db.commit()
        self._update_sample_config()

    def environment_needs_upgrade(self, db):
        dbver = self.env.get_version(db)
        if dbver == db_default.db_version:
            return False
        elif dbver > db_default.db_version:
            raise TracError, 'Database newer than Trac version'
        return True

    def upgrade_environment(self, db):
        cursor = db.cursor()
        dbver = self.env.get_version()
        for i in range(dbver + 1, db_default.db_version + 1):
            name  = 'db%i' % i
            try:
                upgrades = __import__('upgrades', globals(), locals(), [name])
                script = getattr(upgrades, name)
            except AttributeError:
                err = 'No upgrade module for version %i (%s.py)' % (i, name)
                raise TracError, err
            script.do_upgrade(self.env, i, cursor)
        cursor.execute("UPDATE system SET value=%s WHERE "
                       "name='database_version'", (db_default.db_version,))
        self.log.info('Upgraded database version from %d to %d',
                      dbver, db_default.db_version)
        self._update_sample_config()

    # Internal methods

    def _update_sample_config(self):
        from ConfigParser import ConfigParser
        config = ConfigParser()
        for section, options in self.config.defaults().items():
            config.add_section(section)
            for name, value in options.items():
                config.set(section, name, value)
        filename = os.path.join(self.env.path, 'conf', 'trac.ini.sample')
        try:
            fileobj = file(filename, 'w')
            try:
                config.write(fileobj)
                fileobj.close()
            finally:
                fileobj.close()
            self.log.info('Wrote sample configuration file with the new '
                          'settings and their default values: %s',
                          filename)
        except IOError, e:
            self.log.warn('Couldn\'t write sample configuration file (%s)', e,
                          exc_info=True)


def open_environment(env_path=None):
    """Open an existing environment object, and verify that the database is up
    to date.

    @param: env_path absolute path to the environment directory; if ommitted,
            the value of the `TRAC_ENV` environment variable is used
    @return: the `Environment` object
    """
    if not env_path:
        env_path = os.getenv('TRAC_ENV')
    if not env_path:
        raise TracError, 'Missing environment variable "TRAC_ENV". Trac ' \
                         'requires this variable to point to a valid Trac ' \
                         'environment.'

    env = Environment(env_path)
    if env.needs_upgrade():
        raise TracError, 'The Trac Environment needs to be upgraded. Run ' \
                         'trac-admin %s upgrade"' % env_path
    return env
