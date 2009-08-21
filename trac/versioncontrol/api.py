# -*- coding: utf-8 -*-
#
# Copyright (C)2005-2009 Edgewall Software
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
# Author: Christopher Lenz <cmlenz@gmx.de>

import os.path

try:
    import threading
except ImportError:
    import dummy_threading as threading
    threading._get_ident = lambda: 0

from trac.config import Option
from trac.core import *
from trac.perm import PermissionError
from trac.resource import IResourceManager, ResourceSystem, ResourceNotFound
from trac.util.text import to_unicode
from trac.util.translation import _
from trac.web.api import IRequestFilter


class IRepositoryConnector(Interface):
    """Provide support for a specific version control system."""

    error = None # place holder for storing relevant error message

    def get_supported_types():
        """Return the types of version control systems that are supported.

        Yields `(repotype, priority)` pairs, where `repotype` is used to
        match against the configured `[trac] repository_type` value in TracIni.
        
        If multiple provider match a given type, the `priority` is used to
        choose between them (highest number is highest priority).

        If the `priority` returned is negative, this indicates that the 
        connector for the given `repotype` indeed exists but can't be
        used for some reason. The `error` property can then be used to 
        store an error message or exception relevant to the problem detected.
        """

    def get_repository(repos_type, repos_dir, authname):
        """Return a Repository instance for the given repository type and dir.
        """


class RepositoryManager(Component):
    """Component registering the supported version control systems,

    It provides easy access to the configured implementation.
    """

    implements(IRequestFilter, IResourceManager)

    connectors = ExtensionPoint(IRepositoryConnector)

    repository_type = Option('trac', 'repository_type', 'svn',
        """Repository connector type. (''since 0.10'')""")
    repository_dir = Option('trac', 'repository_dir', '',
        """Path to local repository. This can also be a relative path
        (''since 0.11'').""")

    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()
        self._connector = None

    # IRequestFilter methods

    def pre_process_request(self, req, handler):
        from trac.web.chrome import Chrome, add_warning
        if handler is not Chrome(self.env):
            try:
                self.get_repository(req.authname).sync()
            except TracError, e:
                add_warning(req, _("Can't synchronize with the repository "
                              "(%(error)s). Look in the Trac log for more "
                              "information.", error=to_unicode(e.message)))
                          
        return handler

    def post_process_request(self, req, template, content_type):
        return (template, content_type)

    # IResourceManager methods

    def get_resource_realms(self):
        yield 'changeset'
        yield 'source'

    def get_resource_description(self, resource, format=None, **kwargs):
        if resource.realm == 'changeset':
            return _("Changeset %(rev)s", rev=resource.id)
        elif resource.realm == 'source':
            version = ''
            if format == 'summary':
                repos = resource.env.get_repository() # no perm.username!
                node = repos.get_node(resource.id, resource.version)
                if node.isdir:
                    kind = _("Directory")
                elif node.isfile:
                    kind = _("File")
                if resource.version:
                    version = _("at version %(rev)s", rev=resource.version)
            else:
                kind = _("Path")
                if resource.version:
                    version = '@%s' % resource.version
            return '%s %s%s' % (kind, resource.id, version)

    # Public API methods

    def get_repository(self, authname):
        db = self.env.get_db_cnx() # prevent possible deadlock, see #4465
        try:
            self._lock.acquire()
            if not self._connector:
                candidates = [
                    (prio, connector)
                    for connector in self.connectors
                    for repos_type, prio in connector.get_supported_types()
                    if repos_type == self.repository_type
                ]
                if candidates:
                    prio, connector = max(candidates)
                    if prio < 0: # error condition
                        raise TracError(
                            _('Unsupported version control system "%(name)s"'
                              ': "%(error)s" ', name=self.repository_type, 
                              error=to_unicode(connector.error)))
                    self._connector = connector
                else:
                    raise TracError(
                        _('Unsupported version control system "%(name)s": '
                          'Can\'t find an appropriate component, maybe the '
                          'corresponding plugin was not enabled? ',
                          name=self.repository_type))
            tid = threading._get_ident()
            if tid in self._cache:
                repos = self._cache[tid]
            else:
                rtype, rdir = self.repository_type, self.repository_dir
                if not os.path.isabs(rdir):
                    rdir = os.path.join(self.env.path, rdir)
                repos = self._connector.get_repository(rtype, rdir, authname)
                self._cache[tid] = repos
            return repos
        finally:
            self._lock.release()

    def shutdown(self, tid=None):
        if tid:
            assert tid == threading._get_ident()
            try:
                self._lock.acquire()
                repos = self._cache.pop(tid, None)
                if repos:
                    repos.close()
            finally:
                self._lock.release()


class NoSuchChangeset(ResourceNotFound):
    def __init__(self, rev):
        ResourceNotFound.__init__(self,
                                  _('No changeset %(rev)s in the repository',
                                    rev=rev),
                                  _('No such changeset'))

class NoSuchNode(ResourceNotFound):
    def __init__(self, path, rev, msg=None):
        ResourceNotFound.__init__(self, "%sNo node %s at revision %s" %
                                  ((msg and '%s: ' % msg) or '', path, rev),
                                  _('No such node'))

