# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2005 Edgewall Software
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
# Author: Christopher Lenz <cmlenz@gmx.de>


class Repository(object):
    """
    Base class for a repository provided by a version control system.
    """

    def __init__(self, authz, log):
        self.authz = authz or Authorizer()
        self.log = log

    def close(self):
        """
        Close the connection to the repository.
        """
        raise NotImplementedError

    def get_changeset(self, rev):
        """
        Retrieve a Changeset object that describes the changes made in
        revision 'rev'.
        """
        raise NotImplementedError

    def get_node(self, path, rev=None):
        """
        Retrieve a Node (directory or file) from the repository at the
        given path. If the rev parameter is specified, the version of the
        node at that revision is returned, otherwise the latest version
        of the node is returned.
        """
        raise NotImplementedError

    def get_oldest_rev(self):
        """
        Return the oldest revision stored in the repository.
        """
        raise NotImplementedError
    oldest_rev = property(lambda x: x.get_oldest_rev())

    def get_youngest_rev(self):
        """
        Return the youngest revision in the repository.
        """
        raise NotImplementedError
    youngest_rev = property(lambda x: x.get_youngest_rev())

    def previous_rev(self, rev):
        """
        Return the revision immediately preceding the specified revision.
        """
        raise NotImplementedError

    def next_rev(self, rev):
        """
        Return the revision immediately following the specified revision.
        """
        raise NotImplementedError

    def get_youngest_rev_in_cache(self, db):
        """
        Return the youngest revision currently cached.
        The way revisions are sequenced is version control specific.
        By default, one assumes that the revisions are sequenced in time.
        """
        cursor = db.cursor()
        cursor.execute("SELECT rev FROM revision ORDER BY time DESC LIMIT 1")
        row = cursor.fetchone()
        return row and row[0] or None
        

class Node(object):
    """
    Represents a directory or file in the repository.
    """

    DIRECTORY = "dir"
    FILE = "file"

    def __init__(self, path, rev, kind):
        assert kind in (Node.DIRECTORY, Node.FILE), "Unknown node kind %s" % kind
        self.path = str(path)
        self.rev = rev
        self.kind = kind

    def get_content(self):
        """
        Return a stream for reading the content of the node. This method
        will return None for directories. The returned object should provide
        a read([len]) function.
        """
        raise NotImplementedError

    def get_entries(self):
        """
        Generator that yields the immediate child entries of a directory, in no
        particular order. If the node is a file, this method returns None.
        """
        raise NotImplementedError

    def get_history(self):
        """
        Generator that yields (path, rev) tuples, one for each revision in which
        the node was changed. This generator will follow copies and moves of a
        node (if the underlying version control system supports that), which
        will be indicated by the first element of the tuple (i.e. the path)
        changing.
        """
        raise NotImplementedError

    def get_properties(self):
        """
        Returns a dictionary containing the properties (meta-data) of the node.
        The set of properties depends on the version control system.
        """
        raise NotImplementedError

    def get_content_length(self):
        raise NotImplementedError
    content_length = property(lambda x: x.get_content_length())

    def get_content_type(self):
        raise NotImplementedError
    content_type = property(lambda x: x.get_content_type())

    def get_name(self):
        return self.path.split('/')[-1]
    name = property(lambda x: x.get_name())

    def get_last_modified(self):
        raise NotImplementedError
    last_modified = property(lambda x: x.get_last_modified())

    isdir = property(lambda x: x.kind is Node.DIRECTORY)
    isfile = property(lambda x: x.kind is Node.FILE)


class Changeset(object):
    """
    Represents a set of changes of a repository.
    """

    ADD = 'add'
    COPY = 'copy'
    DELETE = 'delete'
    EDIT = 'edit'
    MOVE = 'move'

    def __init__(self, rev, message, author, date):
        self.rev = rev
        self.message = message
        self.author = author
        self.date = date

    def get_changes(self):
        """
        Generator that produces a (path, kind, change, base_rev, base_path)
        tuple for every change in the changeset, where change can be one of
        Changeset.ADD, Changeset.COPY, Changeset.DELETE, Changeset.EDIT or
        Changeset.MOVE, and kind is one of Node.FILE or Node.DIRECTORY.
        """
        raise NotImplementedError


class PermissionDenied(Exception):
    """
    Exception raised by an authorizer if the user has insufficient permissions
    to view a specific part of the repository.
    """
    pass


class Authorizer(object):
    """
    Base class for authorizers that are responsible to granting or denying
    access to view certain parts of a repository.
    """

    def assert_permission(self, path):
        if not self.has_permission(path):
            raise PermissionDenied, \
                  'Insufficient permissions to access %s' % path

    def has_permission(self, path):
        return 1
    
    def has_permission_for_changeset(self, rev):
        return 1

