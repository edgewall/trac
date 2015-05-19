"""
Import a Sourceforge project's tracker items into a Trac database.

Requires:
   Trac 0.11 from http://trac.edgewall.org/
   Python 2.5 from http://www.python.org/
           
The Sourceforge tracker items can be exported from the 'Backup' page
of the project admin section. Substitute XXXXX with project id:
https://sourceforge.net/export/xml_export2.php?group_id=XXXXX


Initial version for Trac 0.7 and old artiface SF export format is
Copyright 2004, Mark Rowe <mrowe@bluewire.net.nz>

Version for Trac 0.11 and SF XML2 export format, completely rewritten
except TracDatabase class is
Copyright 2010, anatoly techtonik <techtonik@php.net>
HGID: 92fd15e8398c

$Id$


Uses Trac 0.11 DB format version 21
SourceForge XML Export format identified by the header:
<!DOCTYPE project_export SYSTEM "http://sourceforge.net/export/sf_project_export_0.2.dtd">

Works with all DB backends. Attachments are not downloaded, but inserted
as links to SF tracker.


Ticket Types, Priorities and Resolutions
----------------------------------------
Conversion kills default Trac ticket types:
- defect      1
- enhancement 2
- task        3

and priorities:
- blocker  1
- critical 2
- major    3
- minor    4
- trivial  5

and resolutions:
- fixed      1
- invalid    2
- wontfix    3
- duplicate  4
- worksforme 5


Versions and Milestones
-----------------------
Kills versions and milestones from existing Trac DB


Mapping
-------
tracker_name == ticket_type
group_name == version
category_name == component

user nobody == anonymous


Not implemented (feature:reason)
--------------------------------
attachments:made as a comment with links to attachments stored on SF
            (type,id,filename,size,time,description,author,ipnr)
ticket_custom:unknown (ticket,name,value)
history:imported only for summary, priority. closed date and owner fields

severities:no field in source data
"""


#: rename users from SF to Trac
user_map = {"nobody":"anonymous"}



complete_msg = """
Conversion complete.

You may want to login into Trac to verify names for ticket owners. You may
also want to rename ticket types and priorities to default.
"""

from xml.etree.ElementTree import ElementTree
import time
import sys

import trac.env

# --- utility
class DBNotEmpty(Exception):
    def __str__(self):
        return "Will not modify database with existing tickets!"

class FlatXML(object):
    """Flat XML is XML without element attributes. Also each element
       may contain other elements or text, but not both.

       This object mirrors XML structure into own properties for convenient
       access to tree elements, i.e. flat.trackers[2].groups[2].group_name

       Uses recursion.
    """

    def __init__(self, el=None):
        """el is ElementTree element"""
        if el:
            self.merge(el)

    def merge(self, el):
        """merge supplied ElementTree element into current object"""
        for c in el:
            if len(c.getchildren()) == 0:
                if c.text != None and len(c.text.strip()) != 0:
                   self.__setattr__(c.tag, c.text)
                else:
                   self.__setattr__(c.tag, [])
            else: #if c.getchildren()[0].tag == c.tag[:-1]:
                # c is a set of elements
                self.__setattr__(c.tag, [FlatXML(x) for x in c.getchildren()])


    def __str__(self):
        buf = ""
        for sub in self.__dict__:
            val = self.__dict__[sub]
            if type(val) != list:
                buf += "%s : %s\n" % (sub, val)
            else:
                for x in val: 
                    buf += "\n  ".join(x.__str__().split("\n"))
        return buf

    def __repr__(self):
        buf = ""
        for sub in self.__dict__:
            val = self.__dict__[sub]
            if type(val) != list:
                buf += "<%s>%s</%s>\n" % (sub, val, sub)
            else:
                for x in val: 
                    buf += "\n  ".join(x.__repr__().split("\n"))
        return buf


