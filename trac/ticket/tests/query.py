from trac.mimeview import Context
from trac.test import Mock, EnvironmentStub, MockPerm
from trac.ticket.query import Query, QueryModule, TicketQueryMacro
from trac.util.datefmt import utc
from trac.web.href import Href
from trac.wiki.formatter import LinkFormatter

import unittest
import difflib

# Note: we don't want to replicate 1:1 all the SQL dialect abstraction
#       methods from the trac.db layer here. 

class QueryTestCase(unittest.TestCase):

    def prettifySQL(self, sql):
        """Returns a prettified version of the SQL as a list of lines to help
        in creating a useful diff between two SQL statements."""
        pretty = []
        for line in sql.split('\n'):
            pretty.extend([ "%s,\n" % x for x in line.split(',')])
        return pretty

    def assertEqualSQL(self, sql, correct_sql):
        sql_split = self.prettifySQL(sql)
        correct_sql_split = self.prettifySQL(correct_sql)
        sql_diff = ''.join(list(
            difflib.unified_diff(correct_sql_split, sql_split)
        ))
        failure_message = "%r != %r\n" % (sql, correct_sql) + sql_diff
        self.assertEqual(sql, correct_sql, failure_message)

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.db = self.env.get_db_cnx()
        self.req = Mock(href=self.env.href, authname='anonymous', tz=utc)
        
    def tearDown(self):
        self.env.reset_db()

    def test_all_ordered_by_id(self):
        query = Query(self.env, order='id')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
ORDER BY COALESCE(t.id,0)=0,t.id""")
        self.assertEqual([], args)
        tickets = query.execute(self.req)

    def test_all_ordered_by_id_desc(self):
        query = Query(self.env, order='id', desc=1)
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
ORDER BY COALESCE(t.id,0)=0 DESC,t.id DESC""")
        self.assertEqual([], args)
        tickets = query.execute(self.req)

    def test_all_ordered_by_id_verbose(self):
        query = Query(self.env, order='id', verbose=1)
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.milestone AS milestone,t.reporter AS reporter,t.description AS description,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
ORDER BY COALESCE(t.id,0)=0,t.id""")
        self.assertEqual([], args)
        tickets = query.execute(self.req)

    def test_all_ordered_by_id_from_unicode(self):
        query = Query.from_string(self.env, u'order=id')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
ORDER BY COALESCE(t.id,0)=0,t.id""")
        self.assertEqual([], args)
        tickets = query.execute(self.req)

    def test_all_ordered_by_priority(self):
        query = Query(self.env) # priority is default order
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
ORDER BY COALESCE(priority.value,'')='',%(cast_priority)s,t.id""" % {
          'cast_priority': self.env.get_db_cnx().cast('priority.value', 'int')})
        self.assertEqual([], args)
        tickets = query.execute(self.req)

    def test_all_ordered_by_priority_desc(self):
        query = Query(self.env, desc=1) # priority is default order
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
ORDER BY COALESCE(priority.value,'')='' DESC,%(cast_priority)s DESC,t.id""" % {
          'cast_priority': self.env.get_db_cnx().cast('priority.value', 'int')})
        self.assertEqual([], args)
        tickets = query.execute(self.req)

    def test_all_ordered_by_version(self):
        query = Query(self.env, order='version')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.version AS version,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
  LEFT OUTER JOIN version ON (version.name=version)
ORDER BY COALESCE(t.version,'')='',COALESCE(version.time,0)=0,version.time,t.version,t.id""")
        self.assertEqual([], args)
        tickets = query.execute(self.req)

    def test_all_ordered_by_version_desc(self):
        query = Query(self.env, order='version', desc=1)
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.version AS version,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
  LEFT OUTER JOIN version ON (version.name=version)
ORDER BY COALESCE(t.version,'')='' DESC,COALESCE(version.time,0)=0 DESC,version.time DESC,t.version DESC,t.id""")
        self.assertEqual([], args)
        tickets = query.execute(self.req)

    def test_constrained_by_milestone(self):
        query = Query.from_string(self.env, 'milestone=milestone1', order='id')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.component AS component,t.time AS time,t.changetime AS changetime,t.milestone AS milestone,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE ((COALESCE(t.milestone,'')=%s))
