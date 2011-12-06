# -*- coding: utf-8 -*-
#
# Copyright (C) 2007 CommProve, Inc. <eli.carter@commprove.com>
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
# Author: Eli Carter <eli.carter@commprove.com>

import unittest

from trac.resource import Resource, get_resource_description, get_resource_url
from trac.test import EnvironmentStub
from trac.versioncontrol.api import Repository


class ApiTestCase(unittest.TestCase):

    def setUp(self):
        self.repo_base = Repository('testrepo', {'name': 'testrepo', 'id': 1},
                                    None)

    def test_raise_NotImplementedError_close(self):
        self.failUnlessRaises(NotImplementedError, self.repo_base.close)

    def test_raise_NotImplementedError_get_changeset(self):
        self.failUnlessRaises(NotImplementedError, self.repo_base.get_changeset, 1)

    def test_raise_NotImplementedError_get_node(self):
        self.failUnlessRaises(NotImplementedError, self.repo_base.get_node, 'path')

    def test_raise_NotImplementedError_get_oldest_rev(self):
        self.failUnlessRaises(NotImplementedError, self.repo_base.get_oldest_rev)

    def test_raise_NotImplementedError_get_youngest_rev(self):
        self.failUnlessRaises(NotImplementedError, self.repo_base.get_youngest_rev)

    def test_raise_NotImplementedError_previous_rev(self):
        self.failUnlessRaises(NotImplementedError, self.repo_base.previous_rev, 1)

    def test_raise_NotImplementedError_next_rev(self):
        self.failUnlessRaises(NotImplementedError, self.repo_base.next_rev, 1)

    def test_raise_NotImplementedError_rev_older_than(self):
        self.failUnlessRaises(NotImplementedError, self.repo_base.rev_older_than, 1, 2)

    def test_raise_NotImplementedError_get_path_history(self):
        self.failUnlessRaises(NotImplementedError, self.repo_base.get_path_history, 'path')

    def test_raise_NotImplementedError_normalize_path(self):
        self.failUnlessRaises(NotImplementedError, self.repo_base.normalize_path, 'path')

    def test_raise_NotImplementedError_normalize_rev(self):
        self.failUnlessRaises(NotImplementedError, self.repo_base.normalize_rev, 1)

    def test_raise_NotImplementedError_get_changes(self):
        self.failUnlessRaises(NotImplementedError, self.repo_base.get_changes, 'path', 1, 'path', 2)


class ResourceManagerTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)

    def test_resource_changeset(self):
        res = Resource('changeset', '42')
        self.assertEqual('Changeset 42', get_resource_description(self.env, res))
        self.assertEqual('/trac.cgi/changeset/42',
                         get_resource_url(self.env, res, self.env.href))

        repo = Resource('repository', 'repo')
        res = Resource('changeset', '42', parent=repo)
        self.assertEqual('Changeset 42 in repo',
                         get_resource_description(self.env, res))
        self.assertEqual('/trac.cgi/changeset/42/repo',
                         get_resource_url(self.env, res, self.env.href))

    def test_resource_source(self):
        res = Resource('source', '/trunk/src')
        self.assertEqual('path /trunk/src',
                         get_resource_description(self.env, res))
        self.assertEqual('/trac.cgi/browser/trunk/src',
                         get_resource_url(self.env, res, self.env.href))

        repo = Resource('repository', 'repo')
        res = Resource('source', '/trunk/src', parent=repo)
        self.assertEqual('path /trunk/src in repo',
                         get_resource_description(self.env, res))
        self.assertEqual('/trac.cgi/browser/repo/trunk/src',
                         get_resource_url(self.env, res, self.env.href))

        repo = Resource('repository', 'repo')
        res = Resource('source', '/trunk/src', version=42, parent=repo)
        self.assertEqual('path /trunk/src@42 in repo',
                         get_resource_description(self.env, res))
        self.assertEqual('/trac.cgi/browser/repo/trunk/src?rev=42',
                         get_resource_url(self.env, res, self.env.href))


    def test_resource_repository(self):
        res = Resource('repository', 'testrepo')
        self.assertEqual('Repository testrepo',
                         get_resource_description(self.env, res))
        self.assertEqual('/trac.cgi/browser/testrepo',
                         get_resource_url(self.env, res, self.env.href))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ApiTestCase, 'test'))
    suite.addTest(unittest.makeSuite(ResourceManagerTestCase, 'test'))
    return suite


if __name__ == '__main__':
    unittest.main()
