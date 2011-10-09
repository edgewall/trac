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

import os.path
import setuptools
import sys
from urlparse import urlsplit

from trac import db_default
from trac.admin import AdminCommandError, IAdminCommandProvider
from trac.cache import CacheManager
from trac.config import *
from trac.core import Component, ComponentManager, implements, Interface, \
                      ExtensionPoint, TracError
from trac.db.api import DatabaseManager, get_read_db, with_transaction
from trac.util import copytree, create_file, get_pkginfo, makedirs
from trac.util.compat import any
from trac.util.concurrency import threading
from trac.util.text import exception_to_unicode, path_to_unicode, printerr, \
                           printout
from trac.util.translation import _, N_
from trac.versioncontrol import RepositoryManager
from trac.web.href import Href

__all__ = ['Environment', 'IEnvironmentSetupParticipant', 'open_environment']


class ISystemInfoProvider(Interface):
    """Provider of system information, displayed in the "About Trac" page and
    in internal error reports.
    """
    def get_system_info():
        """Yield a sequence of `(name, version)` tuples describing the name and
        version information of external packages used by a component.
        """


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
        
        Implementations of this method don't need to commit any database
        transactions. This is done implicitly for each participant
        if the upgrade succeeds without an error being raised.

        However, if the `upgrade_environment` consists of small, restartable,
        steps of upgrade, it can decide to commit on its own after each
        successful step.
        """


class Environment(Component, ComponentManager):
    """Trac environment manager.

    Trac stores project information in a Trac environment. It consists of a
    directory structure containing among other things:
     * a configuration file
     * an SQLite database (stores tickets, wiki pages...)
     * project-specific templates and plugins
     * wiki and ticket attachments
    """
    implements(ISystemInfoProvider)

    required = True
    
    system_info_providers = ExtensionPoint(ISystemInfoProvider)
    setup_participants = ExtensionPoint(IEnvironmentSetupParticipant)

    shared_plugins_dir = PathOption('inherit', 'plugins_dir', '',
        """Path to the //shared plugins directory//.
        
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
        the `base_url` resides. This is used in notification e-mails.""")

    project_admin = Option('project', 'admin', '',
        """E-Mail address of the project's administrator.""")

    project_admin_trac_url = Option('project', 'admin_trac_url', '.',
        """Base URL of a Trac instance where errors in this Trac should be
        reported.
        
        This can be an absolute or relative URL, or '.' to reference this
        Trac instance. An empty value will disable the reporting buttons.
        (''since 0.11.3'')""")

    project_footer = Option('project', 'footer',
                            N_('Visit the Trac open source project at<br />'
                               '<a href="http://trac.edgewall.org/">'
                               'http://trac.edgewall.org/</a>'),
        """Page footer text (right-aligned).""")

    project_icon = Option('project', 'icon', 'common/trac.ico',
        """URL of the icon of the project.""")

    log_type = Option('logging', 'log_type', 'none',
        """Logging facility to use.
        
        Should be one of (`none`, `file`, `stderr`, `syslog`, `winlog`).""")

    log_file = Option('logging', 'log_file', 'trac.log',
        """If `log_type` is `file`, this should be a path to the log-file.
        Relative paths are resolved relative to the `log` directory of the
        environment.""")

    log_level = Option('logging', 'log_level', 'DEBUG',
        """Level of verbosity in log.
        
        Should be one of (`CRITICAL`, `ERROR`, `WARN`, `INFO`, `DEBUG`).""")

    log_format = Option('logging', 'log_format', None,
        """Custom logging format.

        If nothing is set, the following will be used:
        
        Trac[$(module)s] $(levelname)s: $(message)s

        In addition to regular key names supported by the Python logger library
        (see http://docs.python.org/library/logging.html), one could use:
         - $(path)s     the path for the current environment
         - $(basename)s the last path component of the current environment
         - $(project)s  the project name

        Note the usage of `$(...)s` instead of `%(...)s` as the latter form
        would be interpreted by the ConfigParser itself.

        Example:
        `($(thread)d) Trac[$(basename)s:$(module)s] $(levelname)s: $(message)s`

        ''(since 0.10.5)''""")

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
        self.systeminfo = []
        self._href = self._abs_href = None

        if create:
            self.create(options)
        else:
            self.verify()
            self.setup_config()

        if create:
            for setup_participant in self.setup_participants:
                setup_participant.environment_created()

    def get_systeminfo(self):
        """Return a list of `(name, version)` tuples describing the name and
        version information of external packages used by Trac and plugins.
        """
        info = self.systeminfo[:]
        for provider in self.system_info_providers:
            info.extend(provider.get_system_info() or [])
        info.sort(key=lambda (name, version): (name != 'Trac', name.lower()))
        return info

    # ISystemInfoProvider methods

    def get_system_info(self):
        from trac import core, __version__ as VERSION
        yield 'Trac', get_pkginfo(core).get('version', VERSION)
        yield 'Python', sys.version
        yield 'setuptools', setuptools.__version__
        from trac.util.datefmt import pytz
        if pytz is not None:
            yield 'pytz', pytz.__version__
    
    def component_activated(self, component):
        """Initialize additional member variables for components.
        
        Every component activated through the `Environment` object gets three
        member variables: `env` (the environment object), `config` (the
        environment configuration) and `log` (a logger object)."""
        component.env = self
        component.config = self.config
        component.log = self.log

    def _component_name(self, name_or_class):
        name = name_or_class
        if not isinstance(name_or_class, basestring):
            name = name_or_class.__module__ + '.' + name_or_class.__name__
        return name.lower()

    @property
    def _component_rules(self):
        try:
            return self._rules
        except AttributeError:
            self._rules = {}
            for name, value in self.config.options('components'):
                if name.endswith('.*'):
                    name = name[:-2]
                self._rules[name.lower()] = value.lower() in ('enabled', 'on')
            return self._rules
        
    def is_component_enabled(self, cls):
        """Implemented to only allow activation of components that are not
        disabled in the configuration.
        
        This is called by the `ComponentManager` base class when a component is
        about to be activated. If this method returns `False`, the component
        does not get activated. If it returns `None`, the component only gets
        activated if it is located in the `plugins` directory of the
        enironment.
        """
        component_name = self._component_name(cls)

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
        
        rules = self._component_rules
        cname = component_name
        while cname:
            enabled = rules.get(cname)
            if enabled is not None:
                return enabled
            idx = cname.rfind('.')
            if idx < 0:
                break
            cname = cname[:idx]

        # By default, all components in the trac package are enabled
        return component_name.startswith('trac.') or None

    def enable_component(self, cls):
        """Enable a component or module."""
        self._component_rules[self._component_name(cls)] = True

    def verify(self):
        """Verify that the provided path points to a valid Trac environment
        directory."""
        fd = open(os.path.join(self.path, 'VERSION'), 'r')
        try:
            assert fd.read(26) == 'Trac Environment Version 1'
        finally:
            fd.close()

    def get_db_cnx(self):
        """Return a database connection from the connection pool (deprecated)

        Use `with_transaction` for obtaining a writable database connection
        and `get_read_db` for anything else.
        """
        return get_read_db(self)

    def with_transaction(self, db=None):
        """Decorator for transaction functions.

        See `trac.db.api.with_transaction` for detailed documentation."""
        return with_transaction(self, db)

    def get_read_db(self):
        """Return a database connection for read purposes.

        See `trac.db.api.get_read_db` for detailed documentation."""
        return get_read_db(self)

    def shutdown(self, tid=None):
        """Close the environment."""
        RepositoryManager(self).shutdown(tid)
        DatabaseManager(self).shutdown(tid)
        if tid is None:
            self.log.removeHandler(self._log_handler)
            self._log_handler.flush()
            self._log_handler.close()
            del self._log_handler

    def get_repository(self, reponame=None, authname=None):
        """Return the version control repository with the given name, or the
        default repository if `None`.
        
        The standard way of retrieving repositories is to use the methods
        of `RepositoryManager`. This method is retained here for backward
        compatibility.
        
        @param reponame: the name of the repository
        @param authname: the user name for authorization (not used anymore,
                         left here for compatibility with 0.11)
        """
        return RepositoryManager(self).get_repository(reponame)

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
        create_file(os.path.join(self.path, 'conf', 'trac.ini.sample'))
        config = Configuration(os.path.join(self.path, 'conf', 'trac.ini'))
        for section, name, value in options:
            config.set(section, name, value)
        config.save()
        self.setup_config()
        if not any((section, option) == ('inherit', 'file')
                   for section, option, value in options):
            self.config.set_defaults(self)
            self.config.save()

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

    def setup_config(self):
        """Load the configuration file."""
        self.config = Configuration(os.path.join(self.path, 'conf',
                                                 'trac.ini'))
        self.setup_log()
        from trac.loader import load_components
        plugins_dir = self.shared_plugins_dir
        load_components(self, plugins_dir and (plugins_dir,))

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
        from trac.log import logger_handler_factory
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
        self.log, self._log_handler = logger_handler_factory(
            logtype, logfile, self.log_level, self.path, format=format)
        from trac import core, __version__ as VERSION
        self.log.info('-' * 32 + ' environment startup [Trac %s] ' + '-' * 32,
                      get_pkginfo(core).get('version', VERSION))

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
        for username, name, email in cursor:
            yield username, name, email

    def backup(self, dest=None):
        """Create a backup of the database.

        @param dest: Destination file; if not specified, the backup is stored in
                     a file called db_name.trac_version.bak
        """
        return DatabaseManager(self).backup(dest)

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
        
        @param backup: whether or not to backup before upgrading
        @param backup_dest: name of the backup file
        @return: whether the upgrade was performed
        """
        upgraders = []
        db = self.get_read_db()
        for participant in self.setup_participants:
            if participant.environment_needs_upgrade(db):
                upgraders.append(participant)
        if not upgraders:
            return

        if backup:
            self.backup(backup_dest)

        for participant in upgraders:
            self.log.info("%s.%s upgrading...", participant.__module__,
                          participant.__class__.__name__)
            with_transaction(self)(participant.upgrade_environment)
            # Database schema may have changed, so close all connections
            DatabaseManager(self).shutdown()
        return True

    @property
    def href(self):
        """The application root path"""
        if not self._href:
            self._href = Href(urlsplit(self.abs_href.base)[2])
        return self._href

    @property
    def abs_href(self):
        """The application URL"""
        if not self._abs_href:
            if not self.base_url:
                self.log.warn('base_url option not set in configuration, '
                              'generated links may be incorrect')
                self._abs_href = Href('')
            else:
                self._abs_href = Href(self.base_url)
        return self._abs_href


class EnvironmentSetup(Component):
    """Manage automatic environment upgrades."""
    
    required = True

    implements(IEnvironmentSetupParticipant)

    # IEnvironmentSetupParticipant methods

    def environment_created(self):
        """Insert default data into the database."""
        @self.env.with_transaction()
        def do_db_populate(db):
            cursor = db.cursor()
            for table, cols, vals in db_default.get_data(db):
                cursor.executemany("INSERT INTO %s (%s) VALUES (%s)"
                                   % (table, ','.join(cols),
                                      ','.join(['%s' for c in cols])),
                                   vals)
        self._update_sample_config()

    def environment_needs_upgrade(self, db):
        dbver = self.env.get_version(db)
        if dbver == db_default.db_version:
            return False
        elif dbver > db_default.db_version:
            raise TracError(_('Database newer than Trac version'))
        self.log.info("Trac database schema version is %d, should be %d",
                      dbver, db_default.db_version)
        return True

    def upgrade_environment(self, db):
        """Each db version should have its own upgrade module, named
        upgrades/dbN.py, where 'N' is the version number (int).
        """
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
            cursor.execute("""
                UPDATE system SET value=%s WHERE name='database_version'
                """, (i,))
            self.log.info('Upgraded database version from %d to %d', i - 1, i)
            db.commit()
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
            else:
                CacheManager(env).reset_metadata()
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


class EnvironmentAdmin(Component):
    """trac-admin command provider for environment administration."""
    
    implements(IAdminCommandProvider)
    
    # IAdminCommandProvider methods
    
    def get_admin_commands(self):
        yield ('deploy', '<directory>',
               'Extract static resources from Trac and all plugins',
               None, self._do_deploy)
        yield ('hotcopy', '<backupdir>',
               'Make a hot backup copy of an environment',
               None, self._do_hotcopy)
        yield ('upgrade', '',
               'Upgrade database to current version',
               None, self._do_upgrade)
    
    def _do_deploy(self, dest):
        target = os.path.normpath(dest)
        chrome_target = os.path.join(target, 'htdocs')
        script_target = os.path.join(target, 'cgi-bin')

        # Copy static content
        makedirs(target, overwrite=True)
        makedirs(chrome_target, overwrite=True)
        from trac.web.chrome import Chrome
        printout(_("Copying resources from:"))
        for provider in Chrome(self.env).template_providers:
            paths = list(provider.get_htdocs_dirs() or [])
            if not len(paths):
                continue
            printout('  %s.%s' % (provider.__module__, 
                                  provider.__class__.__name__))
            for key, root in paths:
                source = os.path.normpath(root)
                printout('   ', source)
                if os.path.exists(source):
                    dest = os.path.join(chrome_target, key)
                    copytree(source, dest, overwrite=True)

        # Create and copy scripts
        makedirs(script_target, overwrite=True)
        printout(_("Creating scripts."))
        data = {'env': self.env, 'executable': sys.executable}
        for script in ('cgi', 'fcgi', 'wsgi'):
            dest = os.path.join(script_target, 'trac.' + script)
            template = Chrome(self.env).load_template('deploy_trac.' + script,
                                                      'text')
            stream = template.generate(**data)
            out = file(dest, 'w')
            try:
                stream.render('text', out=out, encoding='utf-8')
            finally:
                out.close()
    
    def _do_hotcopy(self, dest):
        if os.path.exists(dest):
            raise TracError(_("hotcopy can't overwrite existing '%(dest)s'",
                              dest=path_to_unicode(dest)))
        import shutil

        # Bogus statement to lock the database while copying files
        cnx = self.env.get_db_cnx()
        cursor = cnx.cursor()
        cursor.execute("UPDATE system SET name=NULL WHERE name IS NULL")

        try:
            printout(_('Hotcopying %(src)s to %(dst)s ...', 
                       src=path_to_unicode(self.env.path),
                       dst=path_to_unicode(dest)))
            db_str = self.env.config.get('trac', 'database')
            prefix, db_path = db_str.split(':', 1)
            if prefix == 'sqlite':
                # don't copy the journal (also, this would fail on Windows)
                db = os.path.join(self.env.path, os.path.normpath(db_path))
                skip = [db + '-journal', db + '-stmtjrnl']
            else:
                skip = []
            try:
                copytree(self.env.path, dest, symlinks=1, skip=skip)
                retval = 0
            except shutil.Error, e:
                retval = 1
                printerr(_('The following errors happened while copying '
                           'the environment:'))
                for (src, dst, err) in e.args[0]:
                    if src in err:
                        printerr('  %s' % err)
                    else:
                        printerr("  %s: '%s'" % (err, path_to_unicode(src)))
        finally:
            # Unlock database
            cnx.rollback()

        printout(_("Hotcopy done."))
        return retval
    
    def _do_upgrade(self, no_backup=None):
        if no_backup not in (None, '-b', '--no-backup'):
            raise AdminCommandError(_("Invalid arguments"), show_usage=True)
        
        if not self.env.needs_upgrade():
            printout(_("Database is up to date, no upgrade necessary."))
            return

        try:
            self.env.upgrade(backup=no_backup is None)
        except TracError, e:
            raise TracError(_("Backup failed: %(msg)s.\nUse '--no-backup' to "
                              "upgrade without doing a backup.",
                              msg=unicode(e)))

        # Remove wiki-macros if it is empty and warn if it isn't
        wiki_macros = os.path.join(self.env.path, 'wiki-macros')
        try:
            entries = os.listdir(wiki_macros)
        except OSError:
            pass
        else:
            if entries:
                printerr(_("Warning: the wiki-macros directory in the "
                           "environment is non-empty, but Trac\n"
                           "doesn't load plugins from there anymore. "
                           "Please remove it by hand."))
            else:
                try:
                    os.rmdir(wiki_macros)
                except OSError, e:
                    printerr(_("Error while removing wiki-macros: %(err)s\n"
                               "Trac doesn't load plugins from wiki-macros "
                               "anymore. Please remove it by hand.",
                               err=exception_to_unicode(e)))
        
        printout(_("Upgrade done.\n\n"
                   "You may want to upgrade the Trac documentation now by "
                   "running:\n\n  trac-admin %(path)s wiki upgrade",
                   path=path_to_unicode(self.env.path)))
