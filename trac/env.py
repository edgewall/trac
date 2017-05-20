# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2014 Edgewall Software
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

"""Trac Environment model and related APIs."""

import hashlib
import os.path
import setuptools
import shutil
import sys
from urlparse import urlsplit

from trac import db_default, log
from trac.admin import AdminCommandError, IAdminCommandProvider
from trac.cache import CacheManager, cached
from trac.config import BoolOption, ChoiceOption, ConfigSection, \
                        Configuration, Option, PathOption
from trac.core import Component, ComponentManager, implements, Interface, \
                      ExtensionPoint, TracBaseError, TracError
from trac.db.api import (DatabaseManager, QueryContextManager,
                         TransactionContextManager, with_transaction)
from trac.loader import load_components
from trac.log import logger_handler_factory
from trac.util import arity, as_bool, copytree, create_file, get_pkginfo, \
                      is_path_below, lazy, makedirs, read_file
from trac.util.concurrency import threading
from trac.util.text import exception_to_unicode, path_to_unicode, printerr, \
                           printout
from trac.util.translation import _, N_
from trac.web.href import Href

__all__ = ['Environment', 'IEnvironmentSetupParticipant', 'open_environment']


# Content of the VERSION file in the environment
_VERSION = 'Trac Environment Version 1'


class ISystemInfoProvider(Interface):
    """Provider of system information, displayed in the "About Trac"
    page and in internal error reports.
    """
    def get_system_info():
        """Yield a sequence of `(name, version)` tuples describing the
        name and version information of external packages used by a
        component.
        """


class IEnvironmentSetupParticipant(Interface):
    """Extension point interface for components that need to participate in
    the creation and upgrading of Trac environments, for example to create
    additional database tables.

    Please note that `IEnvironmentSetupParticipant` instances are called in
    arbitrary order. If your upgrades must be ordered consistently, please
    implement the ordering in a single `IEnvironmentSetupParticipant`. See
    the database upgrade infrastructure in Trac core for an example.
    """

    def environment_created():
        """Called when a new Trac environment is created."""

    def environment_needs_upgrade(db=None):
        """Called when Trac checks whether the environment needs to be
        upgraded.

        Should return `True` if this participant needs an upgrade to
        be performed, `False` otherwise.

        :since 1.1.2: the `db` parameter is deprecated and will be removed
                      in Trac 1.3.1. A database connection should instead be
                      obtained using a context manager.
        """

    def upgrade_environment(db=None):
        """Actually perform an environment upgrade.

        Implementations of this method don't need to commit any
        database transactions. This is done implicitly for each
        participant if the upgrade succeeds without an error being
        raised.

        However, if the `upgrade_environment` consists of small,
        restartable, steps of upgrade, it can decide to commit on its
        own after each successful step.

        :since 1.1.2: the `db` parameter is deprecated and will be removed
                      in Trac 1.3.1. A database connection should instead be
                      obtained using a context manager.
        """


class BackupError(TracBaseError, RuntimeError):
    """Exception raised during an upgrade when the DB backup fails."""


