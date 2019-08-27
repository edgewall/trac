Trac Installation Guide for 1.3
===============================

Trac is written in the Python programming language and needs a
database, `SQLite`_, `PostgreSQL`_, or `MySQL`_. For HTML rendering,
Trac uses the `Jinja2`_ templating system, though Genshi templates
will still be supported until at least Trac 1.5.1.

Trac can also be localized, and there is probably a translation
available in your language. If you want to use the Trac interface in
other languages, then make sure you have installed the optional
package `Babel`_. Pay attention to the extra steps for localization
support in the `Installing Trac`_ section below. Lacking Babel, you
will only get the default English version.

If you're interested in contributing new translations for other
languages or enhancing the existing translations, please have a look
at `TracL10N`_.

What follows are generic instructions for installing and setting up
Trac. While you may find instructions for installing Trac on specific
systems at `TracInstallPlatforms`_, please first read through these
general instructions to get a good understanding of the tasks
involved.


Dependencies
------------


Mandatory Dependencies
~~~~~~~~~~~~~~~~~~~~~~

To install Trac, the following software packages must be installed:


+ `Python`_, version >= 2.7 and < 3.0 (note that we dropped the
  support for Python 2.6 in this release)
+ `setuptools`_, version >= 0.6
+ `Jinja2*`_, version >= 2.9.3


Setuptools Warning: If the version of your setuptools is in the range
5.4 through 5.6, the environment variable
`PKG_RESOURCES_CACHE_ZIP_MANIFESTS` must be set in order to avoid
significant performance degradation. More information may be found in
`Deploying Trac`_.

You also need a database system and the corresponding python bindings.
The database can be either SQLite, PostgreSQL or MySQL.


For the SQLite database
```````````````````````

You already have the SQLite database bindings bundled with the
standard distribution of Python (the `sqlite3` module).

Optionally, you may install a newer version of `pysqlite`_ than the
one provided by the Python distribution. See `PySqlite*`_ for details.


For the PostgreSQL database
```````````````````````````

You need to install the database and its Python bindings:


+ `PostgreSQL`_, version 9.1 or later
+ `psycopg2`_, version 2.0 or later


See `DatabaseBackend`_ for details.


For the MySQL database
``````````````````````

Trac works well with MySQL, provided you use the following:


+ `MySQL`_, version 5.0 or later
+ `PyMySQL`_


Given the caveats and known issues surrounding MySQL, read carefully
the `MySqlDb`_ page before creating the database.


Optional Dependencies
~~~~~~~~~~~~~~~~~~~~~


Subversion
``````````

`Subversion`_, 1.6.x or later and the *corresponding* Python bindings.

There are `pre-compiled SWIG bindings`_ available for various
platforms. See `getting Subversion`_ for more information.

Note:


+ Trac doesn't use `PySVN`_, nor does it work yet with the newer
  `ctype`-style bindings.
+ If using Subversion, Trac must be installed on the same machine .
  Remote repositories are `not supported`_.


For troubleshooting information, see the `TracSubversion`_ page.


Git
```

`Git`_ 1.5.6 or later is supported. More information is available on
the `TracGit`_ page.


Other Version Control Systems
`````````````````````````````

Support for other version control systems is provided via third-party
plugins. See `PluginList#VersionControlSystems`_ and
`VersionControlSystem`_.


Web Server
``````````

A web server is optional because Trac is shipped with a server
included, see the `Running the Standalone Server`_ section below.

Alternatively you can configure Trac to run in any of the following
environments:


+ `Apache`_ with

    + `mod_wsgi`_, see `TracModWSGI`_ and `ModWSGI IntegrationWithTrac`_.
    + `mod_python 3.5.0`_, see `TracModPython`_

+ a `FastCGI`_-capable web server (see `TracFastCgi`_)
+ an `AJP`_-capable web server (see `TracOnWindowsIisAjp`_)
+ Microsoft IIS with FastCGI and a FastCGI-to-WSGI gateway (see `IIS
  with FastCGI`_)
+ a CGI-capable web server (see `TracCgi`_), but usage of Trac as a
  cgi script is highly discouraged , better use one of the previous
  options.


