:mod:`trac.core` -- the Trac "kernel"
=====================================

Component model
---------------

.. module :: trac.core

The Trac component model is very simple, it is based on `Interface`
classes that are used to document a particular set of methods and
properties that must be defined by a `Component` subclass when it
declares it *implements* that interface.

.. autoclass :: trac.core.Interface
   :members:

.. autoclass :: trac.core.Component
   :members:

The static method `Component.implements` is never used as such, but
rather via the global `implements` function. This globally registers
that particular component subclass as an implementation of the listed
interfaces.

.. autofunction :: trac.core.implements

For example::

  class IStuffProvider(Interface):
      """All interfaces start by convention with an "I" and even if it's
      not a convention, in practice most interfaces are "Provider" of
      something ;-)
      """

      def get_stuff(color=None):
          """We usually don't specify "self" here, but try to describe
	  as precisely as possible how the method might be called and
	  what is the expected return type."""

  class ComponentA(Component):

      implements(IStuffProvider)

      # IStuffProvider methods

      def get_stuff(self, color=None):
          if not color or color == 'yellow':
	      yield ('duck', "the regular waterproof plastic duck")

The benefit of implementing an interface is to possibility to define
an `ExtensionPoint` property for an `Interface`, in a `Component`
subclass. Such a property provides a convenient way to retrieve *all*
registered component instances for that interface.

.. autoclass :: trac.core.ExtensionPoint
   :members:

Continuing the example::

  class StuffModule(Component):

      stuff_providers = ExtensionPoint(IStuffProvider)

      def get_all_stuff(self, color=None):
          stuff = {}
          for provider in self.stuff_provider:
	      for name, descr in provider.get_stuff(color) or []:
	          stuff[name] = descr
	  return stuff

Note that besides going through an extension point, `Component`
subclass instances can alternatively be retrieved directly by using
the instantiation syntax.  This is not an usual instantiation though,
as this will always return the same instance in the given
`ComponentManager` "scope" passed to the constructor::

  >>> a1 = ComponentA(mgr)
  >>> a2 = ComponentA(mgr)
  >>> a1 is a2
  True

The same thing happens when retrieving components via an extension
point, the retrieved instances belong to the same "scope" as the
instance used to access the extension point::

  >>> b = StuffModule(mgr)
  >>> any(a is a1 for a in b.stuff_providers)
  True

.. autoclass :: trac.core.ComponentManager
   :members:

In practice, there's only one kind of `ComponentManager` in the Trac
application itself, the `trac.env.Environment`.


Miscellaneous
-------------

.. autoclass :: trac.core.TracError
   :members:
