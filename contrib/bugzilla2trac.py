"""
Import a Bugzilla items into a Trac database.

Requires:  Development version of Trac 0.7-pre from http://trac.edgewall.com/
           Python 2.3 from http://www.python.org/
	   MySQL >= 3.23 from http://www.mysql.org/

Thanks:    Mark Rowe <mrowe@bluewire.net.nz> 
			for original TracDatabase class
           
Copyright 2004, Dmitry Yusupov <dmitry_yus@yahoo.com>
"""

import sys
import MySQLdb
import MySQLdb.cursors
import trac.Environment

class TracDatabase(object):
    def __init__(self, path):
        self.env = trac.Environment.Environment(path)
        self._db = self.env.get_db_cnx()
        self._db.autocommit = False
    
    def db(self):
        return self._db
    
    def hasTickets(self):
        c = self.db().cursor()
        c.execute('''SELECT count(*) FROM Ticket''')
        return int(c.fetchall()[0][0]) > 0
    
    def setSeverityList(self, s):
        """Remove all severities, set them to `s`"""
        if self.hasTickets():
            raise Exception("Will not modify database with existing tickets!")
        
        c = self.db().cursor()
        c.execute("""DELETE FROM enum WHERE type='severity'""")
        for value, i in s:
            print "inserting severity ", value, " ", i
            c.execute("""INSERT INTO enum (type, name, value) VALUES (%s, %s, %s)""",
                      "severity", value, i)
        self.db().commit()
    
    def setPriorityList(self, s):
        """Remove all priorities, set them to `s`"""
        if self.hasTickets():
            raise Exception("Will not modify database with existing tickets!")
        
        c = self.db().cursor()
        c.execute("""DELETE FROM enum WHERE type='priority'""")
        for value, i in s:
            print "inserting priority ", value, " ", i
            c.execute("""INSERT INTO enum (type, name, value) VALUES (%s, %s, %s)""",
                      "priority",
                      value,
                      i)
        self.db().commit()

    
    def setComponentList(self, l, key):
        """Remove all components, set them to `l`"""
        if self.hasTickets():
            raise Exception("Will not modify database with existing tickets!")
        
        c = self.db().cursor()
        c.execute("""DELETE FROM component""")
        for comp in l:
            print "inserting component ", comp[key]
            c.execute("""INSERT INTO component (name) VALUES (%s)""",
                      comp[key])
        self.db().commit()
    
    def setVersionList(self, v, key):
        """Remove all versions, set them to `v`"""
        if self.hasTickets():
            raise Exception("Will not modify database with existing tickets!")
        
        c = self.db().cursor()
        c.execute("""DELETE FROM version""")
        for vers in v:
            print "inserting version ", vers[key]
            c.execute("""INSERT INTO version (name) VALUES (%s)""",
                      vers[key])
        self.db().commit()
        
    def setMilestoneList(self, m, key):
        """Remove all milestones, set them to `m`"""
        if self.hasTickets():
            raise Exception("Will not modify database with existing tickets!")
        
        c = self.db().cursor()
        c.execute("""DELETE FROM milestone""")
        for ms in m:
            print "inserting milestone ", ms[key]
            c.execute("""INSERT INTO milestone (name) VALUES (%s)""",
                      ms[key])
        self.db().commit()
    
    def addTicket(self, time, changetime, component,
                  severity, priority, owner, reporter, cc,
                  version, milestone, status, resolution,
                  summary, description, keywords):
        c = self.db().cursor()

        c.execute("""INSERT INTO ticket (time, changetime, component,
                                         severity, priority, owner, reporter, cc,
                                         version, milestone, status, resolution,
                                         summary, description, keywords)
                                 VALUES (%s, %s, %s,
                                         %s, %s, %s, %s, %s,
                                         %s, %s, %s, %s,
                                         %s, %s, %s)""",
                  time.strftime('%s'), changetime.strftime('%s'), component,
                  severity, priority, owner, reporter, cc,
                  version, milestone, status.lower(), resolution,
                  summary, '{{{\n%s\n}}}' % (description, ), keywords)
        self.db().commit()
        return self.db().db.sqlite_last_insert_rowid()
    
    def addTicketComment(self, ticket, time, author, value):
        c = self.db().cursor()
        c.execute("""INSERT INTO ticket_change (ticket, time, author, field, oldvalue, newvalue)
                                 VALUES        (%s, %s, %s, %s, %s, %s)""",
                  ticket, time.strftime('%s'), author, 'comment', '', '{{{\n%s\n}}}' % (value, ))
        self.db().commit()

    def addTicketChange(self, ticket, time, author, field, oldvalue, newvalue):
        c = self.db().cursor()
        c.execute("""INSERT INTO ticket_change (ticket, time, author, field, oldvalue, newvalue)
                                 VALUES        (%s, %s, %s, %s, %s, %s)""",
                  ticket, time.strftime('%s'), author, field, oldvalue, newvalue)
        self.db().commit()

