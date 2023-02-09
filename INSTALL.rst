.. _tracinstallationguidefor1.5:

Trac Installation Guide for 1.5
===============================

Trac is written in the Python programming language and needs a database,
`SQLite <https://sqlite.org/>`__,
`PostgreSQL <https://www.postgresql.org/>`__, or
`MySQL <https://mysql.com/>`__. For HTML rendering, Trac uses the
`Jinja2 <http://jinja.pocoo.org>`__ templating system, though Genshi
templates are supported until Trac 1.5.1.

Trac can also be localized, and there is probably a translation
available in your language. If you want to use the Trac interface in
other languages, then make sure you have installed the optional package
`Babel <#otherpythonpackages>`__. Pay attention to the extra steps for
localization support in the `Installing Trac <#installingtrac>`__
section below. Lacking Babel, you will only get the default English
version.

If you're interested in contributing new translations for other
languages or enhancing the existing translations, please have a look at
`TracL10N <https://trac.edgewall.org/intertrac/wiki%3ATracL10N>`__.

These are generic instructions for installing and setting up Trac. While
you may find instructions for installing Trac on specific systems at
`TracInstallPlatforms <https://trac.edgewall.org/intertrac/TracInstallPlatforms>`__,
please **first read through these general instructions** to get a good
understanding of the tasks involved.

.. _dependencies:

Dependencies
------------

.. _mandatorydependencies:

Mandatory Dependencies
~~~~~~~~~~~~~~~~~~~~~~

To install Trac, the following software packages must be installed:

-  `Python <https://www.python.org/>`__, version >= 3.5
-  `setuptools <https://pypi.org/project/setuptools>`__, version > 5.6
-  `Jinja2 <https://pypi.org/project/Jinja2>`__, version >= 2.9.3

You also need a database system and the corresponding Python bindings.
The database can be either SQLite, PostgreSQL or MySQL.

.. _forsqlite:

For the SQLite database
^^^^^^^^^^^^^^^^^^^^^^^

You already have the SQLite database bindings bundled with the standard
distribution of Python (the ``sqlite3`` module).

Optionally, you may install a newer version of
`pysqlite <https://pypi.org/project/pysqlite>`__ than the one provided
by the Python distribution. See
`PySqlite <https://trac.edgewall.org/intertrac/PySqlite%23ThePysqlite2bindings>`__
for details.

.. _forpostgresql:

For the PostgreSQL database
^^^^^^^^^^^^^^^^^^^^^^^^^^^

You need to install the database and its Python bindings:

-  `PostgreSQL <https://www.postgresql.org/>`__, version 9.1 or later
-  `psycopg2 <https://pypi.org/project/psycopg2>`__, version 2.5 or
   later

See
`DatabaseBackend <https://trac.edgewall.org/intertrac/DatabaseBackend%23Postgresql>`__
for details.

.. _formysql:

For the MySQL database
^^^^^^^^^^^^^^^^^^^^^^

Trac works well with MySQL, provided you use the following:

-  `MySQL <https://mysql.com/>`__, version 5.0 or later
-  `PyMySQL <https://pypi.org/project/PyMySQL>`__

Given the caveats and known issues surrounding MySQL, read carefully the
`MySqlDb <https://trac.edgewall.org/intertrac/MySqlDb>`__ page before
creating the database.

.. _optionaldependencies:

Optional Dependencies
~~~~~~~~~~~~~~~~~~~~~

.. _subversion:

Subversion
^^^^^^^^^^

`Subversion <https://subversion.apache.org/>`__, 1.14.x or later and the
**corresponding** Python bindings.

There are `pre-compiled SWIG
bindings <https://subversion.apache.org/packages.html>`__ available for
various platforms. See `getting
Subversion <https://trac.edgewall.org/intertrac/TracSubversion%23GettingSubversion>`__
for more information.

.. container:: wikipage

   **Note:**

   -  Trac **doesn't** use `PySVN <https://pypi.org/project/PySVN>`__,
      nor does it work yet with the newer ``ctype``-style bindings.
   -  If using Subversion, Trac must be installed on the **same
      machine**. Remote repositories are `not
      supported <https://trac.edgewall.org/intertrac/ticket%3A493>`__.

For troubleshooting information, see the
`TracSubversion <https://trac.edgewall.org/intertrac/TracSubversion%23Troubleshooting>`__
page.

