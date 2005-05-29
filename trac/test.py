#!/usr/bin/env python
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

from trac.core import ComponentManager
from trac.db import SQLiteConnection

import unittest


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
        for table in schema:
            cursor.execute(SQLiteConnection.to_sql(table))

        self.cnx.commit()


class EnvironmentStub(ComponentManager):
    """A stub of the trac.env.Environment object for testing."""
    def __init__(self, enable=None):
        ComponentManager.__init__(self)
        self.enabled_components = enable
        self.db = InMemoryDatabase()

        from trac.config import Configuration
        self.config = Configuration(None)

        from trac.log import logger_factory
        self.log = logger_factory('test')

        from trac.web.href import Href
        self.href = Href('/trac.cgi')

    def component_activated(self, component):
        component.env = self
        component.config = self.config
        component.log = self.log

    def is_component_enabled(self, cls):
        if self.enabled_components is None:
            return True
        return cls in self.enabled_components

    def get_db_cnx(self):
        return self.db


def suite():
    import trac.tests
    import trac.scripts.tests
    import trac.ticket.tests
    import trac.versioncontrol.tests
    import trac.web.tests
    import trac.wiki.tests

    suite = unittest.TestSuite()
    suite.addTest(trac.tests.suite())
    suite.addTest(trac.scripts.tests.suite())
    suite.addTest(trac.ticket.tests.suite())
    suite.addTest(trac.versioncontrol.tests.suite())
    suite.addTest(trac.web.tests.suite())
    suite.addTest(trac.wiki.tests.suite())

    return suite

if __name__ == '__main__':
    import doctest
    doctest.testmod()
    unittest.main(defaultTest='suite')