class TheBugzillaConverter:
	def __init__(self, _db, _host, _user, _password, _env, _force):

		try:
			# init Bugzilla environment
			print "Bugzilla MySQL('%s':'%s':'%s':'%s'): connecting..." % (_db, _host, _user, _password)
			self.mysql_con = MySQLdb.connect(host=_host, 
						user=_user, passwd=_password, db=_db, compress=1, 
						cursorclass=MySQLdb.cursors.DictCursor)
			self.mysql_cur = self.mysql_con.cursor()

			# init Trac environment
			print "Trac SQLite('%s'): connecting..." % (_env)
			trac = TracDatabase(_env)

			# force mode...
			if _force == 1:
				print "cleaning all tickets..."
				c = trac.db().cursor()
				c.execute("""DELETE FROM ticket_change""")
				trac.db().commit()
				c.execute("""DELETE FROM ticket""")
				trac.db().commit()

			# 1. import all severities...
			severities = (('blocker', '1'), ('critical', '2'), ('major', '3'), ('normal', '4'),
				('minor', '5'), ('trivial', '6'), ('enhancement', '7'))
			trac.setSeverityList(severities)

			# 2. import all components...
			self.mysql_cur.execute("SELECT value FROM components")
			components = self.mysql_cur.fetchall()
			trac.setComponentList(components, 'value')

			# 3. import all priorities...
			priorities = (('P1', '1'), ('P2', '2'), ('P3', '3'), ('P4', '4'), ('P5', '5'))
			trac.setPriorityList(priorities)

			# 4. import all versions...
			self.mysql_cur.execute("SELECT value FROM versions")
			versions = self.mysql_cur.fetchall()
			trac.setVersionList(versions, 'value')

			# 5. import all milestones...
			self.mysql_cur.execute("SELECT value FROM milestones")
			milestones = self.mysql_cur.fetchall()
			if milestones[0] == '---':
				trac.setMilestoneList(milestones, 'value')
			else:
				trac.setMilestoneList([], '')

			# 6. import tickets and history...
			self.mysql_cur.execute("SELECT * FROM bugs ORDER BY bug_id")
			bugs = self.mysql_cur.fetchall()
			ticket = {}
			for bug in bugs:
				ticket['time'] = bug['creation_ts']
				ticket['changetime'] = bug['delta_ts']
				ticket['component'] = bug['component']
				ticket['severity'] = bug['bug_severity']
				ticket['priority'] = bug['priority']

				self.mysql_cur.execute("SELECT * FROM profiles WHERE userid = " + 
								str(bug['assigned_to']))
				owner = self.mysql_cur.fetchall()

				# check for empty 'owner[0]' field...
				if len(owner) == 0:
					ticket['owner'] = ''
				else:
					ticket['owner'] = owner[0]['login_name']

				self.mysql_cur.execute("SELECT * FROM profiles WHERE userid = " + 
								str(bug['reporter']))
				reporter = self.mysql_cur.fetchall()

				# check for empty 'reporter[0]' field...
				if len(reporter) == 0:
					ticket['reporter'] = ''
				else:
					ticket['reporter'] = reporter[0]['login_name']

				self.mysql_cur.execute("SELECT * FROM cc WHERE bug_id = " + 
								str(bug['bug_id']))
				cc_list = self.mysql_cur.fetchall()
				cc_str = ''
				last = 1
				for cc in cc_list:
					self.mysql_cur.execute("SELECT * FROM profiles WHERE userid = " + 
									str(cc['who']))
					cc_profile = self.mysql_cur.fetchall()
					cc_str = cc_str + cc_profile[0]['login_name']
					if len(cc_list) != last:
						cc_str = cc_str + ', '
					last = last + 1
				ticket['cc'] = cc_str

				ticket['version'] = bug['version']

				if bug['target_milestone'] == '---':
					ticket['milestone'] = ''
				else:
					ticket['milestone'] = bug['target_milestone']

				ticket['status'] = bug['bug_status'].lower()
				ticket['resolution'] = bug['resolution'].lower()

				# convert bugzilla's status field...
				if ticket['status'] == 'open':
				    if owner != '':
					ticket['status'] = 'assigned'
				    else:
					ticket['status'] = 'new'
				elif ticket['status'] == 'review ready':
				    if ticket['owner'] != '':
					ticket['status'] = 'assigned'
				    else:
					ticket['status'] = 'new'
				    ticket['resolution'] = 'fixed'
				elif ticket['status'] == 'review completed':
					ticket['status'] = 'closed'
					ticket['resolution'] = 'fixed'
				elif ticket['status'] == 'review rejected':
				    if ticket['owner'] != '':
					ticket['status'] = 'assigned'
				    else:
					ticket['status'] = 'new'

				ticket['summary'] = bug['short_desc']

				self.mysql_cur.execute("SELECT * FROM longdescs WHERE bug_id = " + 
								str(bug['bug_id']))
				longdescs = self.mysql_cur.fetchall()

				# check for empty 'longdescs[0]' field...
				if len(longdescs) == 0:
					ticket['description'] = ''
				else:
					ticket['description'] = longdescs[0]['thetext']

				ticket['keywords'] = bug['keywords']

				i = trac.addTicket(time=ticket['time'],
					changetime=ticket['changetime'],
					component=ticket['component'],
					severity=ticket['severity'],
					priority=ticket['priority'],
					owner=ticket['owner'],
					reporter=ticket['reporter'],
					cc=ticket['cc'],
					version=ticket['version'],
					milestone=ticket['milestone'],
					status=ticket['status'],
					resolution=ticket['resolution'],
					summary=ticket['summary'],
					description=ticket['description'],
					keywords=ticket['keywords'])
				iter = 0
				for desc in longdescs:
					if iter == 0: 
						iter = iter + 1
						continue

					self.mysql_cur.execute("SELECT * FROM profiles WHERE userid = " + 
								str(desc['who']))
					who = self.mysql_cur.fetchall()

					# check for empty 'who[0]' field...
					if len(who) == 0:
						who_name = ''
					else:
						who_name = who[0]['login_name']

					trac.addTicketComment(ticket=i,
						time=desc['bug_when'],
						author=who_name,
						value=desc['thetext'])
					iter = iter + 1

				self.mysql_cur.execute("SELECT * FROM bugs_activity WHERE bug_id = " + 
								str(bug['bug_id']))
				bugs_activity = self.mysql_cur.fetchall()
				for activity in bugs_activity:
					self.mysql_cur.execute("SELECT * FROM profiles WHERE userid = " + 
								str(activity['who']))
					who = self.mysql_cur.fetchall()

					# check for empty 'who[0]' field...
					if len(who) == 0:
						who_name = ''
					else:
						who_name = who[0]['login_name']

					self.mysql_cur.execute("SELECT * FROM fielddefs WHERE fieldid = " + 
								str(activity['fieldid']))
					field = self.mysql_cur.fetchall()

					# check for empty 'field[0]' field...
					if len(field) == 0:
						field_name = ''
					else:
						field_name = field[0]['name'].lower()

					removed = activity['removed'].lower()
					added = activity['added'].lower()

					# convert bugzilla field names...
					if field_name == 'bug_severity':
						field_name = 'severity'
					elif field_name == 'assigned_to':
						field_name = 'owner'
					elif field_name == 'bug_status':
						field_name = 'status'
						if activity['removed'] == 'review ready':
							removed = 'assigned'
						elif activity['removed'] == 'review completed':
							removed = 'closed'
						elif activity['removed'] == 'review rejected':
							removed = 'assigned'
						if activity['added'] == 'review ready':
							added = 'assigned'
						elif activity['added'] == 'review completed':
							added = 'closed'
						elif activity['added'] == 'review rejected':
							added = 'assigned'

					elif field_name.lower() == 'short_desc':
						field_name = 'summary'

					try: 
						trac.addTicketChange(ticket=i,
							time=activity['bug_when'],
							author=who_name,
							field=field_name,
							oldvalue=removed,
							newvalue=added)
					except Exception, e:
						print "bug activity " + str(activity['fieldid']) + " skipped for reason: ", e

				print "inserted ticket ", str(i), " bug_id ", str(bug['bug_id'])

			print "Success!"

		except Exception, e:
			print 'Error:', e

