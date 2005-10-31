# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2005 Edgewall Software
# Copyright (C) 2003-2005 Daniel Lundin <daniel@edgewall.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Daniel Lundin <daniel@edgewall.com>

from trac.config import default_dir
from trac.db import Table, Column, Index

# Database version identifier. Used for automatic upgrades.
db_version = 16

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
    Table('session', key=('sid', 'authenticated', 'var_name'))[
        Column('sid'),
        Column('authenticated', type='int'),
        Column('var_name'),
        Column('var_value')],

    # Attachments
    Table('attachment', key=('type', 'id', 'filename'))[
        Column('type'),
        Column('id'),
        Column('filename'),
        Column('size', type='int'),
        Column('time', type='int'),
        Column('description'),
        Column('author'),
        Column('ipnr')],

    # Wiki system
    Table('wiki', key=('name', 'version'))[
        Column('name'),
        Column('version', type='int'),
        Column('time', type='int'),
        Column('author'),
        Column('ipnr'),
        Column('text'),
        Column('comment'),
        Column('readonly', type='int'),
        Index(['time'])],

    # Version control cache
    Table('revision', key='rev')[
        Column('rev'),
        Column('time', type='int'),
        Column('author'),
        Column('message'),
        Index(['time'])],
    Table('node_change', key=('rev', 'path', 'change'))[
        Column('rev'),
        Column('path'),
        Column('kind', size=1),
        Column('change', size=1),
        Column('base_path'),
        Column('base_rev'),
        Index(['rev'])],

    # Ticket system
    Table('ticket', key='id')[
        Column('id', auto_increment=True),
        Column('type'),
        Column('time', type='int'),
        Column('changetime', type='int'),
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
        Column('time', type='int'),
        Column('author'),
        Column('field'),
        Column('oldvalue'),
        Column('newvalue'),
        Index(['ticket', 'time'])],
    Table('ticket_custom', key=('ticket', 'name'))[
        Column('ticket', type='int'),
        Column('name'),
        Column('value')],
    Table('enum', key=('type', 'name'))[
        Column('type'),
        Column('name'),
        Column('value')],
    Table('component', key='name')[
        Column('name'),
        Column('owner'),
        Column('description')],
    Table('milestone', key='name')[
        Column('name'),
        Column('due', type='int'),
        Column('completed', type='int'),
        Column('description')],
    Table('version', key='name')[
        Column('name'),
        Column('time', type='int'),
        Column('description')],

    # Report system
    Table('report', key='id')[
        Column('id', auto_increment=True),
        Column('author'),
        Column('title'),
        Column('sql'),
        Column('description')],
]


##
## Default Reports
##

