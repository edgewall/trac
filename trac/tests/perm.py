from trac import perm

import unittest


class PermTestCase(unittest.TestCase):

    def setUp(self):
        from trac.test import InMemoryDatabase
        self.db = InMemoryDatabase()

        # Add a few groups
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO permission "
                       "VALUES('employee', 'REPORT_ADMIN')")
        cursor.execute("INSERT INTO permission "
                       "VALUES('developer', 'WIKI_ADMIN')")
        cursor.execute("INSERT INTO permission "
                       "VALUES('developer', 'employee')")
        cursor.execute("INSERT INTO permission "
                       "VALUES('bob', 'developer')")
        self.db.commit()
        self.perm = perm.PermissionCache(self.db, 'bob')

    def test_has_permission(self):
        self.assertEqual(1, self.perm.has_permission(perm.WIKI_VIEW))
        self.assertEqual(1, self.perm.has_permission(perm.REPORT_MODIFY))
        self.assertEqual(0, self.perm.has_permission(perm.TRAC_ADMIN))

    def test_assert_permission(self):
        self.perm.assert_permission(perm.WIKI_VIEW)
        self.perm.assert_permission(perm.REPORT_ADMIN)
        self.assertRaises(perm.PermissionError,
                          self.perm.assert_permission, perm.TRAC_ADMIN)


def suite():
    return unittest.makeSuite(PermTestCase,'test')

if __name__ == '__main__':
    unittest.main()
