# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004, 2005 Edgewall Software
# Copyright (C) 2003, 2004, 2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
# Author: Jonas Borgström <jonas@edgewall.com>
#         Christopher Lenz <cmlenz@gmx.de>

from trac.attachment import Attachment
from trac.core import *
from trac.wiki.api import WikiSystem

import time


class WikiPage(object):
    """
    Represents a wiki page (new or existing).
    """
    def __init__(self, env, name=None, version=None, db=None):
        self.env = env
        self.name = name
        self._fetch(name, version, db)
        self.old_text = self.text
        self.old_readonly = self.readonly

    def _fetch(self, name, version=None, db=None):
        if not db:
            db = self.env.get_db_cnx()
        cursor = db.cursor()
        if version:
            cursor.execute("SELECT version,text,readonly FROM wiki "
                           "WHERE name=%s AND version=%s",
                           (name, int(version)))
        else:
            cursor.execute("SELECT version,text,readonly FROM wiki "
                           "WHERE name=%s ORDER BY version DESC LIMIT 1",
                           (name,))
        row = cursor.fetchone()
        if row:
            version,text,readonly = row
            self.version = int(version)
            self.text = text
            self.readonly = readonly and int(readonly) or 0
        else:
            self.version = -1
            self.text = ''
            self.readonly = 0

    exists = property(fget=lambda self: self.version >= 0)

    def delete(self, version=None, db=None):
        assert self.exists, 'Cannot delete non-existent page'
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        cursor = db.cursor()
        if version is None:
            # Delete a wiki page completely
            cursor.execute("DELETE FROM wiki WHERE name=%s", (self.name,))
            self.env.log.info('Deleted page %s' % self.name)
            page_deleted = True
        else:
            # Delete only a specific page version
            cursor.execute("DELETE FROM wiki WHERE name=%s and version=%s",
                           (self.name, version))
            self.env.log.info('Deleted version %d of page %s'
                              % (version, self.name))
            cursor.execute("SELECT COUNT(*) FROM wiki WHERE name=%s",
                           (self.name,))
            if cursor.fetchone():
                page_deleted = True

        if page_deleted:
            # Delete orphaned attachments
            for attachment in Attachment.select(self.env, 'wiki', self.name, db):
                attachment.delete(db)

            # Let change listeners know about the deletion
            for listener in WikiSystem(self.env).change_listeners:
                listener.wiki_page_deleted(self)

        if handle_ta:
            db.commit()
        self.version = 0

    def save(self, author, comment, remote_addr, t=time.time(), db=None):
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        if self.text != self.old_text:
            cursor = db.cursor()
            cursor.execute("INSERT INTO WIKI (name,version,time,author,ipnr,"
                           "text,comment,readonly) VALUES (%s,%s,%s,%s,%s,%s,"
                           "%s,%s)", (self.name, self.version + 1, t, author,
                           remote_addr, self.text, comment, self.readonly))
            self.version += 1
        elif self.readonly != self.old_readonly:
            cursor = db.cursor()
            cursor.execute("UPDATE wiki SET readonly=%s WHERE name=%s",
                           (self.readonly, self.name))
        else:
            raise TracError('Page not modified')

        if handle_ta:
            db.commit()

        for listener in WikiSystem(self.env).change_listeners:
            if self.version == 0:
                listener.wiki_page_added(self)
            else:
                listener.wiki_page_changed(self, self.version, t, author,
                                           comment, remote_addr)

        self.old_readonly = self.readonly
        self.old_text = self.text

    def get_history(self, db=None):
        if not db:
            db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT version,time,author,comment,ipnr FROM wiki "
                       "WHERE name=%s AND version<=%s "
                       "ORDER BY version DESC", (self.name, self.version))
        for version,time,author,comment,ipnr in cursor:
            yield version,time,author,comment,ipnr