.. _git:

Git
^^^

`Git <https://git-scm.com/>`__ 1.5.6 or later is supported. More
information is available on the
`TracGit <https://trac.edgewall.org/intertrac/TracGit>`__ page.

.. _otherversioncontrolsystems:

Other Version Control Systems
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Support for other version control systems is provided via third-party
plugins. See
`PluginList#VersionControlSystems <https://trac.edgewall.org/intertrac/PluginList%23VersionControlSystems>`__
and
`VersionControlSystem <https://trac.edgewall.org/intertrac/VersionControlSystem>`__.

.. _webserver:

Web Server
^^^^^^^^^^

A web server is optional because Trac is shipped with a server included,
see the `Running the Standalone Server <#runningthestandaloneserver>`__
section below.

Alternatively you can configure Trac to run in any of the following
environments:

-  `Apache <https://httpd.apache.org/>`__ with

   -  `mod_wsgi <https://github.com/GrahamDumpleton/mod_wsgi>`__, see
      `TracModWSGI <https://trac.edgewall.org/wiki/TracModWSGI>`__ and
      `ModWSGI
      IntegrationWithTrac <https://code.google.com/p/modwsgi/wiki/IntegrationWithTrac>`__.
   -  `mod_python 3.5.0 <http://modpython.org/>`__, see
      `TracModPython <https://trac.edgewall.org/wiki/TracModPython>`__

-  a `FastCGI <https://fastcgi-archives.github.io>`__-capable web server
   (see `TracFastCgi <https://trac.edgewall.org/wiki/TracFastCgi>`__)
-  an
   `AJP <https://tomcat.apache.org/connectors-doc/ajp/ajpv13a.html>`__-capable
   web server (see
   `TracOnWindowsIisAjp <https://trac.edgewall.org/intertrac/TracOnWindowsIisAjp>`__)
-  Microsoft IIS with FastCGI and a FastCGI-to-WSGI gateway (see `IIS
   with
   FastCGI <https://trac.edgewall.org/intertrac/CookBook/Installation/TracOnWindowsIisWfastcgi>`__)
-  a CGI-capable web server (see
   `TracCgi <https://trac.edgewall.org/wiki/TracCgi>`__), **but usage of
   Trac as a cgi script is highly discouraged**, better use one of the
   previous options.

.. _otherpythonpackages:

Other Python Packages
^^^^^^^^^^^^^^^^^^^^^

-  `Babel <http://babel.pocoo.org>`__, version >= 2.2, needed for
   localization support
-  `pytz <http://pytz.sourceforge.net>`__ to get a complete list of time
   zones, otherwise Trac will fall back on a shorter list from an
   internal time zone implementation. Installing Babel will install
   pytz.
-  `docutils <http://docutils.sourceforge.net>`__, version >= 0.14, for
   `WikiRestructuredText <https://trac.edgewall.org/wiki/WikiRestructuredText>`__.
-  `Pygments <http://pygments.org>`__, version >= 1.0, for `syntax
   highlighting <https://trac.edgewall.org/wiki/TracSyntaxColoring>`__.
-  `Textile <https://pypi.org/project/textile>`__, version >= 2.3, for
   rendering the `Textile markup
   language <https://github.com/textile/python-textile>`__.
-  `passlib <https://pypi.org/project/passlib>`__ on Windows to decode
   `htpasswd
   formats <https://trac.edgewall.org/wiki/TracStandalone#BasicAuthorization:Usingahtpasswdpasswordfile>`__
   other than ``SHA-1``.
-  `pyreadline <https://pypi.org/project/pyreadline>`__ on Windows for
   trac-admin `command
   completion <https://trac.edgewall.org/wiki/TracAdmin#InteractiveMode>`__.

.. container:: wikipage

   **Attention**: The available versions of these dependencies are not
   necessarily interchangeable, so please pay attention to the version
   numbers. If you are having trouble getting Trac to work, please
   double-check all the dependencies before asking for help on the
   `MailingList <https://trac.edgewall.org/intertrac/MailingList>`__ or
   `IrcChannel <https://trac.edgewall.org/intertrac/IrcChannel>`__.