ORDER BY COALESCE(t.id,0)=0,t.id""")
        self.assertEqual(['milestone1'], args)
        tickets = query.execute(self.req)

    def test_all_grouped_by_milestone(self):
        query = Query(self.env, order='id', group='milestone')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.component AS component,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
  LEFT OUTER JOIN milestone ON (milestone.name=milestone)
ORDER BY COALESCE(t.milestone,'')='',COALESCE(milestone.completed,0)=0,milestone.completed,COALESCE(milestone.due,0)=0,milestone.due,t.milestone,COALESCE(t.id,0)=0,t.id""")
        self.assertEqual([], args)
        tickets = query.execute(self.req)

    def test_all_grouped_by_milestone_desc(self):
        query = Query(self.env, order='id', group='milestone', groupdesc=1)
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.component AS component,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
  LEFT OUTER JOIN milestone ON (milestone.name=milestone)
ORDER BY COALESCE(t.milestone,'')='' DESC,COALESCE(milestone.completed,0)=0 DESC,milestone.completed DESC,COALESCE(milestone.due,0)=0 DESC,milestone.due DESC,t.milestone DESC,COALESCE(t.id,0)=0,t.id""")
        self.assertEqual([], args)
        tickets = query.execute(self.req)

    def test_grouped_by_priority(self):
        query = Query(self.env, group='priority')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.milestone AS milestone,t.component AS component,t.priority AS priority,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
ORDER BY COALESCE(priority.value,'')='',%(cast_priority)s,t.id""" % {
          'cast_priority': self.env.get_db_cnx().cast('priority.value', 'int')})
        self.assertEqual([], args)
        tickets = query.execute(self.req)

    def test_constrained_by_milestone_not(self):
        query = Query.from_string(self.env, 'milestone!=milestone1', order='id')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.milestone AS milestone,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE ((COALESCE(t.milestone,'')!=%s))
ORDER BY COALESCE(t.id,0)=0,t.id""")
        self.assertEqual(['milestone1'], args)
        tickets = query.execute(self.req)

    def test_constrained_by_status(self):
        query = Query.from_string(self.env, 'status=new|assigned|reopened',
                                  order='id')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.status AS status,t.owner AS owner,t.type AS type,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE (COALESCE(t.status,'') IN (%s,%s,%s))
ORDER BY COALESCE(t.id,0)=0,t.id""")
        self.assertEqual(['new', 'assigned', 'reopened'], args)
        tickets = query.execute(self.req)

    def test_constrained_by_owner_containing(self):
        query = Query.from_string(self.env, 'owner~=someone', order='id')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE ((COALESCE(t.owner,'') %(like)s))
ORDER BY COALESCE(t.id,0)=0,t.id""" % {'like': self.env.get_db_cnx().like()})
        self.assertEqual(['%someone%'], args)
        tickets = query.execute(self.req)

    def test_constrained_by_owner_not_containing(self):
        query = Query.from_string(self.env, 'owner!~=someone', order='id')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE ((COALESCE(t.owner,'') NOT %(like)s))
ORDER BY COALESCE(t.id,0)=0,t.id""" % {'like': self.env.get_db_cnx().like()})
        self.assertEqual(['%someone%'], args)
        tickets = query.execute(self.req)

    def test_constrained_by_owner_beginswith(self):
        query = Query.from_string(self.env, 'owner^=someone', order='id')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE ((COALESCE(t.owner,'') %(like)s))
