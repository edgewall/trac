:mod:`trac.wiki.api` -- The Wiki API
====================================

.. module :: trac.wiki.api


Interfaces
----------

The wiki module presents several possibilities of extension, for
interacting with the Wiki application and also for extending the Wiki
syntax.

First, components can be notified of the changes happening in the
wiki.

.. autoclass :: trac.wiki.api.IWikiChangeListener
   :members:

Components can also interfere with the changes, before or after
they're made.

.. autoclass :: trac.wiki.api.IWikiPageManipulator
   :members:

Then, the Wiki syntax itself can be extended. The first and less
intrusive way is to provide new Wiki macros or Wiki processors. Those
are basically the same thing, as they're implemented using the
following interface. The difference comes from the invocation
syntax used in the Wiki markup, which manifests itself in the `args`
parameter of :meth:`IWikiMacroProvider.expand_macro`.

.. autoclass :: trac.wiki.api.IWikiMacroProvider
   :members:

The Wiki syntax can also be extended by introducing new markup.

.. autoclass :: trac.wiki.api.IWikiSyntaxProvider
   :members:

The Wiki System
---------------

The wiky system provide an access to all the pages.

.. autoclass :: trac.wiki.api.WikiSystem
   :members:
   :exclude-members: get_resource_description, resource_exists



Other Functions
---------------

.. autofunction :: trac.wiki.api.parse_args