class Repository(object):
    """Base class for a repository provided by a version control system."""

    def __init__(self, name, authz, log):
        self.name = name
        self.authz = authz or Authorizer()
        self.log = log

    def close(self):
        """Close the connection to the repository."""
        raise NotImplementedError

    def clear(self, youngest_rev=None):
        """Clear any data that may have been cached in instance properties.

        `youngest_rev` can be specified as a way to force the value
        of the `youngest_rev` property (''will change in 0.12'').
        """
        pass

    def sync(self, rev_callback=None):
        """Perform a sync of the repository cache, if relevant.
        
        If given, `rev_callback` must be a callable taking a `rev` parameter.
        The backend will call this function for each `rev` it decided to
        synchronize, once the synchronization changes are committed to the 
        cache.
        """
        pass

    def sync_changeset(self, rev):
        """Resync the repository cache for the given `rev`, if relevant."""
        raise NotImplementedError

    def get_quickjump_entries(self, rev):
        """Generate a list of interesting places in the repository.

        `rev` might be used to restrict the list of available locations,
        but in general it's best to produce all known locations.

        The generated results must be of the form (category, name, path, rev).
        """
        return []
    
    def get_changeset(self, rev):
        """Retrieve a Changeset corresponding to the  given revision `rev`."""
        raise NotImplementedError

    def get_changesets(self, start, stop):
        """Generate Changeset belonging to the given time period (start, stop).
        """
        rev = self.youngest_rev
        while rev:
            if self.authz.has_permission_for_changeset(rev):
                chgset = self.get_changeset(rev)
                if chgset.date < start:
                    return
                if chgset.date < stop:
                    yield chgset
            rev = self.previous_rev(rev)

    def has_node(self, path, rev=None):
        """Tell if there's a node at the specified (path,rev) combination.

        When `rev` is `None`, the latest revision is implied.
        """
        try:
            self.get_node(path, rev)
            return True
        except TracError:
            return False        
    
    def get_node(self, path, rev=None):
        """Retrieve a Node from the repository at the given path.

        A Node represents a directory or a file at a given revision in the
        repository.
        If the `rev` parameter is specified, the Node corresponding to that
        revision is returned, otherwise the Node corresponding to the youngest
        revision is returned.
        """
        raise NotImplementedError

    def get_oldest_rev(self):
        """Return the oldest revision stored in the repository."""
        raise NotImplementedError
    oldest_rev = property(lambda x: x.get_oldest_rev())

    def get_youngest_rev(self):
        """Return the youngest revision in the repository."""
        raise NotImplementedError
    youngest_rev = property(lambda x: x.get_youngest_rev())

    def previous_rev(self, rev, path=''):
        """Return the revision immediately preceding the specified revision."""
        raise NotImplementedError

    def next_rev(self, rev, path=''):
        """Return the revision immediately following the specified revision."""
        raise NotImplementedError

    def rev_older_than(self, rev1, rev2):
        """Provides a total order over revisions.
        
        Return `True` if `rev1` is older than `rev2`, i.e. if `rev1`
        comes before `rev2` in the revision sequence.
        """
        raise NotImplementedError

    def get_youngest_rev_in_cache(self, db):
        """Return the youngest revision currently cached.
        
        The way revisions are sequenced is version control specific.
        By default, one assumes that the revisions are sequenced in time
        (... which is ''not'' correct for most VCS, including Subversion).

        (Deprecated, will not be used anymore in Trac 0.12)
        """
        cursor = db.cursor()
        cursor.execute("SELECT rev FROM revision ORDER BY time DESC LIMIT 1")
        row = cursor.fetchone()
        return row and row[0] or None

    def get_path_history(self, path, rev=None, limit=None):
        """Retrieve all the revisions containing this path

        If given, `rev` is used as a starting point (i.e. no revision
        ''newer'' than `rev` should be returned).
        The result format should be the same as the one of Node.get_history()
        """
        raise NotImplementedError

    def normalize_path(self, path):
        """Return a canonical representation of path in the repos."""
        raise NotImplementedError

    def normalize_rev(self, rev):
        """Return a canonical representation of a revision.

        It's up to the backend to decide which string values of `rev` 
        (usually provided by the user) should be accepted, and how they 
        should be normalized. Some backends may for instance want to match
        against known tags or branch names.
        
        In addition, if `rev` is `None` or '', the youngest revision should
        be returned.
        """
        raise NotImplementedError

    def short_rev(self, rev):
        """Return a compact representation of a revision in the repos."""
        return self.normalize_rev(rev)
        
    def get_changes(self, old_path, old_rev, new_path, new_rev,
                    ignore_ancestry=1):
        """Generates changes corresponding to generalized diffs.
        
        Generator that yields change tuples (old_node, new_node, kind, change)
        for each node change between the two arbitrary (path,rev) pairs.

        The old_node is assumed to be None when the change is an ADD,
        the new_node is assumed to be None when the change is a DELETE.
        """
        raise NotImplementedError


