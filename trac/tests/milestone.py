from trac.Milestone import Milestone
from trac.log import logger_factory
from trac.test import Mock
from trac.Ticket import Ticket

import unittest


class MilestoneTestCase(unittest.TestCase):

    def setUp(self):
        from trac.test import InMemoryDatabase
        self.db = InMemoryDatabase()
        self.env = Mock(log=logger_factory('test'),
                        get_db_cnx=lambda: self.db)
        self.perm = Mock(assert_permission=lambda x: None,
                         has_permission=lambda x: True)

    def test_new_milestone(self):
        milestone = Milestone(self.env, self.perm)
        self.assertEqual(False, milestone.exists)
        self.assertEqual(None, milestone.name)
        self.assertEqual(0, milestone.due)
        self.assertEqual(0, milestone.completed)
        self.assertEqual('', milestone.description)

    def test_existing_milestone(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO milestone (name) VALUES ('Test')")
        cursor.close()

        milestone = Milestone(self.env, self.perm, 'Test')
        self.assertEqual(True, milestone.exists)
        self.assertEqual('Test', milestone.name)
        self.assertEqual(0, milestone.due)
        self.assertEqual(0, milestone.completed)
        self.assertEqual('', milestone.description)

    def test_create_milestone(self):
        milestone = Milestone(self.env, self.perm)
        milestone.name = 'Test'
        milestone.insert()

        cursor = self.db.cursor()
        cursor.execute("SELECT name,due,completed,description FROM milestone "
                       "WHERE name='Test'")
        self.assertEqual(('Test', 0, 0, ''), cursor.fetchone())

    def test_create_milestone_without_name(self):
        milestone = Milestone(self.env, self.perm)
        self.assertRaises(AssertionError, milestone.insert)

    def test_delete_milestone(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO milestone (name) VALUES ('Test')")
        cursor.close()

        milestone = Milestone(self.env, self.perm, 'Test')
        milestone.delete()

        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM milestone WHERE name='Test'")
        self.assertEqual(None, cursor.fetchone())

    def test_delete_milestone_retarget_tickets(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO milestone (name) VALUES ('Test')")
        cursor.close()

        tkt1 = Ticket()
        tkt1.populate({'summary': 'Foo', 'milestone': 'Test'})
        tkt1.insert(self.db)
        tkt2 = Ticket()
        tkt2.populate({'summary': 'Bar', 'milestone': 'Test'})
        tkt2.insert(self.db)

        milestone = Milestone(self.env, self.perm, 'Test')
        milestone.delete(retarget_to='Other')

        self.assertEqual('Other', Ticket(self.db, tkt1['id'])['milestone'])
        self.assertEqual('Other', Ticket(self.db, tkt2['id'])['milestone'])

    def test_update_milestone(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO milestone (name) VALUES ('Test')")
        cursor.close()

        milestone = Milestone(self.env, self.perm, 'Test')
        milestone.due = 42
        milestone.completed = 43
        milestone.description = 'Foo bar'
        milestone.update()

        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM milestone WHERE name='Test'")
        self.assertEqual(('Test', 42, 43, 'Foo bar'), cursor.fetchone())

    def test_update_milestone_without_name(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO milestone (name) VALUES ('Test')")
        cursor.close()

        milestone = Milestone(self.env, self.perm, 'Test')
        milestone.name = None
        self.assertRaises(AssertionError, milestone.update)


    def test_update_milestone_update_tickets(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO milestone (name) VALUES ('Test')")
        cursor.close()

        tkt1 = Ticket()
        tkt1.populate({'summary': 'Foo', 'milestone': 'Test'})
        tkt1.insert(self.db)
        tkt2 = Ticket()
        tkt2.populate({'summary': 'Bar', 'milestone': 'Test'})
        tkt2.insert(self.db)

        milestone = Milestone(self.env, self.perm, 'Test')
        milestone.name = 'Testing'
        milestone.update()

        self.assertEqual('Testing', Ticket(self.db, tkt1['id'])['milestone'])
        self.assertEqual('Testing', Ticket(self.db, tkt2['id'])['milestone'])


def suite():
    return unittest.makeSuite(MilestoneTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
