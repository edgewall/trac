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

import os
import unittest
import sys
import pkg_resources
from fnmatch import fnmatch

from trac.config import Configuration
from trac.core import Component, ComponentManager, ExtensionPoint
from trac.env import Environment
from trac.db.sqlite_backend import SQLiteConnection
from trac.ticket.default_workflow import load_workflow_config_snippet


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
    for k,v in kw.items():
        setattr(mock, k, v)
    return mock


class MockPerm(object):
    """Fake permission class. Necessary as Mock can not be used with operator
    overloading."""
    def has_permission(self, x):
        return True
    __contains__ = has_permission

    def __call__(self, *a, **kw):
        return self

    def require(self, *a, **kw):
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
        for test in self._tests:    # Content of unittest.TestSuite.run()
            if result.shouldStop:   # copied here for Python 2.3 compatibility
                break
            test(result)
        self.tearDown()
        return result

    def __call__(self, *args, **kwds):      # Python 2.3 compatibility
        return self.run(*args, **kwds)


class TestCaseSetup(unittest.TestCase):
    def setFixture(self, fixture):
        self.fixture = fixture


class InMemoryDatabase(SQLiteConnection):
    """
    DB-API connection object for an SQLite in-memory database, containing all
    the default Trac tables but no data.
    """
    def __init__(self):
        SQLiteConnection.__init__(self, ':memory:')
        cursor = self.cnx.cursor()

        from trac.db_default import schema
        from trac.db.sqlite_backend import _to_sql
        for table in schema:
            for stmt in _to_sql(table):
                cursor.execute(stmt)

        self.cnx.commit()


class EnvironmentStub(Environment):
    """A stub of the trac.env.Environment object for testing."""

    href = abs_href = None

    def __init__(self, default_data=False, enable=None):
        """Construct a new Environment stub object.

        default_data: If True, populate the database with some defaults.
        enable: A list of component classes or name globs to activate in the
                stub environment.
        """
        ComponentManager.__init__(self)
        Component.__init__(self)
        self.enabled_components = enable or ['trac.*']
        self.db = InMemoryDatabase()
        self.systeminfo = [('Python', sys.version)]

        import trac
        self.path = os.path.dirname(trac.__file__)
        if not os.path.isabs(self.path):
            self.path = os.path.join(os.getcwd(), self.path)

        self.config = Configuration(None)
        # We have to have a ticket-workflow config for ''lots'' of things to
        # work.  So insert the basic-workflow config here.  There may be a
        # better solution than this.
        load_workflow_config_snippet(self.config, 'basic-workflow.ini')

        from trac.log import logger_factory
        self.log = logger_factory('test')

        from trac.web.href import Href
        self.href = Href('/trac.cgi')
        self.abs_href = Href('http://example.org/trac.cgi')

        from trac import db_default
        if default_data:
            cursor = self.db.cursor()
            for table, cols, vals in db_default.get_data(self.db):
                cursor.executemany("INSERT INTO %s (%s) VALUES (%s)"
                                   % (table, ','.join(cols),
                                      ','.join(['%s' for c in cols])),
                                   vals)
            self.db.commit()
            
        self.known_users = []

    def is_component_enabled(self, cls):
        for component in self.enabled_components:
            if component is cls:
                return True
            if isinstance(component, basestring) and \
                fnmatch(cls.__module__ + '.' + cls.__name__, component):
                return True
        return False

    def get_db_cnx(self):
        return self.db

    def get_known_users(self, cnx=None):
        return self.known_users


def locate(fn):
    """Locates a binary on the path.

    Returns the fully-qualified path, or None.
    """
    import os
    exec_suffix = os.name == 'nt' and '.exe' or ''
    
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

    return suite

if __name__ == '__main__':
    import doctest, sys
    doctest.testmod(sys.modules[__name__])
    #FIXME: this is a bit inelegant
    if '--skip-functional-tests' in sys.argv:
        sys.argv.remove('--skip-functional-tests')
        INCLUDE_FUNCTIONAL_TESTS = False
    unittest.main(defaultTest='suite')