def usage():
	print """\
Usage: bugzilla2trac.py --db <MySQL dbname>              - Bugzilla's database
                        [-h | --host <MySQL hostname>]   - Bugzilla's DNS host name
                        [-u | --user <MySQL username>]   - effective Bugzilla's database user
                        [-p | --passwd <MySQL password>] - Bugzilla's user password
			--tracenv /path/to/trac/env      - full path to Trac db environment
                        [-f | --force]                   - force to clean up Trac db
                        [--help | help]                  - this help info"""
	sys.exit(0)

if __name__ == "__main__":
	db = ''
	host = 'localhost'
	user = ''
	password = ''
	env = ''
	force = 0
	if len (sys.argv) > 1:
		if sys.argv[1] in ['--help','help'] or len(sys.argv) < 4:
			usage()
		iter = 1
		while iter < len(sys.argv):
			if sys.argv[iter] in ['--db'] and iter+1 < len(sys.argv):
				db = sys.argv[iter+1]
				iter = iter + 1
			elif sys.argv[iter] in ['-h', '--host'] and iter+1 < len(sys.argv):
				host = sys.argv[iter+1]
				iter = iter + 1
			elif sys.argv[iter] in ['-u', '--user'] and iter+1 < len(sys.argv):
				user = sys.argv[iter+1]
				iter = iter + 1
			elif sys.argv[iter] in ['-p', '--passwd'] and iter+1 < len(sys.argv):
				passwd = sys.argv[iter+1]
				iter = iter + 1
			elif sys.argv[iter] in ['--tracenv'] and iter+1 < len(sys.argv):
				env = sys.argv[iter+1]
				iter = iter + 1
			elif sys.argv[iter] in ['-f', '--force']:
				force = 1
			else:
				print "Error: unknown parameter: " + sys.argv[iter]
				sys.exit(0)
			iter = iter + 1
	else:
		usage()
	TheBugzillaConverter(db, host, user, password, env, force)
