# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2013 Edgewall Software
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
from datetime import datetime

from trac.resource import Resource, get_resource_description, get_resource_url
from trac.test import EnvironmentStub, Mock
from trac.util.datefmt import utc
from trac.versioncontrol.api import Changeset, EmptyChangeset, Node,\
                                    Repository


class ApiTestCase(unittest.TestCase):

    def test_changeset_raises(self):
        """Abstract base class raises a TypeError when instantiated
        directly."""
        self.assertRaises(TypeError, Node)

    def test_node_raises(self):
        """Abstract base class raises a TypeError when instantiated
        directly."""
        self.assertRaises(TypeError, Changeset)

    def test_repository_raises(self):
        """Abstract base class raises a TypeError when instantiated
        directly."""
        self.assertRaises(TypeError, Repository)

    def test_empty_changeset(self):
        repos = Mock()
        changeset = EmptyChangeset(repos, 1)

        self.assertEqual(repos, changeset.repos)
        self.assertEqual(1, changeset.rev)
        self.assertEqual('', changeset.author)
        self.assertEqual('', changeset.message)
        self.assertEqual(datetime(1970, 1, 1, tzinfo=utc), changeset.date)
        self.assertEqual([], list(changeset.get_changes()))


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

        res = Resource('repository', '')  # default repository
        self.assertEqual('Default repository',
                         get_resource_description(self.env, res))
        self.assertEqual('/trac.cgi/browser',
                         get_resource_url(self.env, res, self.env.href))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ApiTestCase))
    suite.addTest(unittest.makeSuite(ResourceManagerTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
