#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2018 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
#         Christopher Lenz <cmlenz@gmx.de>

import abc
import doctest
import inspect
import numbers
import os
import shutil
import sys
import time
import types
import unittest
import StringIO

try:
    from babel import Locale
except ImportError:
    locale_en = None
else:
    locale_en = Locale.parse('en_US')

from trac.config import Configuration
from trac.core import ComponentManager, ComponentMeta, TracError
from trac.db.api import DatabaseManager, parse_connection_uri
from trac.env import Environment
from trac.perm import PermissionCache
from trac.ticket.default_workflow import load_workflow_config_snippet
from trac.util import translation
from trac.util.datefmt import time_now, utc
from trac.web.api import _RequestArgs, Request, arg_list_to_args
from trac.web.session import Session


def Mock(bases=(), *initargs, **kw):
    """
    Simple factory for dummy classes that can be used as replacement for the
    real implementation in tests.

    Base classes for the mock can be specified using the first parameter, which
    must be either a tuple of class objects or a single class object. If the
    bases parameter is omitted, the base class of the mock will be object.

    So to create a mock that is derived from the builtin dict type, you can do:

    >>> mock = Mock(dict)
    >>> mock['foo'] = 'bar'
    >>> mock['foo']
    'bar'

    Attributes of the class are provided by any additional keyword parameters.

    >>> mock = Mock(foo='bar')
    >>> mock.foo
    'bar'

    Objects produces by this function have the special feature of not requiring
    the 'self' parameter on methods, because you should keep data at the scope
    of the test function. So you can just do:

    >>> mock = Mock(add=lambda x,y: x+y)
    >>> mock.add(1, 1)
    2

    To access attributes from the mock object from inside a lambda function,
    just access the mock itself:

    >>> mock = Mock(dict, do=lambda x: 'going to the %s' % mock[x])
    >>> mock['foo'] = 'bar'
    >>> mock.do('foo')
    'going to the bar'

    Because assignments or other types of statements don't work in lambda
    functions, assigning to a local variable from a mock function requires some
    extra work:

    >>> myvar = [None]
    >>> mock = Mock(set=lambda x: myvar.__setitem__(0, x))
    >>> mock.set(1)
    >>> myvar[0]
    1
    """
    if not isinstance(bases, tuple):
        bases = (bases,)

    # if base classes have abstractmethod and abstractproperty,
    # create dummy methods for abstracts
    attrs = {}
    def dummyfn(self, *args, **kwargs):
        raise NotImplementedError
    for base in bases:
        if getattr(base, '__metaclass__', None) is not abc.ABCMeta:
            continue
        fn = types.UnboundMethodType(dummyfn, None, base)
        for name, attr in inspect.getmembers(base):
            if name in attrs:
                continue
            if isinstance(attr, abc.abstractproperty) or \
                    isinstance(attr, types.UnboundMethodType) and \
                    getattr(attr, '__isabstractmethod__', False) is True:
                attrs[name] = fn

    cls = type('Mock', bases, attrs)
    mock = cls(*initargs)
    for k, v in kw.items():
        setattr(mock, k, v)
    return mock


class MockPerm(object):
    """Fake permission class. Necessary as Mock can not be used with operator
    overloading."""

    username = ''

    def has_permission(self, action, realm_or_resource=None, id=False,
                       version=False):
        return True
    __contains__ = has_permission

    def __call__(self, realm_or_resource, id=False, version=False):
        return self

    def require(self, action, realm_or_resource=None, id=False, version=False,
                message=None):
        pass
    assert_permission = require


