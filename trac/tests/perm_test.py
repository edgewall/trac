from trac import perm
from trac.tests.environment import EnvironmentTestBase

import os
import tempfile
import unittest


class PermTestCase(EnvironmentTestBase, unittest.TestCase):
    def setUp(self):
        EnvironmentTestBase.setUp(self)
        cursor = self.db.cursor()
        # Add a few groups
        cursor.execute("INSERT INTO permission "
                       "VALUES('employee', 'REPORT_ADMIN')")
        cursor.execute("INSERT INTO permission "
                       "VALUES('developer', 'WIKI_ADMIN')")
        cursor.execute("INSERT INTO permission "
                       "VALUES('developer', 'employee')")
        cursor.execute("INSERT INTO permission "
                       "VALUES('bob', 'developer')")
        self.db.commit()
        self.cache = perm.PermissionCache(self.db, 'bob')
    def test1(self):
        self.assertEqual(self.cache.has_permission(perm.WIKI_VIEW), 1)
    def test2(self):
        self.assertEqual(self.cache.has_permission(perm.REPORT_MODIFY), 1)
    def test3(self):
        self.assertEqual(self.cache.has_permission(perm.TRAC_ADMIN), 0)
    def test4(self):
        self.cache.assert_permission(perm.WIKI_VIEW)
    def test5(self):
        self.cache.assert_permission(perm.REPORT_ADMIN)
    def test6(self):
        self.assertRaises(perm.PermissionError,
                          self.cache.assert_permission, perm.TRAC_ADMIN)
        
def suite():
    return unittest.makeSuite(PermTestCase,'test')

if __name__ == '__main__':
    unittest.main()
