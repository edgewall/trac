"""
Import a Sourceforge project's tracker items into a Trac database.

Requires:  Development version of Trac 0.7-pre from http://trac.edgewall.org/
           ElementTree from effbot.org/zone/element.htm
           Python 2.3 from http://www.python.org/
           
The Sourceforge tracker items can be exported from the 'Backup' page of the
project admin section.

Copyright 2004, Mark Rowe <mrowe@bluewire.net.nz>
"""

from elementtree.ElementTree import ElementTree
from datetime import datetime
import trac.env

class FieldParser(object):
    def __init__(self, e):
        for field in e:
            if field.get('name').endswith('date'):
                setattr(self, field.get('name'), datetime.fromtimestamp(int(field.text)))
            else:
                setattr(self, field.get('name'), field.text)        

class ArtifactHistoryItem(FieldParser):
    def __repr__(self):
        return '<ArtifactHistoryItem field_name=%r old_value=%r entrydate=%r mod_by=%r>' % (
            self.field_name, self.old_value, self.entrydate, self.mod_by)

class ArtifactMessage(FieldParser):
    def __repr__(self):
        return '<ArtifactMessage adddate=%r user_name=%r body=%r>' % (self.adddate, self.user_name, self.body)

class Artifact(object):
    def __init__(self, e):
        self._history = []
        self._messages = []
        
        for field in e:
            if field.get('name') == 'artifact_history':
                for h in field:
                    self._history.append(ArtifactHistoryItem(h))
            elif field.get('name') == 'artifact_messages':
                for m in field:
                    self._messages.append(ArtifactMessage(m))
            else:
                setattr(self, field.get('name'), field.text)
    
    def history(self):
        """Returns the history items in reverse chronological order so that the "new value"
           can easily be calculated based on the final value of the field, and the old value
           of the items occuring before it.
        """
        history = [(h.entrydate, h) for h in self._history]
        history.sort()
        return [h[1] for h in history][::-1]
    
    def messages(self):
        return self._messages[:]
    
    def __repr__(self):
        return '<Artifact summary=%r artifact_type=%r category=%r status=%r>' % (self.summary, self.artifact_type, self.category, self.status)

class ExportedProjectData(object):
    def __init__(self, f):
        self._artifacts = []
        
        root = ElementTree().parse(f)   
        
        for artifact in root.find('artifacts'):
            self._artifacts.append(Artifact(artifact))
    
    def artifacts(self):
        """Returns the artifacts in chronological order, so that they will be assigned numbers in sequence."""
        artifacts = [(a.open_date, a) for a in self._artifacts]
        artifacts.sort()
        return [a[1] for a in artifacts]
    
    def featureRequests(self):
        return [a for a in self._artifacts if a.artifact_type == 'Feature Requests']
    
    def bugs(self):
        return [a for a in self._artifacts if a.artifact_type == 'Bugs']
    
    def categories(self):
        """Returns all the category names that are used, in alphabetical order."""
        c = {}
        for a in self._artifacts:
            c[a.category] = 1
        
        categories = c.keys()
        categories.sort()
        return categories
    
    def groups(self):
        """Returns all the group names that are used, in alphabetical order."""
        g = {}
        for a in self._artifacts:
            g[a.artifact_group_id] = 1
        del g['None']
        
        groups = g.keys()
        groups.sort()
        return groups
    
    def artifactTypes(self):
        """Returns all the artifact types that are used, in alphabetical order."""
        t = {}
        for a in self._artifacts:
            t[a.artifact_type] = 1
        types = t.keys()
        types.sort()
        return types

