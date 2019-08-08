#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2019 Edgewall Software
# Copyright (C) 2004 Dmitry Yusupov <dmitry_yus@yahoo.com>
# Copyright (C) 2004 Mark Rowe <mrowe@bluewire.net.nz>
# Copyright (C) 2005 Bill Soudan <bill@soudan.net>
# Copyright (C) 2005 Florent Guillaume <fg@nuxeo.com>
# Copyright (C) 2005 Jeroen Ruigrok van der Werven <asmodai@in-nomine.org>
# Copyright (C) 2010 Jeff Moreland <hou5e@hotmail.com>
#
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.

"""
Import a Bugzilla items into a Trac database.

Requires:  Trac 0.9b1 from https://trac.edgewall.org/
           Python 2.3 from http://www.python.org/
           MySQL >= 3.23 from http://www.mysql.org/
           or PostGreSQL 8.4 from http://www.postgresql.org/
           or SQLite 3 from http://www.sqlite.org/

$Id$
"""

import re

###
### Conversion Settings -- edit these before running if desired
###

# Bugzilla version.  You can find this in Bugzilla's globals.pl file.
#
# Currently, the following bugzilla versions are known to work:
#   2.11 (2110), 2.16.5 (2165), 2.16.7 (2167),  2.18.3 (2183), 2.19.1 (2191),
#   2.23.3 (2233), 3.04.4 (3044)
#
# If you run this script on a version not listed here and it is successful,
# please file a ticket at https://trac.edgewall.org
#
BZ_VERSION = 3044

# MySQL connection parameters for the Bugzilla database.  These can also
# be specified on the command line.
BZ_DB = ""
BZ_HOST = ""
BZ_USER = ""
BZ_PASSWORD = ""

# Path to the Trac environment.
TRAC_ENV = "/usr/local/trac"

# If true, all existing Trac tickets and attachments will be removed
# prior to import.
TRAC_CLEAN = True

# Enclose imported ticket description and comments in a {{{ }}}
# preformat block?  This formats the text in a fixed-point font.
PREFORMAT_COMMENTS = False

# Replace bug numbers in comments with #xyz
REPLACE_BUG_NO = False

# Severities
SEVERITIES = [
    ("blocker",  "1"),
    ("critical", "2"),
    ("major",    "3"),
    ("normal",   "4"),
    ("minor",    "5"),
    ("trivial",  "6")
]

# Priorities
# If using the default Bugzilla priorities of P1 - P5, do not change anything
# here.
# If you have other priorities defined please change the P1 - P5 mapping to
# the order you want.  You can also collapse multiple priorities on bugzilla's
# side into the same priority on Trac's side, simply adjust PRIORITIES_MAP.
PRIORITIES = [
    ("highest", "1"),
    ("high",    "2"),
    ("normal",  "3"),
    ("low",     "4"),
    ("lowest",  "5")
]

# Bugzilla: Trac
# NOTE: Use lowercase.
PRIORITIES_MAP = {
    "p1": "highest",
    "p2": "high",
    "p3": "normal",
    "p4": "low",
    "p5": "lowest"
}

# By default, all bugs are imported from Bugzilla.  If you add a list
# of products here, only bugs from those products will be imported.
PRODUCTS = []
# These Bugzilla products will be ignored during import.
IGNORE_PRODUCTS = []

# These milestones are ignored
IGNORE_MILESTONES = ["---"]

# Don't import user names and passwords into htpassword if
# user is disabled in bugzilla? (i.e. profiles.DisabledText<>'')
IGNORE_DISABLED_USERS = True

# These logins are converted to these user ids
LOGIN_MAP = {
    #'some.user@example.com': 'someuser',
}

# These emails are removed from CC list
IGNORE_CC = [
    #'loser@example.com',
]

# The 'component' field in Trac can come either from the Product or
# or from the Component field of Bugzilla. COMPONENTS_FROM_PRODUCTS
# switches the behavior.
# If COMPONENTS_FROM_PRODUCTS is True:
# - Bugzilla Product -> Trac Component
# - Bugzilla Component -> Trac Keyword
# IF COMPONENTS_FROM_PRODUCTS is False:
# - Bugzilla Product -> Trac Keyword
# - Bugzilla Component -> Trac Component
COMPONENTS_FROM_PRODUCTS = False

