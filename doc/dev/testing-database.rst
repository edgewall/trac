.. _testing-database:

Using an alternate database backend
===================================

The unit tests don't really touch the db.  The functional tests will,
however, but if you're not using sqlite you need to setup the database
yourself.  Once it's set up, just set :envvar:`TRAC_TEST_DB_URI` to
the connection string you would use for an :command:`trac-admin
inittenv` and run the tests.


.. index::
    pair: Postgres; testing on
    pair: PostgreSQL; testing on

Postgres
--------

Testing against Postgres requires you to setup a postgres database and
user for testing, then setting an environment variable. The test
scripts will create a schema within the database, and on consecutive
runs remove the schema.

.. warning:: Do not run this against a live Trac db schema, the schema
             *will* be removed if it exists.

On OS X and Linux, you can run the following to create the test database::

    $ sudo -u postgres createuser -S -D -r -P -e tracuser
    $ sudo -u postgres createdb -O tracuser trac

Windows::

    > createuser -U postgres -S -D -r -P -e tracuser
    > createdb -U postgres -O tracuser trac

Prior to running the tests, set the :envvar:`TRAC_TEST_DB_URI`
variable. If you do not include a schema in the URI, the schema
``tractest`` will be used.

OS X and Linux::

    $ export TRAC_TEST_DB_URI=postgres://tracuser:password@localhost:5432/trac?schema=tractest
    $ make test

Windows::

    set TRAC_TEST_DB_URI=postgres://tracuser:password@localhost:5432/trac?schema=tractest


Finally, run the tests as usual.  Note that if you have already a test
environment set up from a previous run, thesettings in
testenv/trac/conf/trac.ini will be used. In particular, they will take
precedence over the TRAC_TEST_DB_URI variable. Simply edit that
trac.ini file or even remove the whole testenv folder if this gets in
the way.

If in some cases the tests go wrong and you can't run the tests again
because the schema is already there, you can drop the schema manually
like this:

OS X and Linux::

    > echo 'drop schema "tractest" cascade' | psql trac tracuser

Windows::

    > echo drop schema "tractest" cascade | psql trac tracuser

If you later want to remove the test user and database, use the
following:

On OS X and Linux, you can run the following to create the test
database::

    $ sudo -u postgres dropdb tractest
    $ sudo -u postgres dropuser tractest

Windows::

    > dropdb -U postgres trac
    > dropuser -U postgres tracuser


.. index::
    pair: MySQL; testing on

MySQL
-----

Create the database and user as you normally would.  See the MySqlDb_
page for more information.

.. _MySqlDb: http://trac.edgewall.org/wiki/MySqlDb

Example::

    $ mysql -u root
    CREATE DATABASE trac DEFAULT CHARACTER SET utf8 COLLATE utf8_bin;
    CREATE USER tracuser IDENTIFIED BY 'password';
    GRANT ALL ON trac.* TO tracuser;
    FLUSH PRIVILEGES;
    ^D
    $ export TRAC_TEST_DB_URI=mysql://tracuser:password@localhost/trac
    $ make test
    ...
    $ mysql -u root
    DROP DATABASE trac
    DROP USER tracuser
    ^D

If you have better ideas on automating this, please contact us.


Troubleshooting
---------------

If you hit the following error message::

    trac.core.TracError: The Trac Environment needs to be upgraded.

This is because the test environment clean-up stopped half-way: the
testenv/trac environment is still there, but the
testenv/trac/conf/trac.ini file has already been removed. The default
ticket workflow then requests an environment upgrade. Simply remove
manually the whole testenv folder and, when using Postgres, remove the
tractest schema manually as explained above.
