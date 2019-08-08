# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import datetime
import unittest

import trac.versioncontrol.admin
from trac.admin.console import TracAdmin
from trac.admin.test import TracAdminTestCaseBase
from trac.core import Component, implements
from trac.test import EnvironmentStub, Mock
from trac.util.datefmt import utc
from trac.versioncontrol.api import Changeset, DbRepositoryProvider, \
                                    IRepositoryConnector, NoSuchChangeset, \
                                    Repository


class MockRepositoryConnector(Component):

    implements(IRepositoryConnector)

    def get_supported_types(self):
        yield 'mock_type', 8

    def get_repository(self, repos_type, repos_dir, params):
        def get_changeset(rev):
            if rev == 'invalid':
                raise NoSuchChangeset(rev)
            return Mock(Changeset, repos, rev, 'message', 'author',
                        datetime.datetime(2001, 1, 1, tzinfo=utc))

        def get_node(path, rev):
            pass

        repos = Mock(Repository, params['name'], params, self.log,
                     get_youngest_rev=lambda: 1,
                     get_changeset=get_changeset,
                     get_node=get_node,
                     previous_rev=lambda rev, path='': None,
                     next_rev=lambda rev, path='': None)
        return repos


class TracAdminTestCase(TracAdminTestCaseBase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True, enable=('trac.*',),
                                   disable=('trac.tests.*',))
        self.admin = TracAdmin()
        self.admin.env_set('', self.env)
        provider = DbRepositoryProvider(self.env)
        provider.add_repository('mock', '/', 'mock_type')

    def tearDown(self):
        self.env = None

    def test_changeset_add_no_repository_revision(self):
        rv, output = self.execute('changeset added')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_changeset_add_no_revision(self):
        rv, output = self.execute('changeset added mock')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_changeset_modify_no_repository_revision(self):
        rv, output = self.execute('changeset modified')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_changeset_modify_no_revision(self):
        rv, output = self.execute('changeset modified mock')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_changeset_add_invalid_repository(self):
        rv, output = self.execute('changeset added invalid 123')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_changeset_modify_invalid_repository(self):
        rv, output = self.execute('changeset modified invalid 123')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_changeset_add_invalid_changeset(self):
        rv, output = self.execute('changeset added mock invalid')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_changeset_modify_invalid_changeset(self):
        rv, output = self.execute('changeset modified mock invalid')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TracAdminTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