ORDER BY COALESCE(t.id,0)=0,t.id""" % {'like': self.env.get_db_cnx().like()})
        self.assertEqual(['someone%'], args)
        tickets = query.execute(self.req)

    def test_constrained_by_owner_endswith(self):
        query = Query.from_string(self.env, 'owner$=someone', order='id')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE ((COALESCE(t.owner,'') %(like)s))
ORDER BY COALESCE(t.id,0)=0,t.id""" % {'like': self.env.get_db_cnx().like()})
        self.assertEqual(['%someone'], args)
        tickets = query.execute(self.req)

    def test_constrained_by_custom_field(self):
        self.env.config.set('ticket-custom', 'foo', 'text')
        query = Query.from_string(self.env, 'foo=something', order='id')
        sql, args = query.get_sql()
        foo = self.db.quote('foo')
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value,%s.value AS %s
FROM ticket AS t
  LEFT OUTER JOIN ticket_custom AS %s ON (id=%s.ticket AND %s.name='foo')
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE ((COALESCE(%s.value,'')=%%s))
ORDER BY COALESCE(t.id,0)=0,t.id""" % ((foo,) * 6))
        self.assertEqual(['something'], args)
        tickets = query.execute(self.req)

    def test_grouped_by_custom_field(self):
        self.env.config.set('ticket-custom', 'foo', 'text')
        query = Query(self.env, group='foo', order='id')
        sql, args = query.get_sql()
        foo = self.db.quote('foo')
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value,%s.value AS %s
FROM ticket AS t
  LEFT OUTER JOIN ticket_custom AS %s ON (id=%s.ticket AND %s.name='foo')
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
ORDER BY COALESCE(%s.value,'')='',%s.value,COALESCE(t.id,0)=0,t.id""" %
        ((foo,) * 7))
        self.assertEqual([], args)
        tickets = query.execute(self.req)

    def test_constrained_by_multiple_owners(self):
        query = Query.from_string(self.env, 'owner=someone|someone_else',
                                  order='id')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE (COALESCE(t.owner,'') IN (%s,%s))
ORDER BY COALESCE(t.id,0)=0,t.id""")
        self.assertEqual(['someone', 'someone_else'], args)
        tickets = query.execute(self.req)

    def test_constrained_by_multiple_owners_not(self):
        query = Query.from_string(self.env, 'owner!=someone|someone_else',
                                  order='id')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE (COALESCE(t.owner,'') NOT IN (%s,%s))
ORDER BY COALESCE(t.id,0)=0,t.id""")
        self.assertEqual(['someone', 'someone_else'], args)
        tickets = query.execute(self.req)

    def test_constrained_by_multiple_owners_contain(self):
        query = Query.from_string(self.env, 'owner~=someone|someone_else',
                                  order='id')
        sql, args = query.get_sql()
        self.assertEqual(['%someone%', '%someone/_else%'], args)
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE ((COALESCE(t.owner,'') %(like)s OR COALESCE(t.owner,'') %(like)s))
ORDER BY COALESCE(t.id,0)=0,t.id""" % {'like': self.env.get_db_cnx().like()})
        tickets = query.execute(self.req)

    def test_constrained_by_empty_value_contains(self):
        query = Query.from_string(self.env, 'owner~=|', order='id')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
ORDER BY COALESCE(t.id,0)=0,t.id""")
        self.assertEqual([], args)
        tickets = query.execute(self.req)

    def test_constrained_by_empty_value_startswith(self):
        query = Query.from_string(self.env, 'owner^=|', order='id')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
