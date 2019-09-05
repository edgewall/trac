# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2019 Edgewall Software
# Copyright (C) 2003-2005 Daniel Lundin <daniel@edgewall.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.
#
# Author: Daniel Lundin <daniel@edgewall.com>

from trac.db.schema import Table, Column, Index

# Database version identifier. Used for automatic upgrades.
db_version = 45

def __mkreports(reports):
    """Utility function used to create report data in same syntax as the
    default data. This extra step is done to simplify editing the default
    reports."""
    result = []
    for report in reports:
        result.append((None, report[0], report[2], report[1]))
    return result


##
## Database schema
##

schema = [
    # Common
    Table('system', key='name')[
        Column('name'),
        Column('value')],
    Table('permission', key=('username', 'action'))[
        Column('username'),
        Column('action')],
    Table('auth_cookie', key=('cookie', 'ipnr', 'name'))[
        Column('cookie'),
        Column('name'),
        Column('ipnr'),
        Column('time', type='int')],
    Table('session', key=('sid', 'authenticated'))[
        Column('sid'),
        Column('authenticated', type='int'),
        Column('last_visit', type='int'),
        Index(['last_visit']),
        Index(['authenticated'])],
    Table('session_attribute', key=('sid', 'authenticated', 'name'))[
        Column('sid'),
        Column('authenticated', type='int'),
        Column('name'),
        Column('value')],
    Table('cache', key='id')[
        Column('id', type='int'),
        Column('generation', type='int'),
        Column('key')],

    # Attachments
    Table('attachment', key=('type', 'id', 'filename'))[
        Column('type'),
        Column('id'),
        Column('filename'),
        Column('size', type='int'),
        Column('time', type='int64'),
        Column('description'),
        Column('author')],

    # Wiki system
    Table('wiki', key=('name', 'version'))[
        Column('name'),
        Column('version', type='int'),
        Column('time', type='int64'),
        Column('author'),
        Column('text'),
        Column('comment'),
        Column('readonly', type='int'),
        Index(['time'])],

    # Version control cache
    Table('repository', key=('id', 'name'))[
        Column('id', type='int'),
        Column('name'),
        Column('value')],
    Table('revision', key=('repos', 'rev'))[
        Column('repos', type='int'),
        Column('rev', key_size=40),
        Column('time', type='int64'),
        Column('author'),
        Column('message'),
        Index(['repos', 'time'])],
    Table('node_change', key='id')[
        Column('id', auto_increment=True),
        Column('repos', type='int'),
        Column('rev', key_size=40),
        Column('path', key_size=255),
        Column('node_type', size=1),
        Column('change_type', size=1),
        Column('base_path'),
        Column('base_rev'),
        Index(['repos', 'rev', 'path']),
        Index(['repos', 'path', 'rev'])],

    # Ticket system
    Table('ticket', key='id')[
        Column('id', auto_increment=True),
        Column('type'),
        Column('time', type='int64'),
        Column('changetime', type='int64'),
        Column('component'),
        Column('severity'),
        Column('priority'),
        Column('owner'),
        Column('reporter'),
        Column('cc'),
        Column('version'),
        Column('milestone'),
        Column('status'),
        Column('resolution'),
        Column('summary'),
        Column('description'),
        Column('keywords'),
        Index(['time']),
        Index(['status'])],
    Table('ticket_change', key=('ticket', 'time', 'field'))[
        Column('ticket', type='int'),
        Column('time', type='int64'),
        Column('author'),
        Column('field'),
        Column('oldvalue'),
        Column('newvalue'),
        Index(['ticket']),
        Index(['time'])],
    Table('ticket_custom', key=('ticket', 'name'))[
        Column('ticket', type='int'),
        Column('name'),
        Column('value')],
    Table('enum', key=('type', 'name'))[
        Column('type'),
        Column('name'),
        Column('value'),
        Column('description')],
    Table('component', key='name')[
        Column('name'),
        Column('owner'),
        Column('description')],
    Table('milestone', key='name')[
        Column('name'),
        Column('due', type='int64'),
        Column('completed', type='int64'),
        Column('description')],
    Table('version', key='name')[
        Column('name'),
        Column('time', type='int64'),
        Column('description')],

    # Report system
    Table('report', key='id')[
        Column('id', auto_increment=True),
        Column('author'),
        Column('title'),
        Column('query'),
        Column('description')],

    # Notification system
    Table('notify_subscription', key='id')[
        Column('id', auto_increment=True),
        Column('time', type='int64'),
        Column('changetime', type='int64'),
        Column('class'),
        Column('sid'),
        Column('authenticated', type='int'),
        Column('distributor'),
        Column('format'),
        Column('priority', type='int'),
        Column('adverb'),
        Index(['sid', 'authenticated']),
        Index(['class'])],
    Table('notify_watch', key='id')[
        Column('id', auto_increment=True),
        Column('sid'),
        Column('authenticated', type='int'),
        Column('class'),
        Column('realm'),
        Column('target'),
        Index(['sid', 'authenticated', 'class']),
        Index(['class', 'realm', 'target'])],
]


