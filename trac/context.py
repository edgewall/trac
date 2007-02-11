# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# Copyright (C) 2003-2007 Christian Boos <cboos@neuf.fr>
# Copyright (C) 2003-2007 Alec Thomas <alec@swapoff.org>
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
# Author: Christian Boos <cboos@neuf.fr>
#         Alec Thomas <alec@swapoff.org>

from StringIO import StringIO

from trac.util.html import html, Markup
from trac.core import *
from trac.util import reversed


class ResourceError(TracError):
    """Base resource exception."""


class InvalidResourceSelector(ResourceError):
    """Thrown when an invalid resource selector is provided."""


class IContextProvider(Interface):
    """Map between Trac resources and their corresponding contexts."""

    def get_context_classes():
        """Generator yielding a list of `Context` subclasses."""


class Context(object):
    """Base class for Wiki rendering contexts.

    A context specifies ''which'' resource is accessed and ''how''
    this resource is accessed.

    The context is a lightweight resource descriptor. It identifies
    a resource using a `realm` information (e.g. `"wiki"`, `"ticket"`,
    etc.) and a `id` uniquely identifying the resource within its realm.
    If there's a data model associated to the resource, it can be
    retrieved using the `resource` property.
    As a resource is usually versioned, there's also a `version` property
    with the usual convention that `None` refers to the latest version
    of the resource.
    
    The context also knows about the "access context" of a Wiki content,
    i.e. how the resource is actually accessed. Most of the time, this
    is by the way of a web request (`req`). The parameters of that web
    request will be reused in order to generate correct URLs for hyperlinks
    related to the context (like `resource_href()`).
    If the request is not present in the context, the canonical base URLs
    as configured in the environment will be used.

    This also means that the user accessing the resource is known, and that
    specific access control rules can be enforced.

    Another aspect related to the access context consists of the scope or
    context trail by which the information belonging to a context is
    presented. It is quite usual that contexts are embedded in other
    contexts. This can be known by querying the `parent` context, which
    is automatically set when creating a subcontext from another context.
    This does '''not''' automatically imply that there's any relationship
    between the corresponding resources, though it can be that some
    resources are only fully identified when taking their parent context
    into account (like attachments, see `permid()`).

    For example, when rendering a ticket description from within a
    Custom Query rendered by the TicketQuery macro inside a wiki page,
    the context ''path'' will be:
    
    `Context(env, req)('wiki', 'CurrentStatus')('query')('ticket', '12')`

    Finally, the context could also know about the expected output MIME type
    which should be used to present the information to the user (TODO)
    """

    realm = None

    def __init__(self, env, req, realm=None, id=None, parent=None,
                 version=None, abs_urls=False, db=None, resource=None):
        if not env:
            raise TracError("Environment not specified for Context")
        self.env = env
        self.req = req
        self.realm = realm
        self.id = id
        self.parent = parent
        self.version = version
        self.abs_urls = abs_urls
        self._db = db
        self._perm = None
        self.set_resource(resource)

    def __repr__(self):
        path = []
        current = self
        while current:
            name = current.realm or '[root]'
            if current.id:
                name += ':' + unicode(current.id) # id can be numerical
            if current.version:
                name += '@' + unicode(current.version)
            path.append(name)
            current = current.parent
        detail = ''
        if self.abs_urls:
            detail += ' [abs]'
        if self._resource:
            detail += ' %r' % self._resource
        return '<Context %s%s%s>' % \
               (', '.join(reversed(path)),
                self.req and ' %r' % self.req or '', detail)
    
    def __call__(self, realm=None, id=None, version=False, abs_urls=None,
                 resource=None):
        """Create a new Context, usually a child of this Context.

        >>> from trac.test import EnvironmentStub
        >>> c = Context(EnvironmentStub(), None)

        >>> c1 = c('wiki', 'CurrentStatus')
        >>> c1
        <Context [root], wiki:CurrentStatus>

        If both `realm` and `id` are `None`, then the new context will
        actually be a copy of the current context, instead of a child context.
        
        >>> c2 = c1()
        >>> c2 
        <Context [root], wiki:CurrentStatus>
       
        >>> (c1.parent == c2.parent, c1.parent == c)
        (True, True)

        >>> c(abs_urls=True)('query')('ticket', '12')
        <Context [root], query, ticket:12 [abs]>

        In the case of a copy, if `version` is not specified or `False`,
        the current version will be kept. Setting `version` explicitely
        to `None` will request the latest version.

        >>> c3 = c1(version=3)
        >>> c3
        <Context [root], wiki:CurrentStatus@3>

        >>> c4 = c3()
        >>> c3
        <Context [root], wiki:CurrentStatus@3>

        Only changing the `id` results in another resource in the same realm.

        >>> c5 = c4(id='AnotherOne')
        >>> c5
        <Context [root], wiki:CurrentStatus@3, wiki:AnotherOne>
        
        """
        abs_urls = [abs_urls, self.abs_urls][abs_urls is None]
        if realm or id:
            # create a child context
            if version is False: # not set, use latest
                version = None
            return ResourceSystem(self.env).create_context(
                self.req, realm or self.realm, id, self,
                version=version, abs_urls=abs_urls, resource=resource)
        else:
            # copy current context
            copy = object.__new__(self.__class__)
            # strict copy
            copy.env = self.env
            copy.req = self.req
            copy.realm = self.realm
            copy.id = self.id
            copy.parent = self.parent
            copy._db = self._db
            copy._perm = self._perm
            # copy + update
            if version is False: # not set, keep existing
                version = self.version
            copy.version = version
            copy.abs_urls = abs_urls
            copy.set_resource(resource or self._resource)
            return copy

    def from_resource(cls, req, resource, *args, **kwargs):
        """Create a new Context from an existing Resource.

        Can take any other argument `__call__` can take, except `realm` and `id`
        which are deduced from the `resource` itself.
        """
        kwargs['resource'] = resource
        return ResourceSystem(resource.env).create_context(req, resource.realm,
                                                           resource.id, *args,
                                                           **kwargs)
    from_resource = classmethod(from_resource)

    def set_resource(self, resource):
        """Attach the given resource to this context.

        This could be overridden by subclasses, to ensure that the resource
        descriptor properties of the Context are always correctly reflecting
        the state of the `resource` itself (for the `version` property, for
        example).
        """
        self._resource = resource

    def _get_db(self):
        if not self._db:
            self._db = self.env.get_db_cnx()
        return self._db
    db = property(fget=_get_db)

    def _get_href(self):
        """Return an Href instance, adapted to the context."""
        base = self.req or self.env
        if self.abs_urls:
            return base.abs_href
        else:
            return base.href
    href = property(fget=_get_href)

    def get_resource(self):
        """Return the actual resource this context refers to.

        This should be overridden by subclasses in order to return
        the data model object corresponding to resource specified by
        the context.
        """
        if not self._resource:
            raise InvalidResourceSelector("Can't retrieve resource %s:%s" %
                                          (self.realm, self.id))
        return self._resource
    resource = property(lambda self: self.get_resource())

    def _get_perm(self):
        """Permissions specific to this context."""
        from trac.perm import PermissionCache
        if not self._perm:
            self._perm = PermissionCacheProxy(self)
        return self._perm
    perm = property(_get_perm)

    def resource_href(self, path=None, **kwargs):
        """Return a canonical URL for the resource associated to this Context.

        In addition, a relative `path` can be given to refer to another
        resource of the same realm, relative to the current one.

        >>> from trac.test import EnvironmentStub
        >>> c = Context(EnvironmentStub(), None)

        >>> c.resource_href()
        '/trac.cgi'

        >>> c(abs_urls=True).resource_href()
        'http://example.org/trac.cgi'

        >>> c('wiki', 'Main').resource_href()
        '/trac.cgi/wiki/Main'

        Relative references start at the current id:

        >>> c('wiki', 'Main').resource_href('./Sub')
        '/trac.cgi/wiki/Main/Sub'

        >>> c('wiki', 'Main/Sub').resource_href('..')
        '/trac.cgi/wiki/Main'

        >>> c('wiki', 'Main').resource_href('../Other')
        '/trac.cgi/wiki/Other'

        References always stay within the current resource realm:

        >>> main_sub = c('wiki', 'Main/Sub')
        >>> main_sub.resource_href('../..')
        '/trac.cgi/wiki'

        >>> main_sub.resource_href('../../..')
        '/trac.cgi/wiki'
        """
        if path and path[0] == '/': # absolute reference, start at project base
            return self.href(path.lstrip('/'), **kwargs)
        base = unicode(self.id or '').split('/')
        for comp in (path or '').split('/'):
            if comp in ('.', ''):
                continue
            elif comp == '..':
                if base:
                    base.pop()
            else:
                base.append(comp)
        return self.href(self.realm, *base, **kwargs)

    # -- wiki rendering methods

    def wiki_to_html(self, wikitext, escape_newlines=False):
        from trac.wiki.formatter import Formatter
        if not wikitext:
            return Markup()
        out = StringIO()
        Formatter(self).format(wikitext, out, escape_newlines)
        return Markup(out.getvalue())

    def wiki_to_oneliner(self, wikitext, shorten=False):
        from trac.wiki.formatter import OneLinerFormatter
        if not wikitext:
            return Markup()
        out = StringIO()
        OneLinerFormatter(self).format(wikitext, out, shorten)
        return Markup(out.getvalue())

    def wiki_to_outline(self, wikitext, max_depth=None, min_depth=None):
        from trac.wiki.formatter import OutlineFormatter
        if not wikitext:
            return Markup()
        out = StringIO()
        OutlineFormatter(self).format(wikitext, out, max_depth, min_depth)
        return Markup(out.getvalue())

    def wiki_to_link(self, wikitext):
        from trac.wiki.formatter import LinkFormatter
        if not wikitext:
            return ''
        return LinkFormatter(self).match(wikitext)

    # -- resource descriptors methods

    def permid(self):
        return (self.realm, self.id)
    # TODO: consider using a .depth class property?
    #       This would default to 1 and would be 2 for attachments.
    #       permid() would then be:
    #
    #         parent = self
    #         id = (,)
    #         for i in range(self.depth):
    #             id += (parent.realm, parent.id)
    #         return id

    def name(self):
        return '%s:%s' % (self.realm, self.id)

    def shortname(self):
        return self.name()

    def summary(self):
        summary = self.name()
        if self.version:
            summary += ' at version %s' % self.version
        return summary


