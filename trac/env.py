# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2019 Edgewall Software
# Copyright (C) 2003-2007 Jonas Borgström <jonas@edgewall.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.
#
# Author: Jonas Borgström <jonas@edgewall.com>

"""Trac Environment model and related APIs."""

from contextlib import contextmanager
import hashlib
import os.path
import setuptools
import shutil
import sys
import time
from ConfigParser import RawConfigParser
from subprocess import PIPE
from tempfile import mkdtemp
from urlparse import urlsplit

from trac import log
from trac.admin.api import (AdminCommandError, IAdminCommandProvider,
                            get_dir_list)
from trac.api import IEnvironmentSetupParticipant, ISystemInfoProvider
from trac.cache import CacheManager, cached
from trac.config import BoolOption, ChoiceOption, ConfigSection, \
                        Configuration, IntOption, Option, PathOption
from trac.core import Component, ComponentManager, ExtensionPoint, \
                      TracBaseError, TracError, implements
from trac.db.api import (DatabaseManager, QueryContextManager,
                         TransactionContextManager, parse_connection_uri)
from trac.db.convert import copy_tables
from trac.loader import load_components
from trac.util import as_bool, backup_config_file, copytree, create_file, \
                      get_pkginfo, is_path_below, lazy, makedirs
from trac.util.compat import Popen, close_fds
from trac.util.concurrency import threading
from trac.util.datefmt import pytz
from trac.util.text import exception_to_unicode, path_to_unicode, printerr, \
                           printferr, printfout, printout
from trac.util.translation import _, N_
from trac.web.chrome import Chrome
from trac.web.href import Href

__all__ = ['Environment', 'IEnvironmentSetupParticipant', 'open_environment']


