#!/usr/bin/env python

"""
Import a Bugzilla items into a Trac database.

Requires:  Trac 0.7.1 from http://trac.edgewall.com/
           Python 2.3 from http://www.python.org/
           MySQL >= 3.23 from http://www.mysql.org/

Thanks:    Mark Rowe <mrowe@bluewire.net.nz> 
            for original TracDatabase class
           
Copyright 2004, Dmitry Yusupov <dmitry_yus@yahoo.com>

Many enhancements, Bill Soudan <bill@soudan.net>
"""

###
### Conversion Settings -- edit these before running if desired
###

# Bugzilla version.  You can find this in Bugzilla's globals.pl file.
#
# Currently, the following bugzilla versions are known to work:
#   2.11
#
# If you run this script on a version not listed here and it is successful,
# please report it to the Trac mailing list so we can update the list.
BZ_VERSION = '2.16.5'

# MySQL connection parameters for the Bugzilla database.  These can also 
# be specified on the command line.
BZ_DB = ''
BZ_HOST = 'localhost'
BZ_USER = ''
BZ_PASSWORD = ''

# Path to the Trac environment.
TRAC_ENV = ''

# If true, all existing Trac tickets and attachments will be removed 
# prior to import.
TRAC_CLEAN = False

# Enclose imported ticket description and comments in a {{{ }}} 
# preformat block?  This formats the text in a fixed-point font.
PREFORMAT_COMMENTS = False

# By default, all bugs are imported from Bugzilla.  If you add a list
# of products here, only bugs from those products will be imported.
PRODUCTS = []

# Trac doesn't have the concept of a product.  Instead, this script can
# assign keywords in the ticket entry to represent products.
#
# ex. PRODUCT_KEYWORDS = { 'product1' : 'PRODUCT1_KEYWORD' }
PRODUCT_KEYWORDS = {}

# Bug comments that should not be imported.  Each entry in list should
# be a regular expression.
IGNORE_COMMENTS = [
   '^Created an attachment \(id='
]

###########################################################################
### You probably don't need to change any configuration past this line. ###
###########################################################################

# Bugzilla status to Trac status translation map.
#
# NOTE: bug activity is translated as well, which may cause bug
# activity to be deleted (e.g. resolved -> closed in Bugzilla
# would translate into closed -> closed in Trac, so we just ignore the
# change).
#
# There is some special magic for open in the code:  if there is no
# Bugzilla owner, open is mapped to 'new' instead.
STATUS_TRANSLATE = {
  'unconfirmed' : 'new',
  'open' : 'assigned',
  'resolved' : 'closed',
  'verified' : 'closed',
  'released' : 'closed'
}

# Translate Bugzilla statuses into Trac keywords.  This provides a way 
# to retain the Bugzilla statuses in Trac.  e.g. when a bug is marked 
# 'verified' in Bugzilla it will be assigned a VERIFIED keyword.
STATUS_KEYWORDS = {
  'verified' : 'VERIFIED',
  'released' : 'RELEASED'
}

# Some fields in Bugzilla do not have equivalents in Trac.  Changes in
# fields listed here will not be imported into the ticket change history,
# otherwise you'd see changes for fields that don't exist in Trac.
IGNORED_ACTIVITY_FIELDS = ['everconfirmed']

###
### Script begins here
###

import os
import re
import sys
import string
import StringIO

import MySQLdb
import MySQLdb.cursors
import trac.env

if not hasattr(sys, 'setdefaultencoding'):
    reload(sys)

sys.setdefaultencoding('latin1')

# simulated Attachment class for trac.add
class Attachment:
    def __init__(self, name, data):
        self.filename = name
        self.file = StringIO.StringIO(data.tostring())
  
# simple field translation mapping.  if string not in
# mapping, just return string, otherwise return value
class FieldTranslator(dict):
    def __getitem__(self, item):
        if not dict.has_key(self, item):
            return item
            
        return dict.__getitem__(self, item)

statusXlator = FieldTranslator(STATUS_TRANSLATE)