def MockRequest(env, **kwargs):
    """Request object for testing. Keyword arguments populate an
    `environ` dictionary and the callbacks.

    If `authname` is specified in a keyword arguments a `PermissionCache`
    object is created, otherwise if `authname` is not specified or is
    `None` a `MockPerm` object is used and the `authname` is set to
    'anonymous'.

    The following keyword arguments are commonly used:
    :keyword args: dictionary of request arguments
    :keyword authname: the name of the authenticated user, or 'anonymous'
    :keyword method: the HTTP request method
    :keyword path_info: the request path inside the application

    Additionally `cookie`, `format`, `locale`, `lc_time`, `remote_addr`,
    `remote_user`, `script_name`, `server_name`, `server_port`
    and `tz` can be specified as keyword arguments.

    :since: 1.0.11
    """

    authname = kwargs.get('authname')
    if authname is None:
        authname = 'anonymous'
        perm = MockPerm()
    else:
        perm = PermissionCache(env, authname)

    def convert(val):
        if isinstance(val, bool):
            return unicode(int(val))
        elif isinstance(val, numbers.Real):
            return unicode(val)
        elif isinstance(val, (list, tuple)):
            return [convert(v) for v in val]
        else:
            return val

    if 'arg_list' in kwargs:
        arg_list = [(k, convert(v)) for k, v in kwargs['arg_list']]
        args = arg_list_to_args(arg_list)
    else:
        args = _RequestArgs()
        args.update((k, convert(v))
                    for k, v in kwargs.get('args', {}).iteritems())
        arg_list = [(name, value) for name in args
                                  for value in args.getlist(name)]

    environ = {
        'trac.base_url': env.abs_href(),
        'wsgi.url_scheme': 'http',
        'HTTP_ACCEPT_LANGUAGE': 'en-US',
        'HTTP_COOKIE': kwargs.get('cookie', ''),
        'PATH_INFO': kwargs.get('path_info', '/'),
        'REQUEST_METHOD': kwargs.get('method', 'GET'),
        'REMOTE_ADDR': kwargs.get('remote_addr', '127.0.0.1'),
        'REMOTE_USER': kwargs.get('remote_user', authname),
        'SCRIPT_NAME': kwargs.get('script_name', '/trac.cgi'),
        'SERVER_NAME': kwargs.get('server_name', 'localhost'),
        'SERVER_PORT': kwargs.get('server_port', '80'),
    }

    status_sent = []
    headers_sent = {}
    response_sent = StringIO.StringIO()

    def start_response(status, headers, exc_info=None):
        status_sent.append(status)
        headers_sent.update(dict(headers))
        return response_sent.write

    req = Mock(Request, environ, start_response)
    req.status_sent = status_sent
    req.headers_sent = headers_sent
    req.response_sent = response_sent

    from trac.web.chrome import Chrome
    req.callbacks.update({
        'arg_list': lambda req: arg_list,
        'args': lambda req: args,
        'authname': lambda req: authname,
        'chrome': Chrome(env).prepare_request,
        'form_token': lambda req: kwargs.get('form_token'),
        'lc_time': lambda req: kwargs.get('lc_time', locale_en),
        'locale': lambda req: kwargs.get('locale'),
        'perm': lambda req: perm,
        'session': lambda req: Session(env, req),
        'tz': lambda req: kwargs.get('tz', utc),
        'use_xsendfile': lambda req: False,
        'xsendfile_header': lambda req: None,
        'configurable_headers': lambda req: [],
    })

    return req


class TestSetup(unittest.TestSuite):
    """
    Test suite decorator that allows a fixture to be setup for a complete
    suite of test cases.
    """
    def setUp(self):
        """Sets up the fixture, and sets self.fixture if needed"""
        pass

    def tearDown(self):
        """Tears down the fixture"""
        pass

    def run(self, result):
        """Setup the fixture (self.setUp), call .setFixture on all the tests,
        and tear down the fixture (self.tearDown)."""
        self.setUp()
        if hasattr(self, 'fixture'):
            for test in self._tests:
                if hasattr(test, 'setFixture'):
                    test.setFixture(self.fixture)
        unittest.TestSuite.run(self, result)
        self.tearDown()
        return result

    def _wrapped_run(self, *args, **kwargs):
        """Python 2.7 / unittest2 compatibility - there must be a better
        way..."""
        self.setUp()
        if hasattr(self, 'fixture'):
            for test in self._tests:
                if hasattr(test, 'setFixture'):
                    test.setFixture(self.fixture)
        unittest.TestSuite._wrapped_run(self, *args, **kwargs)
        self.tearDown()