Other Python Packages
`````````````````````


+ `Babel*`_, version 0.9.6 or >= 1.3, needed for localization support
+ `docutils`_, version >= 0.3.9 for `WikiRestructuredText`_.
+ `Pygments`_ for `syntax highlighting`_.
+ `Textile`_ for rendering the `Textile markup language`_.
+ `pytz`_ to get a complete list of time zones, otherwise Trac will
  fall back on a shorter list from an internal time zone implementation.
+ `passlib`_ on Windows to decode `htpasswd formats`_ other than
  `SHA-1`.
+ `pyreadline`_ on Windows for trac-admin `command completion`_.


Attention : The available versions of these dependencies are not
necessarily interchangeable, so please pay attention to the version
numbers. If you are having trouble getting Trac to work, please
double-check all the dependencies before asking for help on the
`MailingList`_ or `IrcChannel`_.

Please refer to the documentation of these packages to find out how
they are best installed. In addition, most of the `platform-specific
instructions`_ also describe the installation of the dependencies.
Keep in mind however that the information there *probably concern
older versions of Trac than the one you're installing*.


Installing Trac
---------------

The `trac-admin`_ command-line tool, used to create and maintain
`project environments`_, as well as the `tracd`_ standalone server are
installed along with Trac. There are several methods for installing
Trac.

It is assumed throughout this guide that you have elevated permissions
as the `root` user or by prefixing commands with `sudo`. The umask
`0002` should be used for a typical installation on a Unix-based
platform.


Using `pip`
~~~~~~~~~~~

`pip` is the modern Python package manager and is included in Python
2.7.9 and later. Use `get-pip.py`_ to install `pip` for an earlier
version of Python.


::

    $ pip install Trac


`pip` will automatically resolve the *required* dependencies (Jinja2
and setuptools) and download the latest packages from pypi.org.

You can also install directly from a source package. You can obtain
the source in a tar or zip from the `TracDownload`_ page. After
extracting the archive, change to the directory containing `setup.py`
and run:


::

    $ pip install .


`pip` supports numerous other install mechanisms. It can be passed the
URL of an archive or other download location. Here are some examples:


+ Install the latest stable version from a zip archive:

::

    $ pip install https://download.edgewall.org/trac/Trac-latest.zip


+ Install the latest development version from a tar archive:

::

    $ pip install https://download.edgewall.org/trac/Trac-latest-dev.tar.gz


+ Install the unreleased 1.2-stable from subversion:

::

    $ pip install svn+https://svn.edgewall.org/repos/trac/branches/1.2-stable


+ Install the latest development preview ( *not recommended for
  production installs*):

::

    $ pip install --find-links=https://trac.edgewall.org/wiki/TracDownload Trac


The optional dependencies can be installed from PyPI using `pip`:


::

    $ pip install babel docutils pygments pytz textile


Additionally, you can install several Trac plugins from PyPI (listed
`here`_) using pip. See `TracPlugins`_ for more information.


Using installer
~~~~~~~~~~~~~~~

On Windows, Trac can be installed using the exe installers available
on the `TracDownload`_ page. Installers are available for the 32-bit
and 64-bit versions of Python. Make sure to use the installer that
matches the architecture of your Python installation.


Using package manager
~~~~~~~~~~~~~~~~~~~~~

Trac may be available in your platform's package repository. However,
your package manager may not provide the latest release of Trac.


Creating a Project Environment
------------------------------

A `Trac environment`_ is the backend where Trac stores information
like wiki pages, tickets, reports, settings, etc. An environment is a
directory that contains a human-readable `configuration file`_, and
other files and directories.

A new environment is created using `trac-admin`_:


::

    $ trac-admin /path/to/myproject initenv


`trac-admin`_ will prompt you for the information it needs to create
the environment: the name of the project and the `database connection
string`_. If you're not sure what to specify for any of these options,
just press `<Enter>` to use the default value.

Using the default database connection string will always work as long
as you have SQLite installed. For the other `database backends`_ you
should plan ahead and already have a database ready to use at this
point.

Also note that the values you specify here can be changed later using
`TracAdmin`_ or directly editing the `conf/trac.ini`_ configuration
file.

Finally, make sure the user account under which the web front-end runs
will have write permissions to the environment directory and all the
files inside. This will be the case if you run `trac-admin ...
initenv` as this user. If not, you should set the correct user
afterwards. For example on Linux, with the web server running as user
`apache` and group `apache`, enter:


::

    $ chown -R apache:apache /path/to/myproject


The actual username and groupname of the apache server may not be
exactly `apache`, and are specified in the Apache configuration file
by the directives `User` and `Group` (if Apache `httpd` is what you
use).

Warning: Please only use ASCII-characters for account name and project
path, unicode characters are not supported there.


Deploying Trac
--------------

Setuptools Warning: If the version of your setuptools is in the range
5.4 through 5.6, the environment variable
`PKG_RESOURCES_CACHE_ZIP_MANIFESTS` must be set in order to avoid
significant performance degradation.

If running `tracd`, the environment variable can be set system-wide or
for just the user that runs the `tracd` process. There are several
ways to accomplish this in addition to what is discussed here, and
depending on the distribution of your OS.

To be effective system-wide a shell script with the `export` statement
may be added to `/etc/profile.d`. To be effective for a user session
the `export` statement may be added to `~/.profile`.


::

    export PKG_RESOURCES_CACHE_ZIP_MANIFESTS=1


Alternatively, the variable can be set in the shell before executing
`tracd`:


::

    $ PKG_RESOURCES_CACHE_ZIP_MANIFESTS=1 tracd --port 8000 /path/to/myproject


If running the Apache web server, Ubuntu/Debian users should add the
`export` statement to `/etc/apache2/envvars`. RedHat/CentOS/Fedora
should can add the `export` statement to `/etc/sysconfig/httpd`.


Running the Standalone Server
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

After having created a Trac environment, you can easily try the web
interface by running the standalone server `tracd`_:


::

    $ tracd --port 8000 /path/to/myproject


Then, open a browser and visit `http://localhost:8000/`. You should
get a simple listing of all environments that `tracd` knows about.
Follow the link to the environment you just created, and you should
see Trac in action. If you only plan on managing a single project with
Trac you can have the standalone server skip the environment list by
starting it like this:


::

    $ tracd -s --port 8000 /path/to/myproject


Running Trac on a Web Server
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Trac provides various options for connecting to a "real" web server:


+ `FastCGI*`_
+ `Apache with mod_wsgi`_
+ `Apache with mod_python`_
+ `CGI`_ *(should not be used, as the performance is far from
  optimal)*


Trac also supports `AJP*`_ which may be your choice if you want to
connect to IIS. Other deployment scenarios are possible: `nginx`_,
`uwsgi`_, `Isapi-wsgi`_ etc.


Generating the Trac cgi-bin directory
`````````````````````````````````````

Application scripts for CGI, FastCGI and mod-wsgi can be generated
using the `trac-admin`_ `deploy` command:

::

    deploy <directory>
    
        Extract static resources from Trac and all plugins
    


Grant the web server execution right on scripts in the `cgi-bin`
directory.

For example, the following yields a typical directory structure:


::

    $ mkdir -p /var/trac
    $ trac-admin /var/trac/<project> initenv
    $ trac-admin /var/trac/<project> deploy /var/www
    $ ls /var/www
    cgi-bin htdocs
    $ chmod ugo+x /var/www/cgi-bin/*


Mapping Static Resources
````````````````````````

Without additional configuration, Trac will handle requests for static
resources such as stylesheets and images. For anything other than a
`TracStandalone`_ deployment, this is not optimal as the web server
can be set up to directly serve the static resources. For CGI setup,
this is highly undesirable as it causes abysmal performance.

Web servers such as `Apache`_ allow you to create *Aliases* to
resources, giving them a virtual URL that doesn't necessarily reflect
their location on the file system. We can map requests for static
resources directly to directories on the file system, to avoid Trac
processing the requests.

There are two primary URL paths for static resources: `/chrome/common`
and `/chrome/site`. Plugins can add their own resources, usually
accessible at the `/chrome/<plugin>` path.

A single `/chrome` alias can used if the static resources are
extracted for all plugins. This means that the `deploy` command
(discussed in the previous section) must be executed after installing
or updating a plugin that provides static resources, or after
modifying resources in the `$env/htdocs` directory. This is probably
appropriate for most installations but may not be what you want if,
for example, you wish to upload plugins through the *Plugins*
administration page.

The `deploy` command creates an `htdocs` directory with:


+ `common/` - the static resources of Trac
+ `site/` - a copy of the environment's `htdocs/` directory
+ `shared` - the static resources shared by multiple Trac
  environments, with a location defined by the `[inherit]` `htdocs_dir`
  option
+ `<plugin>/` - one directory for each resource directory provided by
  the plugins enabled for this environment


The example that follows will create a single `/chrome` alias. If that
isn't the correct approach for your installation you simply need to
create more specific aliases:


::

    Alias /trac/chrome/common /path/to/trac/htdocs/common
    Alias /trac/chrome/site /path/to/trac/htdocs/site
    Alias /trac/chrome/shared /path/to/trac/htdocs/shared
    Alias /trac/chrome/<plugin> /path/to/trac/htdocs/<plugin>


Example: Apache and `ScriptAlias`
+++++++++++++++++++++++++++++++++

Assuming the deployment has been done this way:


::

    $ trac-admin /var/trac/<project> deploy /var/www


Add the following snippet to Apache configuration, changing paths to
match your deployment. The snippet must be placed *before* the
`ScriptAlias` or `WSGIScriptAlias` directive, because those directives
map all requests to the Trac application:


::

    Alias /trac/chrome /path/to/trac/htdocs
    
    <Directory "/path/to/www/trac/htdocs">
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


If using mod_python, add this too, otherwise the alias will be
ignored:


::

    <Location "/trac/chrome/common">
      SetHandler None
    </Location>


Alternatively, if you wish to serve static resources directly from
your project's `htdocs` directory rather than the location to which
the files are extracted with the `deploy` command, you can configure
Apache to serve those resources. Again, put this *before* the
`ScriptAlias` or `WSGIScriptAlias` for the .*cgi scripts, and adjust
names and locations to match your installation:


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


Another alternative to aliasing `/trac/chrome/common` is having Trac
generate direct links for those static resources (and only those),
using the `trac.htdocs_location`_ configuration setting:


::

    [trac]
    htdocs_location = http://static.example.org/trac-common/


Note that this makes it easy to have a dedicated domain serve those
static resources, preferentially cookie-less.

Of course, you still need to make the Trac `htdocs/common` directory
available through the web server at the specified URL, for example by
copying (or linking) the directory into the document root of the web
server:


::

    $ ln -s /path/to/trac/htdocs/common /var/www/static.example.org/trac-common


Setting up the Plugin Cache
```````````````````````````