class TracDatabase(object):
    def __init__(self, path):
        self.env = trac.env.Environment(path)
        self._db = self.env.get_db_cnx()
        self._db.autocommit = False
        self.loginNameCache = {}
        self.fieldNameCache = {}
    
    def db(self):
        return self._db
    
    def hasTickets(self):
        c = self.db().cursor()
        c.execute('''SELECT count(*) FROM Ticket''')
        return int(c.fetchall()[0][0]) > 0

    def assertNoTickets(self):
        if self.hasTickets():
            raise Exception("Will not modify database with existing tickets!")
    
    def setSeverityList(self, s):
        """Remove all severities, set them to `s`"""
        self.assertNoTickets()
        
        c = self.db().cursor()
        c.execute("""DELETE FROM enum WHERE type='severity'""")
        for value, i in s:
            print "inserting severity ", value, " ", i
            c.execute("""INSERT INTO enum (type, name, value) VALUES (%s, %s, %s)""",
                      "severity", value.encode('utf-8'), i)
        self.db().commit()
    
    def setPriorityList(self, s):
        """Remove all priorities, set them to `s`"""
        self.assertNoTickets()
        
        c = self.db().cursor()
        c.execute("""DELETE FROM enum WHERE type='priority'""")
        for value, i in s:
            print "inserting priority ", value, " ", i
            c.execute("""INSERT INTO enum (type, name, value) VALUES (%s, %s, %s)""",
                      "priority",
                      value.encode('utf-8'),
                      i)
        self.db().commit()

    
    def setComponentList(self, l, key):
        """Remove all components, set them to `l`"""
        self.assertNoTickets()
        
        c = self.db().cursor()
        c.execute("""DELETE FROM component""")
        for comp in l:
            print "inserting component '",comp[key],"', owner",  comp['owner']
            c.execute("""INSERT INTO component (name, owner) VALUES (%s, %s)""",
                      comp[key].encode('utf-8'), comp['owner'].encode('utf-8'))
        self.db().commit()
    
    def setVersionList(self, v, key):
        """Remove all versions, set them to `v`"""
        self.assertNoTickets()
        
        c = self.db().cursor()
        c.execute("""DELETE FROM version""")
        for vers in v:
            print "inserting version ", vers[key]
            c.execute("""INSERT INTO version (name) VALUES (%s)""",
                      vers[key].encode('utf-8'))
        self.db().commit()
        
    def setMilestoneList(self, m, key):
        """Remove all milestones, set them to `m`"""
        self.assertNoTickets()
        
        c = self.db().cursor()
        c.execute("""DELETE FROM milestone""")
        for ms in m:
            print "inserting milestone ", ms[key]
            c.execute("""INSERT INTO milestone (name) VALUES (%s)""",
                      ms[key].encode('utf-8'))
        self.db().commit()
    
    def addTicket(self, id, time, changetime, component,
                  severity, priority, owner, reporter, cc,
                  version, milestone, status, resolution,
                  summary, description, keywords):
        c = self.db().cursor()
        
        desc = description.encode('utf-8')
        
        if PREFORMAT_COMMENTS:
          desc = '{{{\n%s\n}}}' % desc

        print "inserting ticket %s -- %s" % (id, summary)
        c.execute("""INSERT INTO ticket (id, time, changetime, component,
                                         severity, priority, owner, reporter, cc,
                                         version, milestone, status, resolution,
                                         summary, description, keywords)
                                 VALUES (%s, %s, %s, %s,
                                         %s, %s, %s, %s, %s,
                                         %s, %s, %s, %s,
                                         %s, %s, %s)""",
                  id, time.strftime('%s'), changetime.strftime('%s'), component.encode('utf-8'),
                  severity.encode('utf-8'), priority.encode('utf-8'), owner, reporter, cc,
                  version, milestone.encode('utf-8'), status.lower(), resolution,
                  summary.encode('utf-8'), desc, keywords)
        
        self.db().commit()
        return self.db().db.sqlite_last_insert_rowid()
    
    def addTicketComment(self, ticket, time, author, value):
        comment = value.encode('utf-8')
        
        if PREFORMAT_COMMENTS:
          comment = '{{{\n%s\n}}}' % comment

        c = self.db().cursor()
        c.execute("""INSERT INTO ticket_change (ticket, time, author, field, oldvalue, newvalue)
                                 VALUES        (%s, %s, %s, %s, %s, %s)""",
                  ticket, time.strftime('%s'), author, 'comment', '', comment)
        self.db().commit()

    def addTicketChange(self, ticket, time, author, field, oldvalue, newvalue):
        c = self.db().cursor()
        c.execute("""INSERT INTO ticket_change (ticket, time, author, field, oldvalue, newvalue)
                                 VALUES        (%s, %s, %s, %s, %s, %s)""",
                  ticket, time.strftime('%s'), author, field, oldvalue.encode('utf-8'), newvalue.encode('utf-8'))
        self.db().commit()
        
    def addAttachment(self, id, attachment, description, author):
        print 'inserting attachment for ticket %s -- %s' % (id, description)
        attachment.filename = attachment.filename.encode('utf-8')
        self.env.create_attachment(self.db(), 'ticket', str(id), attachment, description.encode('utf-8'),
            author, 'unknown')
        
    def getLoginName(self, cursor, userid):
        if userid not in self.loginNameCache:
            cursor.execute("SELECT * FROM profiles WHERE userid = %s" % userid)
            loginName = cursor.fetchall()

            if loginName:
                loginName = loginName[0]['login_name']
            else:
                print 'warning: unknown bugzilla userid %d, recording as anonymous' % userid
                loginName = 'anonymous'

            self.loginNameCache[userid] = loginName

        return self.loginNameCache[userid]

    def getFieldName(self, cursor, fieldid):
        if fieldid not in self.fieldNameCache:
            cursor.execute("SELECT * FROM fielddefs WHERE fieldid = %s" % fieldid)
            fieldName = cursor.fetchall()

            if fieldName:
                fieldName = fieldName[0]['name'].lower()
            else:
                print 'warning: unknown bugzilla fieldid %d, recording as unknown' % userid
                fieldName = 'unknown'

            self.fieldNameCache[fieldid] = fieldName

        return self.fieldNameCache[fieldid]