class TestCaseSetup(unittest.TestCase):
    def setFixture(self, fixture):
        self.fixture = fixture


# -- Database utilities

def get_dburi():
    dburi = os.environ.get('TRAC_TEST_DB_URI')
    if dburi:
        scheme, db_prop = parse_connection_uri(dburi)
        # Assume the schema 'tractest' for PostgreSQL
        if scheme == 'postgres' and \
                not db_prop.get('params', {}).get('schema'):
            dburi += ('&' if '?' in dburi else '?') + 'schema=tractest'
        elif scheme == 'sqlite' and db_prop['path'] != ':memory:' and \
                not db_prop.get('params', {}).get('synchronous'):
            # Speed-up tests with SQLite database
            dburi += ('&' if '?' in dburi else '?') + 'synchronous=off'
    else:
        scheme = 'sqlite'
        dburi = '%s::memory:' % scheme
    __import__('trac.db.%s_backend' % scheme)
    return dburi


def reset_sqlite_db(env, db_prop):
    """Deletes all data from the tables.

    :since 1.1.3: deprecated and will be removed in 1.3.1. Use `reset_tables`
                  from the database connection class instead.
    """
    return DatabaseManager(env).reset_tables()


def reset_postgres_db(env, db_prop):
    """Deletes all data from the tables and resets autoincrement indexes.

    :since 1.1.3: deprecated and will be removed in 1.3.1. Use `reset_tables`
                  from the database connection class instead.
    """
    return DatabaseManager(env).reset_tables()


def reset_mysql_db(env, db_prop):
    """Deletes all data from the tables and resets autoincrement indexes.

    :since 1.1.3: deprecated and will be removed in 1.3.1. Use `reset_tables`
                  from the database connection class instead.
    """
    return DatabaseManager(env).reset_tables()