# --- SF data model
class Tracker(FlatXML):
    """
 <trackers>
  <tracker>
   <url>http://sourceforge.net/?group_id=175454&#38;atid=873299</url>
   <tracker_id>873299</tracker_id>
   <name>Bugs</name>
   <description>Bug Tracking System</description>
   <is_public>All site users</is_public>
   <allow_anon>Yes</allow_anon>
   <email_updates>Send to goblinhack@gmail.com</email_updates>
   <due_period>2592000</due_period>
   <submit_instructions></submit_instructions>
   <browse_instructions></browse_instructions>
   <status_timeout>1209600</status_timeout>
   <due_period_initial>0</due_period_initial>
   <due_period_update>0</due_period_update>
   <reopen_on_comment>1</reopen_on_comment>
   <canned_responses>
   </canned_responses>
   <groups>
    <group>
     <id>632324</id>
      <group_name>v1.0 (example)</group_name>
    </group>
   </groups>
   <categories>
    <category>
     <id>885178</id>
      <category_name>Interface (example)</category_name>
     <auto_assignee>nobody</auto_assignee>
    </category>
   </categories>
   <resolutions>
    <resolution>
     <id>1</id>
     <name>Fixed</name>
    </resolution>
    <resolution>
     <id>2</id>
     <name>Invalid</name>
    </resolution>
    ...
   </resolutions>
   <statuses>
    <status>
      <id>1</id>
      <name>Open</name>
    </status>
    <status>
      <id>2</id>
      <name>Closed</name>
    </status>
    <status>
      <id>3</id>
      <name>Deleted</name>
    </status>
    <status>
      <id>4</id>
      <name>Pending</name>
    </status>
   </statuses>
   ...
   <tracker_items>
    <tracker_item>
<url>http://sourceforge.net/support/tracker.php?aid=2471428</url>
<id>2471428</id>
<status_id>2</status_id>
<category_id>100</category_id>
<group_id>100</group_id>
<resolution_id>100</resolution_id>
<submitter>sbluen</submitter>
<assignee>nobody</assignee>
<closer>goblinhack</closer>
<submit_date>1230400444</submit_date>
<close_date>1231087612</close_date>
<priority>5</priority>
<summary>glitch with edge of level</summary>
<details>The mini-laser that the future soldier carries is so powerful that it even lets me go outside the level. I stand at the top edge of the level and then shoot up, and then it gets me somewhere where I am not supposed to go.</details>
<is_private>0</is_private>
<followups>
 <followup>
  <id>2335316</id>
  <submitter>goblinhack</submitter>
  <date>1175610236</date>
  <details>Logged In: YES 
  user_id=1577972
  Originator: NO

  does this happen every game or just once?

  you could send me the saved file and I'll try and load it - old
  versions harldy ever work with newer versions - need to add some
  kind of warnings on that

  tx</details>
 </followup>
 ...
</followups>
<attachments>
 <attachment>
  <url>http://sourceforge.net/tracker/download.php?group_id=175454&#38;atid=873299&#38;file_id=289080&#38;aid=</url>
  <id>289080</id>
  <filename>your_most_recent_game.gz</filename>
  <description>my saved game</description>
  <filesize>112968</filesize>
  <filetype>application/x-gzip</filetype>
  <date>1218987770</date>
  <submitter>sbluen</submitter>
 </attachment>
...
</attachments>
<history_entries>
 <history_entry>
  <id>7304242</id>
  <field_name>IP</field_name>
  <old_value>Artifact Created: 76.173.48.148</old_value>
  <date>1230400444</date>
  <updator>sbluen</updator>
 </history_entry>
 ...
</history_entries>
    </tracker_item>
    ...
   </tracker_items>
  ...
  </tracker>
 </trackers>
    """
    def __init__(self, e):
        self.merge(e)