# Content of the VERSION file in the environment
_VERSION = 'Trac Environment Version 1'


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
      in case the database backend is SQLite

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

        Non-absolute paths are relative to the Environment `conf`
        directory.
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

    anonymous_session_lifetime = IntOption(
        'trac', 'anonymous_session_lifetime', '90',
        """Lifetime of the anonymous session, in days.

        Set the option to 0 to disable purging old anonymous sessions.
        (''since 1.0.17'')""")

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
                               '<a href="https://trac.edgewall.org/">'
                               'https://trac.edgewall.org/</a>'),
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
                             log.LOG_LEVELS + log.LOG_LEVEL_ALIASES,
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

    def __init__(self, path, create=False, options=[], default_data=True):
        """Initialize the Trac environment.

        :param path:   the absolute path to the Trac environment
        :param create: if `True`, the environment is created and otherwise,
                       the environment is expected to already exist.
        :param options: A list of `(section, name, value)` tuples that
                        define configuration options
        :param default_data: if `True` (the default), the environment is
                             populated with default data when created.
        """
        ComponentManager.__init__(self)

        self.path = os.path.normpath(os.path.normcase(path))
        self.log = None
        self.config = None

        if create:
            self.create(options, default_data)
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

    @property
    def system_info(self):
        """List of `(name, version)` tuples describing the name and
        version information of external packages used by Trac and plugins.
        """
        info = []
        for provider in self.system_info_providers:
            info.extend(provider.get_system_info() or [])
        return sorted(set(info),
                      key=lambda args: (args[0] != 'Trac', args[0].lower()))

    # ISystemInfoProvider methods

    def get_system_info(self):
        yield 'Trac', self.trac_version
        yield 'Python', sys.version
        yield 'setuptools', setuptools.__version__
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

    @contextmanager
    def component_guard(self, component, reraise=False):
        """Traps any runtime exception raised when working with a component
        and logs the error.

        :param component: the component responsible for any error that
                          could happen inside the context
        :param reraise: if `True`, an error is logged but not suppressed.
                        By default, errors are suppressed.

        """
        try:
            yield
        except TracError as e:
            self.log.warning("Component %s failed with %s",
                             component, exception_to_unicode(e))
            if reraise:
                raise
        except Exception as e:
            self.log.error("Component %s failed with %s", component,
                           exception_to_unicode(e, traceback=True))
            if reraise:
                raise

    def verify(self):
        """Verify that the provided path points to a valid Trac environment
        directory."""
        try:
            with open(os.path.join(self.path, 'VERSION')) as f:
                tag = f.readline().rstrip('\n')
        except Exception as e:
            raise TracError(_("No Trac environment found at %(path)s\n"
                              "%(e)s",
                              path=self.path, e=exception_to_unicode(e)))
        if tag != _VERSION:
            raise TracError(_("Unknown Trac environment type '%(type)s'",
                              type=tag))

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
        if tid is None:
            log.shutdown(self.log)

    def create(self, options=[], default_data=True):
        """Create the basic directory structure of the environment,
        initialize the database and populate the configuration file
        with default values.

        If options contains ('inherit', 'file'), default values will
        not be loaded; they are expected to be provided by that file
        or other options.

        :raises TracError: if the base directory of `path` does not exist.
        :raises TracError: if `path` exists and is not empty.
        """
        base_dir = os.path.dirname(self.path)
        if not os.path.exists(base_dir):
            raise TracError(_(
                "Base directory '%(env)s' does not exist. Please create it "
                "and retry.", env=base_dir))

        if os.path.exists(self.path) and os.listdir(self.path):
            raise TracError(_("Directory exists and is not empty."))

        # Create the directory structure
        if not os.path.exists(self.path):
            os.mkdir(self.path)
        os.mkdir(self.htdocs_dir)
        os.mkdir(self.log_dir)
        os.mkdir(self.plugins_dir)
        os.mkdir(self.templates_dir)

        # Create a few files
        create_file(os.path.join(self.path, 'VERSION'), _VERSION + '\n')
        create_file(os.path.join(self.path, 'README'),
                    'This directory contains a Trac environment.\n'
                    'Visit https://trac.edgewall.org/ for more information.\n')

        # Setup the default configuration
        os.mkdir(self.conf_dir)
        config = Configuration(self.config_file_path)
        for section, name, value in options:
            config.set(section, name, value)
        config.save()
        self.setup_config()
        if not any((section, option) == ('inherit', 'file')
                   for section, option, value in options):
            self.config.set_defaults(self)
            self.config.save()

        # Create the sample configuration
        create_file(self.config_file_path + '.sample')
        self._update_sample_config()

        # Create the database
        dbm = DatabaseManager(self)
        dbm.init_db()
        if default_data:
            dbm.insert_default_data()

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

        In practice, for a database created before 0.11, this will
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

    @lazy
    def log_file_path(self):
        """Path to the log file."""
        if not os.path.isabs(self.log_file):
            return os.path.join(self.log_dir, self.log_file)
        return self.log_file

    def _get_path_to_dir(self, *dirs):
        path = self.path
        for dir in dirs:
            path = os.path.join(path, dir)
        return os.path.realpath(path)

    @lazy
    def attachments_dir(self):
        """Absolute path to the attachments directory.

        :since: 1.3.1
        """
        return self._get_path_to_dir('files', 'attachments')

    @lazy
    def conf_dir(self):
        """Absolute path to the conf directory.

        :since: 1.0.11
        """
        return self._get_path_to_dir('conf')

    @lazy
    def files_dir(self):
        """Absolute path to the files directory.

        :since: 1.3.2
        """
        return self._get_path_to_dir('files')

    @lazy
    def htdocs_dir(self):
        """Absolute path to the htdocs directory.

        :since: 1.0.11
        """
        return self._get_path_to_dir('htdocs')

    @lazy
    def log_dir(self):
        """Absolute path to the log directory.

        :since: 1.0.11
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

    def setup_log(self):
        """Initialize the logging sub-system."""
        self.log, log_handler = \
            self.create_logger(self.log_type, self.log_file_path,
                               self.log_level, self.log_format)
        self.log.addHandler(log_handler)
        self.log.info('-' * 32 + ' environment startup [Trac %s] ' + '-' * 32,
                      self.trac_version)

    def create_logger(self, log_type, log_file, log_level, log_format):
        log_id = 'Trac.%s' % hashlib.sha1(self.path).hexdigest()
        if log_format:
            log_format = log_format.replace('$(', '%(') \
                                   .replace('%(path)s', self.path) \
                                   .replace('%(basename)s', self.name) \
                                   .replace('%(project)s', self.project_name)
        return log.logger_handler_factory(log_type, log_file, log_level,
                                          log_id, format=log_format)

    def get_known_users(self, as_dict=False):
        """Returns information about all known users, i.e. users that
        have logged in to this Trac environment and possibly set their
        name and email.

        By default this function returns an iterator that yields one
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
        return {u[0]: (u[1], u[2]) for u in self._known_users}

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
            try:
                with self.component_guard(participant, reraise=True):
                    if participant.environment_needs_upgrade():
                        self.log.warning(
                            "Component %s requires an environment upgrade",
                            participant)
                        return True
            except Exception as e:
                raise TracError(_("Unable to check for upgrade of "
                                  "%(module)s.%(name)s: %(err)s",
                                  module=participant.__class__.__module__,
                                  name=participant.__class__.__name__,
                                  err=exception_to_unicode(e)))
        return False

    def upgrade(self, backup=False, backup_dest=None):
        """Upgrade database.

        :param backup: whether or not to backup before upgrading
        :param backup_dest: name of the backup file
        :return: whether the upgrade was performed
        """
        upgraders = []
        for participant in self.setup_participants:
            with self.component_guard(participant, reraise=True):
                if participant.environment_needs_upgrade():
                    upgraders.append(participant)
        if not upgraders:
            return

        if backup:
            try:
                self.backup(backup_dest)
            except Exception as e:
                raise BackupError(e)

        for participant in upgraders:
            self.log.info("upgrading %s...", participant)
            with self.component_guard(participant, reraise=True):
                participant.upgrade_environment()
            # Database schema may have changed, so close all connections
            dbm = DatabaseManager(self)
            if dbm.connection_uri != 'sqlite::memory:':
                dbm.shutdown()

        self._update_sample_config()
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
            self.log.warning("[trac] base_url option not set in "
                             "configuration, generated links may be incorrect")
        return Href(self.base_url)

    def _update_sample_config(self):
        filename = os.path.join(self.config_file_path + '.sample')
        if not os.path.isfile(filename):
            return
        config = Configuration(filename)
        config.set_defaults()
        try:
            config.save()
        except EnvironmentError as e:
            self.log.warning("Couldn't write sample configuration file (%s)%s",
                             e, exception_to_unicode(e, traceback=True))
        else:
            self.log.info("Wrote sample configuration file with the new "
                          "settings and their default values: %s",
                          filename)


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
        try:
            needs_upgrade = env.needs_upgrade()
        except TracError as e:
            env.log.error("Exception caught while checking for upgrade: %s",
                          exception_to_unicode(e))
            raise
        except Exception as e:  # e.g. no database connection
            env.log.error("Exception caught while checking for upgrade: %s",
                          exception_to_unicode(e, traceback=True))
            raise
        else:
            if needs_upgrade:
                raise TracError(_('The Trac Environment needs to be upgraded. '
                                  'Run:\n\n  trac-admin "%(path)s" upgrade',
                                  path=env_path))

    return env