class Node(object):
    """Represents a directory or file in the repository at a given revision."""

    DIRECTORY = "dir"
    FILE = "file"

    # created_path and created_rev properties refer to the Node "creation"
    # in the Subversion meaning of a Node in a versioned tree (see #3340).
    #
    # Those properties must be set by subclasses.
    #
    created_rev = None   
    created_path = None

    def __init__(self, path, rev, kind):
        assert kind in (Node.DIRECTORY, Node.FILE), \
               "Unknown node kind %s" % kind
        self.path = to_unicode(path)
        self.rev = rev
        self.kind = kind

    def get_content(self):
        """Return a stream for reading the content of the node.

        This method will return `None` for directories.
        The returned object must support a `read([len])` method.
        """
        raise NotImplementedError

    def get_entries(self):
        """Generator that yields the immediate child entries of a directory.

        The entries are returned in no particular order.
        If the node is a file, this method returns `None`.
        """
        raise NotImplementedError

    def get_history(self, limit=None):
        """Provide backward history for this Node.
        
        Generator that yields `(path, rev, chg)` tuples, one for each revision
        in which the node was changed. This generator will follow copies and
        moves of a node (if the underlying version control system supports
        that), which will be indicated by the first element of the tuple
        (i.e. the path) changing.
        Starts with an entry for the current revision.

        :param limit: if given, yield at most ``limit`` results.
        """
        raise NotImplementedError

    def get_previous(self):
        """Return the change event corresponding to the previous revision.

        This returns a `(path, rev, chg)` tuple.
        """
        skip = True
        for p in self.get_history(2):
            if skip:
                skip = False
            else:
                return p

    def get_annotations(self):
        """Provide detailed backward history for the content of this Node.

        Retrieve an array of revisions, one `rev` for each line of content
        for that node.
        Only expected to work on (text) FILE nodes, of course.
        """
        raise NotImplementedError

    def get_properties(self):
        """Returns the properties (meta-data) of the node, as a dictionary.

        The set of properties depends on the version control system.
        """
        raise NotImplementedError

    def get_content_length(self):
        """The length in bytes of the content.

        Will be `None` for a directory.
        """
        raise NotImplementedError
    content_length = property(lambda x: x.get_content_length())

    def get_content_type(self):
        """The MIME type corresponding to the content, if known.

        Will be `None` for a directory.
        """
        raise NotImplementedError
    content_type = property(lambda x: x.get_content_type())

    def get_name(self):
        return self.path.split('/')[-1]
    name = property(lambda x: x.get_name())

    def get_last_modified(self):
        raise NotImplementedError
    last_modified = property(lambda x: x.get_last_modified())

    isdir = property(lambda x: x.kind == Node.DIRECTORY)
    isfile = property(lambda x: x.kind == Node.FILE)


class Changeset(object):
    """Represents a set of changes committed at once in a repository."""

    ADD = 'add'
    COPY = 'copy'
    DELETE = 'delete'
    EDIT = 'edit'
    MOVE = 'move'

    # change types which can have diff associated to them
    DIFF_CHANGES = (EDIT, COPY, MOVE) # MERGE
    OTHER_CHANGES = (ADD, DELETE)
    ALL_CHANGES = DIFF_CHANGES + OTHER_CHANGES

    def __init__(self, rev, message, author, date):
        self.rev = rev
        self.message = message or ''
        self.author = author or ''
        self.date = date

    def get_properties(self):
        """Returns the properties (meta-data) of the node, as a dictionary.

        The set of properties depends on the version control system.

        Warning: this used to yield 4-elements tuple (besides `name` and
        `text`, there were `wikiflag` and `htmlclass` values).
        This is now replaced by the usage of IPropertyRenderer (see #1601).
        """
        return []
        
    def get_changes(self):
        """Generator that produces a tuple for every change in the changeset

        The tuple will contain `(path, kind, change, base_path, base_rev)`,
        where `change` can be one of Changeset.ADD, Changeset.COPY,
        Changeset.DELETE, Changeset.EDIT or Changeset.MOVE,
        and `kind` is one of Node.FILE or Node.DIRECTORY.
        The `path` is the targeted path for the `change` (which is
        the ''deleted'' path  for a DELETE change).
        The `base_path` and `base_rev` are the source path and rev for the
        action (`None` and `-1` in the case of an ADD change).
        """
        raise NotImplementedError


class PermissionDenied(PermissionError):
    """Exception raised by an authorizer.

    This exception is raise if the user has insufficient permissions
    to view a specific part of the repository.
    """
    def __str__(self):
        return self.action


class Authorizer(object):
    """Controls the view access to parts of the repository.
    
    Base class for authorizers that are responsible to granting or denying
    access to view certain parts of a repository.
    """

    def assert_permission(self, path):
        if not self.has_permission(path):
            raise PermissionDenied(_('Insufficient permissions to access '
                                     '%(path)s', path=path))

    def assert_permission_for_changeset(self, rev):
        if not self.has_permission_for_changeset(rev):
            raise PermissionDenied(_('Insufficient permissions to access '
                                     'changeset %(id)s', id=rev))

    def has_permission(self, path):
        return True

    def has_permission_for_changeset(self, rev):
        return True