reports = (
('Active Tickets',
"""
 * List all active tickets by priority.
 * Color each row based on priority.
 * If a ticket has been accepted, a '*' is appended after the owner's name
""",
"""
SELECT p.value AS __color__,
   id AS ticket, summary, component, version, milestone, t.type AS type, 
   (CASE status WHEN 'assigned' THEN owner||' *' ELSE owner END) AS owner,
   time AS created,
   changetime AS _changetime, description AS _description,
   reporter AS _reporter
  FROM ticket t, enum p
  WHERE status IN ('new', 'assigned', 'reopened') 
AND p.name = t.priority AND p.type = 'priority'
  ORDER BY p.value, milestone, t.type, time
"""),
#----------------------------------------------------------------------------
 ('Active Tickets by Version',
"""
This report shows how to color results by priority,
while grouping results by version.

Last modification time, description and reporter are included as hidden fields
for useful RSS export.
""",
"""
SELECT p.value AS __color__,
   version AS __group__,
   id AS ticket, summary, component, version, t.type AS type, 
   (CASE status WHEN 'assigned' THEN owner||' *' ELSE owner END) AS owner,
   time AS created,
   changetime AS _changetime, description AS _description,
   reporter AS _reporter
  FROM ticket t, enum p
  WHERE status IN ('new', 'assigned', 'reopened') 
AND p.name = t.priority AND p.type = 'priority'
  ORDER BY (version IS NULL),version, p.value, t.type, time
"""),
#----------------------------------------------------------------------------
('All Tickets by Milestone',
"""
This report shows how to color results by priority,
while grouping results by milestone.

Last modification time, description and reporter are included as hidden fields
for useful RSS export.
""",
"""
SELECT p.value AS __color__,
   milestone||' Release' AS __group__,
   id AS ticket, summary, component, version, t.type AS type, 
   (CASE status WHEN 'assigned' THEN owner||' *' ELSE owner END) AS owner,
   time AS created,
   changetime AS _changetime, description AS _description,
   reporter AS _reporter
  FROM ticket t, enum p
  WHERE status IN ('new', 'assigned', 'reopened') 
AND p.name = t.priority AND p.type = 'priority'
  ORDER BY (milestone IS NULL),milestone, p.value, t.type, time
"""),
#----------------------------------------------------------------------------
('Assigned, Active Tickets by Owner',
"""
List assigned tickets, group by ticket owner, sorted by priority.
""",
"""

SELECT p.value AS __color__,
   owner AS __group__,
   id AS ticket, summary, component, milestone, t.type AS type, time AS created,
   changetime AS _changetime, description AS _description,
   reporter AS _reporter
  FROM ticket t,enum p
  WHERE status = 'assigned'
AND p.name=t.priority AND p.type='priority'
  ORDER BY owner, p.value, t.type, time
"""),
#----------------------------------------------------------------------------
('Assigned, Active Tickets by Owner (Full Description)',
"""
List tickets assigned, group by ticket owner.
This report demonstrates the use of full-row display.
""",
"""
SELECT p.value AS __color__,
   owner AS __group__,
   id AS ticket, summary, component, milestone, t.type AS type, time AS created,
   description AS _description_,
   changetime AS _changetime, reporter AS _reporter
  FROM ticket t, enum p
  WHERE status = 'assigned'
AND p.name = t.priority AND p.type = 'priority'
  ORDER BY owner, p.value, t.type, time
"""),
#----------------------------------------------------------------------------
('All Tickets By Milestone  (Including closed)',
"""
A more complex example to show how to make advanced reports.
""",
"""
SELECT p.value AS __color__,
   t.milestone AS __group__,
   (CASE status 
      WHEN 'closed' THEN 'color: #777; background: #ddd; border-color: #ccc;'
      ELSE 
        (CASE owner WHEN '$USER' THEN 'font-weight: bold' END)
    END) AS __style__,
   id AS ticket, summary, component, status, 
   resolution,version, t.type AS type, priority, owner,
   changetime AS modified,
   time AS _time,reporter AS _reporter
  FROM ticket t,enum p
  WHERE p.name=t.priority AND p.type='priority'
  ORDER BY (milestone IS NULL), milestone DESC, (status = 'closed'), 
        (CASE status WHEN 'closed' THEN modified ELSE (-1)*p.value END) DESC
"""),
#----------------------------------------------------------------------------
('My Tickets',
"""
This report demonstrates the use of the automatically set 
$USER dynamic variable, replaced with the username of the
logged in user when executed.
""",
"""
SELECT p.value AS __color__,
   (CASE status WHEN 'assigned' THEN 'Assigned' ELSE 'Owned' END) AS __group__,
   id AS ticket, summary, component, version, milestone,
   t.type AS type, priority, time AS created,
   changetime AS _changetime, description AS _description,
   reporter AS _reporter
  FROM ticket t, enum p
  WHERE t.status IN ('new', 'assigned', 'reopened') 
AND p.name = t.priority AND p.type = 'priority' AND owner = '$USER'
  ORDER BY (status = 'assigned') DESC, p.value, milestone, t.type, time
"""),
#----------------------------------------------------------------------------
('Active Tickets, Mine first',
"""
 * List all active tickets by priority.
 * Show all tickets owned by the logged in user in a group first.
""",
"""
SELECT p.value AS __color__,
   (CASE owner 
     WHEN '$USER' THEN 'My Tickets' 
     ELSE 'Active Tickets' 
    END) AS __group__,
   id AS ticket, summary, component, version, milestone, t.type AS type, 
   (CASE status WHEN 'assigned' THEN owner||' *' ELSE owner END) AS owner,
   time AS created,
   changetime AS _changetime, description AS _description,
   reporter AS _reporter
  FROM ticket t, enum p
  WHERE status IN ('new', 'assigned', 'reopened') 
AND p.name = t.priority AND p.type = 'priority'
  ORDER BY (owner = '$USER') DESC, p.value, milestone, t.type, time
"""))


##
## Default database values
##