class EnvironmentStub(Environment):
    """A stub of the trac.env.Environment class for testing."""

    global_databasemanager = None  # Deprecated, will be removed in 1.3.1
    required = False
    abstract = True

    def __init__(self, default_data=False, enable=None, disable=None,
                 path=None, destroying=False):
        """Construct a new Environment stub object.

        :param default_data: If True, populate the database with some
                             defaults.
        :param enable: A list of component classes or name globs to
                       activate in the stub environment.
        :param disable: A list of component classes or name globs to
                        deactivate in the stub environment.
        :param path: The location of the environment in the file system.
                     No files or directories are created when specifying
                     this parameter.
        :param destroying: If True, the database will not be reset. This is
                           useful for cases when the object is being
                           constructed in order to call `destroy_db`.
        """
        if enable is not None and not isinstance(enable, (list, tuple)):
            raise TypeError('Keyword argument "enable" must be a list')
        if disable is not None and not isinstance(disable, (list, tuple)):
            raise TypeError('Keyword argument "disable" must be a list')

        ComponentManager.__init__(self)

        self.systeminfo = []
        self._old_registry = None
        self._old_components = None

        import trac
        self.path = path
        if self.path is None:
            self.path = os.path.dirname(trac.__file__)
            if not os.path.isabs(self.path):
                self.path = os.path.join(os.getcwd(), self.path)

        # -- configuration
        self.config = Configuration(None)
        # We have to have a ticket-workflow config for ''lots'' of things to
        # work.  So insert the basic-workflow config here.  There may be a
        # better solution than this.
        load_workflow_config_snippet(self.config, 'basic-workflow.ini')
        self.config.set('logging', 'log_level', 'DEBUG')
        self.config.set('logging', 'log_type', 'stderr')
        if enable is not None:
            self.config.set('components', 'trac.*', 'disabled')
        else:
            self.config.set('components', 'tracopt.versioncontrol.*',
                            'enabled')
        for name_or_class in enable or ():
            config_key = self._component_name(name_or_class)
            self.config.set('components', config_key, 'enabled')
        for name_or_class in disable or ():
            config_key = self._component_name(name_or_class)
            self.config.set('components', config_key, 'disabled')
        self.config.set('trac', 'permission_policies',
                        'DefaultPermissionPolicy, LegacyAttachmentPolicy')

        # -- logging
        from trac.log import logger_handler_factory
        self.log, self._log_handler = logger_handler_factory('test')
        self.log.addHandler(self._log_handler)

        # -- database
        self.dburi = get_dburi()
        self.config.set('components', 'trac.db.*', 'enabled')
        self.config.set('trac', 'database', self.dburi)
        self.config.set('trac', 'debug_sql', True)
        self.global_databasemanager = DatabaseManager(self)  # Remove in 1.3.1

        if not destroying:
            self.reset_db(default_data)

        self.config.set('trac', 'base_url', 'http://example.org/trac.cgi')

        translation.activate(locale_en)

    def reset_db(self, default_data=None):
        """Remove all data from Trac tables, keeping the tables themselves.

        :param default_data: after clean-up, initialize with default data
        :return: True upon success
        """
        from trac import db_default
        tables = []
        dbm = DatabaseManager(self)
        try:
            with self.db_transaction as db:
                db.rollback()  # make sure there's no transaction in progress
                # check the database version
                db_version = dbm.get_database_version()
        except (TracError, self.db_exc.DatabaseError):
            pass
        else:
            if db_version == db_default.db_version:
                # same version, simply clear the tables (faster)
                tables = dbm.reset_tables()
            else:
                # different version or version unknown, drop the tables
                self.destroy_db()

        if not tables:
            dbm.init_db()
            # we need to make sure the next get_db_cnx() will re-create
            # a new connection aware of the new data model - see #8518.
            if self.dburi != 'sqlite::memory:':
                dbm.shutdown()

        if default_data:
            dbm.insert_into_tables(db_default.get_data)
        else:
            dbm.set_database_version(db_default.db_version)

    def destroy_db(self, scheme=None, db_prop=None):
        """Destroy the database.

        :since 1.1.5: the `scheme` and `db_prop` parameters are deprecated and
                      will be removed in 1.3.1.
        """
        try:
            DatabaseManager(self).destroy_db()
        except (TracError, self.db_exc.DatabaseError):
            pass

    def clear_component_registry(self):
        """Clear the component registry.

        The registry entries are saved entries so they can be restored
        later using the `restore_component_registry` method.

        :since: 1.0.11
        """
        self._old_registry = ComponentMeta._registry
        self._old_components = ComponentMeta._components
        ComponentMeta._registry = {}

    def restore_component_registry(self):
        """Restore the component registry.

        The component registry must have been cleared and saved using
        the `clear_component_registry` method.

        :since: 1.0.11
        """
        if self._old_registry is None:
            raise TracError("The clear_component_registry method must be "
                            "called first.")
        ComponentMeta._registry = self._old_registry
        ComponentMeta._components = self._old_components

    # tearDown helper

    def reset_db_and_disk(self):
        """Performs a complete environment reset in a robust way.

        The database is reset, then the connections are shut down, and
        finally all environment files are removed from the disk.
        """
        self.reset_db()
        self.shutdown() # really closes the db connections
        rmtree(self.env.path)
        if self._old_registry is not None:
            self.restore_component_registry()

    # other utilities

    def insert_users(self, users):
        """Insert a tuple representing a user session to the
        `session` and `session_attributes` tables.

        The tuple can be length 3 with entries username, name and
        email, in which case an authenticated user is assumed. The
        tuple can also be length 4, with the last entry specifying
        `1` for an authenticated user or `0` for an unauthenticated
        user.
        """
        with self.db_transaction as db:
            for row in users:
                if len(row) == 3:
                    username, name, email = row
                    authenticated = 1
                else:  # len(row) == 4
                    username, name, email, authenticated = row
                db("INSERT INTO session VALUES (%s, %s, %s)",
                   (username, authenticated, int(time_now())))
                db("INSERT INTO session_attribute VALUES (%s,%s,'name',%s)",
                   (username, authenticated, name))
                db("INSERT INTO session_attribute VALUES (%s,%s,'email',%s)",
                   (username, authenticated, email))

    # overridden

    def is_component_enabled(self, cls):
        if self._component_name(cls).startswith('__main__.'):
            return True
        return Environment.is_component_enabled(self, cls)