class ResourceSystem(Component):
    """Helper component for creating Contexts."""

    context_providers = ExtensionPoint(IContextProvider)

    def __init__(self):
        self._context_map = None

    # Public methods

    def create_context(self, req, realm, *args, **kwargs):
        """Create the appropriate Context for the given `realm`.

        For the remaining arguments, see the Context constructor.
        """
        # build a dict of realm keys to Context subclasses values
        if not self._context_map:
            map = {}
            for provider in self.context_providers:
                for context_class in provider.get_context_classes():
                    map[context_class.realm] = context_class
            self._context_map = map
        context_class = self._context_map.get(realm, Context)
        return context_class(self.env, req, realm, *args, **kwargs)

    def get_known_realms(self):
        realms = []
        for provider in self.context_providers:
            for context_class in provider.get_context_classes():
                realms.append(context_class.realm)
        return realms


class PermissionCacheProxy(object):
    def __init__(self, context):
        self.context = context

    def __contains__(self, action):
        """Checks whether the given `action` is permitted."""
        return self.context.req.perm.__contains__(action, self.context)
    has_permission = __contains__

    def has_all(self, *actions):
        """Return `True` if all the `actions` are permitted."""
        return self.context.req.perm.has_all(actions, self.context)

    def has_any(self, *actions):
        """Return `True` if at least one of the `actions` is permitted."""
        return self.context.req.perm.has_any(actions, self.context)

    def require(self, action):
        """Ensure that the given `action` is permitted."""
        return self.context.req.perm.require(action, self.context)
    assert_permission = require

    def require_all(self, *actions):
        """Ensure that all of the given `actions` are permitted."""
        return self.context.req.perm.require_all(actions, self.context)

    def require_any(self, *actions):
        """Ensure that at least one of the given `actions` is permitted."""
        return self.context.req.perm.require_any(actions, self.context)