Please refer to the documentation of these packages to find out how they
are best installed. In addition, most of the `platform-specific
instructions <https://trac.edgewall.org/intertrac/TracInstallPlatforms>`__
also describe the installation of the dependencies. Keep in mind however
that the information there *probably concern older versions of Trac than
the one you're installing*.

.. _installingtrac:

Installing Trac
---------------

The `trac-admin <https://trac.edgewall.org/wiki/TracAdmin>`__
command-line tool, used to create and maintain `project
environments <https://trac.edgewall.org/wiki/TracEnvironment>`__, as
well as the `tracd <https://trac.edgewall.org/wiki/TracStandalone>`__
standalone server are installed along with Trac. There are several
methods for installing Trac.

It is assumed throughout this guide that you have elevated permissions
as the ``root`` user or by prefixing commands with ``sudo``. The umask
``0002`` should be used for a typical installation on a Unix-based
platform.

.. _usingpip:

Using ``pip``
~~~~~~~~~~~~~

``pip`` is the modern Python package manager and is included in Python
distributions. ``pip`` will automatically resolve the *required*
dependencies (Jinja2 and setuptools) and download the latest packages
from pypi.org.

You can also install directly from a source package. You can obtain the
source in a tar or zip from the
`TracDownload <https://trac.edgewall.org/intertrac/TracDownload>`__
page. After extracting the archive, change to the directory containing
``setup.py`` and run:

.. container:: wiki-code

   .. container:: code

      ::

         $ pip install .

``pip`` supports numerous other install mechanisms. It can be passed the
URL of an archive or other download location. Here are some examples:

-  Install the latest development version from a tar archive:

   .. container:: wiki-code

      .. container:: code

         ::

            $ pip install https://download.edgewall.org/trac/Trac-latest-dev.tar.gz

-  Install the unreleased 1.4-stable from subversion:

   .. container:: wiki-code

      .. container:: code

         ::

            $ pip install svn+https://svn.edgewall.org/repos/trac/branches/1.4-stable

-  Install the latest development preview (*not recommended for
   production installs*):

   .. container:: wiki-code

      .. container:: code

         ::

            $ pip install --find-links=https://trac.edgewall.org/wiki/TracDownload Trac

The optional dependencies can be installed from PyPI using ``pip``:

.. container:: wiki-code

   .. container:: code

      ::

         $ pip install babel docutils pygments textile

The optional dependencies can alternatively be specified using the
``extras`` keys in the setup file:

.. container:: wiki-code

   .. container:: code

      ::

         $ pip install Trac[babel,rest,pygments,textile]

``rest`` is the extra that installs the ``docutils`` dependency.

Include ``mysql`` or ``psycopg2-binary`` in the list if using the MySQL
or PostgreSQL database.

Additionally, you can install several Trac plugins from PyPI (listed
`here <https://pypi.org/search/?c=Framework+%3A%3A+Trac>`__) using pip.
See `TracPlugins <https://trac.edgewall.org/wiki/TracPlugins>`__ for
more information.

.. _usinginstaller:

Using installer
~~~~~~~~~~~~~~~

On Windows, Trac can be installed using the exe installers available on
the `TracDownload <https://trac.edgewall.org/intertrac/TracDownload>`__
page. Installers are available for the 32-bit and 64-bit versions of
Python. Make sure to use the installer that matches the architecture of
your Python installation.

.. _usingpackagemanager:

Using package manager
~~~~~~~~~~~~~~~~~~~~~

Trac may be available in your platform's package repository. However,
your package manager may not provide the latest release of Trac.

.. _creatingaprojectenvironment:

Creating a Project Environment
------------------------------

A `Trac environment <https://trac.edgewall.org/wiki/TracEnvironment>`__
is the backend where Trac stores information like wiki pages, tickets,
reports, settings, etc. An environment is a directory that contains a
human-readable `configuration
file <https://trac.edgewall.org/wiki/TracIni>`__, and other files and
directories.

A new environment is created using
`trac-admin <https://trac.edgewall.org/wiki/TracAdmin>`__:

.. container:: wiki-code

   .. container:: code

      ::

         $ trac-admin /path/to/myproject initenv

`trac-admin <https://trac.edgewall.org/wiki/TracAdmin>`__ will prompt
you for the information it needs to create the environment: the name of
the project and the `database connection
string <https://trac.edgewall.org/wiki/TracEnvironment#DatabaseConnectionStrings>`__.
If you're not sure what to specify for any of these options, just press
``<Enter>`` to use the default value.

