:mod:`trac.util.presentation` -- Utilities for dynamic content generation
=========================================================================

.. module :: trac.util.presentation

.. autofunction :: jinja2_update

We define a few Jinja2 custom filters_.

.. autofunction :: flatten_filter
.. autofunction :: groupattr_filter
.. autofunction :: htmlattr_filter
.. autofunction :: max_filter
.. autofunction :: min_filter
.. autofunction :: trim_filter

We also define a few Jinja2 custom tests_.

.. autofunction :: is_greaterthan
.. autofunction :: is_greaterthanorequal
.. autofunction :: is_lessthan
.. autofunction :: is_lessthanorequal
.. autofunction :: is_not_equalto
.. autofunction :: is_not_in
.. autofunction :: istext

The following utilities are all available within Jinja2 templates.

.. autofunction :: captioned_button
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


.. _filters: http://jinja.pocoo.org/docs/dev/api/#custom-filters
.. _tests: http://jinja.pocoo.org/docs/dev/api/#custom-tests