ORDER BY COALESCE(t.id,0)=0,t.id""")
        self.assertEqual([], args)
        tickets = query.execute(self.req)

    def test_constrained_by_empty_value_endswith(self):
        query = Query.from_string(self.env, 'owner$=|', order='id')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
ORDER BY COALESCE(t.id,0)=0,t.id""")
        self.assertEqual([], args)
        tickets = query.execute(self.req)

    def test_constrained_by_time_range(self):
        query = Query.from_string(self.env, 'created=2008-08-01..2008-09-01', order='id')
        sql, args = query.get_sql(self.req)
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.time AS time,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE (((%(cast_time)s>=%%s AND %(cast_time)s<%%s)))
ORDER BY COALESCE(t.id,0)=0,t.id""" % {
          'cast_time': self.env.get_db_cnx().cast('t.time', 'int64')})
        self.assertEqual([1217548800000000L, 1220227200000000L], args)
        tickets = query.execute(self.req)

    def test_constrained_by_time_range_exclusion(self):
        query = Query.from_string(self.env, 'created!=2008-08-01..2008-09-01', order='id')
        sql, args = query.get_sql(self.req)
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.time AS time,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE ((NOT (%(cast_time)s>=%%s AND %(cast_time)s<%%s)))
ORDER BY COALESCE(t.id,0)=0,t.id""" % {
          'cast_time': self.env.get_db_cnx().cast('t.time', 'int64')})
        self.assertEqual([1217548800000000L, 1220227200000000L], args)
        tickets = query.execute(self.req)

    def test_constrained_by_time_range_open_right(self):
        query = Query.from_string(self.env, 'created=2008-08-01..', order='id')
        sql, args = query.get_sql(self.req)
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.time AS time,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE ((%(cast_time)s>=%%s))
ORDER BY COALESCE(t.id,0)=0,t.id""" % {
          'cast_time': self.env.get_db_cnx().cast('t.time', 'int64')})
        self.assertEqual([1217548800000000L], args)
        tickets = query.execute(self.req)

    def test_constrained_by_time_range_open_left(self):
        query = Query.from_string(self.env, 'created=..2008-09-01', order='id')
        sql, args = query.get_sql(self.req)
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.time AS time,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE ((%(cast_time)s<%%s))
ORDER BY COALESCE(t.id,0)=0,t.id""" % {
          'cast_time': self.env.get_db_cnx().cast('t.time', 'int64')})
        self.assertEqual([1220227200000000L], args)
        tickets = query.execute(self.req)

    def test_constrained_by_time_range_modified(self):
        query = Query.from_string(self.env, 'modified=2008-08-01..2008-09-01', order='id')
        sql, args = query.get_sql(self.req)
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.changetime AS changetime,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.time AS time,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE (((%(cast_changetime)s>=%%s AND %(cast_changetime)s<%%s)))
ORDER BY COALESCE(t.id,0)=0,t.id""" % {
          'cast_changetime': self.env.get_db_cnx().cast('t.changetime', 'int64')})
        self.assertEqual([1217548800000000L, 1220227200000000L], args)
        tickets = query.execute(self.req)

    def test_constrained_by_keywords(self):
        query = Query.from_string(self.env, 'keywords~=foo -bar baz',
                                  order='id')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.keywords AS keywords,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE (((COALESCE(t.keywords,'') %(like)s AND COALESCE(t.keywords,'') NOT %(like)s AND COALESCE(t.keywords,'') %(like)s)))
ORDER BY COALESCE(t.id,0)=0,t.id""" % {'like': self.env.get_db_cnx().like()})
        self.assertEqual(['%foo%', '%bar%', '%baz%'], args)
        tickets = query.execute(self.req)

    def test_constrained_by_milestone_or_version(self):
        query = Query.from_string(self.env, 'milestone=milestone1&or&version=version1', order='id')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.component AS component,t.time AS time,t.changetime AS changetime,t.version AS version,t.milestone AS milestone,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE ((COALESCE(t.milestone,'')=%s)) OR ((COALESCE(t.version,'')=%s))
ORDER BY COALESCE(t.id,0)=0,t.id""")
        self.assertEqual(['milestone1', 'version1'], args)
        tickets = query.execute(self.req)

    def test_equal_in_value(self):
        query = Query.from_string(self.env, r'status=this=that&version=version1',
                                  order='id')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.priority AS priority,t.milestone AS milestone,t.component AS component,t.status AS status,t.time AS time,t.changetime AS changetime,t.version AS version,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE ((COALESCE(t.status,'')=%s) AND (COALESCE(t.version,'')=%s))
ORDER BY COALESCE(t.id,0)=0,t.id""")
        self.assertEqual(['this=that', 'version1'], args)
        tickets = query.execute(self.req)

    def test_special_character_escape(self):
        query = Query.from_string(self.env, r'status=here\&now|maybe\|later|back\slash',
                                  order='id')
        sql, args = query.get_sql()
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.status AS status,t.owner AS owner,t.type AS type,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE (COALESCE(t.status,'') IN (%s,%s,%s))
ORDER BY COALESCE(t.id,0)=0,t.id""")
        self.assertEqual(['here&now', 'maybe|later', 'back\\slash'], args)
        tickets = query.execute(self.req)

    def test_repeated_constraint_field(self):
        like_query = Query.from_string(self.env, 'owner!=someone|someone_else',
                                       order='id')
        query = Query.from_string(self.env, 'owner!=someone&owner!=someone_else',
                                  order='id')
        like_sql, like_args = like_query.get_sql()
        sql, args = query.get_sql()
        self.assertEqualSQL(sql, like_sql)
        self.assertEqual(args, like_args)
        tickets = query.execute(self.req)

    def test_user_var(self):
        query = Query.from_string(self.env, 'owner=$USER&order=id')
        sql, args = query.get_sql(req=self.req)
        self.assertEqualSQL(sql,
"""SELECT t.id AS id,t.summary AS summary,t.owner AS owner,t.type AS type,t.status AS status,t.priority AS priority,t.milestone AS milestone,t.time AS time,t.changetime AS changetime,priority.value AS priority_value
FROM ticket AS t
  LEFT OUTER JOIN enum AS priority ON (priority.type='priority' AND priority.name=priority)
