.. index:: mod_python, Apache; mod_python
.. highlight:: apache
.. _install-mod_python:

==================
Trac on mod_python
==================

Apache
======

First create a handler for Trac::

    <Location /trac>
      SetHandler mod_python
      PythonHandler trac.web.modpython_frontend
      PythonInterpreter main
      PythonOption TracEnv /path/to/env
      PythonOption TracUriRoot /trac
      SetEnv PYTHON_EGG_CACHE /tmp
    </Location>

``PythonInterpreter`` needs to be set to the same string in all VirtualHosts
using Trac, though the actual value is unimportant. ``PythonOption
TracUriRoot`` needs to be set to the same path as in the Location.

For a multiple environment configuration you can use ``PythonOption
TracEnvParentDir``.

See :ref:`install-apacheauth` to setup authentication.


.. index:: mod_python; PythonPath
.. _install-mod_python-pythonpath:

Changing the Python path
------------------------

If Trac, or other modules, are not installed in the standard path, you can use
the ``PythonPath`` option to add additional folders::

    PythonPath "['/new/path'] + sys.path"

.. seealso::
    
    :ref:`Subversion bindings from source <install-subversion-bindings>`
        Add :file:`/usr/lib/svn-python`.
    `viritualenv <http://pypi.python.org/pypi/virtualenv#id17>`_
        Add :file:`/path/to/virtualenv/lib/python2.X/site-packages`.


Example
-------

A full example of a mod_python and mod_dav_svn configuration::

    <VirtualHost *:80>
        ServerName example.com
        ServerAlias www.example.com
        ServerAdmin webmaster@example.com
        
        # Note: This folder should exist, but will generally be empty
        DocumentRoot /srv/example.com/htdocs
        <Directory /srv/example.com/htdocs>
            Order allow,deny
            Allow from all
        </Directory>
        
        # Host the main Trac instance at /
        <Location />
            SetHandler mod_python
            PythonHandler trac.web.modpython_frontend
            PythonInterpreter main
            PythonOption TracEnv /srv/example.com/tracs/main
            PythonOption TracUriRoot /
            SetEnv PYTHON_EGG_CACHE /tmp
        </Location>
        
        # Host all others at /projects/$PROJECT
        <Location /projects>
            PythonOption TracEnv ""
            PythonOption TracEnvParentDir /srv/example.com/tracs
        </Location>
        
        # Handle logins on both /login and /projects/$PROJECT/login
        <LocationMatch ^(/projects/[^/]+)?/login>
            AuthType Basic
            AuthName "example.com Login"
            AuthUserFile /srv/example.com/htpassd
            Require valid-user
        </LocationMatch>
        
        # Host subversion for all projects at /svn
        <Location /svn>
            DAV svn
            SVNParentPath /srv/example.com/repos
            SVNListParentPath on
            
            AuthType Basic
            AuthName "example.com Login"
            AuthUserFile /srv/example.com/htpassd
            # Allow anonymous checkout
            <LimitExcept GET PROPFIND OPTIONS REPORT>
                Require valid-user
            </LimitExcept>
        </Location>
    </VirtualHost>

Troubleshooting
---------------

In general, if you get server error pages, you can either check the Apache
error log, or enable the ``PythonDebug`` option::

    <Location /trac>
        ...
        PythonDebug on
    </Location>

Expat-related segmentation faults
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This problem will most certainly hit you on Unix when using Python 2.4. In
Python 2.4, some version of Expat (an XML parser library written in C) is
used, and if Apache is using another version, this results in segmentation
faults. As Trac 0.11 is using Genshi, which will indirectly use Expat, that
problem can now hit you even if everything was working fine before with Trac
0.10.

See Graham Dumpleton's detailed `explanation and workarounds`__ for the issue.

__ http://code.google.com/p/modwsgi/wiki/IssuesWithExpatLibrary

Form submission problems
^^^^^^^^^^^^^^^^^^^^^^^^

If you're experiencing problems submitting some of the forms in Trac (a common
problem is that you get redirected to the start page after submission), check
whether your ``DocumentRoot`` contains a folder or file with the same path
that you mapped the mod_python handler to. For some reason, mod_python gets
confused when it is mapped to a location that also matches a static resource.

Problem with virtual host configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If the <Location /> directive is used, setting the ``DocumentRoot`` may result
in a ''403 (Forbidden)'' error. Either remove the ``DocumentRoot`` directive, or
make sure that accessing the directory it points is allowed (in a
corresponding ``<Directory>`` block).

Using <Location /> together with ``SetHandler`` resulted in having everything
handled by mod_python, which leads to not being able download any CSS or
images/icons. I used <Location /trac> ``SetHandler None`` </Location> to
circumvent the problem, though I do not know if this is the most elegant
solution.

Using .htaccess
^^^^^^^^^^^^^^^

Although it may seem trivial to rewrite the above configuration as a directory
in your document root with a :file:`.htaccess` file, this does not work.
Apache will append a "/" to any Trac URLs, which interferes with its correct
operation.

It may be possible to work around this with mod_rewrite, but I failed to get
this working. In all, it is more hassle than it is worth. Stick to the
provided instructions. :)

Win32 Issues
^^^^^^^^^^^^

If you run trac with mod_python < 3.2 on Windows, uploading attachments will
not work. This problem is resolved in mod_python 3.1.4 or later, so please
upgrade mod_python to fix this.


OS X issues
^^^^^^^^^^^

When using mod_python on OS X you will not be able to restart Apache using
:command:`apachectl restart`. This is apparently fixed in mod_python 3.2, but
there's also a patch available for earlier versions here__.

__ http://www.dscpl.com.au/projects/vampire/patches.html

SELinux issues
^^^^^^^^^^^^^^

If Trac reports something like: ''Cannot get shared lock on db.lock''
The security context on the repository may need to be set:

.. code-block:: bash

    chcon -R -h -t httpd_sys_content_t PATH_TO_REPOSITORY

.. seealso::
    
    `Subversion FAQ <http://subversion.tigris.org/faq.html#reposperms>`_
        How do I set repository permissions correctly?

FreeBSD issues
^^^^^^^^^^^^^^

Pay attention to the version of the installed mod_python and sqlite packages.
Ports have both the new and old ones, but earlier versions of pysqlite and
mod_python won't integrate as the former requires threaded support in python,
and the latter requires a threadless install.

If you compiled and installed apache2, apache wouldn't support threads (cause
it doesn't work very well on FreeBSD). You could force thread support when
running ./configure for apache, using --enable-threads, but this isn't
recommended. The best option `seems to be`__ adding to
:file:`/usr/local/apache2/bin/ennvars`:

.. code-block:: bash

    export LD_PRELOAD=/usr/lib/libc_r.so

__ http://modpython.org/pipermail/mod_python/2006-September/021983.html

Subversion issues
^^^^^^^^^^^^^^^^^

.. This section needs to folded in to install/subversion

If you get the following Trac Error ``Unsupported version control system
"svn"`` only under mod_python, though it works well on the command-line and
even with TracStandalone, chances are that you forgot to add the path to the
Python bindings with the :ref:`PythonPath <install-mod_python-pythonpath>`
directive. (The better way is to add a link to the bindings in the Python
:file:`site-packages` directory, or create a :file:`.pth` file in that
directory.)

If this is not the case, it's possible that you're using Subversion libraries
that are binary incompatible with the apache ones (an incompatibility of the
``apr`` libraries is usually the cause). In that case, you also won't be able to
use the svn modules for Apache (``mod_dav_svn``).

Segmentation fault with php5-mhash or other php5 modules
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You may encounter segfaults (reported on debian etch) if php5-mhash module is
installed. Try to remove it to see if this solves the problem. See debian bug
report 411487__.

__ http://bugs.debian.org/cgi-bin/bugreport.cgi?bug=411487

Some people also have troubles when using php5 compiled with its own 3rd party
libraries instead of system libraries. Check here__.

__ http://www.djangoproject.com/documentation/modpython/#if-you-get-a-segmentation-fault

