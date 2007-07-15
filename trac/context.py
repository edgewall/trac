# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2007 Edgewall Software
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

from trac.util.html import html
from trac.core import *
from trac.util import reversed


class ResourceError(TracError):
    """Base resource exception."""


class InvalidResourceSelector(ResourceError):
    """Thrown when an invalid resource selector is provided."""


class ResourceNotFound(ResourceError):
    """Thrown when a non-existent resource is requested"""


class IContextProvider(Interface):
    """Map between Trac resources and their corresponding contexts."""

    def get_context_classes():
        """Generator yielding a list of `Context` subclasses."""


class RenderingContext(object):
    """Rendering contexts.

    This specifies ''how'' a rendering should be done, with various
    options that might be relevant to some or all the renderers.
    """

    abs_urls = False
    escape_newlines = False
    shorten = False

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
    
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

    def __init__(self, env, req, **kwargs):
        # XXX Remove and replace ^^ kwargs when sure things aren't going to break.
        assert env, 'Environment not specified for Context'
        self.env = env
        self.req = req
        self.parent = kwargs.pop('parent', None)
        self.abs_urls = kwargs.pop('abs_urls', None)
        self._db = kwargs.pop('db', None)
        self.realm = None
        self.id = None
        self.version = None
        self.resource = None
        assert not kwargs, 'Context now only accepts "env", "req" positional ' \
                           'arguments, followed by keyword arguments "abs_urls", ' \
                           '"parent" and "db"'

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
        return '<Context %r%s%s>' % \
               (', '.join(reversed(path)),
                self.req and ' %r' % self.req or '', detail)
    
    def __call__(self, realm=None, id=None, version=False, abs_urls=None,
                 resource=None):
        """Create a new Context, usually a child of this Context.

        >>> from trac.test import EnvironmentStub
        >>> c = Context(EnvironmentStub(), None)

        >>> c1 = c('wiki', 'CurrentStatus')
        >>> c1
        <Context u'[root], wiki:CurrentStatus'>

        If both `realm` and `id` are `None`, then the new context will
        actually be a copy of the current context, instead of a child context.
        
        >>> c2 = c1()
        >>> c2 
        <Context u'[root], wiki:CurrentStatus'>
       
        >>> (c1.parent == c2.parent, c1.parent == c)
        (True, True)

        >>> c(abs_urls=True)('query')('ticket', '12')
        <Context u'[root], query, ticket:12' [abs]>

        In the case of a copy, if `version` is not specified or `False`,
        the current version will be kept. Setting `version` explicitely
        to `None` will request the latest version.

        >>> c3 = c1(version=3)
        >>> c3
        <Context u'[root], wiki:CurrentStatus@3'>

        >>> c4 = c3()
        >>> c4
        <Context u'[root], wiki:CurrentStatus@3'>

        Only changing the `id` results in another resource in the same realm.

        >>> c5 = c4(id='AnotherOne')
        >>> c5
        <Context u'[root], wiki:CurrentStatus@3, wiki:AnotherOne'>
        
        """
        if abs_urls is None:
            abs_urls = self.abs_urls
        if realm or id:
            # create a child context
            if version is False: # not set, use latest
                version = None
            realm = realm or self.realm
            cls = ResourceSystem(self.env).realm_context_class(realm)
            context = cls(self.env, self.req, parent=self, abs_urls=abs_urls)
            context._populate(realm, id, version, abs_urls, resource)
            return context
        else:
            # copy current context
            copy = object.__new__(self.__class__)
            # strict copy
            copy.env = self.env
            copy.req = self.req
            copy.parent = self.parent
            copy._db = self._db
            if version is False: # not set, keep existing
                version = self.version
            copy._populate(self.realm, self.id, version, abs_urls,
                           resource or self._resource)
            return copy

    def _populate(self, realm=None, id=None, version=None, abs_urls=None,
                  resource=None):
            self.realm = realm
            self.id = id
            self.version = version
            self.resource = resource
            self.version = version
            self.abs_urls = abs_urls

    def from_resource(cls, req, resource, *args, **kwargs):
        """Create a new Context from an existing Resource.

        Can take any other argument `__call__` can take, except `realm` and `id`
        which are deduced from the `resource` itself.
        """
        kwargs['resource'] = resource
        cls = ResourceSystem(self.env).realm_context_class(realm)
        context = cls(self.env, req, resource=resource) \
                     (resource.realm, resource.id, *args, **kwargs)
        context._populate(realm, id, version)
        return context
    from_resource = classmethod(from_resource)

    def get_resource(self):
        """Return the actual resource this context refers to.

        This should be overridden by subclasses in order to return
        the data model object corresponding to resource specified by
        the context.
        """
        return None

    def set_resource(self, resource):
        """Attach the given resource to this context.

        This could be overridden by subclasses, to ensure that the resource
        descriptor properties of the Context are always correctly reflecting
        the state of the `resource` itself (for the `version` property, for
        example).
        """
        pass

    def __hash__(self):
        """Hash this context, including the context heirarchy."""
        path = []
        current = self
        while current:
            path.extend((self.realm, self.id, self.version))
            current = current.parent
        return hash(tuple(path))

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

    def _get_resource(self):
        if not self._resource:
            self._resource = self.get_resource()
            if not self._resource:
                raise InvalidResourceSelector("Can't retrieve resource %s:%s" %
                                              (self.realm, self.id))
        return self._resource
    def _set_resource(self, resource):
        self.set_resource(resource)
        self._resource = resource
    resource = property(_get_resource, _set_resource)

    def get_href(self, href, path=None, **kwargs):
        """Produce a link to the associated resource
        
        Uses the given `Href` as a base. ''ResourceDescriptor''
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
        return href(self.realm, *base, **kwargs)

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
        return self.get_href(self.href, path, **kwargs)

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

    def realm_context_class(self, realm):
        """Return the Context subclass for a realm, or Context."""
        # build a dict of realm keys to Context subclasses values
        if not self._context_map:
            map = {}
            for provider in self.context_providers:
                for context_class in provider.get_context_classes():
                    map[context_class.realm] = context_class
            self._context_map = map
        return self._context_map.get(realm, Context)

    def get_known_realms(self):
        realms = []
        for provider in self.context_providers:
            for context_class in provider.get_context_classes():
                realms.append(context_class.realm)
        return realms
