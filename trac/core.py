# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003-2005 Edgewall Software
# Copyright (C) 2003-2004 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
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

    def __get__(self, instance, owner):
        """Return a list of components that declare to implement the extension
        point interface."""
        if instance:
            extensions = ComponentMeta._registry.get(self.interface, [])
            return filter(None, [instance.compmgr[cls] for cls in extensions])
        return self

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

        new_class = type.__new__(cls, name, bases, d)
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

        if d.get('abstract'):
            # Don't put abstract component classes in the registry
            return new_class

        ComponentMeta._components.append(new_class)
        for interface in d.get('_implements', []):
            ComponentMeta._registry.setdefault(interface, []).append(new_class)
        for base in [base for base in bases if hasattr(base, '_implements')]:
            for interface in base._implements:
                ComponentMeta._registry.setdefault(interface, []).append(new_class)

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