class EnvironmentAdmin(Component):
    """trac-admin command provider for environment administration."""

    implements(IAdminCommandProvider)

    # IAdminCommandProvider methods

    def get_admin_commands(self):
        yield ('convert_db', '<dburi> [new_env]',
               """Convert database

               Converts the database backend in the environment in which
               the command is run (in-place), or in a new copy of the
               environment. For an in-place conversion, the data is
               copied to the database specified in <dburi> and the
               [trac] database setting is changed to point to the new
               database. The new database must be empty, which for an
               SQLite database means the file should not exist. The data
               in the existing database is left unmodified.

               For a database conversion in a new copy of the environment,
               the environment in which the command is executed is copied
               and the [trac] database setting is changed in the new
               environment. The existing environment is left unmodified.

               Be sure to create a backup (see `hotcopy`) before converting
               the database, particularly when doing an in-place conversion.
               """,
               self._complete_convert_db, self._do_convert_db)
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

    def _do_convert_db(self, dburi, env_path=None):
        if env_path:
            return self._do_convert_db_in_new_env(dburi, env_path)
        else:
            return self._do_convert_db_in_place(dburi)

    def _complete_convert_db(self, args):
        if len(args) == 2:
            return get_dir_list(args[1])

    def _do_deploy(self, dest):
        target = os.path.normpath(dest)
        chrome_target = os.path.join(target, 'htdocs')
        script_target = os.path.join(target, 'cgi-bin')
        chrome = Chrome(self.env)

        # Check source and destination to avoid recursively copying files
        for provider in chrome.template_providers:
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
        for provider in chrome.template_providers:
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
        data = {'env': self.env, 'executable': sys.executable, 'repr': repr}
        for script in ('cgi', 'fcgi', 'wsgi'):
            dest = os.path.join(script_target, 'trac.' + script)
            template = chrome.load_template('deploy_trac.' + script, text=True)
            text = chrome.render_template_string(template, data, text=True)

            with open(dest, 'w') as out:
                out.write(text.encode('utf-8'))

    def _do_hotcopy(self, dest, no_db=None):
        if no_db not in (None, '--no-database'):
            raise AdminCommandError(_("Invalid argument '%(arg)s'", arg=no_db),
                                    show_usage=True)

        if os.path.exists(dest):
            raise TracError(_("hotcopy can't overwrite existing '%(dest)s'",
                              dest=path_to_unicode(dest)))

        printout(_("Hotcopying %(src)s to %(dst)s ...",
                   src=path_to_unicode(self.env.path),
                   dst=path_to_unicode(dest)))
        db_str = self.env.config.get('trac', 'database')
        prefix, db_path = db_str.split(':', 1)
        skip = []

        if prefix == 'sqlite':
            db_path = os.path.join(self.env.path, os.path.normpath(db_path))
            # don't copy the journal (also, this would fail on Windows)
            skip = [db_path + '-journal', db_path + '-stmtjrnl',
                    db_path + '-shm', db_path + '-wal']
            if no_db:
                skip.append(db_path)

        # Bogus statement to lock the database while copying files
        with self.env.db_transaction as db:
            db("UPDATE " + db.quote('system') +
               " SET name=NULL WHERE name IS NULL")
            try:
                copytree(self.env.path, dest, symlinks=1, skip=skip)
            except shutil.Error as e:
                retval = 1
                printerr(_("The following errors happened while copying "
                           "the environment:"))
                for src, dst, err in e.args[0]:
                    if src in err:
                        printerr('  %s' % err)
                    else:
                        printerr("  %s: '%s'" % (err, path_to_unicode(src)))
            else:
                retval = 0

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

        printout(_('Upgrade done.\n\n'
                   'You may want to upgrade the Trac documentation now by '
                   'running:\n\n  trac-admin "%(path)s" wiki upgrade',
                   path=path_to_unicode(self.env.path)))

    # Internal methods

    def _do_convert_db_in_new_env(self, dst_dburi, env_path):
        try:
            os.rmdir(env_path)  # remove directory if it's empty
        except OSError:
            pass
        if os.path.exists(env_path) or os.path.lexists(env_path):
            printferr("Cannot create Trac environment: %s: File exists",
                      env_path)
            return 1

        dst_env = self._create_env(env_path, dst_dburi)
        dbm = DatabaseManager(self.env)
        src_dburi = dbm.connection_uri
        src_db = dbm.get_connection()
        dst_db = DatabaseManager(dst_env).get_connection()
        self._copy_tables(dst_env, src_db, dst_db, src_dburi, dst_dburi)
        self._copy_directories(dst_env)

    def _do_convert_db_in_place(self, dst_dburi):
        dbm = DatabaseManager(self.env)
        src_dburi = dbm.connection_uri
        if src_dburi == dst_dburi:
            printferr("Source database and destination database are the "
                      "same: %s", dst_dburi)
            return 1

        env_path = mkdtemp(prefix='convert_db-',
                           dir=os.path.dirname(self.env.path))
        try:
            dst_env = self._create_env(env_path, dst_dburi)
            src_db = dbm.get_connection()
            dst_db = DatabaseManager(dst_env).get_connection()
            self._copy_tables(dst_env, src_db, dst_db, src_dburi, dst_dburi)
            del src_db
            del dst_db
            dst_env.shutdown()
            dst_env = None
            schema, params = parse_connection_uri(dst_dburi)
            if schema == 'sqlite':
                dbpath = os.path.join(self.env.path, params['path'])
                dbdir = os.path.dirname(dbpath)
                if not os.path.isdir(dbdir):
                    os.makedirs(dbdir)
                shutil.copy(os.path.join(env_path, params['path']), dbpath)
        finally:
            shutil.rmtree(env_path)

        backup_config_file(self.env, '.convert_db-%d' % int(time.time()))
        self.config.set('trac', 'database', dst_dburi)
        self.config.save()

    def _create_env(self, env_path, dburi):
        parser = RawConfigParser()
        parser.read(self.env.config_file_path)
        options = dict(((section, name), value)
                       for section in parser.sections()
                       for name, value in parser.items(section))
        options[('trac', 'database')] = dburi
        options = sorted((section, name, value) for (section, name), value
                                                in options.iteritems())

        class MigrateEnvironment(Environment):
            abstract = True
            required = False

            def is_component_enabled(self, cls):
                name = self._component_name(cls)
                if not any(name.startswith(mod) for mod in
                           ('trac.', 'tracopt.')):
                    return False
                return Environment.is_component_enabled(self, cls)

        # create an environment without plugins
        env = MigrateEnvironment(env_path, create=True, options=options)
        env.shutdown()
        # copy plugins directory
        os.rmdir(env.plugins_dir)
        shutil.copytree(self.env.plugins_dir, env.plugins_dir)
        # create tables for plugins to upgrade in other process
        with Popen((sys.executable, '-m', 'trac.admin.console', env_path,
                    'upgrade'), stdin=PIPE, stdout=PIPE, stderr=PIPE,
                   close_fds=close_fds) as proc:
            stdout, stderr = proc.communicate(input='')
        if proc.returncode != 0:
            raise TracError("upgrade command failed (stdout %r, stderr %r)" %
                            (stdout, stderr))
        return Environment(env_path)

    def _copy_tables(self, dst_env, src_db, dst_db, src_dburi, dst_dburi):
        copy_tables(self.env, dst_env, src_db, dst_db, src_dburi, dst_dburi)

    def _copy_directories(self, dst_env):
        printfout("Copying directories:")
        for src in (self.env.files_dir, self.env.htdocs_dir,
                    self.env.templates_dir, self.env.plugins_dir):
            name = os.path.basename(src)
            dst = os.path.join(dst_env.path, name)
            printfout("  %s directory... ", name, newline=False)
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            printfout("done.")
