:mod:`trac.web.chrome` -- Trac content generation for the Web
=============================================================

.. module :: trac.web.chrome


Interfaces
----------

.. autoclass :: trac.web.chrome.INavigationContributor
   :members:

   See also :extensionpoints:`trac.web.chrome.INavigationContributor`

.. autoclass :: trac.web.chrome.ITemplateProvider
   :members:

   See also :extensionpoints:`trac.web.chrome.ITemplateProvider`


Components
----------

The `Chrome` component is in charge of generating the content of the
pages, with the help of template engines. The default engine for Trac
1.4 is Jinja2_, though we'll still support Genshi_ until the next
development cycle begins (Trac 1.5.1).

The high-level API for generating content is the
`~Chrome.render_template` method, which is paired with the output of
the `~trac.web.api.IRequestHandler.process_request` method. As such,
it accepts simple but versatile parameters, and generates output which
can be directly sent to the web front-end.

There's an intermediate level API for generating *fragment* of
content, either HTML or text. A fragment is typically an element of a
web page, or the result for an XHR, or simply not a HTML at all but
just some text. When the output of the fragment will be sent to the
web front-end (typically when responding to XHR), use
`~Chrome.generate_fragment`. Otherwise, when the output should be
manipulated programmatically as a string (typically integrated in a
`~trac.util.html.Fragment`), use `~Chrome.render_fragment`.

The low-level API for generating content with the Jinja2 template
engine comprises `~Chrome.prepare_template`, which creates a
``jinja2.Template``. More precisely, it combines
`~Chrome.load_template` and `~Chrome.populate_data`. Such a
``jinja2.Template`` can then be passed to either
`~Chrome.generate_template_stream` or
`~Chrome.render_template_string`, depending on the desired kind of
output.

For even lower-level access to the template engine, see the section
:ref:`text_util_jinja2` related to Jinja2.

.. autoclass :: trac.web.chrome.Chrome
   :members:

.. _jinja2: http://jinja.pocoo.org/
.. _genshi: http://genshi.edgewall.org/


Functions
---------

Most of the helper functions are related to content generation,
and in particular, (X)HTML content generation, in one way or another.

.. autofunction :: trac.web.chrome.web_context
.. autofunction :: trac.web.chrome.add_meta


Web resources
~~~~~~~~~~~~~

.. autofunction :: trac.web.chrome.add_stylesheet
.. autofunction :: trac.web.chrome.add_script
.. autofunction :: trac.web.chrome.add_script_data


Page admonitions
~~~~~~~~~~~~~~~~

.. autofunction :: trac.web.chrome.add_warning
.. autofunction :: trac.web.chrome.add_notice


Contextual Navigation
~~~~~~~~~~~~~~~~~~~~~

.. autofunction :: trac.web.chrome.add_link
.. autofunction :: trac.web.chrome.add_ctxtnav
.. autofunction :: trac.web.chrome.prevnext_nav


Miscellaneous
~~~~~~~~~~~~~

.. autofunction :: auth_link
