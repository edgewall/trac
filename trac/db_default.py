# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004 Edgewall Software
# Copyright (C) 2003, 2004 Daniel Lundin <daniel@edgewall.com>
#
# Trac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Trac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Daniel Lundin <daniel@edgewall.com>


# Database version identifier. Used for automatic upgrades.
db_version = 7

def __mkreports(reps):
    """Utility function used to create report data in same syntax as the
    default data. This extra step is done to simplify editing the default
    reports."""
    result = []
    i = 1
    for r in reps:
        result.append ((i, None, r[0], r[2], r[1]))
        i = i + 1
    return result


##
## Default data
##

schema = """
CREATE TABLE revision (
        rev             integer PRIMARY KEY,
        time            integer,
        author          text,
        message         text
);
CREATE TABLE node_change (
        rev             integer,
        name            text,
        change          char(1),
        UNIQUE(rev, name, change)
);
CREATE TABLE auth_cookie (
        cookie          text,
        name            text,
        ipnr            text,
        time            integer,
        UNIQUE(cookie, name, ipnr)
);
CREATE TABLE enum (
        type            text,
        name            text,
        value           text,
        UNIQUE(name,type)
);
CREATE TABLE system (
        name            text PRIMARY KEY,
        value           text,
        UNIQUE(name)
);
CREATE TABLE lock (
        name            text PRIMARY KEY,
        owner           text,
        ipnr            text,
        time            integer,
        UNIQUE(name)
);
CREATE TABLE ticket (
        id              integer PRIMARY KEY,
        time            integer,        -- the time it was created
        changetime      integer,
        component       text,
        severity        text,
        priority        text,
        owner           text,           -- who is this ticket assigned to
        reporter        text,
        cc              text,           -- email addresses to notify
        url             text,           -- url related to this ticket
        version         text,           -- 
        milestone       text,           -- 
        status          text,
        resolution      text,
        summary         text,           -- one-line summary
        description     text,           -- problem description (long)
        keywords        text
);
CREATE TABLE ticket_change (
        ticket          integer,
        time            integer,
        author          text,
        field           text,
        oldvalue        text,
        newvalue        text,
        UNIQUE(ticket, time, field)
);
CREATE TABLE ticket_custom (
       ticket               integer,
       name             text,
       value            text,
       UNIQUE(ticket,name)
);
CREATE TABLE report (
        id              integer PRIMARY KEY,
        author          text,
        title           text,
        sql             text,
        description     text
);
CREATE TABLE permission (
        username        text,           -- 
        action          text,           -- allowable activity
        UNIQUE(username,action)
);
CREATE TABLE component (
         name            text PRIMARY KEY,
         owner           text
);
CREATE TABLE milestone (
         id              integer PRIMARY KEY,
         name            text,
         time            integer,
         descr           text,
         UNIQUE(name)
);
CREATE TABLE version (
         name            text PRIMARY KEY,
         time            integer
);
CREATE TABLE wiki (
         name            text,
         version         integer,
         time            integer,
         author          text,
         ipnr            text,
         text            text,
         comment         text,
         readonly        integer,
         UNIQUE(name,version)
);
CREATE TABLE attachment (
         type            text,
         id              text,
         filename        text,
         size            integer,
         time            integer,
         description     text,
         author          text,
         ipnr            text,
         UNIQUE(type,id,filename)
);

CREATE TABLE session (
         sid             text,
         username        text,
         var_name        text,
         var_value       text,
         UNIQUE(sid,var_name)
);

CREATE INDEX node_change_idx ON node_change(rev);
CREATE INDEX ticket_change_idx  ON ticket_change(ticket, time);
CREATE INDEX wiki_idx           ON wiki(name,version);
CREATE INDEX session_idx        ON session(sid,var_name);
"""

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
   id AS ticket, summary, component, version, milestone, severity, 
   (CASE status WHEN 'assigned' THEN owner||' *' ELSE owner END) AS owner,
   time AS created,
   changetime AS _changetime, description AS _description,
   reporter AS _reporter
  FROM ticket t, enum p
  WHERE status IN ('new', 'assigned', 'reopened') 
AND p.name = t.priority AND p.type = 'priority'
  ORDER BY p.value, milestone, severity, time
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
   id AS ticket, summary, component, version, severity, 
   (CASE status WHEN 'assigned' THEN owner||' *' ELSE owner END) AS owner,
   time AS created,
   changetime AS _changetime, description AS _description,
   reporter AS _reporter
  FROM ticket t, enum p
  WHERE status IN ('new', 'assigned', 'reopened') 
AND p.name = t.priority AND p.type = 'priority'
  ORDER BY (version IS NULL),version, p.value, severity, time
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
   id AS ticket, summary, component, version, severity, 
   (CASE status WHEN 'assigned' THEN owner||' *' ELSE owner END) AS owner,
   time AS created,
   changetime AS _changetime, description AS _description,
   reporter AS _reporter
  FROM ticket t, enum p
  WHERE status IN ('new', 'assigned', 'reopened') 