class Environment(Component, ComponentManager):
    """Trac environment manager.

    Trac stores project information in a Trac environment. It consists
    of a directory structure containing among other things:

    * a configuration file,
    * project-specific templates and plugins,
    * the wiki and ticket attachments files,
    * the SQLite database file (stores tickets, wiki pages...)
      in case the database backend is sqlite

    """

    implements(ISystemInfoProvider)

    required = True

    system_info_providers = ExtensionPoint(ISystemInfoProvider)
    setup_participants = ExtensionPoint(IEnvironmentSetupParticipant)

    components_section = ConfigSection('components',
        """This section is used to enable or disable components
        provided by plugins, as well as by Trac itself. The component
        to enable/disable is specified via the name of the
        option. Whether its enabled is determined by the option value;
        setting the value to `enabled` or `on` will enable the
        component, any other value (typically `disabled` or `off`)
        will disable the component.

        The option name is either the fully qualified name of the
        components or the module/package prefix of the component. The
        former enables/disables a specific component, while the latter
        enables/disables any component in the specified
        package/module.

        Consider the following configuration snippet:
        {{{
        [components]
        trac.ticket.report.ReportModule = disabled
        acct_mgr.* = enabled
        }}}

        The first option tells Trac to disable the
        [wiki:TracReports report module].
        The second option instructs Trac to enable all components in
        the `acct_mgr` package. Note that the trailing wildcard is
        required for module/package matching.

        To view the list of active components, go to the ''Plugins''
        page on ''About Trac'' (requires `CONFIG_VIEW`
        [wiki:TracPermissions permissions]).

        See also: TracPlugins
        """)

    shared_plugins_dir = PathOption('inherit', 'plugins_dir', '',
        """Path to the //shared plugins directory//.

        Plugins in that directory are loaded in addition to those in
        the directory of the environment `plugins`, with this one
        taking precedence.
        """)

    base_url = Option('trac', 'base_url', '',
        """Reference URL for the Trac deployment.

        This is the base URL that will be used when producing
        documents that will be used outside of the web browsing
        context, like for example when inserting URLs pointing to Trac
        resources in notification e-mails.""")

    base_url_for_redirect = BoolOption('trac', 'use_base_url_for_redirect',
                                        False,
        """Optionally use `[trac] base_url` for redirects.

        In some configurations, usually involving running Trac behind
        a HTTP proxy, Trac can't automatically reconstruct the URL
        that is used to access it. You may need to use this option to
        force Trac to use the `base_url` setting also for
        redirects. This introduces the obvious limitation that this
        environment will only be usable when accessible from that URL,
        as redirects are frequently used.
        """)

    secure_cookies = BoolOption('trac', 'secure_cookies', False,
        """Restrict cookies to HTTPS connections.

        When true, set the `secure` flag on all cookies so that they
        are only sent to the server on HTTPS connections. Use this if
        your Trac instance is only accessible through HTTPS.
        """)

    project_name = Option('project', 'name', 'My Project',
        """Name of the project.""")

    project_description = Option('project', 'descr', 'My example project',
        """Short description of the project.""")

    project_url = Option('project', 'url', '',
        """URL of the main project web site, usually the website in
        which the `base_url` resides. This is used in notification
        e-mails.""")

    project_admin = Option('project', 'admin', '',
        """E-Mail address of the project's administrator.""")

    project_admin_trac_url = Option('project', 'admin_trac_url', '.',
        """Base URL of a Trac instance where errors in this Trac
        should be reported.

        This can be an absolute or relative URL, or '.' to reference
        this Trac instance. An empty value will disable the reporting
        buttons.
        """)

    project_footer = Option('project', 'footer',
                            N_('Visit the Trac open source project at<br />'
                               '<a href="http://trac.edgewall.org/">'
                               'http://trac.edgewall.org/</a>'),
        """Page footer text (right-aligned).""")

    project_icon = Option('project', 'icon', 'common/trac.ico',
        """URL of the icon of the project.""")

    log_type = ChoiceOption('logging', 'log_type',
                            log.LOG_TYPES + log.LOG_TYPE_ALIASES,
        """Logging facility to use.

        Should be one of (`none`, `file`, `stderr`, `syslog`, `winlog`).""",
        case_sensitive=False)

    log_file = Option('logging', 'log_file', 'trac.log',
        """If `log_type` is `file`, this should be a path to the
        log-file.  Relative paths are resolved relative to the `log`
        directory of the environment.""")

    log_level = ChoiceOption('logging', 'log_level',
                             tuple(reversed(log.LOG_LEVELS)) +
                             log.LOG_LEVEL_ALIASES,
        """Level of verbosity in log.

        Should be one of (`CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG`).
        """, case_sensitive=False)

    log_format = Option('logging', 'log_format', None,
        """Custom logging format.

        If nothing is set, the following will be used:

        `Trac[$(module)s] $(levelname)s: $(message)s`

        In addition to regular key names supported by the
        [http://docs.python.org/library/logging.html Python logger library]
        one could use:

        - `$(path)s`     the path for the current environment
        - `$(basename)s` the last path component of the current environment
        - `$(project)s`  the project name

        Note the usage of `$(...)s` instead of `%(...)s` as the latter form
        would be interpreted by the !ConfigParser itself.

        Example:
        `($(thread)d) Trac[$(basename)s:$(module)s] $(levelname)s: $(message)s`
        """)

    def __init__(self, path, create=False, options=[]):
        """Initialize the Trac environment.

        :param path:   the absolute path to the Trac environment
        :param create: if `True`, the environment is created and
                       populated with default data; otherwise, the
                       environment is expected to already exist.
        :param options: A list of `(section, name, value)` tuples that
                        define configuration options
        """
        ComponentManager.__init__(self)

        self.path = path
        self.log = None
        self.config = None
        self._log_handler = None
        # System info should be provided through ISystemInfoProvider rather
        # than appending to systeminfo, which may be a private in a future
        # release.
        self.systeminfo = []

        if create:
            self.create(options)
            for setup_participant in self.setup_participants:
                setup_participant.environment_created()
        else:
            self.verify()
            self.setup_config()

    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, self.path)

    @lazy
    def name(self):
        """The environment name.

        :since: 1.2
        """
        return os.path.basename(self.path)

    @property
    def env(self):
        """Property returning the `Environment` object, which is often
        required for functions and methods that take a `Component` instance.
        """
        # The cached decorator requires the object have an `env` attribute.
        return self

    def get_systeminfo(self):
        """Return a list of `(name, version)` tuples describing the name
        and version information of external packages used by Trac and plugins.
        """
        info = self.systeminfo[:]
        for provider in self.system_info_providers:
            info.extend(provider.get_system_info() or [])
        return sorted(set(info),
                      key=lambda (name, ver): (name != 'Trac', name.lower()))

    # ISystemInfoProvider methods

    def get_system_info(self):
        yield 'Trac', self.trac_version
        yield 'Python', sys.version
        yield 'setuptools', setuptools.__version__
        from trac.util.datefmt import pytz
        if pytz is not None:
            yield 'pytz', pytz.__version__
        if hasattr(self, 'webfrontend_version'):
            yield self.webfrontend, self.webfrontend_version

    def component_activated(self, component):
        """Initialize additional member variables for components.

        Every component activated through the `Environment` object
        gets three member variables: `env` (the environment object),
        `config` (the environment configuration) and `log` (a logger
        object)."""
        component.env = self
        component.config = self.config
        component.log = self.log

    def _component_name(self, name_or_class):
        name = name_or_class
        if not isinstance(name_or_class, basestring):
            name = name_or_class.__module__ + '.' + name_or_class.__name__
        return name.lower()

    @lazy
    def _component_rules(self):
        _rules = {}
        for name, value in self.components_section.options():
            name = name.rstrip('.*').lower()
            _rules[name] = as_bool(value)
        return _rules

    def is_component_enabled(self, cls):
        """Implemented to only allow activation of components that are
        not disabled in the configuration.

        This is called by the `ComponentManager` base class when a
        component is about to be activated. If this method returns
        `False`, the component does not get activated. If it returns
        `None`, the component only gets activated if it is located in
        the `plugins` directory of the environment.
        """
        component_name = self._component_name(cls)

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

        # By default, all components in the trac package except
        # in trac.test or trac.tests are enabled
        return component_name.startswith('trac.') and \
               not component_name.startswith('trac.test.') and \
               not component_name.startswith('trac.tests.') or None

    def enable_component(self, cls):
        """Enable a component or module."""
        self._component_rules[self._component_name(cls)] = True
        super(Environment, self).enable_component(cls)

    def verify(self):
        """Verify that the provided path points to a valid Trac environment
        directory."""
        try:
            tag = read_file(os.path.join(self.path, 'VERSION')).splitlines()[0]
            if tag != _VERSION:
                raise Exception(_("Unknown Trac environment type '%(type)s'",
                                  type=tag))
        except Exception as e:
            raise TracError(_("No Trac environment found at %(path)s\n"
                              "%(e)s", path=self.path, e=e))

    @lazy
    def db_exc(self):
        """Return an object (typically a module) containing all the
        backend-specific exception types as attributes, named
        according to the Python Database API
        (http://www.python.org/dev/peps/pep-0249/).

        To catch a database exception, use the following pattern::

            try:
                with env.db_transaction as db:
                    ...
            except env.db_exc.IntegrityError as e:
                ...
        """
        return DatabaseManager(self).get_exceptions()

    def with_transaction(self, db=None):
        """Decorator for transaction functions.

        :deprecated: Use the query and transaction context managers instead.
                     Will be removed in Trac 1.3.1.
        """
        return with_transaction(self, db)

    def get_read_db(self):
        """Return a database connection for read purposes.

        See `trac.db.api.get_read_db` for detailed documentation.

        :deprecated: Use :meth:`db_query` instead.
                     Will be removed in Trac 1.3.1.
        """
        return DatabaseManager(self).get_connection(readonly=True)

    @property
    def db_query(self):
        """Return a context manager
        (`~trac.db.api.QueryContextManager`) which can be used to
        obtain a read-only database connection.

        Example::

            with env.db_query as db:
                cursor = db.cursor()
                cursor.execute("SELECT ...")
                for row in cursor.fetchall():
                    ...

        Note that a connection retrieved this way can be "called"
        directly in order to execute a query::

            with env.db_query as db:
                for row in db("SELECT ..."):
                    ...

        :warning: after a `with env.db_query as db` block, though the
          `db` variable is still defined, you shouldn't use it as it
          might have been closed when exiting the context, if this
          context was the outermost context (`db_query` or
          `db_transaction`).

        If you don't need to manipulate the connection itself, this
        can even be simplified to::

            for row in env.db_query("SELECT ..."):
                ...

        """
        return QueryContextManager(self)

    @property
    def db_transaction(self):
        """Return a context manager
        (`~trac.db.api.TransactionContextManager`) which can be used
        to obtain a writable database connection.

        Example::

            with env.db_transaction as db:
                cursor = db.cursor()
                cursor.execute("UPDATE ...")

        Upon successful exit of the context, the context manager will
        commit the transaction. In case of nested contexts, only the
        outermost context performs a commit. However, should an
        exception happen, any context manager will perform a rollback.
        You should *not* call `commit()` yourself within such block,
        as this will force a commit even if that transaction is part
        of a larger transaction.

        Like for its read-only counterpart, you can directly execute a
        DML query on the `db`::

            with env.db_transaction as db:
                db("UPDATE ...")

        :warning: after a `with env.db_transaction` as db` block,
          though the `db` variable is still available, you shouldn't
          use it as it might have been closed when exiting the
          context, if this context was the outermost context
          (`db_query` or `db_transaction`).

        If you don't need to manipulate the connection itself, this
        can also be simplified to::

            env.db_transaction("UPDATE ...")

        """
        return TransactionContextManager(self)

    def shutdown(self, tid=None):
        """Close the environment."""
        from trac.versioncontrol.api import RepositoryManager
        RepositoryManager(self).shutdown(tid)
        DatabaseManager(self).shutdown(tid)
        if tid is None and self._log_handler is not None:
            self.log.removeHandler(self._log_handler)
            self._log_handler.flush()
            self._log_handler.close()
            del self._log_handler

    def get_repository(self, reponame=None):
        """Return the version control repository with the given name,
        or the default repository if `None`.

        The standard way of retrieving repositories is to use the
        methods of `RepositoryManager`. This method is retained here
        for backward compatibility.

        :param reponame: the name of the repository

        :since 1.2: deprecated and will be removed in 1.3.1
        """
        from trac.versioncontrol.api import RepositoryManager
        return RepositoryManager(self).get_repository(reponame)

    def create(self, options=[]):
        """Create the basic directory structure of the environment,
        initialize the database and populate the configuration file
        with default values.

        If options contains ('inherit', 'file'), default values will
        not be loaded; they are expected to be provided by that file
        or other options.
        """
        # Create the directory structure
        if not os.path.exists(self.path):
            os.mkdir(self.path)
        os.mkdir(self.log_dir)
        os.mkdir(self.htdocs_dir)
        os.mkdir(self.plugins_dir)

        # Create a few files
        create_file(os.path.join(self.path, 'VERSION'), _VERSION + '\n')
        create_file(os.path.join(self.path, 'README'),
                    'This directory contains a Trac environment.\n'
                    'Visit http://trac.edgewall.org/ for more information.\n')

        # Setup the default configuration
        os.mkdir(self.conf_dir)
        create_file(self.config_file_path + '.sample')
        config = Configuration(self.config_file_path)
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

    @lazy
    def database_version(self):
        """Returns the current version of the database.

        :since 1.0.2:
        """
        return DatabaseManager(self) \
               .get_database_version('database_version')

    @lazy
    def database_initial_version(self):
        """Returns the version of the database at the time of creation.

        In practice, for database created before 0.11, this will
        return `False` which is "older" than any db version number.

        :since 1.0.2:
        """
        return DatabaseManager(self) \
               .get_database_version('initial_database_version')

    @lazy
    def trac_version(self):
        """Returns the version of Trac.
        :since: 1.2
        """
        from trac import core, __version__
        return get_pkginfo(core).get('version', __version__)

    def get_version(self, initial=False):
        """Return the current version of the database.  If the
        optional argument `initial` is set to `True`, the version of
        the database used at the time of creation will be returned.

        In practice, for database created before 0.11, this will
        return `False` which is "older" than any db version number.

        :since: 0.11

        :since 1.0.2: The lazily-evaluated attributes `database_version` and
                      `database_initial_version` should be used instead. This
                      method will be removed in release 1.3.1.
        """
        dbm = DatabaseManager(self)
        return dbm.get_database_version(
            '{0}database_version'.format('initial_' if initial else ''))

    def setup_config(self):
        """Load the configuration file."""
        self.config = Configuration(self.config_file_path,
                                    {'envname': self.name})
        if not self.config.exists:
            raise TracError(_("The configuration file is not found at "
                              "%(path)s", path=self.config_file_path))
        self.setup_log()
        plugins_dir = self.shared_plugins_dir
        load_components(self, plugins_dir and (plugins_dir,))

    @lazy
    def config_file_path(self):
        """Path of the trac.ini file."""
        return os.path.join(self.conf_dir, 'trac.ini')

    def _get_path_to_dir(self, dir):
        path = os.path.join(self.path, dir)
        return os.path.normcase(os.path.realpath(path))

    @lazy
    def conf_dir(self):
        """Absolute path to the conf directory.

        :since: 1.0.11
        """
        return self._get_path_to_dir('conf')

    @lazy
    def htdocs_dir(self):
        """Absolute path to the htdocs directory.

        :since: 1.0.11
        """
        return self._get_path_to_dir('htdocs')

    def get_htdocs_dir(self):
        """Return absolute path to the htdocs directory.

        :since 1.0.11: Deprecated and will be removed in 1.3.1. Use the
                       `htdocs_dir` property instead.
        """
        return self._get_path_to_dir('htdocs')

    @lazy
    def log_dir(self):
        """Absolute path to the log directory.

        :since: 1.0.11
        """
        return self._get_path_to_dir('log')

    def get_log_dir(self):
        """Return absolute path to the log directory.

        :since 1.0.11: Deprecated and will be removed in 1.3.1. Use the
                       `log_dir` property instead.
        """
        return self._get_path_to_dir('log')

    @lazy
    def plugins_dir(self):
        """Absolute path to the plugins directory.

        :since: 1.0.11
        """
        return self._get_path_to_dir('plugins')

    @lazy
    def templates_dir(self):
        """Absolute path to the templates directory.

        :since: 1.0.11
        """
        return self._get_path_to_dir('templates')

    def get_templates_dir(self):
        """Return absolute path to the templates directory.

        :since 1.0.11: Deprecated and will be removed in 1.3.1. Use the
                       `templates_dir` property instead.
        """
        return self._get_path_to_dir('templates')

    def setup_log(self):
        """Initialize the logging sub-system."""
        logtype = self.log_type
        logfile = self.log_file
        if logtype == 'file' and not os.path.isabs(logfile):
            logfile = os.path.join(self.log_dir, logfile)
        self.log, self._log_handler = \
            self.create_logger(self.log_type, logfile, self.log_level,
                               self.log_format)
        self.log.addHandler(self._log_handler)
        self.log.info('-' * 32 + ' environment startup [Trac %s] ' + '-' * 32,
                      self.trac_version)

    def create_logger(self, log_type, log_file, log_level, log_format):
        log_id = 'Trac.%s' % hashlib.sha1(self.path).hexdigest()
        if log_format:
            log_format = log_format.replace('$(', '%(') \
                                   .replace('%(path)s', self.path) \
                                   .replace('%(basename)s', self.name) \
                                   .replace('%(project)s', self.project_name)
        return logger_handler_factory(log_type, log_file, log_level, log_id,
                                      format=log_format)

    def get_known_users(self, as_dict=False):
        """Returns information about all known users, i.e. users that
        have logged in to this Trac environment and possibly set their
        name and email.

        By default this function returns a iterator that yields one
        tuple for every user, of the form (username, name, email),
        ordered alpha-numerically by username. When `as_dict` is `True`
        the function returns a dictionary mapping username to a
        (name, email) tuple.

        :since 1.2: the `as_dict` parameter is available.
        """
        return self._known_users_dict if as_dict else iter(self._known_users)

    @cached
    def _known_users(self):
        return self.db_query("""
                SELECT DISTINCT s.sid, n.value, e.value
                FROM session AS s
                 LEFT JOIN session_attribute AS n ON (n.sid=s.sid
                  AND n.authenticated=1 AND n.name = 'name')
                 LEFT JOIN session_attribute AS e ON (e.sid=s.sid
                  AND e.authenticated=1 AND e.name = 'email')
                WHERE s.authenticated=1 ORDER BY s.sid
        """)

    @cached
    def _known_users_dict(self):
        return dict([(u[0], (u[1], u[2])) for u in self._known_users])

    def invalidate_known_users_cache(self):
        """Clear the known_users cache."""
        del self._known_users
        del self._known_users_dict

    def backup(self, dest=None):
        """Create a backup of the database.

        :param dest: Destination file; if not specified, the backup is
                     stored in a file called db_name.trac_version.bak
        """
        return DatabaseManager(self).backup(dest)

    def needs_upgrade(self):
        """Return whether the environment needs to be upgraded."""
        for participant in self.setup_participants:
            args = ()
            with self.db_query as db:
                if arity(participant.environment_needs_upgrade) == 1:
                    args = (db,)
                if participant.environment_needs_upgrade(*args):
                    self.log.warn("Component %s requires environment upgrade",
                                  participant)
                    return True
        return False

    def upgrade(self, backup=False, backup_dest=None):
        """Upgrade database.

        :param backup: whether or not to backup before upgrading
        :param backup_dest: name of the backup file
        :return: whether the upgrade was performed
        """
        upgraders = []
        for participant in self.setup_participants:
            args = ()
            with self.db_query as db:
                if arity(participant.environment_needs_upgrade) == 1:
                    args = (db,)
                if participant.environment_needs_upgrade(*args):
                    upgraders.append(participant)
        if not upgraders:
            return

        if backup:
            try:
                self.backup(backup_dest)
            except Exception as e:
                raise BackupError(e)

        for participant in upgraders:
            self.log.info("%s.%s upgrading...", participant.__module__,
                          participant.__class__.__name__)
            args = ()
            with self.db_transaction as db:
                if arity(participant.upgrade_environment) == 1:
                    args = (db,)
                participant.upgrade_environment(*args)
            # Database schema may have changed, so close all connections
            dbm = DatabaseManager(self)
            if dbm.connection_uri != 'sqlite::memory:':
                dbm.shutdown()
        del self.database_version
        return True

    @lazy
    def href(self):
        """The application root path"""
        return Href(urlsplit(self.abs_href.base).path)

    @lazy
    def abs_href(self):
        """The application URL"""
        if not self.base_url:
            self.log.warn("base_url option not set in configuration, "
                          "generated links may be incorrect")
        return Href(self.base_url)


