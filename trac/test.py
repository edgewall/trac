#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
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

from trac.config import Configuration
from trac.core import Component, ComponentManager, ExtensionPoint
from trac.env import Environment
from trac.db.sqlite_backend import SQLiteConnection


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


class TestSetup(unittest.TestSuite):
    """
    Test suite decorator that allows a fixture to be setup for a complete
    suite of test cases.
    """
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def __call__(self, result):
        self.setUp()
        unittest.TestSuite.__call__(self, result)
        self.tearDown()
        return result


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


class TestConfiguration(Configuration):
    def __init__(self, filename):
        Configuration.__init__(self, filename)
        # insulate us from "real" global trac.ini (ref. #3700)
        from ConfigParser import ConfigParser
        self.site_parser = ConfigParser()


class EnvironmentStub(Environment):
    """A stub of the trac.env.Environment object for testing."""

    def __init__(self, default_data=False, enable=None):
        ComponentManager.__init__(self)
        Component.__init__(self)
        self.enabled_components = enable
        self.db = InMemoryDatabase()
        self.systeminfo = {'Python': sys.version}

        import trac
        self.path = os.path.dirname(trac.__file__)
        if not os.path.isabs(self.path):
            self.path = os.path.join(os.getcwd(), self.path)

        self.config = TestConfiguration(None)

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
        if self.enabled_components is None:
            return True
        return cls in self.enabled_components

    def get_db_cnx(self):
        return self.db

    def get_known_users(self, db):
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


def suite():
    import trac.tests
    import trac.db.tests
    import trac.mimeview.tests
    import trac.scripts.tests
    import trac.ticket.tests
    import trac.util.tests
    import trac.versioncontrol.tests
    import trac.versioncontrol.web_ui.tests
    import trac.web.tests
    import trac.wiki.tests

    suite = unittest.TestSuite()
    suite.addTest(trac.tests.suite())
    suite.addTest(trac.db.tests.suite())
    suite.addTest(trac.mimeview.tests.suite())
    suite.addTest(trac.scripts.tests.suite())
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
    unittest.main(defaultTest='suite')