Some Python plugins need to be extracted to a cache directory. By
default the cache resides in the home directory of the current user.
When running Trac on a Web Server as a dedicated user (which is highly
recommended) who has no home directory, this might prevent the plugins
from starting. To override the cache location you can set the
`PYTHON_EGG_CACHE` environment variable. Refer to your server
documentation for detailed instructions on how to set environment
variables.


Configuring Authentication
--------------------------

Trac uses HTTP authentication. You'll need to configure your webserver
to request authentication when the `.../login` URL is hit (the virtual
path of the "login" button). Trac will automatically pick the
`REMOTE_USER` variable up after you provide your credentials.
Therefore, all user management goes through your web server
configuration. Please consult the documentation of your web server for
more info.

The process of adding, removing, and configuring user accounts for
authentication depends on the specific way you run Trac.

Please refer to one of the following sections:


+ `TracStandalone#UsingAuthentication`_ if you use the standalone
  server, `tracd`.
+ `TracModWSGI#ConfiguringAuthentication`_ if you use the Apache web
  server, with any of its front end: `mod_wsgi`, `mod_python`,
  `mod_fcgi` or `mod_fastcgi`.
+ `TracFastCgi`_ if you're using another web server with FCGI support
  (Cherokee, Lighttpd, LiteSpeed, nginx)


`TracAuthenticationIntroduction`_ also contains some useful
information for beginners.


Granting admin rights to the admin user
---------------------------------------

Grant admin rights to user admin:


::

    $ trac-admin /path/to/myproject permission add admin TRAC_ADMIN


This user will have an *Admin* navigation item that directs to pages
for administering your Trac project.


Configuring Trac
----------------

Configuration options are documented on the `TracIni`_ page.

`TracRepositoryAdmin`_ provides information on configuring version
control repositories for your project.

In addition to the optional version control backends, Trac provides
several optional features that are disabled by default:


+ `Fine-grained permission policy`_
+ `Custom permissions`_
+ `Ticket deletion`_
+ `Ticket cloning`_
+ `Ticket changeset references`_


