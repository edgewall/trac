.. index::
    pair: tests; prerequisites

Running the tests
=================

Prerequisites
-------------

Beyond the standard installation prereqs, you also need:

* `Pygments <http://pygments.org/>`_ (0.8+)
* `Twill <http://twill.idyll.org/>`_ (0.9+)
* `Coverage <http://nedbatchelder.com/code/coverage/>`_ (for coverage)
* `Figleaf <http://darcs.idyll.org/~t/projects/figleaf/doc/>`_ (0.6.1+, alternative for coverage)

Additionally, if you're on Windows, you need to get fcrypt.  See
`Prerequisites on Windows`_ below for more information.

.. index::
    pair: tests; running

Invoking the tests
------------------

Just run :command:`make test` in the Trac tree once you have
everything installed.  This will run the unit tests first, then the
functional tests (if you have the dependencies) against SQLite.  On a
reasonably fast machine, the former takes 10 seconds and the latter a
couple of minutes.

A few environment variables will influence the way tests are executed:

.. envvar:: TRAC_TEST_DB_URI

Use another database backend than the default in-memory SQLite
database.  See :ref:`Using an alternate database backend
<testing-database>` for more.

.. envvar:: TRAC_TEST_TRACD_OPTIONS

Provide additional options to the standalone
:command:`tracd` server used for the functional tests.

.. envvar:: TRAC_TEST_ENV_PATH

Use the specified path for the test environment directory.

.. envvar:: TRAC_TEST_PORT

Use the specified port for running the standalone :command:`tracd` server.

The :file:`Makefile` is actually written in a way that allow you to
get more control, if you want.

Other possible usages::

  make test=trac/tests/allwiki.py # run all the Wiki formatter tests

  make unit-test db=postgres # run only the unit tests with PostgreSQL

  make functional-test db=mysql # run only the functional tests with MySQL

  make test python=24 # run all the tests using Python 2.4

If you're running the tests on Windows and don't have cygwin, you'll
need to manually run the tests using :command:`python trac\\test.py`,
but this will run all the tests interleaved.


Understanding failures
----------------------

Functional test failures can happen a few different ways.

:Running trac-admin fails every time:

    Make sure the prereqs are met.  In particular, that new enough
    Genshi is available and has :command:`python setup.py egg_info`
    run.

:Repo creation fails:

    Subversion is required for the tests; they are not designed to run
    without it.

:Repo creation works, other repo access fails:

    Probably a mismatch in svn bindings versus the :command:`svn`
    binary.

:Twill errors which save to HTML:

    Check the html and see if there's a traceback contained in it.
    Chances are it has an obvious traceback with an error -- these are
    triggered on the server, not the tester, so they're difficult for
    us to show in the failure itself.

    If you can't decipher what the problem is from viewing the HTML,
    run the server manually and see what state that particular page is
    in.

:Random weird platform issues:

    Please report them.

:Can't remove files on Windows:

    Ugh.  Please report them.

:Reload tests fail:

    Chances are, you're on a Windows VM that has an unstable clock and
    FAT32 filesystem (which has a granularity of several seconds).  If
    that's not the case, report it.

:Coverage doesn't work with functional tests:

    Know issue, patches welcome...


Prerequisites on Windows
------------------------

* You have to install fcrypt_
* You may install pywin32_ (optional, improve `subprocess` performance)

.. _pywin32: http://sourceforge.net/projects/pywin32/
.. _fcrypt: http://carey.geek.nz/code/python-fcrypt/
