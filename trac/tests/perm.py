from trac import perm
from trac.config import Configuration
from trac.core import *
from trac.test import EnvironmentStub

import unittest


class DefaultPermissionStoreTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=[perm.DefaultPermissionStore,
                                           perm.DefaultPermissionGroupProvider])
        self.store = perm.DefaultPermissionStore(self.env)

    def test_simple_actions(self):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.executemany("INSERT INTO permission VALUES (%s,%s)", [
                           ('john', 'WIKI_MODIFY'), ('john', 'REPORT_ADMIN'),
                           ('kate', 'TICKET_CREATE')])
        self.assertEquals(['WIKI_MODIFY', 'REPORT_ADMIN'],
                          self.store.get_user_permissions('john'))
        self.assertEquals(['TICKET_CREATE'], self.store.get_user_permissions('kate'))

    def test_simple_group(self):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.executemany("INSERT INTO permission VALUES (%s,%s)", [
                           ('dev', 'WIKI_MODIFY'), ('dev', 'REPORT_ADMIN'),
                           ('john', 'dev')])
        self.assertEquals(['WIKI_MODIFY', 'REPORT_ADMIN'],
                          self.store.get_user_permissions('john'))

    def test_nested_groups(self):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.executemany("INSERT INTO permission VALUES (%s,%s)", [
                           ('dev', 'WIKI_MODIFY'), ('dev', 'REPORT_ADMIN'),
                           ('admin', 'dev'), ('john', 'admin')])
        self.assertEquals(['WIKI_MODIFY', 'REPORT_ADMIN'],
                          self.store.get_user_permissions('john'))

    def test_builtin_groups(self):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.executemany("INSERT INTO permission VALUES (%s,%s)", [
                           ('authenticated', 'WIKI_MODIFY'),
                           ('authenticated', 'REPORT_ADMIN'),
                           ('anonymous', 'TICKET_CREATE')])
        self.assertEquals(['WIKI_MODIFY', 'REPORT_ADMIN', 'TICKET_CREATE'],
                          self.store.get_user_permissions('john'))
        self.assertEquals(['TICKET_CREATE'],
                          self.store.get_user_permissions('anonymous'))

    def test_get_all_permissions(self):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.executemany("INSERT INTO permission VALUES (%s,%s)", [
                           ('dev', 'WIKI_MODIFY'), ('dev', 'REPORT_ADMIN'),
                           ('john', 'dev')])
        expected = [('dev', 'WIKI_MODIFY'),
                    ('dev', 'REPORT_ADMIN'),
                    ('john', 'dev')]
        for res in self.store.get_all_permissions():
            self.failIf(res not in expected)


class TestPermissionRequestor(Component):
    implements(perm.IPermissionRequestor)

    def get_permission_actions(self):
        return ['TEST_CREATE', 'TEST_DELETE', 'TEST_MODIFY',
                ('TEST_ADMIN', ['TEST_CREATE', 'TEST_DELETE',
                                'TEST_MODIFY'])]

class PermissionSystemTestCase(unittest.TestCase):

    def setUp(self):
        from trac.core import ComponentMeta

        self.env = EnvironmentStub(enable=[perm.PermissionSystem,
                                           perm.DefaultPermissionStore,
                                           TestPermissionRequestor])
        self.perm = perm.PermissionSystem(self.env)

    def test_all_permissions(self):
        self.assertEqual({'TEST_CREATE': True, 'TEST_DELETE': True,
                          'TEST_MODIFY': True,  'TEST_ADMIN': True,
                          'TRAC_ADMIN': True},
                         self.perm.get_user_permissions())

    def test_simple_permissions(self):
        self.perm.grant_permission('bob', 'TEST_CREATE')
        self.perm.grant_permission('jane', 'TEST_DELETE')
        self.perm.grant_permission('jane', 'TEST_MODIFY')
        self.assertEqual({'TEST_CREATE': True},
                         self.perm.get_user_permissions('bob'))
        self.assertEqual({'TEST_DELETE': True, 'TEST_MODIFY': True},
                         self.perm.get_user_permissions('jane'))

    def test_meta_permissions(self):
        self.perm.grant_permission('bob', 'TEST_CREATE')
        self.perm.grant_permission('jane', 'TEST_ADMIN')
        self.assertEqual({'TEST_CREATE': True},
                         self.perm.get_user_permissions('bob'))
        self.assertEqual({'TEST_CREATE': True, 'TEST_DELETE': True,
                          'TEST_MODIFY': True,  'TEST_ADMIN': True},
                         self.perm.get_user_permissions('jane'))

    def test_get_all_permissions(self):
        self.perm.grant_permission('bob', 'TEST_CREATE')
        self.perm.grant_permission('jane', 'TEST_ADMIN')
        expected = [('bob', 'TEST_CREATE'),
                    ('jane', 'TEST_ADMIN')]
        for res in self.perm.get_all_permissions():
            self.failIf(res not in expected)


class PermTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=[perm.PermissionSystem,
                                           perm.DefaultPermissionStore,
                                           TestPermissionRequestor])
        # Add a few groups
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.executemany("INSERT INTO permission VALUES(%s,%s)", [
                           ('employee', 'TEST_MODIFY'),
                           ('developer', 'TEST_ADMIN'),
                           ('developer', 'employee'),
                           ('bob', 'developer')])
        db.commit()
        self.perm = perm.PermissionCache(self.env, 'bob')

    def test_has_permission(self):
        self.assertEqual(1, self.perm.has_permission('TEST_MODIFY'))
        self.assertEqual(1, self.perm.has_permission('TEST_ADMIN'))
        self.assertEqual(0, self.perm.has_permission('TRAC_ADMIN'))

    def test_assert_permission(self):
        self.perm.assert_permission('TEST_MODIFY')
        self.perm.assert_permission('TEST_ADMIN')
        self.assertRaises(perm.PermissionError,
                          self.perm.assert_permission, 'TRAC_ADMIN')


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(DefaultPermissionStoreTestCase, 'test'))
    suite.addTest(unittest.makeSuite(PermissionSystemTestCase, 'test'))
    suite.addTest(unittest.makeSuite(PermTestCase, 'test'))
    return suite

if __name__ == '__main__':
    unittest.main()