Using Trac
----------

Once you have your Trac site up and running, you should be able to
create tickets, view the timeline, browse your version control
repository if configured, etc.

Keep in mind that *anonymous* (not logged in) users can by default
access only a few of the features, in particular they will have a
read-only access to the resources. You will need to configure
authentication and grant additional `permissions`_ to authenticated
users to see the full set of features.

*Enjoy!*

`The Trac Team`_


See also: `TracInstallPlatforms`_, `TracGuide`_, `TracUpgrade`_

.. _AJP*: https://trac.edgewall.org/intertrac/TracOnWindowsIisAjp
.. _AJP: https://tomcat.apache.org/connectors-doc/ajp/ajpv13a.html
.. _Apache with mod_python: https://trac.edgewall.org/wiki/TracModPython
.. _Apache with mod_wsgi: https://trac.edgewall.org/wiki/TracModWSGI
.. _Apache: https://httpd.apache.org/
.. _Babel*: http://babel.pocoo.org
.. _Babel: https://trac.edgewall.org/wiki/TracInstall#OtherPythonPackages
.. _CGI: https://trac.edgewall.org/wiki/TracCgi
.. _command completion: https://trac.edgewall.org/wiki/TracAdmin#InteractiveMode
.. _conf/trac.ini: https://trac.edgewall.org/wiki/TracIni
.. _configuration file: https://trac.edgewall.org/wiki/TracIni
.. _Custom permissions: https://trac.edgewall.org/wiki/TracPermissions#CreatingNewPrivileges
.. _database backends: https://trac.edgewall.org/intertrac/DatabaseBackend
.. _database connection string: https://trac.edgewall.org/wiki/TracEnvironment#DatabaseConnectionStrings
.. _DatabaseBackend: https://trac.edgewall.org/intertrac/DatabaseBackend%23Postgresql
.. _Deploying Trac: https://trac.edgewall.org/wiki/TracInstall#DeployingTrac
.. _docutils: http://docutils.sourceforge.net
.. _FastCGI*: https://trac.edgewall.org/wiki/TracFastCgi
.. _FastCGI: https://fastcgi-archives.github.io
.. _Fine-grained permission policy: https://trac.edgewall.org/wiki/TracFineGrainedPermissions#AuthzPolicy
.. _get-pip.py: https://bootstrap.pypa.io/get-pip.py
.. _getting Subversion: https://trac.edgewall.org/intertrac/TracSubversion%23GettingSubversion
.. _Git: https://git-scm.com/
.. _here: https://pypi.org/search/?c=Framework+%3A%3A+Trac
.. _htpasswd formats: https://trac.edgewall.org/wiki/TracStandalone#BasicAuthorization:Usingahtpasswdpasswordfile
.. _IIS with FastCGI: https://trac.edgewall.org/intertrac/CookBook/Installation/TracOnWindowsIisWfastcgi
.. _Installing Trac: https://trac.edgewall.org/wiki/TracInstall#InstallingTrac
.. _IrcChannel: https://trac.edgewall.org/intertrac/IrcChannel
.. _Isapi-wsgi: https://trac.edgewall.org/intertrac/TracOnWindowsIisIsapi
.. _Jinja2*: https://pypi.org/project/Jinja2
.. _Jinja2: http://jinja.pocoo.org
.. _MailingList: https://trac.edgewall.org/intertrac/MailingList
.. _mod_python 3.5.0: http://modpython.org/
.. _mod_wsgi: https://github.com/GrahamDumpleton/mod_wsgi
.. _ModWSGI IntegrationWithTrac: https://code.google.com/p/modwsgi/wiki/IntegrationWithTrac
.. _MySQL: https://mysql.com/
.. _MySqlDb: https://trac.edgewall.org/intertrac/MySqlDb
.. _nginx: https://trac.edgewall.org/intertrac/TracNginxRecipe
.. _not supported: https://trac.edgewall.org/intertrac/ticket%3A493
.. _passlib: https://pypi.org/project/passlib
.. _permissions: https://trac.edgewall.org/wiki/TracPermissions
.. _platform-specific instructions: https://trac.edgewall.org/intertrac/TracInstallPlatforms
.. _PluginList#VersionControlSystems: https://trac.edgewall.org/intertrac/PluginList%23VersionControlSystems
.. _PostgreSQL: https://www.postgresql.org/
.. _pre-compiled SWIG bindings: https://subversion.apache.org/packages.html
.. _project environments: https://trac.edgewall.org/wiki/TracEnvironment
.. _psycopg2: https://pypi.org/project/psycopg2
.. _Pygments: http://pygments.org
.. _PyMySQL: https://pypi.org/project/PyMySQL
.. _pyreadline: https://pypi.org/project/pyreadline
.. _PySqlite*: https://trac.edgewall.org/intertrac/PySqlite%23ThePysqlite2bindings
.. _pysqlite: https://pypi.org/project/pysqlite
.. _PySVN: http://pysvn.tigris.org/
.. _Python: https://www.python.org/
.. _pytz: http://pytz.sourceforge.net
.. _Running the Standalone Server: https://trac.edgewall.org/wiki/TracInstall#RunningtheStandaloneServer
.. _setuptools: https://pypi.org/project/setuptools
.. _SQLite: https://sqlite.org/
.. _Subversion: https://subversion.apache.org/
.. _syntax highlighting: https://trac.edgewall.org/wiki/TracSyntaxColoring
.. _Textile markup language: https://github.com/textile/python-textile
.. _Textile: https://pypi.org/project/textile
.. _The Trac Team: https://trac.edgewall.org/intertrac/TracTeam
.. _Ticket changeset references: https://trac.edgewall.org/wiki/TracRepositoryAdmin#CommitTicketUpdater
.. _Ticket cloning: https://trac.edgewall.org/wiki/TracTickets#cloner
.. _Ticket deletion: https://trac.edgewall.org/wiki/TracTickets#deleter
.. _Trac environment: https://trac.edgewall.org/wiki/TracEnvironment
.. _trac-admin: https://trac.edgewall.org/wiki/TracAdmin
.. _trac.htdocs_location: https://trac.edgewall.org/wiki/TracIni#trac-htdocs_location-option
.. _TracAdmin: https://trac.edgewall.org/wiki/TracAdmin
.. _TracAuthenticationIntroduction: https://trac.edgewall.org/intertrac/TracAuthenticationIntroduction
.. _TracCgi: https://trac.edgewall.org/wiki/TracCgi
.. _tracd: https://trac.edgewall.org/wiki/TracStandalone
.. _TracDownload: https://trac.edgewall.org/intertrac/TracDownload
.. _TracFastCgi: https://trac.edgewall.org/wiki/TracFastCgi
.. _TracGit: https://trac.edgewall.org/intertrac/TracGit
.. _TracGuide: https://trac.edgewall.org/wiki/TracGuide
.. _TracIni: https://trac.edgewall.org/wiki/TracIni
.. _TracInstallPlatforms: https://trac.edgewall.org/intertrac/TracInstallPlatforms
.. _TracL10N: https://trac.edgewall.org/intertrac/wiki%3ATracL10N
.. _TracModPython: https://trac.edgewall.org/wiki/TracModPython
.. _TracModWSGI#ConfiguringAuthentication: https://trac.edgewall.org/wiki/TracModWSGI#ConfiguringAuthentication
.. _TracModWSGI: https://trac.edgewall.org/wiki/TracModWSGI
.. _TracOnWindowsIisAjp: https://trac.edgewall.org/intertrac/TracOnWindowsIisAjp
.. _TracPlugins: https://trac.edgewall.org/wiki/TracPlugins
.. _TracRepositoryAdmin: https://trac.edgewall.org/wiki/TracRepositoryAdmin
.. _TracStandalone#UsingAuthentication: https://trac.edgewall.org/wiki/TracStandalone#UsingAuthentication
.. _TracStandalone: https://trac.edgewall.org/wiki/TracStandalone
.. _TracSubversion: https://trac.edgewall.org/intertrac/TracSubversion%23Troubleshooting
.. _TracUpgrade: https://trac.edgewall.org/wiki/TracUpgrade
.. _uwsgi: https://uwsgi-docs.readthedocs.io/en/latest/#Traconapacheinasub-uri
.. _VersionControlSystem: https://trac.edgewall.org/intertrac/VersionControlSystem
.. _WikiRestructuredText: https://trac.edgewall.org/wiki/WikiRestructuredText
