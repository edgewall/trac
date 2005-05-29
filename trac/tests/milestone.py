from trac.Milestone import Milestone
from trac.log import logger_factory
from trac.test import Mock
from trac.ticket import Ticket

import unittest


class MilestoneTestCase(unittest.TestCase):

    def setUp(self):
        from trac.test import InMemoryDatabase
        self.db = InMemoryDatabase()
        self.env = Mock(log=logger_factory('test'),
                        get_db_cnx=lambda: self.db)

    def test_new_milestone(self):
        milestone = Milestone(self.env)
        self.assertEqual(False, milestone.exists)
        self.assertEqual(None, milestone.name)
        self.assertEqual(0, milestone.due)
        self.assertEqual(0, milestone.completed)
        self.assertEqual('', milestone.description)

    def test_new_milestone_empty_name(self):
        """
        Verifies that specifying an empty milestone name results in the
        milestone being correctly detected as non-existent.
        """
        milestone = Milestone(self.env, '')
        self.assertEqual(False, milestone.exists)
        self.assertEqual(None, milestone.name)
        self.assertEqual(0, milestone.due)
        self.assertEqual(0, milestone.completed)
        self.assertEqual('', milestone.description)

    def test_existing_milestone(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO milestone (name) VALUES ('Test')")
        cursor.close()

        milestone = Milestone(self.env, 'Test')
        self.assertEqual(True, milestone.exists)
        self.assertEqual('Test', milestone.name)
        self.assertEqual(0, milestone.due)
        self.assertEqual(0, milestone.completed)
        self.assertEqual('', milestone.description)

    def test_create_milestone(self):
        milestone = Milestone(self.env)
        milestone.name = 'Test'
        milestone.insert()

        cursor = self.db.cursor()
        cursor.execute("SELECT name,due,completed,description FROM milestone "
                       "WHERE name='Test'")
        self.assertEqual(('Test', 0, 0, ''), cursor.fetchone())

    def test_create_milestone_without_name(self):
        milestone = Milestone(self.env)
        self.assertRaises(AssertionError, milestone.insert)

    def test_delete_milestone(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO milestone (name) VALUES ('Test')")
        cursor.close()

        milestone = Milestone(self.env, 'Test')
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

        milestone = Milestone(self.env, 'Test')
        milestone.delete(retarget_to='Other')

        self.assertEqual('Other', Ticket(self.db, tkt1['id'])['milestone'])
        self.assertEqual('Other', Ticket(self.db, tkt2['id'])['milestone'])

    def test_update_milestone(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO milestone (name) VALUES ('Test')")
        cursor.close()

        milestone = Milestone(self.env, 'Test')
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

        milestone = Milestone(self.env, 'Test')
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

        milestone = Milestone(self.env, 'Test')
        milestone.name = 'Testing'
        milestone.update()

        self.assertEqual('Testing', Ticket(self.db, tkt1['id'])['milestone'])
        self.assertEqual('Testing', Ticket(self.db, tkt2['id'])['milestone'])

    def test_select_milestones(self):
        cursor = self.db.cursor()
        cursor.executemany("INSERT INTO milestone (name) VALUES (%s)",
                           [('1.0',), ('2.0',)])
        cursor.close()

        milestones = list(Milestone.select(self.env))
        self.assertEqual('1.0', milestones[0].name)
        assert milestones[0].exists
        self.assertEqual('2.0', milestones[1].name)
        assert milestones[1].exists


def suite():
    return unittest.makeSuite(MilestoneTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