WHERE ((COALESCE(t.owner,'')=%s))
ORDER BY COALESCE(t.id,0)=0,t.id""")
        self.assertEqual(['anonymous'], args)
        tickets = query.execute(self.req)

    def test_csv_escape(self):
        query = Mock(get_columns=lambda: ['col1'],
                     execute=lambda r,c: [{'id': 1,
                                           'col1': 'value, needs escaped'}],
                     time_fields=['time', 'changetime'])
        content, mimetype = QueryModule(self.env).export_csv(
                                Mock(href=self.env.href, perm=MockPerm()),
                                query)
        self.assertEqual('col1\r\n"value, needs escaped"\r\n',
                         content)

    def test_template_data(self):
        req = Mock(href=self.env.href, perm=MockPerm(), authname='anonymous',
                   tz=None)
        context = Context.from_request(req, 'query')

        query = Query.from_string(self.env, 'owner=$USER&order=id')
        tickets = query.execute(req)
        data = query.template_data(context, tickets, req=req)
        self.assertEqual(['anonymous'], data['clauses'][0]['owner']['values'])

        query = Query.from_string(self.env, 'owner=$USER&order=id')
        tickets = query.execute(req)
        data = query.template_data(context, tickets)
        self.assertEqual(['$USER'], data['clauses'][0]['owner']['values'])


class QueryLinksTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.query_module = QueryModule(self.env)
        req = Mock(perm=MockPerm(), args={}, href=Href('/'))
        self.formatter = LinkFormatter(self.env, Context.from_request(req))

    def tearDown(self):
        self.env.reset_db()

    def _format_link(self, query, label):
        return str(self.query_module._format_link(self.formatter, 'query',
                                                  query, label))

    def test_empty_query(self):
        self.assertEqual(self._format_link('', 'label'),
                         '<em class="error">[Error: Query filter requires '
                         'field and constraints separated by a "="]</em>')


class TicketQueryMacroTestCase(unittest.TestCase):

    def assertQueryIs(self, content, query, kwargs, format):
        qs, kw, f = TicketQueryMacro.parse_args(content)
        self.assertEqual(query, qs)
        self.assertEqual(kwargs, kw)
        self.assertEqual(format, f)
    
    def test_owner_and_milestone(self):
        self.assertQueryIs('owner=joe, milestone=milestone1',
                           'owner=joe&milestone=milestone1',
                           dict(col='status|summary', max='0', order='id'),
                           'list')

    def test_owner_or_milestone(self):
        self.assertQueryIs('owner=joe, or, milestone=milestone1',
                           'owner=joe&or&milestone=milestone1',
                           dict(col='status|summary', max='0', order='id'),
                           'list')
    
    def test_format_arguments(self):
        self.assertQueryIs('owner=joe, milestone=milestone1, col=component|severity, max=15, order=component, format=compact',
                           'owner=joe&milestone=milestone1',
                           dict(col='status|summary|component|severity', max='15', order='component'),
                           'compact')
        self.assertQueryIs('owner=joe, milestone=milestone1, col=id|summary|component, max=30, order=component, format=table',
                           'owner=joe&milestone=milestone1',
                           dict(col='id|summary|component', max='30', order='component'),
                           'table')

    def test_special_char_escaping(self):
        self.assertQueryIs(r'owner=joe|jack, milestone=this\&that\|here\,now',
                           r'owner=joe|jack&milestone=this\&that\|here,now',
                           dict(col='status|summary', max='0', order='id'),
                           'list')
        

def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(QueryTestCase, 'test'))
    suite.addTest(unittest.makeSuite(QueryLinksTestCase, 'test'))
    suite.addTest(unittest.makeSuite(TicketQueryMacroTestCase, 'test'))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
