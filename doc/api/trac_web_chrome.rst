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

.. autofunction :: web_context
.. autofunction :: add_meta


Web resources
~~~~~~~~~~~~~

.. autofunction :: add_stylesheet
.. autofunction :: add_javascript
.. autofunction :: add_script
.. autofunction :: add_script_data


Page admonitions
~~~~~~~~~~~~~~~~

.. autofunction :: add_warning
.. autofunction :: add_notice


Contextual Navigation
~~~~~~~~~~~~~~~~~~~~~

.. autofunction :: add_link
.. autofunction :: add_ctxtnav
.. autofunction :: prevnext_nav


Miscellaneous
~~~~~~~~~~~~~

.. autofunction :: auth_link


Internals
~~~~~~~~~

.. autofunction :: chrome_info_script
.. autofunction :: chrome_resource_path
