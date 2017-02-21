:mod:`trac.util.html` -- HTML transformations
=============================================

.. module :: trac.util.html

Building HTML programmatically
------------------------------

With the introduction of the Jinja2_ template engine in Trac 1.3.x,
the (X)HTML content is produced either using Jinja2 snippet templates
(see `jinja2template`) or using the builder API defined in this
module.  This builder API closely matches the Genshi_ `genshi.builder`
API on the surface.

The builder API
...............

The `tag` builder has some knowledge about generating HTML content,
like knowing which elements are "void" elements, how attributes should
be written when given a boolean value, etc.

.. data :: tag

   An `ElementFactory`.

.. autoclass :: ElementFactory
.. autoclass :: Element
.. autoclass :: Fragment

Note that the `Element` relies on the following lower-level API for
generating the HTML attributes.

.. autofunction :: html_attribute
.. autofunction :: classes
.. autofunction :: styles

This HTML-specific behavior can be a hindrance to writing generic XML.
In that case, better use the `xml` builder.

.. data :: xml

   An `XMLElementFactory`.

.. autoclass :: XMLElementFactory
.. autoclass :: XMLElement

.. _Jinja2: http://jinja.pocoo.org/docs/dev/intro/
.. _Genshi: http://genshi.edgewall.org/wiki/ApiDocs/genshi.builder

Building HTML from strings
..........................

It is also possible to mark an arbitrary string as containing HTML
content, so that it will not be HTML-escaped by the template engine.

For this, use the `Markup` class, taken from the `markupsafe` package
(itself a dependency of the Jinja2_ package).

The `Markup` class should be imported from the present module:

.. sourcecode:: python

   from trac.util.html import Markup


HTML clean-up and sanitization
------------------------------

.. autoclass :: TracHTMLSanitizer
   :members:

.. autoclass :: Deuglifier

.. autofunction :: escape
.. autofunction :: unescape

.. autofunction :: stripentities
.. autofunction :: striptags
.. autofunction :: plaintext

.. autoclass :: FormTokenInjector
.. autoclass :: HTMLTransform
.. autoclass :: HTMLSanitization


Misc. HTML processing
---------------------

.. autofunction :: find_element
.. autofunction :: to_fragment
.. autofunction :: valid_html_bytes
.. autofunction :: to_fragment

Kept for backward compatibility purposes:

.. autofunction :: expand_markup
