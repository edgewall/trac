# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2009 Edgewall Software
# Copyright (C) 2006-2007 Alec Thomas <alec@swapoff.org>
# Copyright (C) 2007 Christian Boos <cboos@neuf.fr>
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

from trac.core import *
from trac.util.translation import _


class ResourceNotFound(TracError):
    """Thrown when a non-existent resource is requested"""


class IResourceManager(Interface):

    def get_resource_realms():
        """Return resource realms managed by the component.

        :rtype: `basestring` generator
        """

    def get_resource_url(resource, href, **kwargs):
        """Return the canonical URL for displaying the given resource.

        :param resource: a `Resource`
        :param href: an `Href` used for creating the URL

        Note that if there's no special rule associated to this realm for
        creating URLs (i.e. the standard convention of using realm/id applies),
        then it's OK to not define this method.
        """

    def get_resource_description(resource, format='default', context=None,
                                 **kwargs):
        """Return a string representation of the resource, according to the
        `format`.

        :param resource: the `Resource` to describe
        :param format: the kind of description wanted. Typical formats are:
                       `'default'`, `'compact'` or `'summary'`.
        :param context: an optional rendering context to allow rendering rich
                        output (like markup containing links)
        :type context: `Context`

        Additional keyword arguments can be given as extra information for
        some formats. 

        For example, the ticket with the id 123 is represented as:
         - `'#123'` in `'compact'` format,
         - `'Ticket #123'` for the `default` format.
         - `'Ticket #123 (closed defect): This is the summary'` for the
           `'summary'` format

        Note that it is also OK to not define this method if there's no
        special way to represent the resource, in which case the standard
        representations 'realm:id' (in compact mode) or 'Realm id' (in
        default mode) will be used.
        """

    def resource_exists(resource):
        """Check whether the given `resource` exists physically.

        :rtype: bool

        Attempting to retrieve the model object for a non-existing
        resource should raise a `ResourceNotFound` exception.
        (''since 0.11.8'')
        """


class Resource(object):
    """Resource identifier.

    This specifies as precisely as possible *which* resource from a Trac
    environment is manipulated.

    A resource is identified by:
    (- a `project` identifier) 0.12?
     - a `realm` (a string like `'wiki'` or `'ticket'`)
     - an `id`, which uniquely identifies a resource within its realm.
       If the `id` information is not set, then the resource represents
       the realm as a whole.
     - an optional `version` information.
       If `version` is `None`, this refers by convention to the latest
       version of the resource.

    Some generic and commonly used rendering methods are associated as well
    to the Resource object. Those properties and methods actually delegate
    the real work to the Resource's manager.
    """

    __slots__ = ('realm', 'id', 'version', 'parent')

    def __repr__(self):
        path = []
        r = self
        while r:
            name = r.realm
            if r.id:
                name += ':' + unicode(r.id) # id can be numerical
            if r.version is not None:
                name += '@' + unicode(r.version)
            path.append(name or '')
            r = r.parent
        return '<Resource %r>' % (', '.join(reversed(path)))

    def __eq__(self, other):
        return self.realm == other.realm and \
               self.id == other.id and \
               self.version == other.version and \
               self.parent == other.parent

    def __hash__(self):
        """Hash this resource descriptor, including its hierarchy."""
        path = ()
        current = self
        while current:
            path += (self.realm, self.id, self.version)
            current = current.parent
        return hash(path)

    # -- methods for creating other Resource identifiers

    def __new__(cls, resource_or_realm=None, id=False, version=False,
                parent=False):
        """Create a new Resource object from a specification.

        :param resource_or_realm: this can be either:
           - a `Resource`, which is then used as a base for making a copy
           - a `basestring`, used to specify a `realm`
        :param id: the resource identifier
        :param version: the version or `None` for indicating the latest version

        >>> main = Resource('wiki', 'WikiStart')
        >>> repr(main)
        "<Resource u'wiki:WikiStart'>"
        
        >>> Resource(main) is main
        True

        >>> main3 = Resource(main, version=3)
        >>> repr(main3)
        "<Resource u'wiki:WikiStart@3'>"

        >>> main0 = main3(version=0)
        >>> repr(main0)
        "<Resource u'wiki:WikiStart@0'>"

        In a copy, if `id` is overriden, then the original `version` value
        will not be reused.

        >>> repr(Resource(main3, id="WikiEnd"))
        "<Resource u'wiki:WikiEnd'>"

        >>> repr(Resource(None))
        "<Resource ''>"
        """
        realm = resource_or_realm
        if isinstance(resource_or_realm, Resource):
            if id is False and version is False and parent is False:
                return resource_or_realm
            else: # copy and override
                realm = resource_or_realm.realm
            if id is False:
                id = resource_or_realm.id
            if version is False:
                if id == resource_or_realm.id:
                    version = resource_or_realm.version # could be 0...
                else:
                    version = None
            if parent is False:
                parent = resource_or_realm.parent
        else:
            if id is False:
                id = None
            if version is False:
                version = None
            if parent is False:
                parent = None
        resource = super(Resource, cls).__new__(cls)
        resource.realm = realm
        resource.id = id
        resource.version = version
        resource.parent = parent
        return resource

    def __call__(self, realm=False, id=False, version=False, parent=False):
        """Create a new Resource using the current resource as a template.

        Optional keyword arguments can be given to override `id` and
        `version`.
        """
        return Resource(realm is False and self or realm, id, version, parent)

    # -- methods for retrieving children Resource identifiers
    
    def child(self, realm, id=False, version=False):
        """Retrieve a child resource for a secondary `realm`.

        Same as `__call__`, except that this one sets the parent to `self`.

        >>> repr(Resource(None).child('attachment', 'file.txt'))
        "<Resource u', attachment:file.txt'>"
        """
        return Resource(realm, id, version, self)


