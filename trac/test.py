#!/usr/bin/env python
# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004, 2005 Edgewall Software
# Copyright (C) 2003, 2004, 2005 Jonas Borgstršm <jonas@edgewall.com>
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

from trac.db import SQLiteConnection

import unittest


class Mock(object):
    """
    Simple builder for dummy classes that can be used as replacement for the 
    real implementation in tests.
    """

    def __init__(self, **kw):
        for k,v in kw.items():
            setattr(self, k, v)


class InMemoryDatabase(SQLiteConnection):
    """
    DB-API connection object for an SQLite in-memory database, containing all
    the default Trac tables but no data.
    """
    def __init__(self):
        SQLiteConnection.__init__(self, ':memory:')

        cursor = self.cnx.cursor()
        from trac.db_default import schema
        cursor.execute(schema)
        self.cnx.commit()


def suite():
    from trac.tests import wiki, ticket, perm, environment, diff, query, href, \
                           tracadmin
    from trac.web.tests import auth, cgi_frontend, clearsilver, session

    suite = unittest.TestSuite()

    # trac
    suite.addTest(wiki.suite())
    suite.addTest(ticket.suite())
    suite.addTest(perm.suite())
    suite.addTest(environment.suite())
    suite.addTest(diff.suite())
    suite.addTest(href.suite())
    suite.addTest(query.suite())

    # trac.web
    suite.addTest(auth.suite())
    suite.addTest(cgi_frontend.suite())
    suite.addTest(clearsilver.suite())
    suite.addTest(session.suite())

    # trac-admin
    suite.addTest(tracadmin.suite())

    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
