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
    """Dummy base class for interfaces.
    
    (Might use PyProtocols in the future.)
    """

class ExtensionPoint(object):
    """Marker class for extension points in components."""

    def __init__(self, interface):
        """Create the extension point.
        
        @param interface: the `Interface` class that defines the protocol for
                          the extension point
        """
        self.interface = interface

    def __repr__(self):
        """Return a textual representation of the extension point."""
        return '<ExtensionPoint %s>' % self.interface.__name__


class ComponentMeta(type):
    """Meta class for components.
    
    Takes care of component and extension point registration.
    """
    _components = []
    _registry = {}

    def __new__(cls, name, bases, d):
        """Create the component class."""
        xtnpts = {}
        for base in [base for base in bases
                     if hasattr(base, '_extension_points')]:
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

        # Only override __init__ for Components not inheriting ComponentManager
        if True not in [issubclass(x, ComponentManager) for x in bases]:
            # Allow components to have a no-argument initializer so that
            # they don't need to worry about accepting the component manager
            # as argument and invoking the super-class initializer
            init = d.get('__init__')
            if not init:
                # Because we're replacing the initializer, we need to make sure
                # that any inherited initializers are also called.
                for init in [b.__init__._original for b in new_class.mro()
                             if issubclass(b, Component)
                             and b.__dict__.has_key('__init__')]:
                    break
            def maybe_init(self, compmgr, init=init, cls=new_class):
                if not cls in compmgr.components:
                    compmgr.components[cls] = self
                    if init:
                        init(self)
            maybe_init._original = init
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
    """Base class for components.
    
    Every component can declare what extension points it provides, as well as
    what extension points of other components it extends.
    """
    __metaclass__ = ComponentMeta

    def __new__(cls, *args, **kwargs):
        """Return an existing instance of the component if it has already been
        activated, otherwise create a new instance.
        """
        # If this component is also the component manager, just invoke that
        if issubclass(cls, ComponentManager):
            self = super(Component, cls).__new__(cls)
            self.compmgr = self
            return self

        # The normal case where the component is not also the component manager
        compmgr = args[0]
        if not cls in compmgr.components:
            self = super(Component, cls).__new__(cls)
            self.compmgr = compmgr
            compmgr.component_activated(self)
            return self
        return compmgr[cls]

    def __getattr__(self, name):
        """If requesting an extension point member, return a list of components
        that declare to implement the extension point interface."""
        xtnpt = self._extension_points.get(name)
        if xtnpt:
            extensions = ComponentMeta._registry.get(xtnpt.interface, [])
            return [self.compmgr[cls] for cls in extensions
                    if self.compmgr[cls]]
        raise AttributeError, name


class ComponentManager(object):
    """The component manager keeps a pool of active components."""

    def __init__(self):
        """Initialize the component manager."""
        self.components = {}
        if isinstance(self, Component):
            self.components[self.__class__] = self

    def __contains__(self, cls):
        """Return wether the given class is in the list of active components."""
        return cls in self.components

    def __getitem__(self, cls):
        """Activate the component instance for the given class, or return the
        existing the instance if the component has already been activated."""
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
        """Can be overridden by sub-classes so that special initialization for
        components can be provided.
        """

    def is_component_enabled(self, cls):
        """Can be overridden by sub-classes to veto the activation of a
        component.

        If this method returns False, the component with the given class will
        not be available.
        """
        return True
