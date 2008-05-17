.. index:: CGI
.. highlight:: apache
.. _install-cgi:

===========
Trac on CGI
===========

.. warning::
    The way CGI works requires that the entire Trac application be reloaded on
    every request. This ends up being very slow. **Use CGI only as a last 
    resort.**

To generate the :file:`trac.cgi` script run:

.. code-block:: bash

    trac-admin /path/to/env deploy /path/to/www/trac

It will be in the :file:`cgi-bin` folder inside the path given.

.. index::
    pair: CGI; Apache
.. _install-cgi-apache:

Apache
======

Add an alias for the path you want to run Trac at to your VirtualHost::

    ScriptAlias /trac /path/to/www/trac/cgi-bin/trac.cgi

For a multiple environment configuration you can use::

    ScriptAlias /trac /path/to/www/trac/cgi-bin/trac.cgi
    <Location /trac>
        SetEnv TRAC_ENV_PARENT_DIR /path/to/base
    </Location>

See :ref:`install-apacheauth` to setup authentication.