# (table, (column1, column2), ((row1col1, row1col2), (row2col1, row2col2)))
data = (('component',
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
               (('status', 'new', 1),
                ('status', 'assigned', 2),
                ('status', 'reopened', 3),
                ('status', 'closed', 4),
                ('resolution', 'fixed', 1),
                ('resolution', 'invalid', 2),
                ('resolution', 'wontfix', 3),
                ('resolution', 'duplicate', 4),
                ('resolution', 'worksforme', 5),
                ('priority', 'blocker', 1),
                ('priority', 'critical', 2),
                ('priority', 'major', 3),
                ('priority', 'minor', 4),
                ('priority', 'trivial', 5),
                ('ticket_type', 'defect', 1),
                ('ticket_type', 'enhancement', 2),
                ('ticket_type', 'task', 3))),
           ('permission',
             ('username', 'action'),
               (('anonymous', 'LOG_VIEW'),
                ('anonymous', 'FILE_VIEW'),
                ('anonymous', 'WIKI_VIEW'),
                ('anonymous', 'WIKI_CREATE'),
                ('anonymous', 'WIKI_MODIFY'),
                ('anonymous', 'SEARCH_VIEW'),
                ('anonymous', 'REPORT_VIEW'),
                ('anonymous', 'REPORT_SQL_VIEW'),
                ('anonymous', 'TICKET_VIEW'),
                ('anonymous', 'TICKET_CREATE'),
                ('anonymous', 'TICKET_MODIFY'),
                ('anonymous', 'BROWSER_VIEW'),
                ('anonymous', 'TIMELINE_VIEW'),
                ('anonymous', 'CHANGESET_VIEW'),
                ('anonymous', 'ROADMAP_VIEW'),
                ('anonymous', 'MILESTONE_VIEW'))),
           ('system',
             ('name', 'value'),
               (('database_version', str(db_version)),)),
           ('report',
             ('author', 'title', 'sql', 'description'),
               __mkreports(reports)))

default_config = \
 (('trac', 'repository_dir', ''),
  ('trac', 'templates_dir', default_dir('templates')),
  ('trac', 'database', 'sqlite:db/trac.db'),
  ('trac', 'default_charset', 'iso-8859-15'),
  ('trac', 'default_handler', 'WikiModule'),
  ('trac', 'check_auth_ip', 'true'),
  ('trac', 'ignore_auth_case', 'false'),
  ('trac', 'metanav', 'login,logout,settings,help,about'),
  ('trac', 'mainnav', 'wiki,timeline,roadmap,browser,tickets,newticket,search'),
  ('trac', 'permission_store', 'DefaultPermissionStore'),
  ('logging', 'log_type', 'none'),
  ('logging', 'log_file', 'trac.log'),
  ('logging', 'log_level', 'DEBUG'),
  ('project', 'name', 'My Project'),
  ('project', 'descr', 'My example project'),
  ('project', 'url', 'http://example.com/'),
  ('project', 'icon', 'common/trac.ico'),
  ('project', 'footer',
   ' Visit the Trac open source project at<br />'
   '<a href="http://trac.edgewall.com/">http://trac.edgewall.com/</a>'),
  ('ticket', 'default_version', ''),
  ('ticket', 'default_type', 'defect'),
  ('ticket', 'default_priority', 'major'),
  ('ticket', 'default_milestone', ''),
  ('ticket', 'default_component', 'component1'),
  ('ticket', 'restrict_owner', 'false'),
  ('header_logo', 'link', 'http://trac.edgewall.com/'),
  ('header_logo', 'src', 'common/trac_banner.png'),
  ('header_logo', 'alt', 'Trac'),
  ('header_logo', 'width', '236'),
  ('header_logo', 'height', '73'),
  ('attachment', 'max_size', '262144'),
  ('mimeviewer', 'enscript_path', 'enscript'),
  ('mimeviewer', 'php_path', 'php'),
  ('mimeviewer', 'tab_width', '8'),
  ('mimeviewer', 'max_preview_size', '262144'),
  ('notification', 'smtp_enabled', 'false'),
  ('notification', 'smtp_server', 'localhost'),
  ('notification', 'smtp_port', '25'),
  ('notification', 'smtp_user', ''),
  ('notification', 'smtp_password', ''),
  ('notification', 'smtp_always_cc', ''),
  ('notification', 'always_notify_owner', 'false'),
  ('notification', 'always_notify_reporter', 'false'),
  ('notification', 'smtp_from', 'trac@localhost'),
  ('notification', 'smtp_replyto', 'trac@localhost'),
  ('timeline', 'default_daysback', '30'),
  ('timeline', 'changeset_show_files', '0'),
  ('timeline', 'ticket_show_details', 'false'),
  ('browser', 'hide_properties', 'svk:merge'),
  ('wiki', 'ignore_missing_pages', 'false'),
)

default_components = ('trac.About', 'trac.attachment', 
                      'trac.mimeview.enscript', 'trac.mimeview.patch',
                      'trac.mimeview.php', 'trac.mimeview.rst',
                      'trac.mimeview.silvercity', 'trac.mimeview.txtl',
                      'trac.Search', 'trac.Settings',
                      'trac.ticket.query', 'trac.ticket.report',
                      'trac.ticket.roadmap', 'trac.ticket.web_ui',
                      'trac.Timeline',
                      'trac.versioncontrol.web_ui',
                      'trac.wiki.macros', 'trac.wiki.web_ui',
                      'trac.web.auth')