Using the default database connection string will always work as long as
you have SQLite installed. For the other `database
backends <https://trac.edgewall.org/intertrac/DatabaseBackend>`__ you
should plan ahead and already have a database ready to use at this
point.

Also note that the values you specify here can be changed later using
`TracAdmin <https://trac.edgewall.org/wiki/TracAdmin>`__ or directly
editing the `conf/trac.ini <https://trac.edgewall.org/wiki/TracIni>`__
configuration file.

Finally, make sure the user account under which the web front-end runs
will have **write permissions** to the environment directory and all the
files inside. This will be the case if you run
``trac-admin ... initenv`` as this user. If not, you should set the
correct user afterwards. For example on Linux, with the web server
running as user ``apache`` and group ``apache``, enter:

.. container:: wiki-code

   .. container:: code

      ::

         $ chown -R apache:apache /path/to/myproject

The actual username and groupname of the apache server may not be
exactly ``apache``, and are specified in the Apache configuration file
by the directives ``User`` and ``Group`` (if Apache ``httpd`` is what
you use).

.. important::

   **Warning:** Please only use ASCII-characters for account name and
   project path, unicode characters are not supported there.

.. _deployingtrac:

Deploying Trac
--------------

.. _runningthestandaloneserver:

Running the Standalone Server
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

After having created a Trac environment, you can easily try the web
interface by running the standalone server
`tracd <https://trac.edgewall.org/wiki/TracStandalone>`__:

.. container:: wiki-code

   .. container:: code

      ::

         $ tracd --port 8000 /path/to/myproject

Then, open a browser and visit ``http://localhost:8000/``. You should
get a simple listing of all environments that ``tracd`` knows about.
Follow the link to the environment you just created, and you should see
Trac in action. If you only plan on managing a single project with Trac
you can have the standalone server skip the environment list by starting
it like this:

.. container:: wiki-code

   .. container:: code

      ::

         $ tracd -s --port 8000 /path/to/myproject

.. _runningtraconawebserver:

Running Trac on a Web Server
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Trac provides various options for connecting to a "real" web server:

-  `FastCGI <https://trac.edgewall.org/wiki/TracFastCgi>`__
-  `Apache with mod_wsgi <https://trac.edgewall.org/wiki/TracModWSGI>`__
-  `Apache with
   mod_python <https://trac.edgewall.org/wiki/TracModPython>`__
-  `CGI <https://trac.edgewall.org/wiki/TracCgi>`__ *(should not be
   used, as the performance is far from optimal)*

Trac also supports
`AJP <https://trac.edgewall.org/intertrac/TracOnWindowsIisAjp>`__ which
may be your choice if you want to connect to IIS. Other deployment
scenarios are possible:
`nginx <https://trac.edgewall.org/intertrac/TracNginxRecipe>`__,
`uwsgi <https://uwsgi-docs.readthedocs.io/en/latest/#Traconapacheinasub-uri>`__,
`Isapi-wsgi <https://trac.edgewall.org/intertrac/TracOnWindowsIisIsapi>`__
etc.

.. _cgi-bin:

Generating the Trac cgi-bin directory
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Application scripts for CGI, FastCGI and mod-wsgi can be generated using
the `trac-admin <https://trac.edgewall.org/wiki/TracAdmin>`__ ``deploy``
command:

.. code::

   deploy <directory>

       Extract static resources from Trac and all plugins

Grant the web server execution right on scripts in the ``cgi-bin``
directory.

For example, the following yields a typical directory structure:

.. container:: wiki-code

   .. container:: code

      ::

         $ mkdir -p /var/trac
         $ trac-admin /var/trac/<project> initenv
         $ trac-admin /var/trac/<project> deploy /var/www
         $ ls /var/www
         cgi-bin htdocs
         $ chmod ugo+x /var/www/cgi-bin/*

.. _mappingstaticresources:

Mapping Static Resources
^^^^^^^^^^^^^^^^^^^^^^^^

Without additional configuration, Trac will handle requests for static
resources such as stylesheets and images. For anything other than a
`TracStandalone <https://trac.edgewall.org/wiki/TracStandalone>`__
deployment, this is not optimal as the web server can be set up to
directly serve the static resources. For CGI setup, this is **highly
undesirable** as it causes abysmal performance.

Web servers such as `Apache <https://httpd.apache.org/>`__ allow you to
create *Aliases* to resources, giving them a virtual URL that doesn't
necessarily reflect their location on the file system. We can map
requests for static resources directly to directories on the file
system, to avoid Trac processing the requests.

There are two primary URL paths for static resources: ``/chrome/common``
and ``/chrome/site``. Plugins can add their own resources, usually
accessible at the ``/chrome/<plugin>`` path.

A single ``/chrome`` alias can used if the static resources are
extracted for all plugins. This means that the ``deploy`` command
(discussed in the previous section) must be executed after installing or
updating a plugin that provides static resources, or after modifying
resources in the ``$env/htdocs`` directory. This is probably appropriate
for most installations but may not be what you want if, for example, you
wish to upload plugins through the *Plugins* administration page.

The ``deploy`` command creates an ``htdocs`` directory with:

-  ``common/`` - the static resources of Trac
-  ``site/`` - a copy of the environment's ``htdocs/`` directory
-  ``shared`` - the static resources shared by multiple Trac
   environments, with a location defined by the ``[inherit]``
   ``htdocs_dir`` option
-  ``<plugin>/`` - one directory for each resource directory provided by
   the plugins enabled for this environment

The example that follows will create a single ``/chrome`` alias. If that
isn't the correct approach for your installation you simply need to
create more specific aliases:

.. container:: wiki-code

   .. container:: code

      ::

         Alias /trac/chrome/common /path/to/trac/htdocs/common
         Alias /trac/chrome/site /path/to/trac/htdocs/site
         Alias /trac/chrome/shared /path/to/trac/htdocs/shared
         Alias /trac/chrome/<plugin> /path/to/trac/htdocs/<plugin>

.. _scriptalias-example:

Example: Apache and ``ScriptAlias``
'''''''''''''''''''''''''''''''''''

Assuming the deployment has been done this way:

.. container:: wiki-code

   .. container:: code

      ::

         $ trac-admin /var/trac/<project> deploy /var/www/trac

Add the following snippet to Apache configuration, changing paths to
match your deployment. The snippet must be placed *before* the
``ScriptAlias`` or ``WSGIScriptAlias`` directive, because those
directives map all requests to the Trac application:

.. container:: wiki-code

   .. container:: code

      ::

         Alias /trac/chrome /var/www/trac/htdocs

         <Directory "/var/www/trac/htdocs">
           # For Apache 2.2
           <IfModule !mod_authz_core.c>
             Order allow,deny
             Allow from all
           </IfModule>
           # For Apache 2.4
           <IfModule mod_authz_core.c>
             Require all granted
           </IfModule>
         </Directory>

If using mod_python, add this too, otherwise the alias will be ignored:

.. container:: wiki-code

   .. container:: code

      ::

         <Location "/trac/chrome/common">
           SetHandler None
         </Location>

Alternatively, if you wish to serve static resources directly from your
project's ``htdocs`` directory rather than the location to which the
files are extracted with the ``deploy`` command, you can configure
Apache to serve those resources. Again, put this *before* the
``ScriptAlias`` or ``WSGIScriptAlias`` for the .*cgi scripts, and adjust
names and locations to match your installation:

.. container:: wiki-code

   .. container:: code

      ::

         Alias /trac/chrome/site /path/to/projectenv/htdocs

         <Directory "/path/to/projectenv/htdocs">
           # For Apache 2.2
           <IfModule !mod_authz_core.c>
             Order allow,deny
             Allow from all
           </IfModule>
           # For Apache 2.4
           <IfModule mod_authz_core.c>
             Require all granted
           </IfModule>
         </Directory>

Another alternative to aliasing ``/trac/chrome/common`` is having Trac
generate direct links for those static resources (and only those), using
the
`trac.htdocs_location <https://trac.edgewall.org/wiki/TracIni#trac-htdocs_location-option>`__
configuration setting:

.. container:: wiki-code

   .. container:: code

      ::

         [trac]
         htdocs_location = http://static.example.org/trac-common/

Note that this makes it easy to have a dedicated domain serve those
static resources, preferentially cookie-less.

Of course, you still need to make the Trac ``htdocs/common`` directory
available through the web server at the specified URL, for example by
copying (or linking) the directory into the document root of the web
server:

.. container:: wiki-code

   .. container:: code

      ::

         $ ln -s /path/to/trac/htdocs/common /var/www/static.example.org/trac-common

.. _settinguptheplugincache:

Setting up the Plugin Cache
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Some Python plugins need to be extracted to a cache directory. By
default the cache resides in the home directory of the current user.
When running Trac on a Web Server as a dedicated user (which is highly
recommended) who has no home directory, this might prevent the plugins
from starting. To override the cache location you can set the
``PYTHON_EGG_CACHE`` environment variable. Refer to your server
documentation for detailed instructions on how to set environment
variables.

.. _configuringauthentication:

Configuring Authentication
--------------------------

Trac uses HTTP authentication. You'll need to configure your web server
to request authentication when the ``.../login`` URL is hit (the virtual
path of the "login" button). Trac will automatically pick the
``REMOTE_USER`` variable up after you provide your credentials.
Therefore, all user management goes through your web server
configuration. Please consult the documentation of your web server for
more info.

The process of adding, removing, and configuring user accounts for
authentication depends on the specific way you run Trac.

Please refer to one of the following sections:

-  `TracStandalone#UsingAuthentication <https://trac.edgewall.org/wiki/TracStandalone#UsingAuthentication>`__
   if you use the standalone server, ``tracd``.
-  `TracModWSGI#ConfiguringAuthentication <https://trac.edgewall.org/wiki/TracModWSGI#ConfiguringAuthentication>`__
   if you use the Apache web server, with any of its front end:
   ``mod_wsgi``, ``mod_python``, ``mod_fcgi`` or ``mod_fastcgi``.
-  `TracFastCgi <https://trac.edgewall.org/wiki/TracFastCgi>`__ if
   you're using another web server with FCGI support (Cherokee,
   Lighttpd, LiteSpeed, nginx)

`TracAuthenticationIntroduction <https://trac.edgewall.org/intertrac/TracAuthenticationIntroduction>`__
also contains some useful information for beginners.

.. _grantingadminrightstotheadminuser:

Granting admin rights to the admin user
---------------------------------------

Grant admin rights to user admin:

.. container:: wiki-code

   .. container:: code

      ::

         $ trac-admin /path/to/myproject permission add admin TRAC_ADMIN

This user will have an *Admin* navigation item that directs to pages for
administering your Trac project.

.. _configuringtrac:

Configuring Trac
----------------

Configuration options are documented on the
`TracIni <https://trac.edgewall.org/wiki/TracIni>`__ page.

`TracRepositoryAdmin <https://trac.edgewall.org/wiki/TracRepositoryAdmin>`__
provides information on configuring version control repositories for
your project.

In addition to the optional version control backends, Trac provides
several optional features that are disabled by default:

-  `Fine-grained permission
   policy <https://trac.edgewall.org/wiki/TracFineGrainedPermissions#AuthzPolicy>`__
-  `Custom
   permissions <https://trac.edgewall.org/wiki/TracPermissions#CreatingNewPrivileges>`__
-  `Ticket
   deletion <https://trac.edgewall.org/wiki/TracTickets#deleter>`__
-  `Ticket
   cloning <https://trac.edgewall.org/wiki/TracTickets#cloner>`__
-  `Ticket changeset
   references <https://trac.edgewall.org/wiki/TracRepositoryAdmin#CommitTicketUpdater>`__

.. _usingtrac:

Using Trac
----------

Once you have your Trac site up and running, you should be able to
create tickets, view the timeline, browse your version control
repository if configured, etc.

Keep in mind that *anonymous* (not logged in) users can by default
access only a few of the features, in particular they will have a
read-only access to the resources. You will need to configure
authentication and grant additional
`permissions <https://trac.edgewall.org/wiki/TracPermissions>`__ to
authenticated users to see the full set of features.

*Enjoy!*

`The Trac Team <https://trac.edgewall.org/intertrac/TracTeam>`__

--------------

See also:
`TracInstallPlatforms <https://trac.edgewall.org/intertrac/TracInstallPlatforms>`__,
`TracGuide <https://trac.edgewall.org/wiki/TracGuide>`__,
`TracUpgrade <https://trac.edgewall.org/wiki/TracUpgrade>`__