class EnvironmentSetup(Component):
    """Manage automatic environment upgrades."""

    required = True

    implements(IEnvironmentSetupParticipant)

    # IEnvironmentSetupParticipant methods

    def environment_created(self):
        """Insert default data into the database."""
        DatabaseManager(self.env).insert_into_tables(db_default.get_data)
        self._update_sample_config()

    def environment_needs_upgrade(self):
        return DatabaseManager(self.env).needs_upgrade(db_default.db_version)

    def upgrade_environment(self):
        DatabaseManager(self.env).upgrade(db_default.db_version,
                                          pkg='trac.upgrades')
        self._update_sample_config()

    # Internal methods

    def _update_sample_config(self):
        filename = os.path.join(self.env.config_file_path + '.sample')
        if not os.path.isfile(filename):
            return
        config = Configuration(filename)
        for (section, name), option in Option.get_registry().iteritems():
            config.set(section, name, option.dumps(option.default))
        try:
            config.save()
            self.log.info("Wrote sample configuration file with the new "
                          "settings and their default values: %s",
                          filename)
        except IOError as e:
            self.log.warn("Couldn't write sample configuration file (%s)", e,
                          exc_info=True)


env_cache = {}
env_cache_lock = threading.Lock()


def open_environment(env_path=None, use_cache=False):
    """Open an existing environment object, and verify that the database is up
    to date.

    :param env_path: absolute path to the environment directory; if
                     omitted, the value of the `TRAC_ENV` environment
                     variable is used
    :param use_cache: whether the environment should be cached for
                      subsequent invocations of this function
    :return: the `Environment` object
    """
    if not env_path:
        env_path = os.getenv('TRAC_ENV')
    if not env_path:
        raise TracError(_('Missing environment variable "TRAC_ENV". '
                          'Trac requires this variable to point to a valid '
                          'Trac environment.'))

    env_path = os.path.normcase(os.path.normpath(env_path))
    if use_cache:
        with env_cache_lock:
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
                env = env_cache.setdefault(env_path,
                                           open_environment(env_path))
            else:
                CacheManager(env).reset_metadata()
    else:
        env = Environment(env_path)
        needs_upgrade = False
        try:
            needs_upgrade = env.needs_upgrade()
        except Exception as e:  # e.g. no database connection
            env.log.error("Exception caught while checking for upgrade: %s",
                          exception_to_unicode(e, traceback=True))
        if needs_upgrade:
            raise TracError(_('The Trac Environment needs to be upgraded.\n\n'
                              'Run \'trac-admin "%(path)s" upgrade\'',
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
        yield ('hotcopy', '<backupdir> [--no-database]',
               """Make a hot backup copy of an environment

               The database is backed up to the 'db' directory of the
               destination, unless the --no-database option is
               specified.
               """,
               None, self._do_hotcopy)
        yield ('upgrade', '[--no-backup]',
               """Upgrade database to current version

               The database is backed up to the directory specified by [trac]
               backup_dir (the default is 'db'), unless the --no-backup
               option is specified. The shorthand alias -b can also be used
               to specify --no-backup.
               """,
               None, self._do_upgrade)

    def _do_deploy(self, dest):
        from trac.web.chrome import Chrome

        target = os.path.normpath(dest)
        chrome_target = os.path.join(target, 'htdocs')
        script_target = os.path.join(target, 'cgi-bin')

        # Check source and destination to avoid recursively copying files
        for provider in Chrome(self.env).template_providers:
            paths = list(provider.get_htdocs_dirs() or [])
            if not paths:
                continue
            for key, root in paths:
                if not root:
                    continue
                source = os.path.normpath(root)
                dest = os.path.join(chrome_target, key)
                if os.path.exists(source) and is_path_below(dest, source):
                    raise AdminCommandError(
                        _("Resources cannot be deployed to a target "
                          "directory that is equal to or below the source "
                          "directory '%(source)s'.\n\nPlease choose a "
                          "different target directory and try again.",
                          source=source))

        # Copy static content
        makedirs(target, overwrite=True)
        makedirs(chrome_target, overwrite=True)
        printout(_("Copying resources from:"))
        for provider in Chrome(self.env).template_providers:
            paths = list(provider.get_htdocs_dirs() or [])
            if not paths:
                continue
            printout('  %s.%s' % (provider.__module__,
                                  provider.__class__.__name__))
            for key, root in paths:
                if not root:
                    continue
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
            with open(dest, 'w') as out:
                stream.render('text', out=out, encoding='utf-8')

    def _do_hotcopy(self, dest, no_db=None):
        if no_db not in (None, '--no-database'):
            raise AdminCommandError(_("Invalid argument '%(arg)s'", arg=no_db),
                                    show_usage=True)

        if os.path.exists(dest):
            raise TracError(_("hotcopy can't overwrite existing '%(dest)s'",
                              dest=path_to_unicode(dest)))

        # Bogus statement to lock the database while copying files
        with self.env.db_transaction as db:
            db("UPDATE system SET name=NULL WHERE name IS NULL")

            printout(_("Hotcopying %(src)s to %(dst)s ...",
                       src=path_to_unicode(self.env.path),
                       dst=path_to_unicode(dest)))
            db_str = self.env.config.get('trac', 'database')
            prefix, db_path = db_str.split(':', 1)
            skip = []

            if prefix == 'sqlite':
                db_path = os.path.join(self.env.path,
                                       os.path.normpath(db_path))
                # don't copy the journal (also, this would fail on Windows)
                skip = [db_path + '-journal', db_path + '-stmtjrnl',
                        db_path + '-shm', db_path + '-wal']
                if no_db:
                    skip.append(db_path)

            try:
                copytree(self.env.path, dest, symlinks=1, skip=skip)
                retval = 0
            except shutil.Error as e:
                retval = 1
                printerr(_("The following errors happened while copying "
                           "the environment:"))
                for (src, dst, err) in e.args[0]:
                    if src in err:
                        printerr('  %s' % err)
                    else:
                        printerr("  %s: '%s'" % (err, path_to_unicode(src)))

            # db backup for non-sqlite
            if prefix != 'sqlite' and not no_db:
                printout(_("Backing up database ..."))
                sql_backup = os.path.join(dest, 'db',
                                          '%s-db-backup.sql' % prefix)
                self.env.backup(sql_backup)

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
        except BackupError as e:
            printerr(_("The pre-upgrade backup failed.\nUse '--no-backup' to "
                       "upgrade without doing a backup.\n"))
            raise e.args[0]
        except Exception:
            printerr(_("The upgrade failed. Please fix the issue and try "
                       "again.\n"))
            raise

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
                except OSError as e:
                    printerr(_("Error while removing wiki-macros: %(err)s\n"
                               "Trac doesn't load plugins from wiki-macros "
                               "anymore. Please remove it by hand.",
                               err=exception_to_unicode(e)))

        printout(_('Upgrade done.\n\n'
                   'You may want to upgrade the Trac documentation now by '
                   'running:\n\n  trac-admin "%(path)s" wiki upgrade',
                   path=path_to_unicode(self.env.path)))
