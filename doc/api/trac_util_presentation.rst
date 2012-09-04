:mod:`trac.util.presentation` -- Utilities for dynamic content generation
=========================================================================

.. module :: trac.util.presentation

The following utilities are all available within Genshi templates.

.. autofunction :: captioned_button
.. autofunction :: classes
.. autofunction :: first_last
.. autofunction :: group
.. autofunction :: istext
.. autofunction :: paginate
.. autofunction :: separated
.. autofunction :: to_json

Modules generating paginated output will be happy to use a rich
pagination controller. See *Query*, *Report* and *Search* modules for
example usage.

.. autoclass :: Paginator
