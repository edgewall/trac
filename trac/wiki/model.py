# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2018 Edgewall Software
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

from trac.core import *
from trac.resource import Resource
from trac.util.datefmt import datetime_now, from_utimestamp, to_utimestamp, utc
from trac.util.translation import _
from trac.wiki.api import WikiSystem, validate_page_name


class WikiPage(object):
    """Represents a wiki page (new or existing).

    :since 1.0.3: the `ipnr` is deprecated and will be removed in 1.3.1
    """

    realm = WikiSystem.realm

    @property
    def resource(self):
        return Resource(self.realm, self.name, self._resource_version)

    def __init__(self, env, name=None, version=None):
        """Create a new page object or retrieves an existing page.

        :param env: an `Environment` object.
        :param name: the page name or a `Resource` object.
        :param version: the page version. The value takes precedence over the
                        `Resource` version when both are specified.
        """
        self.env = env
        if version:
            try:
                version = int(version)
            except ValueError:
                version = None

        if isinstance(name, Resource):
            resource = name
            name = resource.id
            if version is None and resource.version is not None:
                try:
                    version = int(resource.version)
                except ValueError:
                    version = None

        self.name = name
        # The version attribute always returns the version of the page,
        # however resource.version will be None when version hasn't been
        # specified when creating the object and the object represents the
        # most recent version of the page. This behavior is used in web_ui.py
        # to determine whether to render a versioned page, or just the most
        # recent version of the page.
        self._resource_version = version
        if name:
            self._fetch(name, version)
        else:
            self.version = 0
            self.text = self.comment = self.author = ''
            self.time = None
            self.readonly = 0
        self.old_text = self.text
        self.old_readonly = self.readonly

    def _fetch(self, name, version=None):
        if version is not None:
            sql = """SELECT version, time, author, text, comment, readonly
                     FROM wiki WHERE name=%s AND version=%s"""
            args = (name, int(version))
        else:
            sql = """SELECT version, time, author, text, comment, readonly
                     FROM wiki WHERE name=%s ORDER BY version DESC LIMIT 1"""
            args = (name,)
        for version, time, author, text, comment, readonly in \
                self.env.db_query(sql, args):
            self.version = int(version)
            self.author = author
            self.time = from_utimestamp(time)
            self.text = text
            self.comment = comment
            self.readonly = int(readonly) if readonly else 0
            break
        else:
            self.version = 0
            self.text = self.comment = self.author = ''
            self.time = None
            self.readonly = 0

    def __repr__(self):
        if self.name is None:
            name = self.name
        else:
            name = u'%s@%s' % (self.name, self.version)
        return '<%s %r>' % (self.__class__.__name__, name)

    exists = property(lambda self: self.version > 0)

    def delete(self, version=None):
        """Delete one or all versions of a page.
        """
        if not self.exists:
            raise TracError(_("Cannot delete non-existent page"))

        with self.env.db_transaction as db:
            if version is None:
                # Delete a wiki page completely
                db("DELETE FROM wiki WHERE name=%s", (self.name,))
                self.env.log.info("Deleted page %s", self.name)
            else:
                # Delete only a specific page version
                db("DELETE FROM wiki WHERE name=%s and version=%s",
                   (self.name, version))
                self.env.log.info("Deleted version %d of page %s", version,
                                  self.name)

            if version is None or version == self.version:
                self._fetch(self.name, None)

            if not self.exists:
                # Invalidate page name cache
                del WikiSystem(self.env).pages
                # Delete orphaned attachments
                from trac.attachment import Attachment
                Attachment.delete_all(self.env, self.realm, self.name)

        # Let change listeners know about the deletion
        if not self.exists:
            for listener in WikiSystem(self.env).change_listeners:
                listener.wiki_page_deleted(self)
        else:
            for listener in WikiSystem(self.env).change_listeners:
                if hasattr(listener, 'wiki_page_version_deleted'):
                    listener.wiki_page_version_deleted(self)

    def save(self, author, comment, remote_addr=None, t=None):
        """Save a new version of a page.

        :since 1.0.3: `remote_addr` is optional and deprecated, and will be
                      removed in 1.3.1
        """
        if not validate_page_name(self.name):
            raise TracError(_("Invalid Wiki page name '%(name)s'",
                              name=self.name))

        new_text = self.text != self.old_text
        if not new_text and self.readonly == self.old_readonly:
            raise TracError(_("Page not modified"))
        t = t or datetime_now(utc)

        with self.env.db_transaction as db:
            if new_text:
                db("""INSERT INTO wiki (name, version, time, author, ipnr,
                                        text, comment, readonly)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                      """, (self.name, self.version + 1, to_utimestamp(t),
                            author, remote_addr, self.text, comment,
                            self.readonly))
                self.version += 1
            else:
                db("UPDATE wiki SET readonly=%s WHERE name=%s",
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
                from trac.util import arity
                if arity(listener.wiki_page_changed) == 6:
                    listener.wiki_page_changed(self, self.version, t,
                                               comment, author, remote_addr)
                else:
                    listener.wiki_page_changed(self, self.version, t,
                                               comment, author)

        self.old_readonly = self.readonly
        self.old_text = self.text

    def rename(self, new_name):
        """Rename wiki page in-place, keeping the history intact.
        Renaming a page this way will eventually leave dangling references
        to the old page - which literally doesn't exist anymore.
        """
        if not self.exists:
            raise TracError(_("Cannot rename non-existent page"))

        if not validate_page_name(new_name):
            raise TracError(_("Invalid Wiki page name '%(name)s'",
                              name=new_name))
        old_name = self.name

        with self.env.db_transaction as db:
            new_page = WikiPage(self.env, new_name)
            if new_page.exists:
                raise TracError(_("Can't rename to existing %(name)s page.",
                                  name=new_name))

            db("UPDATE wiki SET name=%s WHERE name=%s", (new_name, old_name))
            # Invalidate page name cache
            del WikiSystem(self.env).pages
            # Reparent attachments
            from trac.attachment import Attachment
            Attachment.reparent_all(self.env, self.realm, old_name,
                                    self.realm, new_name)

        self.name = new_name
        self.env.log.info("Renamed page %s to %s", old_name, new_name)

        for listener in WikiSystem(self.env).change_listeners:
            if hasattr(listener, 'wiki_page_renamed'):
                listener.wiki_page_renamed(self, old_name)

    def edit_comment(self, new_comment):
        """Edit comment of wiki page version in-place."""
        if not self.exists:
            raise TracError(_("Cannot edit comment of non-existent page"))

        old_comment = self.comment

        with self.env.db_transaction as db:
            db("UPDATE wiki SET comment=%s WHERE name=%s AND version=%s",
               (new_comment, self.name, self.version))

        self.comment = new_comment
        self.env.log.info("Changed comment on page %s version %s to %s",
                          self.name, self.version, new_comment)

        for listener in WikiSystem(self.env).change_listeners:
            if hasattr(listener, 'wiki_page_comment_modified'):
                listener.wiki_page_comment_modified(self, old_comment)

    def get_history(self):
        """Retrieve the edit history of a wiki page.

        :return: a tuple containing the `version`, `datetime`, `author`,
                  `comment` and `ipnr`.
        :since 1.0.3: use of `ipnr` is deprecated and will be removed in 1.3.1
        """
        for version, ts, author, comment, ipnr in self.env.db_query("""
                SELECT version, time, author, comment, ipnr FROM wiki
                WHERE name=%s AND version<=%s ORDER BY version DESC
                """, (self.name, self.version)):
            yield version, from_utimestamp(ts), author, comment, ipnr
