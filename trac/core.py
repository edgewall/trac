# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004, 2005 Edgewall Software
# Copyright (C) 2003, 2004 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004, 2005 Christopher Lenz <cmlenz@gmx.de>
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

from trac.util import TracError

__all__ = ['Component', 'ExtensionPoint', 'implements', 'Interface',
           'TracError']


class Interface(object):
    """
    Dummy base class for interfaces. Might use PyProtocols in the future.
    """
    __slots__ = []


class ExtensionPoint(object):
    """
    Marker class for extension points in components. Could be extended
    to hold the protocol/interface required.
    """

    __slots__ = ['interface']

    def __init__(self, interface):
        self.interface = interface

    def __str__(self):
        return '<ExtensionPoint %s>' % self.interface.__name__


class ComponentMeta(type):
    """
    Meta class for components. Takes care of component and extension point
    registration.
    """

    _components = []
    _registry = {}

    def __new__(cls, name, bases, d):
        xtnpts = {}
        for base in [b for b in bases
                     if hasattr(b, '_extension_points')]:
            xtnpts.update(base._extension_points)
        for key, value in d.items():
            if isinstance(value, ExtensionPoint):
                xtnpts[key] = value
                del d[key]

        new_class = type.__new__(cls, name, bases, d)
        new_class._extension_points = xtnpts

        if name == 'Component':
            # Don't put the Component base class in the registry
            return new_class

        # Allow components to have a no-argument initializer so that
        # they don't need to worry about accepting the component manager
        # as argument and invoking the super-class initializer
        def maybe_init(self, compmgr, init=d.get('__init__'), cls=new_class):
            if not cls in compmgr.components:
                compmgr.components[cls] = self
                if init:
                    init(self)
        setattr(new_class, '__init__', maybe_init)

        ComponentMeta._components.append(new_class)
        for interface in d.get('_implements', []):
            if not interface in ComponentMeta._registry:
                ComponentMeta._registry[interface] = []
            ComponentMeta._registry[interface].append(new_class)

        return new_class


def implements(*interfaces):
    """
    Can be used in the class definiton of `Component` subclasses to declare
    the extension points that are extended.
    """
    import sys

    frame = sys._getframe(1)
    locals = frame.f_locals

    # Some sanity checks
    assert locals is not frame.f_globals and '__module__' in frame.f_locals, \
           'implements() can only be used in a class definition'
    assert not '_implements' in locals, \
           'implements() can only be used once in a class definition'

    locals['_implements'] = interfaces


class Component(object):
    """
    Base class for components. Every component can declare what extension points
    it provides, as well as what extension points of other components it
    extends.
    """
    __metaclass__ = ComponentMeta
    __slots__ = ['compmgr']

    def __new__(cls, compmgr):
        if not cls in compmgr.components:
            self = object.__new__(cls)
            self.compmgr = compmgr
            compmgr.component_activated(self)
            return self
        return compmgr[cls]

    def __getattr__(self, name):
        xtnpt = self._extension_points.get(name)
        if xtnpt:
            extensions = ComponentMeta._registry.get(xtnpt.interface, [])
            return filter(None, [self.compmgr[cls] for cls in extensions])
        raise AttributeError, name


class ComponentManager(object):
    """
    The component manager keeps a pool of active components.
    """
    __slots__ = ['components']

    def __init__(self):
        self.components = {}

    def __contains__(self, cls):
        return cls in self.components

    def __getitem__(self, cls):
        component = self.components.get(cls)
        if not component:
            if not self.is_component_enabled(cls):
                return None
            if cls not in ComponentMeta._components:
                raise TracError, 'Component "%s" not registered' % cls.__name__
            try:
                component = cls(self)
            except TypeError, e:
                raise TracError, 'Unable to instantiate component "%s" (%s)' \
                                 % (cls.__name__, e)
        return component

    def component_activated(self, component):
        """
        Can be overridden by sub-classes so that special initialization for
        components can be provided.
        """

    def is_component_enabled(self, cls):
        """
        Can be overridden by sub-classes to veto the activation of a component.
        If this method returns False, the component with the given class will
        not be available.
        """
        return True
