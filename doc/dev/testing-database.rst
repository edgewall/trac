Using an alternate database backend
===================================

The unit tests don't really touch the db.  The functional tests will, however,
but if you're not using sqlite you need to setup the database yourself.  Once
it's set up, just set :envvar:`TRAC_TEST_DB_URI` to the connection string you
would use for an :command:`trac-admin inittenv` and run the tests.


.. index::
    pair: Postgres; testing on
    pair: PostgreSQL; testing on

Postgres
--------

Testing against Postgres requires you to setup a postgres database and user
for testing, then setting an environment variable. The test scripts will create
a schema within the database, and on consecutive runs remove the schema.

.. warning:: Do not run this against a live Trac db schema, the schema *will*
             be removed if it exists.

On OS X and Linux, you can run the following to create the test database::

    $ sudo -u postgres createuser -S -D -r -P -e tractest
    $ sudo -u postgres createdb -O tractest tractest

Windows::

    TODO

Prior to running the tests, set the :envvar:`TRAC_TEST_DB_URI` variable. If you do not
include a schema in the URI, the schema ``tractest`` will be used.

OS X and Linux::

    $ export TRAC_TEST_DB_URI=postgres://tractest:tractest@localhost:5432/tractest?schema=tractest
    $ make test

Windows::

    set TRAC_TEST_DB_URI=postgres://tractest:tractest@localhost:5432/tractest?schema=tractest


Finally, run the tests as usual.

If you later want to remove the test user and database, use the following:

On OS X and Linux, you can run the following to create the test database::

    $ sudo -u postgres dropdb tractest
    $ sudo -u postgres dropuser tractest

Windows::

    TODO


.. index::
    pair: MySQL; testing on

MySQL
-----

Create the database and user as you normally would.  See the MySqlDb_ page for
more information.

.. _MySqlDb: http://twill.idyll.org/commands.html

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