class ExportedProjectData(object):
    """Project data container as Python object.
    """
    def __init__(self, f):
        """Data parsing"""

        self.trackers = []    #: tracker properties and data
        self.groups = []      #: groups []
        self.priorities = []  #: priorities used
        self.resolutions = [] #: resolutions (index, name)
        self.tickets = []     #: all tickets
        self.statuses = []    #: status (idx, name)

        self.used_resolutions = {} #: id:name
        self.used_categories  = {} #: id:name
        # id '100' means no category
        self.used_categories['100'] = None
        self.users = {}       #: id:name
        
        root = ElementTree().parse(f)   
        
        self.users = dict([(FlatXML(u).userid, FlatXML(u).username) for u in root.find('referenced_users')])

        for tracker in root.find('trackers'):
            tr = Tracker(tracker)
            self.trackers.append(tr)

            # groups-versions
            for grp in tr.groups:
                # group ids are tracker-specific even if names match
                g = (grp.id, grp.group_name)
                if g not in self.groups:
                    self.groups.append(g)

            # resolutions
            for res in tr.resolutions:
                r = (res.id, res.name)
                if r not in self.resolutions:
                    self.resolutions.append(r)

            # statuses
            self.statuses = [(s.id, s.name) for s in tr.statuses]

            # tickets
            for tck in tr.tracker_items:
                if type(tck) == str: print repr(tck)
                self.tickets.append(tck)
                if int(tck.priority) not in self.priorities:
                    self.priorities.append(int(tck.priority))
                res_id = getattr(tck, "resolution_id", None) 
                if res_id is not None and res_id not in self.used_resolutions:
                    for idx, name in self.resolutions:
                        if idx == res_id: break
                    self.used_resolutions[res_id] = dict(self.resolutions)[res_id]
                # used categories
                categories = dict(self.get_categories(tr, noowner=True))
                if tck.category_id not in self.used_categories:
                    self.used_categories[tck.category_id] = categories[tck.category_id]

        # sorting everything
        self.trackers.sort(key=lambda x:x.name)
        self.groups.sort()
        self.priorities.sort()

    def get_categories(self, tracker=None, noid=False, noowner=False):
        """ SF categories : Trac components
            (id, name, owner) tuples for specified tracker or all trackers
            if noid or noowner flags are set, specified tuple attribute is
            stripped
        """
        trs = [tracker] if tracker is not None else self.trackers
        categories = []
        for tr in trs:
            for cat in tr.categories:
                c = (cat.id, cat.category_name, cat.auto_assignee)
                if c not in categories:
                    categories.append(c)
        #: sort by name
        if noid:
            categories.sort()
        else:
            categories.sort(key=lambda x:x[1])
        if noowner:
            categories = [x[:2] for x in categories]
        if noid:
            categories = [x[1:] for x in categories]
        return categories

    
