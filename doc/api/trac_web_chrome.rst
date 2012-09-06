:mod:`trac.web.chrome` -- Trac content generation for the Web
=============================================================

.. automodule :: trac.web.chrome


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

.. autoclass :: trac.web.chrome.Chrome
   :members:


Functions
---------

Most of the helper functions are related to content generation,
and in particular, (X)HTML content generation, in one way or another.

.. autofunction :: trac.web.chrome.web_context
.. autofunction :: trac.web.chrome.add_meta


Web resources
~~~~~~~~~~~~~

.. autofunction :: trac.web.chrome.add_stylesheet
.. autofunction :: trac.web.chrome.add_javascript
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
