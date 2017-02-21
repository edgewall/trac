:mod:`trac.util.html` -- HTML transformations
=============================================
.. module :: trac.util.html

Building HTML programmatically
------------------------------

With the introduction of the Genshi_ template engine in Trac 0.11,
most of the (X)HTML content is produced directly using Genshi
facilities, like the builder_ or snippet templates.  The old `html`
tag building facility is now not much more than an alias to the `tag`
ElementFactory_, and most of the code uses directly the latter.

.. data :: html

   A `TransposingElementFactory` using `str.lower` transformation.

.. autoclass :: TransposingElementFactory

.. _Genshi: http://genshi.edgewall.org
.. _builder: http://genshi.edgewall.org/wiki/ApiDocs/genshi.builder
.. _ElementFactory:
   http://genshi.edgewall.org/wiki/ApiDocs/genshi.builder#genshi.builder:ElementFactory


HTML clean-up and sanitization
------------------------------

.. autoclass :: TracHTMLSanitizer
   :members:

.. autoclass :: Deuglifier

.. autofunction :: escape
.. autofunction :: unescape

.. autoclass :: FormTokenInjector


Misc. HTML processing
---------------------

.. autofunction :: expand_markup
.. autofunction :: find_element
.. autofunction :: plaintext
.. autofunction :: to_fragment
