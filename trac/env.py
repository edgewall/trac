# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2007 Jonas Borgström <jonas@edgewall.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Jonas Borgström <jonas@edgewall.com>

import os
try:
    import threading
except ImportError:
    import dummy_threading as threading
import setuptools
import sys
from urlparse import urlsplit

from trac import db_default
from trac.config import *
from trac.core import Component, ComponentManager, implements, Interface, \
                      ExtensionPoint, TracError
from trac.db import DatabaseManager
from trac.util import create_file, get_pkginfo
from trac.util.text import exception_to_unicode
from trac.util.translation import _
from trac.versioncontrol import RepositoryManager
from trac.web.href import Href

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
     * Project specific templates and plugins.
     * wiki and ticket attachments.
    """   
    setup_participants = ExtensionPoint(IEnvironmentSetupParticipant)

    shared_plugins_dir = PathOption('inherit', 'plugins_dir', '',
        """Path of the directory containing additional plugins.
        
        Plugins in that directory are loaded in addition to those in the
        directory of the environment `plugins`, with this one taking 
        precedence.
        
        (''since 0.11'')""")

    base_url = Option('trac', 'base_url', '',
        """Reference URL for the Trac deployment.
        
        This is the base URL that will be used when producing documents that
        will be used outside of the web browsing context, like for example
        when inserting URLs pointing to Trac resources in notification
        e-mails.""")

    base_url_for_redirect = BoolOption('trac', 'use_base_url_for_redirect',
            False, 
        """Optionally use `[trac] base_url` for redirects.
        
        In some configurations, usually involving running Trac behind a HTTP
        proxy, Trac can't automatically reconstruct the URL that is used to
        access it. You may need to use this option to force Trac to use the
        `base_url` setting also for redirects. This introduces the obvious
        limitation that this environment will only be usable when accessible
        from that URL, as redirects are frequently used. ''(since 0.10.5)''""")

    secure_cookies = BoolOption('trac', 'secure_cookies', False,
        """Restrict cookies to HTTPS connections.
        
        When true, set the `secure` flag on all cookies so that they are
        only sent to the server on HTTPS connections. Use this if your Trac
        instance is only accessible through HTTPS. (''since 0.11.2'')""")

    project_name = Option('project', 'name', 'My Project',
        """Name of the project.""")

    project_description = Option('project', 'descr', 'My example project',
        """Short description of the project.""")

    project_url = Option('project', 'url', '',
        """URL of the main project web site, usually the website in which
        the `base_url` resides.""")

    project_admin = Option('project', 'admin', '',
        """E-Mail address of the project's administrator.""")

    project_admin_trac_url = Option('project', 'admin_trac_url', '.',
        """Base URL of a Trac instance where errors in this Trac should be
        reported.
        
        This can be an absolute or relative URL, or '.' to reference this
        Trac instance. An empty value will disable the reporting buttons.
        (''since 0.11.3'')""")

    project_footer = Option('project', 'footer',
                            'Visit the Trac open source project at<br />'
                            '<a href="http://trac.edgewall.org/">'
                            'http://trac.edgewall.org/</a>',
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

    log_format = Option('logging', 'log_format', None,
        """Custom logging format.

        If nothing is set, the following will be used:
        
        Trac[$(module)s] $(levelname)s: $(message)s

        In addition to regular key names supported by the Python logger library
        library (see http://docs.python.org/lib/node422.html), one could use:
         - $(path)s     the path for the current environment
         - $(basename)s the last path component of the current environment
         - $(project)s  the project name

         Note the usage of `$(...)s` instead of `%(...)s` as the latter form
         would be interpreted by the ConfigParser itself.

         Example:
         ($(thread)d) Trac[$(basename)s:$(module)s] $(levelname)s: $(message)s

         (since 0.10.5)""")

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

        from trac import core, __version__ as VERSION
        self.systeminfo = [
            ('Trac', get_pkginfo(core).get('version', VERSION)),
            ('Python', sys.version),
            ('setuptools', setuptools.__version__),
            ]
        self._href = self._abs_href = None

        from trac.loader import load_components
        plugins_dir = self.shared_plugins_dir
        load_components(self, plugins_dir and (plugins_dir,))

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
        if not hasattr(self, '_rules'):
            self._rules = {}
            for name, value in self.config.options('components'):
                if name.endswith('.*'):
                    name = name[:-2]
                self._rules[name.lower()] = value.lower() in ('enabled', 'on')

        if not isinstance(cls, basestring):
            component_name = (cls.__module__ + '.' + cls.__name__).lower()
        else:
            component_name = cls.lower()

        # Disable the pre-0.11 WebAdmin plugin
        # Please note that there's no recommendation to uninstall the
        # plugin because doing so would obviously break the backwards
        # compatibility that the new integration administration
        # interface tries to provide for old WebAdmin extensions
        if component_name.startswith('webadmin.'):
            self.log.info('The legacy TracWebAdmin plugin has been '
                          'automatically disabled, and the integrated '
                          'administration interface will be used '
                          'instead.')
            return False
        
        cname = component_name
        while cname:
            enabled = self._rules.get(cname)
            if enabled is not None:
                return enabled
            idx = cname.rfind('.')
            if idx < 0:
                break
            cname = cname[:idx]

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

    def shutdown(self, tid=None, except_logging=False):
        """Close the environment."""
        RepositoryManager(self).shutdown(tid)
        DatabaseManager(self).shutdown(tid)
        if tid is None and not except_logging and \
                hasattr(self.log, '_trac_handler'):
            hdlr = self.log._trac_handler
            self.log.removeHandler(hdlr)
            hdlr.flush()
            hdlr.close()
            del self.log._trac_handler

    def get_repository(self, authname=None):
        """Return the version control repository configured for this
        environment.
        
        @param authname: user name for authorization
        """
        return RepositoryManager(self).get_repository(authname)

    def create(self, options=[]):
        """Create the basic directory structure of the environment, initialize
        the database and populate the configuration file with default values.

        If options contains ('inherit', 'file'), default values will not be
        loaded; they are expected to be provided by that file or other options.
        """
        # Create the directory structure
        if not os.path.exists(self.path):
            os.mkdir(self.path)
        os.mkdir(self.get_log_dir())
        os.mkdir(self.get_htdocs_dir())
        os.mkdir(os.path.join(self.path, 'plugins'))

        # Create a few files
        create_file(os.path.join(self.path, 'VERSION'),
                    'Trac Environment Version 1\n')
        create_file(os.path.join(self.path, 'README'),
                    'This directory contains a Trac environment.\n'
                    'Visit http://trac.edgewall.org/ for more information.\n')

        # Setup the default configuration
        os.mkdir(os.path.join(self.path, 'conf'))
        create_file(os.path.join(self.path, 'conf', 'trac.ini'))
        create_file(os.path.join(self.path, 'conf', 'trac.ini.sample'))
        skip_defaults = options and ('inherit', 'file') in [(section, option) \
                for (section, option, value) in options]
        self.setup_config(load_defaults=not skip_defaults)
        for section, name, value in options:
            self.config.set(section, name, value)
        self.config.save()
        self.config.parse_if_needed() # Full reload to get 'inherit' working

        # Create the database
        DatabaseManager(self).init_db()

    def get_version(self, db=None, initial=False):
        """Return the current version of the database.
        If the optional argument `initial` is set to `True`, the version
        of the database used at the time of creation will be returned.

        In practice, for database created before 0.11, this will return `False`
        which is "older" than any db version number.

        :since 0.11:
        """
        if not db:
            db = self.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT value FROM system "
                       "WHERE name='%sdatabase_version'" %
                       (initial and 'initial_' or ''))
        row = cursor.fetchone()
        return row and int(row[0])

    def setup_config(self, load_defaults=False):
        """Load the configuration file."""
        self.config = Configuration(os.path.join(self.path, 'conf', 'trac.ini'))
        if load_defaults:
            for section, default_options in self.config.defaults().items():
                for name, value in default_options.items():
                    if self.config.parent and name in self.config.parent[section]:
                        value = None
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
        format = self.log_format
        if format:
            format = format.replace('$(', '%(') \
                     .replace('%(path)s', self.path) \
                     .replace('%(basename)s', os.path.basename(self.path)) \
                     .replace('%(project)s', self.project_name)
        self.log = logger_factory(logtype, logfile, self.log_level, self.path,
                                  format=format)

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
        return DatabaseManager(self).backup(dest)

    def needs_upgrade(self):
        """Return whether the environment needs to be upgraded."""
        db = self.get_db_cnx()
        for participant in self.setup_participants:
            if participant.environment_needs_upgrade(db):
                self.log.warning('Component %s requires environmet upgrade',
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
        self.shutdown(except_logging=True)

        return True

    def _get_href(self):
        if not self._href:
            self._href = Href(urlsplit(self.abs_href.base)[2])
        return self._href
    href = property(_get_href, 'The application root path')

    def _get_abs_href(self):
        if not self._abs_href:
            if not self.base_url:
                self.log.warn('base_url option not set in configuration, '
                              'generated links may be incorrect')
                self._abs_href = Href('')
            else:
                self._abs_href = Href(self.base_url)
        return self._abs_href
    abs_href = property(_get_abs_href, 'The application URL')


class EnvironmentSetup(Component):
    implements(IEnvironmentSetupParticipant)

    # IEnvironmentSetupParticipant methods

    def environment_created(self):
        """Insert default data into the database."""
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        for table, cols, vals in db_default.get_data(db):
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
            raise TracError(_('Database newer than Trac version'))
        self.log.info("Database version is %d, current is %d",
                      dbver, db_default.db_version)
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
                raise TracError(_('No upgrade module for version %(num)i '
                                  '(%(version)s.py)', num=i, version=name))
            script.do_upgrade(self.env, i, cursor)
        cursor.execute("UPDATE system SET value=%s WHERE "
                       "name='database_version'", (db_default.db_version,))
        self.log.info('Upgraded database version from %d to %d',
                      dbver, db_default.db_version)
        self._update_sample_config()

    # Internal methods

    def _update_sample_config(self):
        filename = os.path.join(self.env.path, 'conf', 'trac.ini.sample')
        if not os.path.isfile(filename):
            return
        config = Configuration(filename)
        for section, default_options in config.defaults().iteritems():
            for name, value in default_options.iteritems():
                config.set(section, name, value)
        try:
            config.save()
            self.log.info('Wrote sample configuration file with the new '
                          'settings and their default values: %s',
                          filename)
        except IOError, e:
            self.log.warn('Couldn\'t write sample configuration file (%s)', e,
                          exc_info=True)


env_cache = {}
env_cache_lock = threading.Lock()

def open_environment(env_path=None, use_cache=False):
    """Open an existing environment object, and verify that the database is up
    to date.

    @param env_path: absolute path to the environment directory; if ommitted,
                     the value of the `TRAC_ENV` environment variable is used
    @param use_cache: whether the environment should be cached for subsequent
                      invocations of this function
    @return: the `Environment` object
    """
    global env_cache, env_cache_lock

    if not env_path:
        env_path = os.getenv('TRAC_ENV')
    if not env_path:
        raise TracError(_('Missing environment variable "TRAC_ENV". '
                          'Trac requires this variable to point to a valid '
                          'Trac environment.'))

    env_path = os.path.normcase(os.path.normpath(env_path))
    if use_cache:
        env_cache_lock.acquire()
        try:
            env = env_cache.get(env_path)
            if env and env.config.parse_if_needed():
                # The environment configuration has changed, so shut it down
                # and remove it from the cache so that it gets reinitialized
                env.log.info('Reloading environment due to configuration '
                             'change')
                env.shutdown()
                del env_cache[env_path]
                env = None
            if env is None:
                env = env_cache.setdefault(env_path, open_environment(env_path))
        finally:
            env_cache_lock.release()
    else:
        env = Environment(env_path)
        needs_upgrade = False
        try:
            needs_upgrade = env.needs_upgrade()
        except Exception, e: # e.g. no database connection
            env.log.error("Exception caught while checking for upgrade: %s",
                          exception_to_unicode(e, traceback=True))
        if needs_upgrade:
            raise TracError(_('The Trac Environment needs to be upgraded.\n\n'
                              'Run "trac-admin %(path)s upgrade"',
                              path=env_path))

    return env
