.. _install-index:

=======================
Trac Installation Guide
=======================

Trac is written in the Python_ programming language and needs a database,
SQLite_, Postgres_, or MySQL_. For HTML rendering, Trac uses the Genshi_
templating system.

.. _Python: http://python.org/
.. _SQLite: http://sqlite.org/
.. _Postgres: http://www.postgresql.org/
.. _MySQL: http://mysql.com/
.. _Genshi: http://genshi.edgewall.org/

What follows are generic instructions for installing and setting up Trac and
its requirements. While you can find instructions for installing Trac on
specific systems at TracInstallPlatforms_ on the main Trac site, please be
sure to **first read through these general instructions** to get a good
understanding of the tasks involved.

.. _TracInstallPlatforms: http://trac.edgewall.org/wiki/TracInstallPlatforms

.. _install-index-quick:

Quick Install
=============

If you already have Python 2.5 and setuptools_ installed, just run this
command to install the latest version of Trac::

    easy_install Trac

.. _setuptools: http://peak.telecommunity.com/DevCenter/EasyInstall#installing-easy-install

After this skip down to `creating a project environment`__.

__ install-index-environment_


.. index:: requirements
.. _install-index-requirements:

Requirements
============

:Python: >= 2.4 *(If using mod_python or mod_wsgi, 2.5 is preferred.)*
:setuptools: >= 0.6
:Genshi: >= 0.4.1
:Database: See below
:ClearSilver: >= 0.9.3 **optional** *(Needed only for using older plugins.)*

You will need database bindings for whichever database you plan to use. We
highly recommend using SQLite to begin with, and then move to Postgres if you
run in to problems.

.. index::
    pair: SQLite; requirements

SQLite
------

Python 2.5 ships with compatible a version of the bindings included, so if you
use it, stop reading here.

:SQLite: >= 3.3.4
:PySQLite: >= 2.3.2

It is possible to use the older SQLite 2.x and PySQLite 1.1.x, however you may
run in to compatibility problems with some plugins and scripts. In addition
you will hit many throughput and locking issues.

.. index::
    pair: Postgres; requirements
    pair: PostgreSQL; requirements

Postgres
--------

:Postgres: >= 8.0 *(>=8.3 requires Trac >=0.11.)*
:pyscopg2: Any version

or

:pyPgSQL: Any version

pyscopg2 is generally faster, and is preferred.

.. index::
    pair: MySQL; requirements

MySQL
-----

.. warning::
    MySQL has several issues that cannot be easily worked around by Trac. As
    such, it should only be used if there is no other option.

:MySQL: >= 4.1
:MySQLdb: >= 1.2.1

.. index::
    pair: subversion; requirements

Subversion
----------

Using Subversion with Trac is optional, however if you wish to, you will need
to install the Subversion Python bindings.

:Subversion: >= 1.0 

.. note::
    You do **NOT** need to install SWIG in order to install the Python bindings.
    
    The SWIG bindings should not be confused with PySVN_, which is an
    unrelated project.

.. _PySVN: http://pysvn.tigris.org/

For other version control backends, please see VersioningSystemBackend_

.. _VersioningSystemBackend: http://trac.edgewall.org/wiki/VersioningSystemBackend

.. index::
    pair: syntax coloring; requirements

Syntax Coloring
---------------

Trac optionally supports code syntax coloring in the source browser, and in
wiki text. While Pygments_ is the preferred back-end for this you can install
any or all of the following:

.. _Pygments: http://pygments.org/

:Pygments: >= 0.6
:SilverCity: >= 0.9.7, 0.9.5 *(0.9.6 is not compatible.)*
:Enscript: Any version

.. index::
    single: requirements; docutils
    single: requirements; pytz

Other Libraries
---------------

These Python libraries are all optional.

:docutils: >= 0.3 *(Needed for rendering reStructuredText_)*
:pytz: Any version *(Needed for displaying a full list of timezones, without
       it a smaller, internal list will be used.)*

.. _reStructuredText: http://docutils.sourceforge.net/rst.html


.. _install-index-installation:

Installation
============

:command:`easy_install Trac` is the preferred method of installing Trac, but
you can also use the more traditional style from a source bundle::

    python setup.py install

To install in a non-standard path, use the ``--prefix`` option.

See `Installing Python Modules`_ for full instructions on install Python
modules.

.. _Installing Python Modules: http://docs.python.org/inst/inst.html


.. _install-index-environment:

Creating a Project Environment
==============================

A :ref:`Trac environment <admin-environment>` is the back-end storage where
Trac stores information like wiki pages, tickets, reports, settings, etc. An
environment is basically a directory that contains a human-readable
configuration file and various other files and directories.

A new environment is created using :ref:`trac-admin <admin-tracadmin>`::

    trac-admin /path/to/myproject initenv

:ref:`trac-admin <admin-tracadmin>` will prompt you for the information it
needs to create the environment, such as the name of the project, the type and
the path to an existing source code repository, the :ref:`database connection
string <admin-environment-database>`, and so on. If you're not sure what to
specify for one of these options, just leave it blank to use the default
value. The database connection string in particular will always work as long
as you have SQLite installed. Leaving the path to the source code repository
empty will disable any functionality related to version control, but you can
always add that back when the basic system is running.

Also note that the values you specify here can be changed later by directly
editing the :ref:`trac.ini <admin-ini>` configuration file.

Common paths used for the Trac environment are :file:`/var/trac` and
:file:`/srv/trac`.

Web Server
==========

Trac offers much flexibility with its web server options. If you are not
already running a server, the standalone tracd option is generally sufficient
for most projects.

.. toctree::
    :maxdepth: 2
    
    cgi
    fastcgi
    mod_python
    apacheauth
    

Further Configuration
=====================

Once you have your Trac site up and running, you should be able to view the
wiki, browse your subversion repository, view the timeline, etc.

Keep in mind that anonymous (not logged in) users can by default access most
but not all of the features. You will need to configure authentication and
grant additional :ref:`permissions <admin-permissions>` to authenticated users
to see the full set of features.

*Enjoy!*

`The Trac Team`__

__ http://trac.edgewall.org/wiki/TracTeam