#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
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

from __future__ import with_statement

import doctest
import os
import unittest
import sys

try:
    from babel import Locale
    locale_en = Locale.parse('en_US')
except ImportError:
    locale_en = None

from trac.config import Configuration
from trac.core import Component, ComponentManager
from trac.env import Environment
from trac.db.api import _parse_db_str, DatabaseManager
from trac.db.sqlite_backend import SQLiteConnection
from trac.db.util import ConnectionWrapper
import trac.db.postgres_backend
import trac.db.mysql_backend
from trac.ticket.default_workflow import load_workflow_config_snippet
from trac.util import translation


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
    cls = type('Mock', bases, {})
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

    def require(self, action, realm_or_resource=None, id=False, version=False):
        pass
    assert_permission = require


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
        "Python 2.7 / unittest2 compatibility - there must be a better way..."
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
        scheme, db_prop = _parse_db_str(dburi)
        # Assume the schema 'tractest' for Postgres
        if scheme == 'postgres' and \
                not db_prop.get('params', {}).get('schema'):
            if '?' in dburi:
                dburi += "&schema=tractest"
            else:
                dburi += "?schema=tractest"
        return dburi
    return 'sqlite::memory:'


def reset_sqlite_db(env, db_prop):
    dbname = os.path.basename(db_prop['path'])
    with env.db_transaction as db:
        tables = db("SELECT name FROM sqlite_master WHERE type='table'")
        for table in tables:
            db("DELETE FROM %s" % table)
        return tables


def reset_postgres_db(env, db_prop):
    with env.db_transaction as db:
        dbname = db.schema
        if dbname:
            # reset sequences
            # information_schema.sequences view is available in PostgreSQL 8.2+
            # however Trac supports PostgreSQL 8.0+, uses
            # pg_get_serial_sequence()
            for seq in db("""
                    SELECT sequence_name FROM (
                        SELECT pg_get_serial_sequence(%s||table_name,
                                                      column_name)
                               AS sequence_name
                        FROM information_schema.columns
                        WHERE table_schema=%s) AS tab
                    WHERE sequence_name IS NOT NULL""",
                    (dbname + '.', dbname)):
                db("ALTER SEQUENCE %s RESTART WITH 1" % seq)
            # clear tables
            tables = db("""SELECT table_name FROM information_schema.tables
                           WHERE table_schema=%s""", (dbname,))
            for table in tables:
                db("DELETE FROM %s" % table)
            # PostgreSQL supports TRUNCATE TABLE as well
            # (see http://www.postgresql.org/docs/8.1/static/sql-truncate.html)
            # but on the small tables used here, DELETE is actually much faster
            return tables


def reset_mysql_db(env, db_prop):
    dbname = os.path.basename(db_prop['path'])
    if dbname:
        with env.db_transaction as db:
            tables = db("""SELECT table_name FROM information_schema.tables
                           WHERE table_schema=%s""", (dbname,))
            for table in tables:
                # TRUNCATE TABLE is prefered to DELETE FROM, as we need to reset
                # the auto_increment in MySQL.
                db("TRUNCATE TABLE %s" % table)
            return tables


# -- Environment stub