class TracDatabase(object):
    def __init__(self, path):
        self.env = trac.env.Environment(path)
        self._db = self.env.get_db_cnx()
        self._db.autocommit = False
        self._db.cnx.ping()
    
    def db(self):
        return self._db
    
    def hasTickets(self):
        c = self.db().cursor()
        #c.execute("""DELETE FROM ticket""")
        c.execute('''SELECT count(*) FROM ticket''')
        return int(c.fetchall()[0][0]) > 0

    def dbCheck(self):
        if self.hasTickets():
            raise DBNotEmpty
    
    def setTypeList(self, s):
        """Remove all types, set them to `s`"""
        self.dbCheck()
        c = self.db().cursor()
        c.execute("""DELETE FROM enum WHERE type='ticket_type'""")
        for i, value in enumerate(s):
            c.execute("""INSERT INTO enum (type, name, value) VALUES (%s, %s, %s)""",
                      ("ticket_type", value, i))
        self.db().commit()
    
    def setPriorityList(self, s):
        """Remove all priorities, set them to `s`"""
        self.dbCheck()
        c = self.db().cursor()
        c.execute("""DELETE FROM enum WHERE type='priority'""")
        for i, value in enumerate(s):
            c.execute("""INSERT INTO enum (type, name, value) VALUES (%s, %s, %s)""",
                      ("priority", value, i))
        self.db().commit()

    def setResolutionList(self, t):
        """Remove all resolutions, set them to `t` (index, name)"""
        self.dbCheck()
        c = self.db().cursor()
        c.execute("""DELETE FROM enum WHERE type='resolution'""")
        for value, name in t:
            c.execute("""INSERT INTO enum (type, name, value) VALUES (%s, %s, %s)""",
                      ("resolution", name, value))
        self.db().commit()
    
    def setComponentList(self, t):
        """Remove all components, set them to `t` (name, owner)"""
        self.dbCheck()
        c = self.db().cursor()
        c.execute("""DELETE FROM component""")
        for name, owner in t:
            c.execute("""INSERT INTO component (name, owner) VALUES (%s, %s)""",
                      (name, owner))
        self.db().commit()
    
    def setVersionList(self, v):
        """Remove all versions, set them to `v`"""
        self.dbCheck()
        c = self.db().cursor()
        c.execute("""DELETE FROM version""")
        for value in v:
            # time and description are also available
            c.execute("""INSERT INTO version (name) VALUES (%s)""",
                      value)
        self.db().commit()
        
    def setMilestoneList(self, m):
        """Remove all milestones, set them to `m` ("""
        self.dbCheck()
        c = self.db().cursor()
        c.execute("""DELETE FROM milestone""")
        for value in m:
            # due, completed, description are also available
            c.execute("""INSERT INTO milestone (name) VALUES (%s)""",
                      value)
        self.db().commit()
    
    def addTicket(self, type, time, changetime, component,
                  priority, owner, reporter, cc,
                  version, milestone, status, resolution,
                  summary, description, keywords):
        """ ticket table db21.py format

        id              integer PRIMARY KEY,
        type            text,           -- the nature of the ticket
        time            integer,        -- the time it was created
        changetime      integer,
        component       text,
        severity        text,
        priority        text,
        owner           text,           -- who is this ticket assigned to
        reporter        text,
        cc              text,           -- email addresses to notify
        version         text,           --
        milestone       text,           --
        status          text,
        resolution      text,
        summary         text,           -- one-line summary
        description     text,           -- problem description (long)
        keywords        text
        """
        db = self.db()
        c = db.cursor()
        if status.lower() == 'open':
            if owner != '':
                status = 'assigned'
            else:
                status = 'new'

        c.execute("""INSERT INTO ticket (type, time, changetime, component,
                                         priority, owner, reporter, cc,
                                         version, milestone, status, resolution,
                                         summary, description, keywords)
                                 VALUES (%s, %s, %s,
                                         %s, %s, %s, %s, %s,
                                         %s, %s, %s, %s,
                                         %s, %s, %s)""",
                  (type, time, changetime, component,
                  priority, owner, reporter, cc,
                  version, milestone, status.lower(), resolution,
                  summary, '%s' % description, keywords))
        db.commit()
        return db.get_last_id(c, 'ticket')
    
    def addTicketComment(self, ticket, time, author, value):
        c = self.db().cursor()
        c.execute("""INSERT INTO ticket_change (ticket, time, author, field, oldvalue, newvalue)
                                 VALUES        (%s, %s, %s, %s, %s, %s)""",
                  (ticket, time, author, 'comment', '', '%s' % value))
        self.db().commit()

    def addTicketChange(self, ticket, time, author, field, oldvalue, newvalue):
        c = self.db().cursor()
        c.execute("""INSERT INTO ticket_change (ticket, time, author, field, oldvalue, newvalue)
                                 VALUES        (%s, %s, %s, %s, %s, %s)""",
                  (ticket, time, author, field, oldvalue, newvalue))
        self.db().commit()