def locate(fn):
    """Locates a binary on the path.

    Returns the fully-qualified path, or None.
    """
    exec_suffix = '.exe' if os.name == 'nt' else ''

    for p in ["."] + os.environ['PATH'].split(os.pathsep):
        f = os.path.join(p, fn + exec_suffix)
        if os.path.exists(f):
            return f
    return None


def rmtree(path):
    import errno
    def onerror(function, path, excinfo, retry=1):
        # `os.remove` fails for a readonly file on Windows.
        # Then, it attempts to be writable and remove.
        if function != os.remove:
            raise
        e = excinfo[1]
        if isinstance(e, OSError) and e.errno == errno.EACCES:
            mode = os.stat(path).st_mode
            os.chmod(path, mode | 0666)
            try:
                function(path)
            except Exception:
                # print "%d: %s %o" % (retry, path, os.stat(path).st_mode)
                if retry > 10:
                    raise
                time.sleep(0.1)
                onerror(function, path, excinfo, retry + 1)
        else:
            raise
    if os.name == 'nt' and isinstance(path, str):
        # Use unicode characters in order to allow non-ansi characters
        # on Windows.
        path = unicode(path, sys.getfilesystemencoding())
    shutil.rmtree(path, onerror=onerror)


INCLUDE_FUNCTIONAL_TESTS = True


def test_suite():
    import trac.tests
    import trac.admin.tests
    import trac.db.tests
    import trac.mimeview.tests
    import trac.notification.tests
    import trac.search.tests
    import trac.ticket.tests
    import trac.timeline.tests
    import trac.upgrades.tests
    import trac.util.tests
    import trac.versioncontrol.tests
    import trac.versioncontrol.web_ui.tests
    import trac.web.tests
    import trac.wiki.tests
    import tracopt.perm.tests
    import tracopt.ticket.tests
    import tracopt.versioncontrol.git.tests
    import tracopt.versioncontrol.svn.tests

    suite = unittest.TestSuite()
    suite.addTest(trac.tests.basicSuite())
    suite.addTest(trac.admin.tests.test_suite())
    suite.addTest(trac.db.tests.test_suite())
    suite.addTest(trac.mimeview.tests.test_suite())
    suite.addTest(trac.notification.tests.test_suite())
    suite.addTest(trac.search.tests.test_suite())
    suite.addTest(trac.ticket.tests.test_suite())
    suite.addTest(trac.timeline.tests.test_suite())
    suite.addTest(trac.upgrades.tests.test_suite())
    suite.addTest(trac.util.tests.test_suite())
    suite.addTest(trac.versioncontrol.tests.test_suite())
    suite.addTest(trac.versioncontrol.web_ui.tests.test_suite())
    suite.addTest(trac.web.tests.test_suite())
    suite.addTest(trac.wiki.tests.test_suite())
    suite.addTest(tracopt.perm.tests.test_suite())
    suite.addTest(tracopt.ticket.tests.test_suite())
    suite.addTest(tracopt.versioncontrol.git.tests.test_suite())
    suite.addTest(tracopt.versioncontrol.svn.tests.test_suite())
    suite.addTest(doctest.DocTestSuite(sys.modules[__name__]))
    if INCLUDE_FUNCTIONAL_TESTS:
        suite.addTest(trac.tests.functionalSuite())
    return suite


if __name__ == '__main__':
    # FIXME: this is a bit inelegant
    if '--skip-functional-tests' in sys.argv:
        sys.argv.remove('--skip-functional-tests')
        INCLUDE_FUNCTIONAL_TESTS = False
    unittest.main(defaultTest='test_suite')
