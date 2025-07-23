:mod:`trac.wiki.macros` -- The standard set of Wiki macros
==========================================================

.. module :: trac.wiki.macros

The standard set of components corresponding to Wiki macros are not
meant to be used directly from the API. You may study their
implementation though, for getting inspiration. In particular, you'll
see they all subclass the `WikiMacroBase` class, which provides a
convenient way to implement a new `~trac.wiki.api.IWikiMacroProvider`
interface.

.. autoclass :: WikiMacroBase
   :members:

See also :teo:`wiki/WikiMacros#DevelopingCustomMacros`.
