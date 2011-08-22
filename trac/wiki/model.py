# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Jonas Borgström <jonas@edgewall.com>
#         Christopher Lenz <cmlenz@gmx.de>

from datetime import datetime

from trac.core import *
from trac.resource import Resource
from trac.util.datefmt import from_utimestamp, to_utimestamp, utc
from trac.util.translation import _
from trac.wiki.api import WikiSystem, validate_page_name


class WikiPage(object):
    """Represents a wiki page (new or existing)."""

    realm = 'wiki'

    def __init__(self, env, name=None, version=None, db=None):
        self.env = env
        if isinstance(name, Resource):
            self.resource = name
            name = self.resource.id
        else:
            if version:
                version = int(version) # must be a number or None
            self.resource = Resource('wiki', name, version)
        self.name = name
        if name:
            self._fetch(name, version, db)
        else:
            self.version = 0
            self.text = self.comment = self.author = ''
            self.time = None
            self.readonly = 0
        self.old_text = self.text
        self.old_readonly = self.readonly

    def _fetch(self, name, version=None, db=None):
        if not db:
            db = self.env.get_db_cnx()
        cursor = db.cursor()
        if version is not None:
            cursor.execute("SELECT version,time,author,text,comment,readonly "
                           "FROM wiki "
                           "WHERE name=%s AND version=%s",
                           (name, int(version)))
        else:
            cursor.execute("SELECT version,time,author,text,comment,readonly "
                           "FROM wiki "
                           "WHERE name=%s ORDER BY version DESC LIMIT 1",
                           (name,))
        row = cursor.fetchone()
        if row:
            version, time, author, text, comment, readonly = row
            self.version = int(version)
            self.author = author
            self.time = from_utimestamp(time)
            self.text = text
            self.comment = comment
            self.readonly = readonly and int(readonly) or 0
        else:
            self.version = 0
            self.text = self.comment = self.author = ''
            self.time = None
            self.readonly = 0
            
    exists = property(lambda self: self.version > 0)

    def delete(self, version=None, db=None):
        assert self.exists, 'Cannot delete non-existent page'
        
        @self.env.with_transaction(db)
        def do_delete(db):
            cursor = db.cursor()
            if version is None:
                # Delete a wiki page completely
                cursor.execute("DELETE FROM wiki WHERE name=%s", (self.name,))
                self.env.log.info('Deleted page %s' % self.name)
            else:
                # Delete only a specific page version
                cursor.execute("DELETE FROM wiki WHERE name=%s and version=%s",
                               (self.name, version))
                self.env.log.info('Deleted version %d of page %s'
                                  % (version, self.name))

            if version is None or version == self.version:
                self._fetch(self.name, None, db)

            if not self.exists:
                # Invalidate page name cache
                del WikiSystem(self.env).pages
                # Delete orphaned attachments
                from trac.attachment import Attachment
                Attachment.delete_all(self.env, 'wiki', self.name, db)

        # Let change listeners know about the deletion
        if not self.exists:
            for listener in WikiSystem(self.env).change_listeners:
                listener.wiki_page_deleted(self)
        else:
            for listener in WikiSystem(self.env).change_listeners:
                if hasattr(listener, 'wiki_page_version_deleted'):
                    listener.wiki_page_version_deleted(self)

    def save(self, author, comment, remote_addr, t=None, db=None):
        if not validate_page_name(self.name):
            raise TracError(_("Invalid Wiki page name '%(name)s'",
                              name=self.name))

        new_text = self.text != self.old_text
        if not new_text and self.readonly == self.old_readonly:
            raise TracError(_('Page not modified'))
        t = t or datetime.now(utc)

        @self.env.with_transaction(db)
        def do_save(db):
            cursor = db.cursor()
            if new_text:
                cursor.execute("""
                    INSERT INTO wiki (name,version,time,author,ipnr,text,
                                      comment,readonly)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (self.name, self.version + 1, to_utimestamp(t),
                          author, remote_addr, self.text, comment,
                          self.readonly))
                self.version += 1
                self.resource = self.resource(version=self.version)
            else:
                cursor.execute("UPDATE wiki SET readonly=%s WHERE name=%s",
                               (self.readonly, self.name))
            if self.version == 1:
                # Invalidate page name cache
                del WikiSystem(self.env).pages
        
        self.author = author
        self.comment = comment
        self.time = t

        for listener in WikiSystem(self.env).change_listeners:
            if self.version == 1:
                listener.wiki_page_added(self)
            else:
                listener.wiki_page_changed(self, self.version, t, comment,
                                           author, remote_addr)

        self.old_readonly = self.readonly
        self.old_text = self.text

    def rename(self, new_name):
        """Rename wiki page in-place, keeping the history intact.
        Renaming a page this way will eventually leave dangling references
        to the old page - which litterally doesn't exist anymore.
        """
        assert self.exists, 'Cannot rename non-existent page'

        if not validate_page_name(new_name):
            raise TracError(_("Invalid Wiki page name '%(name)s'",
                              name=new_name))
        old_name = self.name
        
        @self.env.with_transaction()
        def do_rename(db):
            cursor = db.cursor()
            new_page = WikiPage(self.env, new_name, db=db)
            if new_page.exists:
                raise TracError(_("Can't rename to existing %(name)s page.",
                                  name=new_name))

            cursor.execute("UPDATE wiki SET name=%s WHERE name=%s",
                           (new_name, old_name))
            # Invalidate page name cache
            del WikiSystem(self.env).pages
            # Reparent attachments
            from trac.attachment import Attachment
            Attachment.reparent_all(self.env, 'wiki', old_name, 'wiki',
                                    new_name)

        self.name = new_name
        self.env.log.info('Renamed page %s to %s', old_name, new_name)
        
        for listener in WikiSystem(self.env).change_listeners:
            if hasattr(listener, 'wiki_page_renamed'):
                listener.wiki_page_renamed(self, old_name)

    def get_history(self, db=None):
        if not db:
            db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT version,time,author,comment,ipnr FROM wiki "
                       "WHERE name=%s AND version<=%s "
                       "ORDER BY version DESC", (self.name, self.version))
        for version, ts, author, comment, ipnr in cursor:
            yield version, from_utimestamp(ts), author, comment, ipnr
