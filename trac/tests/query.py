from trac.test import Mock
from trac.Query import Query

import unittest


class QueryTestCase(unittest.TestCase):

    def setUp(self):
        self.env = Mock(config=Mock(options=lambda x: []))

    def test_all_ordered_by_id(self):
        query = Query(self.env, order='id')
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,milestone,component,time,changetime,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
ORDER BY COALESCE(id,0)=0,id""")

    def test_all_ordered_by_id_desc(self):
        query = Query(self.env, order='id', desc=1)
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,milestone,component,time,changetime,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
ORDER BY COALESCE(id,0)=0 DESC,id DESC""")

    def test_all_ordered_by_id_verbose(self):
        query = Query(self.env, order='id', verbose=1)
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,milestone,component,reporter,description,time,changetime,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
ORDER BY COALESCE(id,0)=0,id""")

    def test_all_ordered_by_priority(self):
        query = Query(self.env) # priority is default order
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,milestone,component,time,changetime,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
ORDER BY COALESCE(priority,'')='',priority.value,id""")

    def test_all_ordered_by_priority_desc(self):
        query = Query(self.env, desc=1) # priority is default order
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,milestone,component,time,changetime,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
ORDER BY COALESCE(priority,'')='' DESC,priority.value DESC,id""")

    def test_all_ordered_by_version(self):
        query = Query(self.env, order='version')
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,milestone,version,time,changetime,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
  LEFT OUTER JOIN version ON (version.name=version)
ORDER BY COALESCE(version,'')='',COALESCE(version.time,0)=0,version.time,version,id""")

    def test_all_ordered_by_version_desc(self):
        query = Query(self.env, order='version', desc=1)
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,milestone,version,time,changetime,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
  LEFT OUTER JOIN version ON (version.name=version)
ORDER BY COALESCE(version,'')='' DESC,COALESCE(version.time,0)=0 DESC,version.time DESC,version DESC,id""")

    def test_constrained_by_milestone(self):
        query = Query.from_string(self.env, 'milestone=milestone1', order='id')
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,component,version,time,changetime,milestone,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE COALESCE(milestone,'')='milestone1'
ORDER BY COALESCE(id,0)=0,id""")

    def test_all_grouped_by_milestone(self):
        query = Query(self.env, order='id', group='milestone')
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,component,version,milestone,time,changetime,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
  LEFT OUTER JOIN milestone ON (milestone.name=milestone)
ORDER BY COALESCE(milestone,'')='',COALESCE(milestone.due,0)=0,milestone.due,milestone,COALESCE(id,0)=0,id""")

    def test_all_grouped_by_milestone_desc(self):
        query = Query(self.env, order='id', group='milestone', groupdesc=1)
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,component,version,milestone,time,changetime,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
  LEFT OUTER JOIN milestone ON (milestone.name=milestone)
ORDER BY COALESCE(milestone,'')='' DESC,COALESCE(milestone.due,0)=0 DESC,milestone.due DESC,milestone DESC,COALESCE(id,0)=0,id""")

    def test_grouped_by_priority(self):
        query = Query(self.env, group='priority')
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,milestone,component,version,priority,time,changetime,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
ORDER BY COALESCE(priority,'')='',priority.value,id""")

    def test_constrained_by_milestone_not(self):
        query = Query.from_string(self.env, 'milestone!=milestone1', order='id')
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,milestone,status,owner,priority,component,time,changetime,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE COALESCE(milestone,'')!='milestone1'
ORDER BY COALESCE(id,0)=0,id""")

    def test_constrained_by_status(self):
        query = Query.from_string(self.env, 'status=new|assigned|reopened',
                                  order='id')
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,milestone,component,time,changetime,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE COALESCE(status,'') IN ('new','assigned','reopened')
ORDER BY COALESCE(id,0)=0,id""")

    def test_constrained_by_owner_containing(self):
        query = Query.from_string(self.env, 'owner~=someone', order='id')
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,owner,status,priority,milestone,component,time,changetime,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE COALESCE(owner,'') LIKE '%someone%'
ORDER BY COALESCE(id,0)=0,id""")

    def test_constrained_by_owner_not_containing(self):
        query = Query.from_string(self.env, 'owner!~=someone', order='id')
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,owner,status,priority,milestone,component,time,changetime,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE COALESCE(owner,'') NOT LIKE '%someone%'
ORDER BY COALESCE(id,0)=0,id""")

    def test_constrained_by_owner_beginswith(self):
        query = Query.from_string(self.env, 'owner^=someone', order='id')
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,owner,status,priority,milestone,component,time,changetime,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE COALESCE(owner,'') LIKE 'someone%'
ORDER BY COALESCE(id,0)=0,id""")

    def test_constrained_by_owner_endswith(self):
        query = Query.from_string(self.env, 'owner$=someone', order='id')
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,owner,status,priority,milestone,component,time,changetime,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE COALESCE(owner,'') LIKE '%someone'
ORDER BY COALESCE(id,0)=0,id""")

    def test_constrained_by_custom_field(self):
        self.env.config.options = lambda x: [('foo', 'text')]
        query = Query.from_string(self.env, 'foo=something', order='id')
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,status,owner,priority,milestone,component,time,changetime,priority.value AS priority_value, foo.value AS foo
FROM ticket
  LEFT OUTER JOIN ticket_custom AS foo ON (id=foo.ticket AND foo.name='foo')
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE COALESCE(foo,'')='something'
ORDER BY COALESCE(id,0)=0,id""")

    def test_constrained_by_multiple_owners(self):
        query = Query.from_string(self.env, 'owner=someone|someone_else',
                                  order='id')
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,owner,status,priority,milestone,component,time,changetime,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE COALESCE(owner,'') IN ('someone','someone_else')
ORDER BY COALESCE(id,0)=0,id""")

    def test_constrained_by_multiple_owners_not(self):
        query = Query.from_string(self.env, 'owner!=someone|someone_else',
                                  order='id')
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,owner,status,priority,milestone,component,time,changetime,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE COALESCE(owner,'') NOT IN ('someone','someone_else')
ORDER BY COALESCE(id,0)=0,id""")

    def test_constrained_by_multiple_owners_contain(self):
        query = Query.from_string(self.env, 'owner~=someone|someone_else',
                                  order='id')
        sql = query.get_sql()
        self.assertEqual(sql,
"""SELECT id,summary,owner,status,priority,milestone,component,time,changetime,priority.value AS priority_value
FROM ticket
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE (COALESCE(owner,'') LIKE '%someone%' OR COALESCE(owner,'') LIKE '%someone_else%')
ORDER BY COALESCE(id,0)=0,id""")


def suite():
    return unittest.makeSuite(QueryTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