class TracDatabase(object):
    def __init__(self, path):
        self.env = trac.env.Environment(path)
        self._db = self.env.get_db_cnx()
        self._db.autocommit = False
    
    def db(self):
        return self._db
    
    def hasTickets(self):
        c = self.db().cursor()
        c.execute('''SELECT count(*) FROM Ticket''')
        return int(c.fetchall()[0][0]) > 0
    
    def setTypeList(self, s):
        """Remove all types, set them to `s`"""
        if self.hasTickets():
            raise Exception("Will not modify database with existing tickets!")
        
        c = self.db().cursor()
        c.execute("""DELETE FROM enum WHERE kind='ticket_type'""")
        for i, value in enumerate(s):
            c.execute("""INSERT INTO enum (kind, name, value) VALUES (%s, %s, %s)""",
                      "ticket_type",
                      value,
                      i)
        self.db().commit()
    
    def setPriorityList(self, s):
        """Remove all priorities, set them to `s`"""
        if self.hasTickets():
            raise Exception("Will not modify database with existing tickets!")
        
        c = self.db().cursor()
        c.execute("""DELETE FROM enum WHERE kind='priority'""")
        for i, value in enumerate(s):
            c.execute("""INSERT INTO enum (kind, name, value) VALUES (%s, %s, %s)""",
                      "priority",
                      value,
                      i)
        self.db().commit()

    
    def setComponentList(self, l):
        """Remove all components, set them to `l`"""
        if self.hasTickets():
            raise Exception("Will not modify database with existing tickets!")
        
        c = self.db().cursor()
        c.execute("""DELETE FROM component""")
        for value in l:
            c.execute("""INSERT INTO component (name) VALUES (%s)""",
                      value)
        self.db().commit()
    
    def setVersionList(self, v):
        """Remove all versions, set them to `v`"""
        if self.hasTickets():
            raise Exception("Will not modify database with existing tickets!")
        
        c = self.db().cursor()
        c.execute("""DELETE FROM version""")
        for value in v:
            c.execute("""INSERT INTO version (name) VALUES (%s)""",
                      value)
        self.db().commit()
        
    def setMilestoneList(self, m):
        """Remove all milestones, set them to `m`"""
        if self.hasTickets():
            raise Exception("Will not modify database with existing tickets!")
        
        c = self.db().cursor()
        c.execute("""DELETE FROM milestone""")
        for value in m:
            c.execute("""INSERT INTO milestone (name) VALUES (%s)""",
                      value)
        self.db().commit()
    
    def addTicket(self, type, time, changetime, component,
                  priority, owner, reporter, cc,
                  version, milestone, status, resolution,
                  summary, description, keywords):
        c = self.db().cursor()
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
                  type, time, changetime, component,
                  priority, owner, reporter, cc,
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


def main():
    import optparse
    p = optparse.OptionParser('usage: %prog xml_export.xml /path/to/trac/environment')
    opt, args = p.parse_args()
    if len(args) != 2:
        p.error("Incorrect number of arguments")
    
    try:
        importData(open(args[0]), args[1])
    except Exception, e:
        print 'Error:', e

def importData(f, env):
    project = ExportedProjectData(f)
    
    db = TracDatabase(env)
    db.setTypeList(project.artifactTypes())
    db.setComponentList(project.categories())
    db.setPriorityList(range(1, 11))
    db.setVersionList(project.groups())
    db.setMilestoneList([])
    
    for a in project.artifacts():
        i = db.addTicket(type=a.artifact_type,
                         time=a.open_date,
                         changetime='',
                         component=a.category,
                         priority=a.priority,
                         owner=a.assigned_to,
                         reporter=a.submitted_by,
                         cc='',
                         version=a.artifact_group_id,
                         milestone='',
                         status=a.status,
                         resolution=a.resolution,
                         summary=a.summary,
                         description=a.details,
                         keywords='')
        print 'Imported %s as #%d' % (a.artifact_id, i)
        for msg in a.messages():
            db.addTicketComment(ticket=i,
                                time=msg.adddate,
                                author=msg.user_name,
                                value=msg.body)
        if a.messages():
            print '    imported %d messages for #%d' % (len(a.messages()), i)
        
        values = a.__dict__.copy()
        field_map = {'summary': 'summary'}
        for h in a.history():
            if h.field_name == 'close_date' and values.get(h.field_name, '') == '':
                f = 'status'
                oldvalue = 'assigned'
                newvalue = 'closed'
            else:
                f = field_map.get(h.field_name, None)
                oldvalue = h.old_value
                newvalue = values.get(h.field_name, '')
                
            if f:
                db.addTicketChange(ticket=i,
                                   time=h.entrydate,
                                   author=h.mod_by,
                                   field=f,
                                   oldvalue=oldvalue,
                                   newvalue=newvalue)
            values[h.field_name] = h.old_value

if __name__ == '__main__':
    main()