# If COMPONENTS_FROM_PRODUCTS is True, the default owner for each
# Trac component is inferred from a default Bugzilla component.
DEFAULT_COMPONENTS = ["default", "misc", "main"]

# This mapping can assign keywords in the ticket entry to represent
# products or components (depending on COMPONENTS_FROM_PRODUCTS).
# The keyword will be ignored if empty.
KEYWORDS_MAPPING = {
    #'Bugzilla_product_or_component': 'Keyword',
    "default": "",
    "misc": "",
    }

# If this is True, products or components are all set as keywords
# even if not mentionned in KEYWORDS_MAPPING.
MAP_ALL_KEYWORDS = True

# Custom field mappings
CUSTOMFIELD_MAP = {
    #'Bugzilla_field_name': 'Trac_customfield_name',
    #'op_sys': 'os',
    #'cf_featurewantedby': 'wanted_by',
    #'product': 'product'
}

# Bug comments that should not be imported.  Each entry in list should
# be a regular expression.
IGNORE_COMMENTS = [
   "^Created an attachment \(id="
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
  "unconfirmed": "new",
  "open":        "assigned",
  "resolved":    "closed",
  "verified":    "closed",
  "released":    "closed"
}

# Translate Bugzilla statuses into Trac keywords.  This provides a way
# to retain the Bugzilla statuses in Trac.  e.g. when a bug is marked
# 'verified' in Bugzilla it will be assigned a VERIFIED keyword.
STATUS_KEYWORDS = {
  "verified": "VERIFIED",
  "released": "RELEASED"
}

# Some fields in Bugzilla do not have equivalents in Trac.  Changes in
# fields listed here will not be imported into the ticket change history,
# otherwise you'd see changes for fields that don't exist in Trac.
IGNORED_ACTIVITY_FIELDS = ["everconfirmed"]

# Regular expression and its replacement
# this expression will update references to bugs 1 - 99999 that
# have the form "bug 1" or "bug #1"
BUG_NO_RE = re.compile(r"\b(bug #?)([0-9]{1,5})\b", re.I)
BUG_NO_REPL = r"#\2"

###
### Script begins here
###

import io
import os
import sys
import string

import pymysql
from trac.attachment import Attachment
from trac.env import Environment

if not hasattr(sys, 'setdefaultencoding'):
    reload(sys)

sys.setdefaultencoding('latin1')

# simulated Attachment class for trac.add
#class Attachment:
#    def __init__(self, name, data):
#        self.filename = name
#        self.file = io.BytesIO(data.tostring())

# simple field translation mapping.  if string not in
# mapping, just return string, otherwise return value
class FieldTranslator(dict):
    def __getitem__(self, item):
        if item not in self:
            return item

        return dict.__getitem__(self, item)

statusXlator = FieldTranslator(STATUS_TRANSLATE)