class ResourceSystem(Component):
    """Resource identification and description manager.

    This component makes the link between `Resource` identifiers and their
    corresponding manager `Component`.
    """

    resource_managers = ExtensionPoint(IResourceManager)

    def __init__(self):
        self._resource_managers_map = None

    # Public methods

    def get_resource_manager(self, realm):
        """Return the component responsible for resources in the given `realm`

        :param realm: the realm name
        :return: a `Component` implementing `IResourceManager` or `None`
        """
        # build a dict of realm keys to IResourceManager implementations
        if not self._resource_managers_map:
            map = {}
            for manager in self.resource_managers:
                for manager_realm in manager.get_resource_realms() or []:
                    map[manager_realm] = manager
            self._resource_managers_map = map
        return self._resource_managers_map.get(realm)

    def get_known_realms(self):
        """Return a list of all the realm names of resource managers."""
        realms = []
        for manager in self.resource_managers:
            for realm in manager.get_resource_realms() or []:
                realms.append(realm)
        return realms


# -- Utilities for manipulating resources in a generic way

def get_resource_url(env, resource, href, **kwargs):
    """Retrieve the canonical URL for the given resource.

    This function delegates the work to the resource manager for that
    resource if it implements a `get_resource_url` method, otherwise
    reverts to simple '/realm/identifier' style URLs.
    
    :param env: the `Environment` where `IResourceManager` components live
    :param resource: the `Resource` object specifying the Trac resource
    :param href: an `Href` object used for building the URL

    Additional keyword arguments are translated as query paramaters in the URL.

    >>> from trac.test import EnvironmentStub
    >>> from trac.web.href import Href
    >>> env = EnvironmentStub()
    >>> href = Href('/trac.cgi')
    >>> main = Resource('generic', 'Main')
    >>> get_resource_url(env, main, href)
    '/trac.cgi/generic/Main'
    
    >>> get_resource_url(env, main(version=3), href)
    '/trac.cgi/generic/Main?version=3'
    
    >>> get_resource_url(env, main(version=3), href)
    '/trac.cgi/generic/Main?version=3'
    
    >>> get_resource_url(env, main(version=3), href, action='diff')
    '/trac.cgi/generic/Main?action=diff&version=3'
    
    >>> get_resource_url(env, main(version=3), href, action='diff', version=5)
    '/trac.cgi/generic/Main?action=diff&version=5'
    
    """
    manager = ResourceSystem(env).get_resource_manager(resource.realm)
    if manager and hasattr(manager, 'get_resource_url'):
        return manager.get_resource_url(resource, href, **kwargs)
    args = {'version': resource.version}
    args.update(kwargs)
    return href(resource.realm, resource.id, **args)

