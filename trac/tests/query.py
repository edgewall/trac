from trac.Query import Query

import unittest


class QueryTestCase(unittest.TestCase):

    def setUp(self):
        class EnvironmentStub(object):
            def __init__(self):
                self.custom_fields = {}
            def get_config_items(self, section):
                if section != 'ticket-custom':
                    return None
                return self.custom_fields.items()
        self.env = EnvironmentStub()

    def test_all_ordered_by_id(self):
        query = Query(self.env, order='id')
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,milestone,component,time,changetime
FROM ticket
ORDER BY COALESCE(id,0)=0,id""")

    def test_all_ordered_by_id_desc(self):
        query = Query(self.env, order='id', desc=1)
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,milestone,component,time,changetime
FROM ticket
ORDER BY COALESCE(id,0)=0 DESC,id DESC""")

    def test_all_ordered_by_id_verbose(self):
        query = Query(self.env, order='id', verbose=1)
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,milestone,component,reporter,description,time,changetime
FROM ticket
ORDER BY COALESCE(id,0)=0,id""")

    def test_all_ordered_by_priority(self):
        query = Query(self.env) # priority is default order
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,milestone,component,time,changetime
FROM ticket
  LEFT OUTER JOIN (SELECT name AS priority_name, value AS priority_value FROM enum WHERE type='priority') ON priority_name=priority
ORDER BY COALESCE(priority,'')='',priority_value,id""")

    def test_all_ordered_by_priority_desc(self):
        query = Query(self.env, desc=1) # priority is default order
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,milestone,component,time,changetime
FROM ticket
  LEFT OUTER JOIN (SELECT name AS priority_name, value AS priority_value FROM enum WHERE type='priority') ON priority_name=priority
ORDER BY COALESCE(priority,'')='' DESC,priority_value DESC,id""")

    def test_all_ordered_by_version(self):
        query = Query(self.env, order='version')
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,milestone,version,time,changetime
FROM ticket
  LEFT OUTER JOIN (SELECT name AS version_name, time AS version_time FROM version) ON version_name=version
ORDER BY COALESCE(version,'')='',COALESCE(version_time,0)=0,version_time,version,id""")

    def test_all_ordered_by_version_desc(self):
        query = Query(self.env, order='version', desc=1)
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,milestone,version,time,changetime
FROM ticket
  LEFT OUTER JOIN (SELECT name AS version_name, time AS version_time FROM version) ON version_name=version
ORDER BY COALESCE(version,'')='' DESC,COALESCE(version_time,0)=0 DESC,version_time DESC,version DESC,id""")

    def test_constrained_by_milestone(self):
        query = Query(self.env, order='id')
        query.constraints['milestone'] = ['milestone1']
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,component,version,time,changetime,milestone
FROM ticket
WHERE COALESCE(milestone,'')='milestone1'
ORDER BY COALESCE(id,0)=0,id""")

    def test_all_grouped_by_milestone(self):
        query = Query(self.env, order='id', group='milestone')
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,component,version,milestone,time,changetime
FROM ticket
  LEFT OUTER JOIN (SELECT name AS milestone_name, due AS milestone_time FROM milestone) ON milestone_name=milestone
ORDER BY COALESCE(milestone,'')='',COALESCE(milestone_time,0)=0,milestone_time,milestone,COALESCE(id,0)=0,id""")

    def test_all_grouped_by_milestone_desc(self):
        query = Query(self.env, order='id', group='milestone', groupdesc=1)
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,component,version,milestone,time,changetime
FROM ticket
  LEFT OUTER JOIN (SELECT name AS milestone_name, due AS milestone_time FROM milestone) ON milestone_name=milestone
ORDER BY COALESCE(milestone,'')='' DESC,COALESCE(milestone_time,0)=0 DESC,milestone_time DESC,milestone DESC,COALESCE(id,0)=0,id""")

    def test_grouped_by_priority(self):
        query = Query(self.env, group='priority')
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,milestone,component,version,priority,time,changetime
FROM ticket
  LEFT OUTER JOIN (SELECT name AS priority_name, value AS priority_value FROM enum WHERE type='priority') ON priority_name=priority