def productFilter(fieldName, products):
    first = True
    result = ''
    for product in products:
        if not first: 
            result += " or "
        first = False
        result += "%s = '%s'" % (fieldName, product)
    return result

def convert(_db, _host, _user, _password, _env, _force):
    activityFields = FieldTranslator()

    # account for older versions of bugzilla
    if BZ_VERSION == '2.11':
        print 'Using Buzvilla v%s schema.' % BZ_VERSION
        activityFields['removed'] = 'oldvalue'
        activityFields['added'] = 'newvalue'

    # init Bugzilla environment
    print "Bugzilla MySQL('%s':'%s':'%s':'%s'): connecting..." % (_db, _host, _user, _password)
    mysql_con = MySQLdb.connect(host=_host, 
                user=_user, passwd=_password, db=_db, compress=1, 
                cursorclass=MySQLdb.cursors.DictCursor)
    mysql_cur = mysql_con.cursor()

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
        c.execute("""DELETE FROM attachment""")
        os.system('rm -rf %s' % trac.env.get_attachments_dir())
        os.mkdir(trac.env.get_attachments_dir())
        trac.db().commit()


    print
    print "1. import severities..."
    severities = (('blocker', '1'), ('critical', '2'), ('major', '3'), ('normal', '4'),
        ('minor', '5'), ('trivial', '6'), ('enhancement', '7'))
    trac.setSeverityList(severities)

    print
    print "2. import components..."
    sql = "SELECT value, initialowner AS owner FROM components"
    if PRODUCTS:
       sql += " WHERE %s" % productFilter('program', PRODUCTS)
    mysql_cur.execute(sql)
    components = mysql_cur.fetchall()
    for component in components:
    		component['owner'] = trac.getLoginName(mysql_cur, component['owner'])
    trac.setComponentList(components, 'value')

    print
    print "3. import priorities..."
    priorities = (('P1', '1'), ('P2', '2'), ('P3', '3'), ('P4', '4'), ('P5', '5'))
    trac.setPriorityList(priorities)

    print
    print "4. import versions..."
    sql = "SELECT DISTINCTROW value FROM versions"
    if PRODUCTS:
       sql += " WHERE %s" % productFilter('program', PRODUCTS)
    mysql_cur.execute(sql)
    versions = mysql_cur.fetchall()
    trac.setVersionList(versions, 'value')

    print
    print "5. import milestones..."
    mysql_cur.execute("SELECT value FROM milestones")
    milestones = mysql_cur.fetchall()
    if milestones[0] == '---':
        trac.setMilestoneList(milestones, 'value')
    else:
        trac.setMilestoneList([], '')

    print
    print '6. retrieving bugs...'
    sql = "SELECT * FROM bugs "
    if PRODUCTS:
       sql += " WHERE %s" % productFilter('product', PRODUCTS)
    sql += " ORDER BY bug_id"
    mysql_cur.execute(sql)
    bugs = mysql_cur.fetchall()
    
    print
    print "7. import bugs and bug activity..."
    for bug in bugs:
        bugid = bug['bug_id']
        
        ticket = {}
        keywords = []
        ticket['id'] = bugid
        ticket['time'] = bug['creation_ts']
        ticket['changetime'] = bug['delta_ts']
        ticket['component'] = bug['component']
        ticket['severity'] = bug['bug_severity']
        ticket['priority'] = bug['priority']

        ticket['owner'] = trac.getLoginName(mysql_cur, bug['assigned_to'])
        ticket['reporter'] = trac.getLoginName(mysql_cur, bug['reporter'])

        mysql_cur.execute("SELECT * FROM cc WHERE bug_id = %s" % bugid)
        cc_records = mysql_cur.fetchall()
        cc_list = []
        for cc in cc_records:
            cc_list.append(trac.getLoginName(mysql_cur, cc['who']))
        ticket['cc'] = string.join(cc_list, ', ')

        ticket['version'] = bug['version']

        if bug['target_milestone'] == '---':
            ticket['milestone'] = ''
        else:
            ticket['milestone'] = bug['target_milestone']

        bug_status = bug['bug_status'].lower()
        ticket['status'] = statusXlator[bug_status]
        ticket['resolution'] = bug['resolution'].lower()

        # a bit of extra work to do open tickets
        if bug_status == 'open':
            if owner != '':
                ticket['status'] = 'assigned'
            else:
                ticket['status'] = 'new'

        ticket['summary'] = bug['short_desc']

        keywords = string.split(bug['keywords'], ' ')

        mysql_cur.execute("SELECT * FROM longdescs WHERE bug_id = %s" % bugid) 
        longdescs = list(mysql_cur.fetchall())

        # check for empty 'longdescs[0]' field...
        if len(longdescs) == 0:
            ticket['description'] = ''
        else:
            ticket['description'] = longdescs[0]['thetext']
            del longdescs[0]

        for desc in longdescs:
            ignore = False
            for comment in IGNORE_COMMENTS:
                if re.match(comment, desc['thetext']):
                    ignore = True
                    
            if ignore: continue
            
            trac.addTicketComment(ticket=bugid,
                time=desc['bug_when'],
                author=trac.getLoginName(mysql_cur, desc['who']),
                value=desc['thetext'])

        mysql_cur.execute("SELECT * FROM bugs_activity WHERE bug_id = %s ORDER BY bug_when" % bugid)
        bugs_activity = mysql_cur.fetchall()
        resolution = ''
        ticketChanges = []
        for activity in bugs_activity:
            field_name = trac.getFieldName(mysql_cur, activity['fieldid']).lower()
            
            removed = activity[activityFields['removed']]
            added = activity[activityFields['added']]

            # statuses and resolutions are in lowercase in trac
            if field_name == 'resolution' or field_name == 'bug_status':
                removed = removed.lower()
                added = added.lower()

            # remember most recent resolution, we need this later
            if field_name == 'resolution':
                resolution = added.lower()

            keywordChange = False
            oldKeywords = string.join(keywords, " ")

            # convert bugzilla field names...
            if field_name == 'bug_severity':
                field_name = 'severity'
            elif field_name == 'assigned_to':
                field_name = 'owner'
            elif field_name == 'bug_status':
                field_name = 'status'
                if removed in STATUS_KEYWORDS:
                    kw = STATUS_KEYWORDS[removed]
                    if kw in keywords:
                        keywords.remove(kw)
                    else:
                        oldKeywords = string.join(keywords + [ kw ], " ")
                    keywordChange = True
                if added in STATUS_KEYWORDS:
                    kw = STATUS_KEYWORDS[added]
                    keywords.append(kw)
                    keywordChange = True
                added = statusXlator[added]
                removed = statusXlator[removed]
            elif field_name == 'short_desc':
                field_name = 'summary'
            elif field_name == 'product':
                if removed in PRODUCT_KEYWORDS:
                    kw = PRODUCT_KEYWORDS[removed]
                    if kw in keywords:
                        keywords.remove(kw)
                    else:
                        oldKeywords = string.join(keywords + [ kw ], " ")
                    keywordChange = True
                if added in PRODUCT_KEYWORDS:
                    kw = PRODUCT_KEYWORDS[added]
                    keywords.append(kw)
                    keywordChange = True

            ticketChange = {}
            ticketChange['ticket'] = bugid
            ticketChange['time'] = activity['bug_when']
            ticketChange['author'] = trac.getLoginName(mysql_cur, activity['who'])
            ticketChange['field'] = field_name
            ticketChange['oldvalue'] = removed
            ticketChange['newvalue'] = added

            if keywordChange:
                newKeywords = string.join(keywords, " ")
                ticketChangeKw = ticketChange
                ticketChangeKw['field'] = 'keywords'
                ticketChangeKw['oldvalue'] = oldKeywords
                ticketChangeKw['newvalue'] = newKeywords
                #trac.addTicketChange(ticket=bugid, time=activity['bug_when'],
                #    author=trac.getLoginName(mysql_cur, activity['who']),
                #    field='keywords', oldvalue=oldKeywords, newvalue=newKeywords)
                ticketChanges.append(ticketChangeKw)

            if field_name in IGNORED_ACTIVITY_FIELDS:
                continue

            # skip changes that have no effect (think translation!)
            if added == removed:
                continue
                
            # bugzilla splits large summary changes into two records
            for oldChange in ticketChanges:
              if (field_name == 'summary'
                  and oldChange['field'] == ticketChange['field'] 
                  and oldChange['time'] == ticketChange['time'] 
                  and oldChange['author'] == ticketChange['author']):
                  oldChange['oldvalue'] += " " + ticketChange['oldvalue'] 
                  oldChange['newvalue'] += " " + ticketChange['newvalue']
                  break
            else:
                #trac.addTicketChange(ticket=bugid, time=activity['bug_when'],
                #    author=trac.getLoginName(mysql_cur, activity['who']),
                #    field=field_name, oldvalue=removed, newvalue=added)
                ticketChanges.append (ticketChange)

        for ticketChange in ticketChanges:
            trac.addTicketChange (**ticketChange)


        # for some reason, bugzilla v2.11 seems to clear the resolution
        # when you mark a bug as closed.  let's remember it and restore
        # it if the ticket is closed but there's no resolution.
        if not ticket['resolution'] and ticket['status'] == 'closed':
            ticket['resolution'] = resolution

        if bug['bug_status'] in STATUS_KEYWORDS:
            kw = STATUS_KEYWORDS[bug['bug_status']]
            # may have already been added during activity import
            if kw not in keywords:
                keywords.append(kw)

        if bug['product'] in PRODUCT_KEYWORDS:
            kw = PRODUCT_KEYWORDS[bug['product']]
            # may have already been added during activity import
            if kw not in keywords:
                keywords.append(kw)

        mysql_cur.execute("SELECT * FROM attachments WHERE bug_id = %s" % bugid)
        attachments = mysql_cur.fetchall()
        for a in attachments:
            author = trac.getLoginName(mysql_cur, a['submitter_id'])
            
            tracAttachment = Attachment(a['filename'], a['thedata'])
            trac.addAttachment(bugid, tracAttachment, a['description'], author)
            
        ticket['keywords'] = string.join(keywords)                
        ticketid = trac.addTicket(**ticket)

    print "Success!"