##
## Default Reports
##

def get_reports(db):
    return (
('Active Tickets',
"""\
 * List all active tickets by priority.
 * Color each row based on priority.
""",
"""\
SELECT p.value AS __color__,
   t.id AS ticket, t.summary, t.component, t.version, t.milestone,
   t.type AS type, t.owner, t.status, t.time AS created,
   t.changetime AS _changetime, t.description AS _description,
   t.reporter AS _reporter
  FROM ticket t
  LEFT JOIN enum p ON p.name = t.priority AND p.type = 'priority'
  WHERE t.status <> 'closed'
  ORDER BY """ + db.cast('p.value', 'int') + """, t.milestone, t.type, t.time
"""),
#----------------------------------------------------------------------------
 ('Active Tickets by Version',
"""\
This report shows how to color results by priority,
while grouping results by version.

Last modification time, description and reporter are included as hidden fields
for useful RSS export.
""",
"""\
SELECT p.value AS __color__,
   t.version AS __group__,
   t.id AS ticket, t.summary, t.component, t.version, t.type AS type,
   t.owner, t.status, t.time AS created,
   t.changetime AS _changetime, t.description AS _description,
   t.reporter AS _reporter
  FROM ticket t
  LEFT JOIN enum p ON p.name = t.priority AND p.type = 'priority'
  WHERE t.status <> 'closed'
  ORDER BY (t.version IS NULL), t.version, """ + db.cast('p.value', 'int') +
  """, t.type, t.time
"""),
#----------------------------------------------------------------------------
('Active Tickets by Milestone',
"""\
This report shows how to color results by priority,
while grouping results by milestone.

Last modification time, description and reporter are included as hidden fields
for useful RSS export.
""",
"""\
SELECT p.value AS __color__,
   %s AS __group__,
   t.id AS ticket, t.summary, t.component, t.version, t.type AS type,
   t.owner, t.status, t.time AS created, t.changetime AS _changetime,
   t.description AS _description, t.reporter AS _reporter
  FROM ticket t
  LEFT JOIN enum p ON p.name = t.priority AND p.type = 'priority'
  WHERE t.status <> 'closed'
  ORDER BY (t.milestone IS NULL), t.milestone, %s, t.type, t.time
""" % (db.concat("'Milestone '", 't.milestone'), db.cast('p.value', 'int'))),
#----------------------------------------------------------------------------
('Accepted, Active Tickets by Owner',
"""\
List accepted tickets, group by ticket owner, sorted by priority.
""",
"""\
SELECT p.value AS __color__,
   t.owner AS __group__,
   t.id AS ticket, t.summary, t.component, t.milestone, t.type AS type,
   t.time AS created, t.changetime AS _changetime,
   t.description AS _description, t.reporter AS _reporter
  FROM ticket t
  LEFT JOIN enum p ON p.name = t.priority AND p.type = 'priority'
  WHERE t.status = 'accepted'
  ORDER BY t.owner, """ + db.cast('p.value', 'int') + """, t.type, t.time
"""),
#----------------------------------------------------------------------------
('Accepted, Active Tickets by Owner (Full Description)',
"""\
List tickets accepted, group by ticket owner.
This report demonstrates the use of full-row display.
""",
"""\
SELECT p.value AS __color__,
   t.owner AS __group__,
   t.id AS ticket, t.summary, t.component, t.milestone, t.type AS type,
   t.time AS created, t.description AS _description_,
   t.changetime AS _changetime, t.reporter AS _reporter
  FROM ticket t
  LEFT JOIN enum p ON p.name = t.priority AND p.type = 'priority'
  WHERE t.status = 'accepted'
  ORDER BY t.owner, """ + db.cast('p.value', 'int') + """, t.type, t.time
"""),
#----------------------------------------------------------------------------
('All Tickets By Milestone  (Including closed)',
"""\
A more complex example to show how to make advanced reports.
""",
"""\
SELECT p.value AS __color__,
   t.milestone AS __group__,
   (CASE t.status
      WHEN 'closed' THEN 'color: #777; background: #ddd; border-color: #ccc;'
      ELSE
        (CASE t.owner WHEN $USER THEN 'font-weight: bold' END)
    END) AS __style__,
   t.id AS ticket, t.summary, t.component, t.status, t.resolution, t.version,
   t.type AS type, t.priority, t.owner, t.changetime AS modified,
   t.time AS _time, t.reporter AS _reporter
  FROM ticket t
  LEFT JOIN enum p ON p.name = t.priority AND p.type = 'priority'
  ORDER BY (t.milestone IS NULL), t.milestone DESC, (t.status = 'closed'),
        (CASE t.status WHEN 'closed' THEN t.changetime ELSE (-1) * %s END) DESC
""" % db.cast('p.value', 'int')),
#----------------------------------------------------------------------------
('My Tickets',
"""\
This report demonstrates the use of the automatically set
USER dynamic variable, replaced with the username of the
logged in user when executed.
""",
"""\
SELECT p.value AS __color__,
       (CASE
         WHEN t.owner = $USER AND t.status = 'accepted' THEN 'Accepted'
         WHEN t.owner = $USER THEN 'Owned'
         WHEN t.reporter = $USER THEN 'Reported'
         ELSE 'Commented' END) AS __group__,
       t.id AS ticket, t.summary, t.component, t.version, t.milestone,
       t.type AS type, t.priority, t.time AS created,
       t.changetime AS _changetime, t.description AS _description,
       t.reporter AS _reporter
  FROM ticket t
  LEFT JOIN enum p ON p.name = t.priority AND p.type = 'priority'
  WHERE t.status <> 'closed' AND
        (t.owner = $USER OR t.reporter = $USER OR
         EXISTS (SELECT * FROM ticket_change tc
                 WHERE tc.ticket = t.id AND tc.author = $USER AND
                       tc.field = 'comment'))
  ORDER BY (COALESCE(t.owner, '') = $USER AND t.status = 'accepted') DESC,
           COALESCE(t.owner, '') = $USER DESC,
           COALESCE(t.reporter, '') = $USER DESC,
           """ + db.cast('p.value', 'int') + """, t.milestone, t.type, t.time
"""),
#----------------------------------------------------------------------------
('Active Tickets, Mine first',
"""\
 * List all active tickets by priority.
 * Show all tickets owned by the logged in user in a group first.
""",
"""\
SELECT p.value AS __color__,
   (CASE t.owner
     WHEN $USER THEN 'My Tickets'
     ELSE 'Active Tickets'
    END) AS __group__,
   t.id AS ticket, t.summary, t.component, t.version, t.milestone,
   t.type AS type, t.owner, t.status, t.time AS created,
   t.changetime AS _changetime, t.description AS _description,
   t.reporter AS _reporter
  FROM ticket t
  LEFT JOIN enum p ON p.name = t.priority AND p.type = 'priority'
  WHERE t.status <> 'closed'
  ORDER BY (COALESCE(t.owner, '') = $USER) DESC, """
  + db.cast('p.value', 'int') + """, t.milestone, t.type, t.time
"""))