def importData(f, env, opt):
    project = ExportedProjectData(f)
    trackers = project.trackers
    
    db = TracDatabase(env)

    # Data conversion
    typeList = [x.name for x in trackers]
    print("%d trackers will be converted to the following ticket types:\n  %s" \
        % (len(trackers), typeList))

    used_cat_names = set(project.used_categories.values())
    #: make names unique, forget about competing owners (the last one wins)
    components = dict(project.get_categories(noid=True)).items()
    components.sort()
    components = [x for x in components if x[0] in used_cat_names]
    print "%d out of %d categories are used and will be converted to the following components:\n  %s" \
        % (len(components), len(project.get_categories()), components)
    print "..renaming component owners:"
    for i,c in enumerate(components):
        if c[1] in user_map:
            components[i] = (c[0], user_map[c[1]])
    print "  %s" % components

    print "%d groups which will be converted to the following versions:\n  %s" \
        % (len(project.groups), project.groups)
    print "%d resolutions found :\n  %s" \
        % (len(project.resolutions), project.resolutions)
    resolutions = [(k,project.used_resolutions[k]) for k in project.used_resolutions]
    resolutions.sort(key=lambda x:int(x[0]))
    print ".. only %d used will be imported:\n  %s" \
        % (len(resolutions), resolutions)
    print "Priorities used so far: %s" % project.priorities
    if not(raw_input("Continue [y/N]?").lower() == 'y'):
        sys.exit()

    # Data save
    db.setTypeList(typeList)
    db.setComponentList(components)
    db.setPriorityList(range(min(project.priorities), max(project.priorities)))
    db.setVersionList(set([x[1] for x in project.groups]))
    db.setResolutionList(resolutions)
    db.setMilestoneList([])
    
    for tracker in project.trackers:
      # id 100 means no component selected
      component_lookup = dict(project.get_categories(noowner=True)+[("100", None)])
      for t in tracker.tracker_items:
        i = db.addTicket(type=tracker.name,
                         time=int(t.submit_date),
                         changetime=int(t.submit_date),
                         component=component_lookup[t.category_id],
                         priority=t.priority,
                         owner=t.assignee if t.assignee not in user_map else user_map[t.assignee],
                         reporter=t.submitter if t.submitter not in user_map else user_map[t.submitter],
                         cc=None,
                         # 100 means no group selected
                         version=dict(project.groups+[("100", None)])[t.group_id],
                         milestone=None,
                         status=dict(project.statuses)[t.status_id],
                         resolution=dict(resolutions)[t.resolution_id] if hasattr(t, "resolution_id") else None,
                         summary=t.summary,
                         description=t.details,
                         keywords='sf'+t.id)

        print 'Imported %s as #%d' % (t.id, i)

        if len(t.attachments):
            attmsg = "SourceForge attachments:\n"
            for a in t.attachments:
                attmsg = attmsg + " * [%s %s] (%s) - added by '%s' %s [[BR]] "\
                         % (a.url+t.id, a.filename, a.filesize+" bytes",
                            user_map.get(a.submitter, a.submitter),
                            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(a.date))))
                attmsg = attmsg + "''%s ''\n" % (a.description or '') # empty description is as empty list
            db.addTicketComment(ticket=i,
                                time=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(t.submit_date))),
                                author=None, value=attmsg)
            print '    added information about %d attachments for #%d' % (len(t.attachments), i) 

        for msg in t.followups:
            """
            <followup>
            <id>3280792</id>
            <submitter>goblinhack</submitter>
            <date>1231087739</date>
            <details>done</details>
            </followup>
            """
            db.addTicketComment(ticket=i,
                                time=msg.date,
                                author=msg.submitter,
                                value=msg.details)
        if t.followups:
            print '    imported %d messages for #%d' % (len(t.followups), i)
        
        # Import history
        """
        <history_entry>
        <id>4452195</id>
        <field_name>resolution_id</field_name>
        <old_value>100</old_value>
        <date>1176043865</date>
        <updator>goblinhack</updator>
        </history_entry>
        """
        revision = t.__dict__.copy()

        # iterate the history in reverse order and update ticket revision from
        # current (last) to initial
        changes = 0
        for h in sorted(t.history_entries, reverse=True):
            """
             Processed fields (field - notes):
            IP         - no target field, just skip
            summary
            priority
            close_date
            assigned_to

             Fields not processed (field: explanation):
            File Added - TODO
            resolution_id - need to update used_resolutions
            status_id
            artifact_group_id
            category_id
            group_id
            """
            f = None
            if h.field_name in ("IP",):
                changes += 1
                continue
            elif h.field_name in ("summary", "priority"):
                f = h.field_name
                oldvalue = h.old_value
                newvalue = revision.get(h.field_name, None) 
            elif h.field_name == 'assigned_to':
                f = "owner"
                newvalue = revision['assignee']
                if h.old_value == '100': # was not assigned
                    revision['assignee'] = None
                    oldvalue = None
                else:
                    username = project.users[h.old_value]
                    if username in user_map: username = user_map[username]
                    revision['assignee'] = oldvalue = username
            elif h.field_name == 'close_date' and revision['close_date'] != 0:
                f = 'status'
                oldvalue = 'assigned'
                newvalue = 'closed'
                
            if f:
                changes += 1
                db.addTicketChange(ticket=i,
                                   time=h.date,
                                   author=h.updator,
                                   field=f,
                                   oldvalue=oldvalue,
                                   newvalue=newvalue)
    
            if h.field_name != 'assigned_to':
                revision[h.field_name] = h.old_value
        if changes:
            print '    processed %d out of %d history items for #%d' % (changes, len(t.history_entries), i)
  

def main():
    import optparse
    p = optparse.OptionParser('usage: %prog xml_export.xml /path/to/trac/environment')
    opt, args = p.parse_args()
    if len(args) != 2:
        p.error("Incorrect number of arguments")

    try:
        importData(open(args[0]), args[1], opt)
    except DBNotEmpty, e:
        print 'Error:', e
        sys.exit(1)

    print complete_msg


if __name__ == '__main__':
    main()