class EnvironmentStub(Environment):
    """A stub of the trac.env.Environment object for testing."""

    href = abs_href = None
    global_databasemanager = None

    def __init__(self, default_data=False, enable=None, disable=None,
                 path=None, destroying=False):
        """Construct a new Environment stub object.

        :param default_data: If True, populate the database with some
                             defaults.
        :param enable: A list of component classes or name globs to
                       activate in the stub environment.
        """
        ComponentManager.__init__(self)
        Component.__init__(self)

        self.systeminfo = []

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
            self.config.set('components', 'tracopt.versioncontrol.svn.*',
                            'enabled')
        for name_or_class in enable or ():
            config_key = self._component_name(name_or_class)
            self.config.set('components', config_key, 'enabled')
        for name_or_class in disable or ():
            config_key = self._component_name(name_or_class)
            self.config.set('components', config_key, 'disabled')

        # -- logging
        from trac.log import logger_handler_factory
        self.log, self._log_handler = logger_handler_factory('test')

        # -- database
        self.config.set('components', 'trac.db.*', 'enabled')
        self.dburi = get_dburi()

        init_global = False
        if self.global_databasemanager:
            self.components[DatabaseManager] = global_databasemanager
        else:
            self.config.set('trac', 'database', self.dburi)
            self.global_databasemanager = DatabaseManager(self)
            self.config.set('trac', 'debug_sql', True)
            self.config.set('logging', 'log_type', 'stderr')
            self.config.set('logging', 'log_level', 'DEBUG')
            init_global = not destroying

        if default_data or init_global:
            self.reset_db(default_data)

        from trac.web.href import Href
        self.href = Href('/trac.cgi')
        self.abs_href = Href('http://example.org/trac.cgi')

        self.known_users = []
        translation.activate(locale_en)

    def reset_db(self, default_data=None):
        """Remove all data from Trac tables, keeping the tables themselves.
        :param default_data: after clean-up, initialize with default data
        :return: True upon success
        """
        from trac import db_default
        scheme, db_prop = _parse_db_str(self.dburi)
        tables = []
        remove_sqlite_db = False
        try:
            with self.db_transaction as db:
                db.rollback() # make sure there's no transaction in progress
                # check the database version
                database_version = db(
                    "SELECT value FROM system WHERE name='database_version'")
                if database_version:
                    database_version = int(database_version[0][0])
                if database_version == db_default.db_version:
                    # same version, simply clear the tables (faster)
                    m = sys.modules[__name__]
                    reset_fn = 'reset_%s_db' % scheme
                    if hasattr(m, reset_fn):
                        tables = getattr(m, reset_fn)(self, db_prop)
                else:
                    # different version or version unknown, drop the tables
                    remove_sqlite_db = True
                    self.destroy_db(scheme, db_prop)
        except Exception, e:
            # "Database not found ...",
            # "OperationalError: no such table: system" or the like
            pass

        db = None # as we might shutdown the pool     FIXME no longer needed!

        if scheme == 'sqlite' and remove_sqlite_db:
            path = db_prop['path']
            if path != ':memory:':
                if not os.path.isabs(path):
                    path = os.path.join(self.path, path)
                self.global_databasemanager.shutdown()
                os.remove(path)

        if not tables:
            self.global_databasemanager.init_db()
            # we need to make sure the next get_db_cnx() will re-create
            # a new connection aware of the new data model - see #8518.
            if self.dburi != 'sqlite::memory:':
                self.global_databasemanager.shutdown()

        with self.db_transaction as db:
            if default_data:
                for table, cols, vals in db_default.get_data(db):
                    db.executemany("INSERT INTO %s (%s) VALUES (%s)"
                                   % (table, ','.join(cols),
                                      ','.join(['%s' for c in cols])),
                                   vals)
            else:
                db("INSERT INTO system (name, value) VALUES (%s, %s)",
                   ('database_version', str(db_default.db_version)))

    def destroy_db(self, scheme=None, db_prop=None):
        if not (scheme and db_prop):
            scheme, db_prop = _parse_db_str(self.dburi)
        try:
            with self.db_transaction as db:
                if scheme == 'postgres' and db.schema:
                    db('DROP SCHEMA "%s" CASCADE' % db.schema)
                elif scheme == 'mysql':
                    dbname = os.path.basename(db_prop['path'])
                    for table in db("""
                          SELECT table_name FROM information_schema.tables
                          WHERE table_schema=%s""", (dbname,)):
                        db("DROP TABLE IF EXISTS `%s`" % table)
        except Exception:
            # "TracError: Database not found...",
            # psycopg2.ProgrammingError: schema "tractest" does not exist
            pass
        return False

    # overriden

    def is_component_enabled(self, cls):
        if self._component_name(cls).startswith('__main__.'):
            return True
        return Environment.is_component_enabled(self, cls)

    def get_known_users(self, cnx=None):
        return self.known_users


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


INCLUDE_FUNCTIONAL_TESTS = True

def suite():
    import trac.tests
    import trac.admin.tests
    import trac.db.tests
    import trac.mimeview.tests
    import trac.ticket.tests
    import trac.util.tests
    import trac.versioncontrol.tests
    import trac.versioncontrol.web_ui.tests
    import trac.web.tests
    import trac.wiki.tests
    import tracopt.mimeview.tests
    import tracopt.perm.tests
    import tracopt.versioncontrol.git.tests
    import tracopt.versioncontrol.svn.tests

    suite = unittest.TestSuite()
    suite.addTest(trac.tests.basicSuite())
    if INCLUDE_FUNCTIONAL_TESTS:
        suite.addTest(trac.tests.functionalSuite())
    suite.addTest(trac.admin.tests.suite())
    suite.addTest(trac.db.tests.suite())
    suite.addTest(trac.mimeview.tests.suite())
    suite.addTest(trac.ticket.tests.suite())
    suite.addTest(trac.util.tests.suite())
    suite.addTest(trac.versioncontrol.tests.suite())
    suite.addTest(trac.versioncontrol.web_ui.tests.suite())
    suite.addTest(trac.web.tests.suite())
    suite.addTest(trac.wiki.tests.suite())
    suite.addTest(tracopt.mimeview.tests.suite())
    suite.addTest(tracopt.perm.tests.suite())
    suite.addTest(tracopt.versioncontrol.git.tests.suite())
    suite.addTest(tracopt.versioncontrol.svn.tests.suite())
    suite.addTest(doctest.DocTestSuite(sys.modules[__name__]))

    return suite

if __name__ == '__main__':
    #FIXME: this is a bit inelegant
    if '--skip-functional-tests' in sys.argv:
        sys.argv.remove('--skip-functional-tests')
        INCLUDE_FUNCTIONAL_TESTS = False
    unittest.main(defaultTest='suite')
