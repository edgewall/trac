# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

import unittest

import trac.tests.compat
from trac.test import Mock
from trac.versioncontrol.api import EmptyChangeset, NoSuchChangeset
from trac.versioncontrol.web_ui import util


class UtilTestCase(unittest.TestCase):

    def test_get_changes_raises_nosuchchangeset(self):
        def get_changeset(rev):
            raise NoSuchChangeset(rev)
        repos = Mock(get_changeset=lambda rev: get_changeset(rev))

        rev = 1
        changes = util.get_changes(repos, (rev, ))

        self.assertEqual(1, len(changes))
        self.assertIsInstance(changes[rev], EmptyChangeset)
        self.assertEqual(rev, changes[rev].rev)
        self.assertEqual(repos, changes[rev].repos)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(UtilTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