def get_resource_description(env, resource, format='default', **kwargs):
    """Retrieve a standardized description for the given resource.

    This function delegates the work to the resource manager for that
    resource if it implements a `get_resource_description` method,
    otherwise reverts to simple presentation of the realm and identifier
    information.
    
    :param env: the `Environment` where `IResourceManager` components live
    :param resource: the `Resource` object specifying the Trac resource
    :param format: which formats to use for the description

    Additional keyword arguments can be provided and will be propagated
    to resource manager that might make use of them (typically, a `context`
    parameter for creating context dependent output).

    >>> from trac.test import EnvironmentStub
    >>> env = EnvironmentStub()
    >>> main = Resource('generic', 'Main')
    >>> get_resource_description(env, main)
    u'generic:Main'
    
    >>> get_resource_description(env, main(version=3))
    u'generic:Main'

    >>> get_resource_description(env, main(version=3), format='summary')
    u'generic:Main at version 3'
    
    """
    manager = ResourceSystem(env).get_resource_manager(resource.realm)
    if manager and hasattr(manager, 'get_resource_description'):
        return manager.get_resource_description(resource, format, **kwargs)
    name = u'%s:%s' % (resource.realm, resource.id)
    if format == 'summary':
        name = _('%(name)s at version %(version)s',
                 name=name, version=resource.version)
    return name

def get_resource_name(env, resource):
    return get_resource_description(env, resource)

def get_resource_shortname(env, resource):
    return get_resource_description(env, resource, 'compact')

def get_resource_summary(env, resource):
    return get_resource_description(env, resource, 'summary')

def get_relative_resource(resource, path=''):
    """Build a Resource relative to a reference resource.
    
    :param path: path leading to another resource within the same realm.
    """
    if path in (None, '', '.'):
        return resource
    else:
        base = unicode(path[0] != '/' and resource.id or '').split('/')
        for comp in path.split('/'):
            if comp == '..':
                if base:
                    base.pop()
            elif comp and comp != '.':
                base.append(comp)
        return resource(id=base and '/'.join(base) or None)

def get_relative_url(env, resource, href, path='', **kwargs):
    """Build an URL relative to a resource given as reference.

    :param path: path leading to another resource within the same realm.

    >>> from trac.test import EnvironmentStub
    >>> env = EnvironmentStub()
    >>> from trac.web.href import Href
    >>> href = Href('/trac.cgi')
    >>> main = Resource('wiki', 'Main', version=3)

    Without parameters, return the canonical URL for the resource, like
    `get_resource_url` does.

    >>> get_relative_url(env, main, href)
    '/trac.cgi/wiki/Main?version=3'

    Paths are relative to the given resource:

    >>> get_relative_url(env, main, href, '.')
    '/trac.cgi/wiki/Main?version=3'

    >>> get_relative_url(env, main, href, './Sub')
    '/trac.cgi/wiki/Main/Sub'

    >>> get_relative_url(env, main, href, './Sub/Infra')
    '/trac.cgi/wiki/Main/Sub/Infra'

    >>> get_relative_url(env, main, href, './Sub/')
    '/trac.cgi/wiki/Main/Sub'

    >>> mainsub = main(id='Main/Sub')
    >>> get_relative_url(env, mainsub, href, '..')
    '/trac.cgi/wiki/Main'

    >>> get_relative_url(env, main, href, '../Other')
    '/trac.cgi/wiki/Other'

    References always stay within the current resource realm:

    >>> get_relative_url(env, mainsub, href, '../..')
    '/trac.cgi/wiki'

    >>> get_relative_url(env, mainsub, href, '../../..')
    '/trac.cgi/wiki'

    >>> get_relative_url(env, mainsub, href, '/toplevel')
    '/trac.cgi/wiki/toplevel'

    Extra keyword arguments are forwarded as query parameters:

    >>> get_relative_url(env, main, href, action='diff')
    '/trac.cgi/wiki/Main?action=diff&version=3'

    """
    return get_resource_url(env, get_relative_resource(resource, path),
                            href, **kwargs)

def render_resource_link(env, context, resource, format='default'):
    """Utility for generating a link `Element` to the given resource.

    Some component manager may directly use an extra `context` parameter
    in order to directly generate rich content. Otherwise, the textual output
    is wrapped in a link to the resource.
    """
    from genshi.builder import Element, tag
    link = get_resource_description(env, resource, format, context=context)
    if not isinstance(link, Element):
        link = tag.a(link, href=get_resource_url(env, resource, context.href))
    return link

def resource_exists(env, resource):
    """Checks for resource existence without actually instantiating a model.

        :return: `True` if the resource exists, `False` if it doesn't
        and `None` in case no conclusion could be made (i.e. when
        `IResourceManager.resource_exists` is not implemented).

        >>> from trac.test import EnvironmentStub
        >>> env = EnvironmentStub()

        >>> resource_exists(env, Resource('dummy-realm', 'dummy-id')) is None
        True
        >>> resource_exists(env, Resource('dummy-realm'))
        False
    """
    manager = ResourceSystem(env).get_resource_manager(resource.realm)
    if manager and hasattr(manager, 'resource_exists'):
        return manager.resource_exists(resource)
    elif resource.id is None:
        return False
