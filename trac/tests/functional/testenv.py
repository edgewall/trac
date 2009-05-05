#!/usr/bin/python
"""Object for creating and destroying a Trac environment for testing purposes.
Provides some Trac environment-wide utility functions, and a way to call
:command:`trac-admin` without it being on the path."""

import os
import time
import signal
import sys
import errno
import locale

from subprocess import call, Popen, PIPE, STDOUT
from trac.tests.functional.compat import rmtree, close_fds
from trac.tests.functional import logfile
from trac.tests.functional.better_twill import tc, ConnectError
from trac.env import open_environment
from trac.db.api import _parse_db_str, DatabaseManager
from trac.db.mysql_backend import MySQLConnection
from trac.db.postgres_backend import PostgreSQLConnection
from trac.util.compat import close_fds

# TODO: refactor to support testing multiple frontends, backends (and maybe
# repositories and authentication).
# Frontends:
# tracd, ap2+mod_python, ap2+mod_wsgi, ap2+mod_fastcgi, ap2+cgi,
# lighty+fastcgi, lighty+cgi, cherrypy+wsgi
# Backends:
# sqlite2+pysqlite, sqlite3+pysqlite2, postgres python bindings #1,
# postgres python bindings #2, mysql with server v4, mysql with server v5
# (those need to test search escaping, among many other things like long
# paths in browser and unicode chars being allowed/translating...)
class FunctionalTestEnvironment(object):
    """Common location for convenience functions that work with the test
    environment on Trac.  Subclass this and override some methods if you are
    using a different :term:`VCS`.
    
    :class:`FunctionalTestEnvironment` requires a `dirname` in which the test
    repository and Trac environment will be created, `port` for the
    :command:`tracd` webserver to run on, and the `url` which can
    access this (usually ``localhost``)."""

    def __init__(self, dirname, port, url):
        """Create a :class:`FunctionalTestEnvironment`, see the class itself
        for parameter information."""
        self.url = url
        self.command_cwd = os.path.normpath(os.path.join(dirname, '..'))
        self.dirname = os.path.abspath(dirname)
        self.tracdir = os.path.join(self.dirname, "trac")
        self.htpasswd = os.path.join(self.dirname, "htpasswd")
        self.port = port
        self.pid = None
        self.destroy()
        self.create()
        locale.setlocale(locale.LC_ALL, '')

    def get_dburi(self):
        if os.environ.has_key('TRAC_TEST_DB_URI'):
            dburi = os.environ['TRAC_TEST_DB_URI']

            scheme, db_prop = _parse_db_str(dburi)
            # Assume the schema 'tractest' for Postgres
            if scheme == 'postgres' and db_prop.get('schema'):
                if '?' in dburi:
                    dburi += "&schema=tractest"
                else:
                    dburi += "?schema=tractest"
            return dburi
        return 'sqlite:db/trac.db'
    dburi = property(get_dburi)

    def destroy_mysqldb(self, db, db_prop):
        dbname = os.path.basename(db_prop['path'])
        try:
            cursor = db.cursor()
            cursor.execute('SELECT table_name FROM information_schema.tables '
                           'WHERE table_schema=%s', (dbname,))
            tables = cursor.fetchall()
            for t in tables:
                cursor.execute('DROP TABLE IF EXISTS `%s`' % t)
            db.commit()
        except Exception, e:
            print e
            db.rollback()

    def destroy_postgresql(self, db):
        # We'll remove the schema automatically for Postgres, if it
        # exists.
        # With this, you can run functional tests multiple times without
        # running external tools (just like when running against sqlite)
        if db.schema:
            try:
                cursor = db.cursor()
                cursor.execute('DROP SCHEMA "%s" CASCADE' % db.schema)
                db.commit()
            except: 
                # if drop schema fails, either it's already gone
                # or a manual drop will be needed
                db.rollback()

    def destroy(self):
        """Remove all of the test environment data."""
        scheme, db_prop = _parse_db_str(self.dburi)
        if scheme == 'postgres':
            db = PostgreSQLConnection(**db_prop)
            self.destroy_postgresql(db)
        elif scheme == 'mysql':
            db = MySQLConnection(**db_prop)
            self.destroy_mysqldb(db, db_prop)

        self.destroy_repo()
        if os.path.exists(self.dirname):
            rmtree(self.dirname)

    repotype = 'svn'

    def create_repo(self):
        """Hook for creating the repository."""
        # The default test environment does not include a source repo

    def destroy_repo(self):
        """Hook for removing the repository."""
        # The default test environment does not include a source repo

    def post_create(self, env):
        """Hook for modifying the environment after creation.  For example, to
        set configuration like::

            def post_create(self, env):
                env.config.set('git', 'path', '/usr/bin/git')
                env.config.save()
        """
        pass

    def get_enabled_components(self):
        """Return a list of components that should be enabled after
        environment creation.  For anything more complicated, use the
        :meth:`post_create` method.
        """
        return []

    def create(self):
        """Create a new test environment.
        This sets up Trac, calls :meth:`create_repo` and sets up
        authentication.
        """
        if os.mkdir(self.dirname):
            raise Exception('unable to create test environment')
        self.create_repo()

        self._tracadmin('initenv', 'testenv%s' % self.port,
                        self.dburi, self.repotype,
                        self.repo_path_for_initenv())
        if call([sys.executable, './contrib/htpasswd.py', "-c", "-b",
                 self.htpasswd, "admin", "admin"], close_fds=close_fds,
                 cwd=self.command_cwd):
            raise Exception('Unable to setup admin password')
        self.adduser('user')
        self._tracadmin('permission', 'add', 'admin', 'TRAC_ADMIN')
        # Setup Trac logging
        env = self.get_trac_environment()
        env.config.set('logging', 'log_type', 'file')
        for component in self.get_enabled_components():
            env.config.set('components', component, 'enabled')
        env.config.save()
        self.post_create(env)

    def adduser(self, user):
        """Add a user to the environment.  The password will be set to the
        same as username."""
        if call([sys.executable, './contrib/htpasswd.py', '-b', self.htpasswd,
                 user, user], close_fds=close_fds, cwd=self.command_cwd):
            raise Exception('Unable to setup password for user "%s"' % user)

    def _tracadmin(self, *args):
        """Internal utility method for calling trac-admin"""
        proc = Popen([sys.executable, "./trac/admin/console.py", self.tracdir]
                      + list(args), stdout=PIPE, stderr=STDOUT,
                      close_fds=close_fds, cwd=self.command_cwd)
        out = proc.communicate()[0]
        if proc.returncode:
            print(out)
            logfile.write(out)
            raise Exception('Failed with exitcode %s running trac-admin ' \
                            'with %r' % (proc.returncode, args))

    def start(self):
        """Starts the webserver, and waits for it to come up."""
        if 'FIGLEAF' in os.environ:
            exe = os.environ['FIGLEAF']
        else:
            exe = sys.executable
        server = Popen([exe, "./trac/web/standalone.py",
                        "--port=%s" % self.port, "-s",
                        "--hostname=127.0.0.1",
                        "--basic-auth=trac,%s," % self.htpasswd,
                        self.tracdir],
                       stdout=logfile, stderr=logfile,
                       close_fds=close_fds,
                       cwd=self.command_cwd,
                      )
        self.pid = server.pid
        # Verify that the url is ok
        timeout = 30
        while timeout:
            try:
                tc.go(self.url)
                break
            except ConnectError:
                time.sleep(1)
            timeout -= 1
        else:
            raise Exception('Timed out waiting for server to start.')
        tc.url(self.url)

    def stop(self):
        """Stops the webserver, if running"""
        if self.pid:
            if os.name == 'nt':
                # Untested
                call(["taskkill", "/f", "/pid", str(self.pid)],
                     stdin=PIPE, stdout=PIPE, stderr=PIPE)
            else:
                os.kill(self.pid, signal.SIGINT)
                try:
                    os.waitpid(self.pid, 0)
                except OSError, e:
                    if e.errno != errno.ESRCH:
                        raise

    def restart(self):
        """Restarts the webserver"""
        self.stop()
        self.start()

    def get_trac_environment(self):
        """Returns a Trac environment object"""
        return open_environment(self.tracdir, use_cache=True)

    def repo_path_for_initenv(self):
        """Default to no repository"""
        return "''" # needed for Python 2.3 and 2.4 on win32

    def call_in_workdir(self, args):
        proc = Popen(args, stdout=PIPE, stderr=logfile,
                     close_fds=close_fds, cwd=self.work_dir())
        (data, _) = proc.communicate()
        if proc.wait():
            raise Exception('Unable to run command %s in %s' % (args, self.work_dir()))

        logfile.write(data)
        return data