AND p.name = t.priority AND p.type = 'priority'
  ORDER BY (milestone IS NULL),milestone, p.value, severity, time
"""),
#----------------------------------------------------------------------------
('Assigned, Active Tickets by Owner',
"""
List assigned tickets, group by ticket owner, sorted by priority.
""",
"""

SELECT p.value AS __color__,
   owner AS __group__,
   id AS ticket, summary, component, milestone, severity, time AS created,
   changetime AS _changetime, description AS _description,
   reporter AS _reporter
  FROM ticket t,enum p
  WHERE status = 'assigned'
AND p.name=t.priority AND p.type='priority'
  ORDER BY owner, p.value, severity, time
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
   id AS ticket, summary, component, milestone, severity, time AS created,
   description AS _description_,
   changetime AS _changetime, reporter AS _reporter
  FROM ticket t, enum p
  WHERE status = 'assigned'
AND p.name = t.priority AND p.type = 'priority'
  ORDER BY owner, p.value, severity, time
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
   resolution,version, severity, priority, owner,
   changetime AS modified,
   time AS _time,reporter AS _reporter
  FROM ticket t,enum p
  WHERE p.name=t.priority AND p.type='priority'
  ORDER BY (milestone IS NULL), milestone DESC, (status = 'closed'), 
        (CASE status WHEN 'closed' THEN modified ELSE -p.value END) DESC
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
   severity, priority, time AS created,
   changetime AS _changetime, description AS _description,
   reporter AS _reporter
  FROM ticket t, enum p
  WHERE t.status IN ('new', 'assigned', 'reopened') 
AND p.name = t.priority AND p.type = 'priority' AND owner = '$USER'
  ORDER BY (status = 'assigned') DESC, p.value, milestone, severity, time
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
   id AS ticket, summary, component, version, milestone, severity, 
   (CASE status WHEN 'assigned' THEN owner||' *' ELSE owner END) AS owner,
   time AS created,
   changetime AS _changetime, description AS _description,
   reporter AS _reporter
  FROM ticket t, enum p
  WHERE status IN ('new', 'assigned', 'reopened') 
AND p.name = t.priority AND p.type = 'priority'
  ORDER BY (owner = '$USER') DESC, p.value, milestone, severity, time
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
             ('name', 'time'),
               (('', 0), 
                ('milestone1', 0),
                ('milestone2', 0),
                ('milestone3', 0),
                ('milestone4', 0))),
           ('version',
             ('name', 'time'),
               (('', 0),
                ('1.0', 0),
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
                ('severity', 'blocker', 1),
                ('severity', 'critical', 2),
                ('severity', 'major', 3),
                ('severity', 'normal', 4),
                ('severity', 'minor', 5),
                ('severity', 'trivial', 6),
                ('severity', 'enhancement', 7),
                ('priority', 'highest', 1),
                ('priority', 'high', 2),
                ('priority', 'normal', 3),
                ('priority', 'low', 4),
                ('priority', 'lowest', 5))),
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
             ('id', 'author', 'title', 'sql', 'description'),
               __mkreports(reports)))

default_config = \
 (('trac', 'htdocs_location', '/trac/'),
  ('trac', 'repository_dir', '/var/svn/myrep'),
  ('trac', 'templates_dir', '/usr/lib/trac/templates'),
  ('trac', 'database', 'sqlite:db/trac.db'),
  ('trac', 'default_charset', 'iso-8859-15'),
  ('logging', 'log_type', 'none'),
  ('logging', 'log_file', 'trac.log'),
  ('logging', 'log_level', 'DEBUG'),
  ('project', 'name', 'My Project'),
  ('project', 'descr', 'My example project'),
  ('project', 'url', 'http://example.com/'),
  ('project', 'footer',
   ' Visit the Trac open source project at<br />'
   '<a href="http://trac.edgewall.com/">http://trac.edgewall.com/</a>'),
  ('ticket', 'default_version', ''),
  ('ticket', 'default_severity', 'normal'),
  ('ticket', 'default_priority', 'normal'),
  ('ticket', 'default_milestone', ''),
  ('ticket', 'default_component', 'component1'),
  ('header_logo', 'link', 'http://trac.edgewall.com/'),
  ('header_logo', 'src', 'trac_banner.png'),
  ('header_logo', 'alt', 'Trac'),
  ('header_logo', 'width', '236'),
  ('header_logo', 'height', '73'),
  ('attachment', 'max_size', '262144'),
  ('diff', 'tab_width', '8'),
  ('mimeviewer', 'enscript_path', 'enscript'),
  ('notification', 'smtp_enabled', 'false'),
  ('notification', 'smtp_server', 'localhost'),
  ('notification', 'smtp_always_cc', ''),
  ('notification', 'always_notify_reporter', 'false'),
  ('notification', 'smtp_from', 'trac@localhost'),
  ('notification', 'smtp_replyto', 'trac@localhost'),
  ('timeline', 'changeset_show_files', '0'))
   