##
## Default database values
##

# (table, (column1, column2), ((row1col1, row1col2), (row2col1, row2col2)))
def get_data(db):
    return (('component',
              ('name', 'owner'),
                (('component1', 'somebody'),
                 ('component2', 'somebody'))),
            ('milestone',
              ('name', 'due', 'completed'),
                (('milestone1', 0, 0),
                 ('milestone2', 0, 0),
                 ('milestone3', 0, 0),
                 ('milestone4', 0, 0))),
            ('version',
              ('name', 'time'),
                (('1.0', 0),
                 ('2.0', 0))),
            ('enum',
              ('type', 'name', 'value'),
                (('resolution', 'fixed', '1'),
                 ('resolution', 'invalid', '2'),
                 ('resolution', 'wontfix', '3'),
                 ('resolution', 'duplicate', '4'),
                 ('resolution', 'worksforme', '5'),
                 ('priority', 'blocker', '1'),
                 ('priority', 'critical', '2'),
                 ('priority', 'major', '3'),
                 ('priority', 'minor', '4'),
                 ('priority', 'trivial', '5'),
                 ('ticket_type', 'defect', '1'),
                 ('ticket_type', 'enhancement', '2'),
                 ('ticket_type', 'task', '3'))),
            ('permission',
              ('username', 'action'),
                (('anonymous', 'LOG_VIEW'),
                 ('anonymous', 'FILE_VIEW'),
                 ('anonymous', 'WIKI_VIEW'),
                 ('authenticated', 'WIKI_CREATE'),
                 ('authenticated', 'WIKI_MODIFY'),
                 ('anonymous', 'SEARCH_VIEW'),
                 ('anonymous', 'REPORT_VIEW'),
                 ('anonymous', 'REPORT_SQL_VIEW'),
                 ('anonymous', 'TICKET_VIEW'),
                 ('authenticated', 'TICKET_CREATE'),
                 ('authenticated', 'TICKET_MODIFY'),
                 ('anonymous', 'BROWSER_VIEW'),
                 ('anonymous', 'TIMELINE_VIEW'),
                 ('anonymous', 'CHANGESET_VIEW'),
                 ('anonymous', 'ROADMAP_VIEW'),
                 ('anonymous', 'MILESTONE_VIEW'))),
            ('report',
              ('author', 'title', 'query', 'description'),
                __mkreports(get_reports(db))))