class TracDatabase(object):
    def __init__(self, path):
        self.env = Environment(path)
        self.loginNameCache = {}
        self.fieldNameCache = {}
        from trac.db.api import DatabaseManager
        self.using_postgres = \
            DatabaseManager(self.env).connection_uri.startswith("postgres:")

    def hasTickets(self):
        return int(self.env.db_query("SELECT count(*) FROM ticket")[0][0] > 0)

    def assertNoTickets(self):
        if self.hasTickets():
            raise Exception("Will not modify database with existing tickets!")

    def setSeverityList(self, s):
        """Remove all severities, set them to `s`"""
        self.assertNoTickets()

        with self.env.db_transaction as db:
            db("DELETE FROM enum WHERE type='severity'")
            for value, i in s:
                print("  inserting severity '%s' - '%s'" % (value, i))
                db("""INSERT INTO enum (type, name, value)
                      VALUES (%s, %s, %s)""",
                   ("severity", value, i))

    def setPriorityList(self, s):
        """Remove all priorities, set them to `s`"""
        self.assertNoTickets()

        with self.env.db_transaction as db:
            db("DELETE FROM enum WHERE type='priority'")
            for value, i in s:
                print("  inserting priority '%s' - '%s'" % (value, i))
                db("INSERT INTO enum (type, name, value) VALUES (%s, %s, %s)",
                   ("priority", value, i))

    def setComponentList(self, l, key):
        """Remove all components, set them to `l`"""
        self.assertNoTickets()

        with self.env.db_transaction as db:
            db("DELETE FROM component")
            for comp in l:
                print("  inserting component '%s', owner '%s'"
                      % (comp[key], comp['owner']))
                db("INSERT INTO component (name, owner) VALUES (%s, %s)",
                   (comp[key], comp['owner']))

    def setVersionList(self, v, key):
        """Remove all versions, set them to `v`"""
        self.assertNoTickets()

        with self.env.db_transaction as db:
            db("DELETE FROM version")
            for vers in v:
                print("  inserting version '%s'" % vers[key])
                db("INSERT INTO version (name) VALUES (%s)",
                   (vers[key],))

    def setMilestoneList(self, m, key):
        """Remove all milestones, set them to `m`"""
        self.assertNoTickets()

        with self.env.db_transaction as db:
            db("DELETE FROM milestone")
            for ms in m:
                milestone = ms[key]
                print("  inserting milestone '%s'" % milestone)
                db("INSERT INTO milestone (name) VALUES (%s)",
                   (milestone,))

    def addTicket(self, id, time, changetime, component, severity, priority,
                  owner, reporter, cc, version, milestone, status, resolution,
                  summary, description, keywords, customfields):

        desc = description
        type = "defect"

        if SEVERITIES:
            if severity.lower() == "enhancement":
                severity = "minor"
                type = "enhancement"

        else:
            if priority.lower() == "enhancement":
                priority = "minor"
                type = "enhancement"

        if PREFORMAT_COMMENTS:
            desc = '{{{\n%s\n}}}' % desc

        if REPLACE_BUG_NO:
            if BUG_NO_RE.search(desc):
                desc = re.sub(BUG_NO_RE, BUG_NO_REPL, desc)

        if priority in PRIORITIES_MAP:
            priority = PRIORITIES_MAP[priority]

        print("  inserting ticket %s -- %s" % (id, summary))

        with self.env.db_transaction as db:
            db("""INSERT INTO ticket (id, type, time, changetime, component,
                                      severity, priority, owner, reporter, cc,
                                      version, milestone, status, resolution,
                                      summary, description, keywords)
                  VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          %s, %s, %s, %s)
                  """, (id, type, datetime2epoch(time),
                        datetime2epoch(changetime), component, severity,
                        priority, owner, reporter, cc, version, milestone,
                        status.lower(), resolution, summary, desc, keywords))

        if self.using_postgres:
            with self.env.db_transaction as db:
                c = db.cursor()
                c.execute("""
                    SELECT SETVAL('ticket_id_seq', MAX(id)) FROM ticket;
                    SELECT SETVAL('report_id_seq', MAX(id)) FROM report""")
                ticket_id = db.get_last_id(c, 'ticket')

        # add all custom fields to ticket
        for name, value in customfields.iteritems():
            self.addTicketCustomField(ticket_id, name, value)

        return ticket_id

    def addTicketCustomField(self, ticket_id, field_name, field_value):
        if field_value is None:
            return
        self.env.db_transaction("""
            INSERT INTO ticket_custom (ticket, name, value) VALUES (%s, %s, %s)
            """, (ticket_id, field_name, field_value))

    def addTicketComment(self, ticket, time, author, value):
        comment = value

        if PREFORMAT_COMMENTS:
            comment = '{{{\n%s\n}}}' % comment

        if REPLACE_BUG_NO:
            if BUG_NO_RE.search(comment):
                comment = re.sub(BUG_NO_RE, BUG_NO_REPL, comment)

        with self.env.db_transaction as db:
            db("""INSERT INTO ticket_change (ticket, time, author, field,
                                             oldvalue, newvalue)
                  VALUES (%s, %s, %s, %s, %s, %s)
                  """, (ticket, datetime2epoch(time), author, 'comment', '',
                        comment))

    def addTicketChange(self, ticket, time, author, field, oldvalue, newvalue):

        if field == "owner":
            if oldvalue in LOGIN_MAP:
                oldvalue = LOGIN_MAP[oldvalue]
            if newvalue in LOGIN_MAP:
                newvalue = LOGIN_MAP[newvalue]

        if field == "priority":
            if oldvalue.lower() in PRIORITIES_MAP:
                oldvalue = PRIORITIES_MAP[oldvalue.lower()]
            if newvalue.lower() in PRIORITIES_MAP:
                newvalue = PRIORITIES_MAP[newvalue.lower()]

        # Doesn't make sense if we go from highest -> highest, for example.
        if oldvalue == newvalue:
            return

        with self.env.db_transaction as db:
            db("""INSERT INTO ticket_change (ticket, time, author, field,
                                             oldvalue, newvalue)
                  VALUES (%s, %s, %s, %s, %s, %s)
                  """, (ticket, datetime2epoch(time), author, field,
                        oldvalue, newvalue))

    def addAttachment(self, author, a):
        if a['filename'] != '':
            description = a['description']
            id = a['bug_id']
            filename = a['filename']
            filedata = io.BytesIO(a['thedata'])
            filesize = len(filedata.getvalue())
            time = a['creation_ts']
            print("    ->inserting attachment '%s' for ticket %s -- %s"
                  % (filename, id, description))
            attachment = Attachment(self.env, 'ticket', id)
            attachment.author = author
            attachment.description = description
            attachment.insert(filename, filedata, filesize,
                              datetime2epoch(time))
            del attachment

    def getLoginName(self, cursor, userid):
        if userid not in self.loginNameCache:
            cursor.execute("SELECT * FROM profiles WHERE userid = %s", userid)
            loginName = cursor.fetchall()

            if loginName:
                loginName = loginName[0]['login_name']
            else:
                print("WARNING: unknown bugzilla userid %d, recording as"
                      "         anonymous" % userid)
                loginName = "anonymous"

            loginName = LOGIN_MAP.get(loginName, loginName)

            self.loginNameCache[userid] = loginName

        return self.loginNameCache[userid]

    def getFieldName(self, cursor, fieldid):
        if fieldid not in self.fieldNameCache:
            # fielddefs.fieldid got changed to fielddefs.id in Bugzilla
            # 2.23.3.
            if BZ_VERSION >= 2233:
                cursor.execute("SELECT * FROM fielddefs WHERE id = %s",
                               fieldid)
            else:
                cursor.execute("SELECT * FROM fielddefs WHERE fieldid = %s",
                               fieldid)
            fieldName = cursor.fetchall()

            if fieldName:
                fieldName = fieldName[0]['name'].lower()
            else:
                print("WARNING: unknown bugzilla fieldid %d, "
                      "         recording as unknown" % fieldid)
                fieldName = "unknown"

            self.fieldNameCache[fieldid] = fieldName

        return self.fieldNameCache[fieldid]