def usage():
    print "bugzilla2trac - Imports a bug database from Bugzilla into Trac."
    print
    print "Usage: bugzilla2trac.py [options]"
    print
    print "Available Options:"
    print "  --db <MySQL dbname>              - Bugzilla's database"
    print "  --tracenv /path/to/trac/env      - full path to Trac db environment"
    print "  -h | --host <MySQL hostname>     - Bugzilla's DNS host name"
    print "  -u | --user <MySQL username>     - effective Bugzilla's database user"
    print "  -p | --passwd <MySQL password>   - Bugzilla's user password"
    print "  -c | --clean                     - remove current Trac tickets before importing"
    print "  --help | help                    - this help info"
    print
    print "Additional configuration options can be defined directly in the script."
    print
    sys.exit(0)

def main():
    global BZ_DB, BZ_HOST, BZ_USER, BZ_PASSWORD, TRAC_ENV, TRAC_CLEAN
    if len (sys.argv) > 1:
        if sys.argv[1] in ['--help','help'] or len(sys.argv) < 4:
            usage()
        iter = 1
        while iter < len(sys.argv):
            if sys.argv[iter] in ['--db'] and iter+1 < len(sys.argv):
                BZ_DB = sys.argv[iter+1]
                iter = iter + 1
            elif sys.argv[iter] in ['-h', '--host'] and iter+1 < len(sys.argv):
                BZ_HOST = sys.argv[iter+1]
                iter = iter + 1
            elif sys.argv[iter] in ['-u', '--user'] and iter+1 < len(sys.argv):
                BZ_USER = sys.argv[iter+1]
                iter = iter + 1
            elif sys.argv[iter] in ['-p', '--passwd'] and iter+1 < len(sys.argv):
                BZ_PASSWORD = sys.argv[iter+1]
                iter = iter + 1
            elif sys.argv[iter] in ['--tracenv'] and iter+1 < len(sys.argv):
                TRAC_ENV = sys.argv[iter+1]
                iter = iter + 1
            elif sys.argv[iter] in ['-c', '--clean']:
                TRAC_CLEAN = 1
            else:
                print "Error: unknown parameter: " + sys.argv[iter]
                sys.exit(0)
            iter = iter + 1
    else:
        usage()
        
    convert(BZ_DB, BZ_HOST, BZ_USER, BZ_PASSWORD, TRAC_ENV, TRAC_CLEAN)

if __name__ == '__main__':
    main()
