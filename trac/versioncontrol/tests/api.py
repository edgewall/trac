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


def suite():
    return unittest.makeSuite(ApiTestCase, 'test')


if __name__ == '__main__':
    unittest.main()