def makeWhereClause(fieldName, values, negative=False):
    if not values:
        return ''
    if negative:
        connector, op = ' AND ', '!='
    else:
        connector, op = ' OR ', '='
    clause = connector.join("%s %s '%s'" % (fieldName, op, value)
                            for value in values)
    return ' (' + clause + ')'

def convert(_db, _host, _user, _password, _env, _force):
    activityFields = FieldTranslator()

    # account for older versions of bugzilla
    print("Using Bugzilla v%s schema." % BZ_VERSION)
    if BZ_VERSION == 2110:
        activityFields['removed'] = "oldvalue"
        activityFields['added'] = "newvalue"

    # init Bugzilla environment
    print("Bugzilla MySQL('%s':'%s':'%s':'%s'): connecting..."
          % (_db, _host, _user, ("*" * len(_password))))
    mysql_con = pymysql.connect(host=_host,
                user=_user, passwd=_password, db=_db, compress=1,
                cursorclass=pymysql.cursors.DictCursor,
                charset='utf8')
    mysql_cur = mysql_con.cursor()

    # init Trac environment
    print("Trac SQLite('%s'): connecting..." % _env)
    trac = TracDatabase(_env)

    # force mode...
    if _force == 1:
        print("\nCleaning all tickets...")
        with trac.env.db_transaction as db:
            db("DELETE FROM ticket_change")
            db("DELETE FROM ticket")
            db("DELETE FROM ticket_custom")
            db("DELETE FROM attachment")
        # Straight from the Python documentation.
        for root, dirs, files in os.walk(trac.env.attachments_dir,
                                         topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        if not os.stat(trac.env.attachments_dir):
            os.mkdir(trac.env.attachments_dir)
        print("All tickets cleaned...")


    print("\n0. Filtering products...")
    if BZ_VERSION >= 2180:
        mysql_cur.execute("SELECT name FROM products")
    else:
        mysql_cur.execute("SELECT product AS name FROM products")
    products = []
    for line in mysql_cur.fetchall():
        product = line['name']
        if PRODUCTS and product not in PRODUCTS:
            continue
        if product in IGNORE_PRODUCTS:
            continue
        products.append(product)
    PRODUCTS[:] = products
    print("  Using products", " ".join(PRODUCTS))

    print("\n1. Import severities...")
    trac.setSeverityList(SEVERITIES)

    print("\n2. Import components...")
    if not COMPONENTS_FROM_PRODUCTS:
        if BZ_VERSION >= 2180:
            sql = """SELECT DISTINCT c.name AS name, c.initialowner AS owner
                               FROM components AS c, products AS p
                               WHERE c.product_id = p.id AND"""
            sql += makeWhereClause('p.name', PRODUCTS)
        else:
            sql = "SELECT value AS name, initialowner AS owner FROM components"
            sql += " WHERE" + makeWhereClause('program', PRODUCTS)
        mysql_cur.execute(sql)
        components = mysql_cur.fetchall()
        for component in components:
            component['owner'] = trac.getLoginName(mysql_cur,
                                                   component['owner'])
        trac.setComponentList(components, 'name')
    else:
        if BZ_VERSION >= 2180:
            sql = ("SELECT p.name AS product, c.name AS comp, "
                   " c.initialowner AS owner "
                   "FROM components c, products p "
                   "WHERE c.product_id = p.id AND" +
                   makeWhereClause('p.name', PRODUCTS))
        else:
            sql = ("SELECT program AS product, value AS comp, "
                   " initialowner AS owner "
                   "FROM components WHERE" +
                   makeWhereClause('program', PRODUCTS))
        mysql_cur.execute(sql)
        lines = mysql_cur.fetchall()
        all_components = {} # product -> components
        all_owners = {} # product, component -> owner
        for line in lines:
            product = line['product']
            comp = line['comp']
            owner = line['owner']
            all_components.setdefault(product, []).append(comp)
            all_owners[(product, comp)] = owner
        component_list = []
        for product, components in all_components.items():
            # find best default owner
            default = None
            for comp in DEFAULT_COMPONENTS:
                if comp in components:
                    default = comp
                    break
            if default is None:
                default = components[0]
            owner = all_owners[(product, default)]
            owner_name = trac.getLoginName(mysql_cur, owner)
            component_list.append({'product': product, 'owner': owner_name})
        trac.setComponentList(component_list, 'product')

    print("\n3. Import priorities...")
    trac.setPriorityList(PRIORITIES)

    print("\n4. Import versions...")
    if BZ_VERSION >= 2180:
        sql = """SELECT DISTINCTROW v.value AS value
                               FROM products p, versions v"""
        sql += " WHERE v.product_id = p.id AND"
        sql += makeWhereClause('p.name', PRODUCTS)
    else:
        sql = "SELECT DISTINCTROW value FROM versions"
        sql += " WHERE" + makeWhereClause('program', PRODUCTS)
    mysql_cur.execute(sql)
    versions = mysql_cur.fetchall()
    trac.setVersionList(versions, 'value')

    print("\n5. Import milestones...")
    sql = "SELECT DISTINCT value FROM milestones"
    sql += " WHERE" + makeWhereClause('value', IGNORE_MILESTONES, negative=True)
    mysql_cur.execute(sql)
    milestones = mysql_cur.fetchall()
    trac.setMilestoneList(milestones, 'value')

    print("\n6. Retrieving bugs...")
    if BZ_VERSION >= 2180:
        sql = """SELECT DISTINCT b.*, c.name AS component, p.name AS product
                            FROM bugs AS b, components AS c, products AS p """
        sql += " WHERE" + makeWhereClause('p.name', PRODUCTS)
        sql += " AND b.product_id = p.id"
        sql += " AND b.component_id = c.id"
        sql += " ORDER BY b.bug_id"
    else:
        sql = """SELECT DISTINCT b.*, c.value AS component, p.product AS product
                            FROM bugs AS b, components AS c, products AS p """
        sql += " WHERE" + makeWhereClause('p.product', PRODUCTS)
        sql += " AND b.product = p.product"
        sql += " AND b.component = c.value"
        sql += " ORDER BY b.bug_id"
    mysql_cur.execute(sql)
    bugs = mysql_cur.fetchall()


    print("\n7. Import bugs and bug activity...")
    for bug in bugs:

        bugid = bug['bug_id']

        ticket = {}
        keywords = []
        ticket['id'] = bugid
        ticket['time'] = bug['creation_ts']
        ticket['changetime'] = bug['delta_ts']
        if COMPONENTS_FROM_PRODUCTS:
            ticket['component'] = bug['product']
        else:
            ticket['component'] = bug['component']

        if SEVERITIES:
            ticket['severity'] = bug['bug_severity']
            ticket['priority'] = bug['priority'].lower()
        else:
            # use bugzilla severities as trac priorities, and ignore bugzilla
            # priorities
            ticket['severity'] = ''
            ticket['priority'] = bug['bug_severity']

        ticket['owner'] = trac.getLoginName(mysql_cur, bug['assigned_to'])
        ticket['reporter'] = trac.getLoginName(mysql_cur, bug['reporter'])

        # pack bugzilla fields into dictionary of trac custom field
        # names and values
        customfields = {}
        for bugfield, customfield in CUSTOMFIELD_MAP.iteritems():
            customfields[customfield] = bug[bugfield]
        ticket['customfields'] = customfields

        mysql_cur.execute("SELECT * FROM cc WHERE bug_id = %s", bugid)
        cc_records = mysql_cur.fetchall()
        cc_list = []
        for cc in cc_records:
            cc_list.append(trac.getLoginName(mysql_cur, cc['who']))
        cc_list = [cc for cc in cc_list if cc not in IGNORE_CC]
        ticket['cc'] = string.join(cc_list, ', ')

        ticket['version'] = bug['version']

        target_milestone = bug['target_milestone']
        if target_milestone in IGNORE_MILESTONES:
            target_milestone = ''
        ticket['milestone'] = target_milestone

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

            if ignore:
                continue

            trac.addTicketComment(ticket=bugid,
                time = desc['bug_when'],
                author=trac.getLoginName(mysql_cur, desc['who']),
                value = desc['thetext'])

        mysql_cur.execute("""SELECT * FROM bugs_activity WHERE bug_id = %s
                             ORDER BY bug_when""" % bugid)
        bugs_activity = mysql_cur.fetchall()
        resolution = ''
        ticketChanges = []
        keywords = []
        for activity in bugs_activity:
            field_name = trac.getFieldName(mysql_cur, activity['fieldid']).lower()

            removed = activity[activityFields['removed']]
            added = activity[activityFields['added']]

            # statuses and resolutions are in lowercase in trac
            if field_name in ('resolution', 'bug_status'):
                removed = removed.lower()
                added = added.lower()

            # remember most recent resolution, we need this later
            if field_name == "resolution":
                resolution = added.lower()

            add_keywords = []
            remove_keywords = []

            # convert bugzilla field names...
            if field_name == "bug_severity":
                if SEVERITIES:
                    field_name = "severity"
                else:
                    field_name = "priority"
            elif field_name == "assigned_to":
                field_name = "owner"
            elif field_name == "bug_status":
                field_name = "status"
                if removed in STATUS_KEYWORDS:
                    remove_keywords.append(STATUS_KEYWORDS[removed])
                if added in STATUS_KEYWORDS:
                    add_keywords.append(STATUS_KEYWORDS[added])
                added = statusXlator[added]
                removed = statusXlator[removed]
            elif field_name == "short_desc":
                field_name = "summary"
            elif field_name == "product" and COMPONENTS_FROM_PRODUCTS:
                field_name = "component"
            elif ((field_name == "product" and not COMPONENTS_FROM_PRODUCTS) or
                  (field_name == "component" and COMPONENTS_FROM_PRODUCTS)):
                if MAP_ALL_KEYWORDS or removed in KEYWORDS_MAPPING:
                    kw = KEYWORDS_MAPPING.get(removed, removed)
                    if kw:
                        remove_keywords.append(kw)
                if MAP_ALL_KEYWORDS or added in KEYWORDS_MAPPING:
                    kw = KEYWORDS_MAPPING.get(added, added)
                    if kw:
                        add_keywords.append(kw)
                if field_name == "component":
                    # just keep the keyword change
                    added = removed = ""
            elif field_name == "target_milestone":
                field_name = "milestone"
                if added in IGNORE_MILESTONES:
                    added = ""
                if removed in IGNORE_MILESTONES:
                    removed = ""

            ticketChange = {}
            ticketChange['ticket'] = bugid
            ticketChange['time'] = activity['bug_when']
            ticketChange['author'] = trac.getLoginName(mysql_cur,
                                                       activity['who'])
            ticketChange['field'] = field_name
            ticketChange['oldvalue'] = removed
            ticketChange['newvalue'] = added

            if add_keywords or remove_keywords:
                # ensure removed ones are in old
                old_keywords = keywords + [kw for kw in remove_keywords if kw
                                           not in keywords]
                # remove from new
                keywords = [kw for kw in keywords if kw not in remove_keywords]
                # add to new
                keywords += [kw for kw in add_keywords if kw not in keywords]
                if old_keywords != keywords:
                    ticketChangeKw = ticketChange.copy()
                    ticketChangeKw['field'] = "keywords"
                    ticketChangeKw['oldvalue'] = ' '.join(old_keywords)
                    ticketChangeKw['newvalue'] = ' '.join(keywords)
                    ticketChanges.append(ticketChangeKw)

            if field_name in IGNORED_ACTIVITY_FIELDS:
                continue

            # Skip changes that have no effect (think translation!).
            if added == removed:
                continue

            # Bugzilla splits large summary changes into two records.
            for oldChange in ticketChanges:
                if (field_name == "summary"
                    and oldChange['field'] == ticketChange['field']
                    and oldChange['time'] == ticketChange['time']
                    and oldChange['author'] == ticketChange['author']):
                    oldChange['oldvalue'] += " " + ticketChange['oldvalue']
                    oldChange['newvalue'] += " " + ticketChange['newvalue']
                    break
                # cc and attachments.isobsolete sometime appear
                # in different activities with same time
                if field_name in ('cc', 'attachments.isobsolete') and \
                        oldChange['time'] == ticketChange['time']:
                    oldChange['newvalue'] += ", " + ticketChange['newvalue']
                    break
            else:
                ticketChanges.append (ticketChange)

        for ticketChange in ticketChanges:
            trac.addTicketChange (**ticketChange)

        # For some reason, bugzilla v2.11 seems to clear the resolution
        # when you mark a bug as closed.  Let's remember it and restore
        # it if the ticket is closed but there's no resolution.
        if not ticket['resolution'] and ticket['status'] == "closed":
            ticket['resolution'] = resolution

        bug_status = bug['bug_status']
        if bug_status in STATUS_KEYWORDS:
            kw = STATUS_KEYWORDS[bug_status]
            if kw not in keywords:
                keywords.append(kw)

        product = bug['product']
        if product in KEYWORDS_MAPPING and not COMPONENTS_FROM_PRODUCTS:
            kw = KEYWORDS_MAPPING.get(product, product)
            if kw and kw not in keywords:
                keywords.append(kw)

        component = bug['component']
        if (COMPONENTS_FROM_PRODUCTS and
                (MAP_ALL_KEYWORDS or component in KEYWORDS_MAPPING)):
            kw = KEYWORDS_MAPPING.get(component, component)
            if kw and kw not in keywords:
                keywords.append(kw)

        ticket['keywords'] = string.join(keywords)
        ticketid = trac.addTicket(**ticket)

        if BZ_VERSION >= 2210:
            mysql_cur.execute("SELECT attachments.*, attach_data.thedata "
                              "FROM attachments, attach_data "
                              "WHERE attachments.bug_id = %s AND "
                              "attachments.attach_id = attach_data.id" % bugid)
        else:
            mysql_cur.execute("SELECT * FROM attachments WHERE bug_id = %s" %
                              bugid)
        attachments = mysql_cur.fetchall()
        for a in attachments:
            author = trac.getLoginName(mysql_cur, a['submitter_id'])
            trac.addAttachment(author, a)

    print("\n8. Importing users and passwords...")
    if BZ_VERSION >= 2164:
        selectlogins = "SELECT login_name, cryptpassword FROM profiles"
        if IGNORE_DISABLED_USERS:
            selectlogins = selectlogins + " WHERE disabledtext=''"
        mysql_cur.execute(selectlogins)
        users = mysql_cur.fetchall()
    else:
        users = ()
    with open('htpasswd', 'w') as f:
        for user in users:
            if user['login_name'] in LOGIN_MAP:
                login = LOGIN_MAP[user['login_name']]
            else:
                login = user['login_name']
            f.write(login + ':' + user['cryptpassword'] + '\n')

    print("  Bugzilla users converted to htpasswd format, see 'htpasswd'.")

    print("\nAll tickets converted.")

def log(msg):
    print("DEBUG: %s" % msg)

def datetime2epoch(dt) :
    import time
    return time.mktime(dt.timetuple()) * 1000000

def usage():
    print("""bugzilla2trac - Imports a bug database from Bugzilla into Trac.

Usage: bugzilla2trac.py [options]

Available Options:
  --db <MySQL dbname>              - Bugzilla's database name
  --tracenv /path/to/trac/env      - Full path to Trac db environment
  -h | --host <MySQL hostname>     - Bugzilla's DNS host name
  -u | --user <MySQL username>     - Effective Bugzilla's database user
  -p | --passwd <MySQL password>   - Bugzilla's user password
  -c | --clean                     - Remove current Trac tickets before
                                     importing
  -n | --noseverities              - import Bugzilla severities as Trac
                                     priorities and forget Bugzilla priorities
  --help | help                    - This help info

Additional configuration options can be defined directly in the script.
""")
    sys.exit(0)

def main():
    global BZ_DB, BZ_HOST, BZ_USER, BZ_PASSWORD, TRAC_ENV, TRAC_CLEAN
    global SEVERITIES, PRIORITIES, PRIORITIES_MAP
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
            elif sys.argv[iter] in ['-n', '--noseverities']:
                # treat Bugzilla severites as Trac priorities
                PRIORITIES = SEVERITIES
                SEVERITIES = []
                PRIORITIES_MAP = {}
            else:
                print("Error: unknown parameter: " + sys.argv[iter])
                sys.exit(0)
            iter = iter + 1

    convert(BZ_DB, BZ_HOST, BZ_USER, BZ_PASSWORD, TRAC_ENV, TRAC_CLEAN)

if __name__ == '__main__':
    main()