ORDER BY COALESCE(priority,'')='',priority_value,id""")

    def test_constrained_by_milestone_not(self):
        query = Query(self.env, order='id')
        query.constraints['milestone'] = ['!milestone1']
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,milestone,status,owner,priority,component,time,changetime
FROM ticket
WHERE COALESCE(milestone,'')!='milestone1'
ORDER BY COALESCE(id,0)=0,id""")

    def test_constrained_by_status(self):
        query = Query(self.env, order='id')
        query.constraints['status'] = ['new', 'assigned', 'reopened']
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,milestone,component,time,changetime
FROM ticket
WHERE COALESCE(status,'') IN ('new','assigned','reopened')
ORDER BY COALESCE(id,0)=0,id""")

    def test_constrained_by_owner_containing(self):
        query = Query(self.env, order='id')
        query.constraints['owner'] = ['~someone']
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,owner,status,priority,milestone,component,time,changetime
FROM ticket
WHERE COALESCE(owner,'') LIKE '%someone%'
ORDER BY COALESCE(id,0)=0,id""")

    def test_constrained_by_owner_not_containing(self):
        query = Query(self.env, order='id')
        query.constraints['owner'] = ['!~someone']
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,owner,status,priority,milestone,component,time,changetime
FROM ticket
WHERE COALESCE(owner,'') NOT LIKE '%someone%'
ORDER BY COALESCE(id,0)=0,id""")

    def test_constrained_by_owner_beginswith(self):
        query = Query(self.env, order='id')
        query.constraints['owner'] = ['^someone']
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,owner,status,priority,milestone,component,time,changetime
FROM ticket
WHERE COALESCE(owner,'') LIKE 'someone%'
ORDER BY COALESCE(id,0)=0,id""")

    def test_constrained_by_owner_endswith(self):
        query = Query(self.env, order='id')
        query.constraints['owner'] = ['$someone']
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,owner,status,priority,milestone,component,time,changetime
FROM ticket
WHERE COALESCE(owner,'') LIKE '%someone'
ORDER BY COALESCE(id,0)=0,id""")

    def test_constrained_by_custom_field(self):
        self.env.custom_fields.update({'foo': 'text'})
        query = Query(self.env, order='id')
        query.constraints['foo'] = ['something']
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,milestone,component,time,changetime, foo.value AS foo
FROM ticket
  LEFT OUTER JOIN ticket_custom AS foo ON (id=foo.ticket AND foo.name='foo')
WHERE COALESCE(foo,'')='something'
ORDER BY COALESCE(id,0)=0,id""")

    def test_constrained_by_multiple_owners(self):
        query = Query(self.env, order='id')
        query.constraints['owner'] = ['someone', 'someone_else']
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,owner,status,priority,milestone,component,time,changetime
FROM ticket
WHERE COALESCE(owner,'') IN ('someone','someone_else')
ORDER BY COALESCE(id,0)=0,id""")

    def test_constrained_by_multiple_owners_not(self):
        query = Query(self.env, order='id')
        query.constraints['owner'] = ['!someone', '!someone_else']
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,owner,status,priority,milestone,component,time,changetime
FROM ticket
WHERE COALESCE(owner,'') NOT IN ('someone','someone_else')
ORDER BY COALESCE(id,0)=0,id""")

    def test_constrained_by_multiple_owners_contain(self):
        query = Query(self.env, order='id')
        query.constraints['owner'] = ['~someone', '~someone_else']
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,owner,status,priority,milestone,component,time,changetime
FROM ticket
WHERE (COALESCE(owner,'') LIKE '%someone%' OR COALESCE(owner,'') LIKE '%someone_else%')
ORDER BY COALESCE(id,0)=0,id""")

def suite():
    return unittest.makeSuite(QueryTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
