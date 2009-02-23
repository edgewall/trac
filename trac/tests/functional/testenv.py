#!/usr/bin/python
"""Object for creating and destroying a Trac environment for testing purposes.
Provides some Trac environment-wide utility functions, and a way to call
trac-admin."""

import os
import time
import signal
import sys
import errno
import locale

from subprocess import call, Popen, PIPE
from trac.tests.functional.compat import rmtree, close_fds
from trac.tests.functional import logfile
from trac.tests.functional.better_twill import tc, ConnectError
from trac.env import open_environment

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
    """Provides a way to work with a test environment in a simpler way."""
    # TODO: Need to see if we can remove the limitation that the tests have
    # to have the cwd be the top of the trac source tree... that limits the
    # places we can put the test environment data.

    def __init__(self, dirname, port, url):
        """A functional test environment requires a directory name in which
        to create the test repository and Trac environment, and a port
        number to use for the webserver."""
        self.url = url
        self.command_cwd = os.path.normpath(os.path.join(dirname, '..'))
        self.dirname = os.path.abspath(dirname)
        self.repodir = os.path.join(self.dirname, "repo")
        self.tracdir = os.path.join(self.dirname, "trac")
        self.htpasswd = os.path.join(self.dirname, "htpasswd")
        self.port = port
        self.pid = None
        self.destroy()
        self.create()
        locale.setlocale(locale.LC_ALL, '')

    def destroy(self):
        """Remove all of the test environment data."""
        if os.path.exists(self.dirname):
            rmtree(self.dirname)

    def create(self):
        """Create a new test environment; Trac, Subversion,
        authentication."""
        if os.mkdir(self.dirname):
            raise Exception('unable to create test environment')
        if call(["svnadmin", "create", self.repodir], stdout=logfile,
                stderr=logfile, close_fds=close_fds):
            raise Exception('unable to create subversion repository')
        self._tracadmin('initenv', 'testenv%s' % self.port,
                        'sqlite:db/trac.db', 'svn', self.repodir)
        if call([sys.executable, "./contrib/htpasswd.py", "-c", "-b",
                 self.htpasswd, "admin", "admin"], close_fds=close_fds,
                 cwd=self.command_cwd):
            raise Exception('Unable to setup admin password')
        self.adduser('user')
        self._tracadmin('permission', 'add', 'admin', 'TRAC_ADMIN')
        # Setup Trac logging
        env = self.get_trac_environment()
        env.config.set('logging', 'log_type', 'file')
        env.config.save()

    def adduser(self, user):
        """Add a user to the environment.  Password is the username."""
        if call([sys.executable, './contrib/htpasswd.py', '-b', self.htpasswd,
                 user, user], close_fds=close_fds, cwd=self.command_cwd):
            raise Exception('Unable to setup password for user "%s"' % user)

    def _tracadmin(self, *args):
        """Internal utility method for calling trac-admin"""
        retval = call([sys.executable, "./trac/admin/console.py", self.tracdir]
                      + list(args), stdout=logfile, stderr=logfile,
                      close_fds=close_fds, cwd=self.command_cwd)
        if retval:
            raise Exception('Failed with exitcode %s running trac-admin ' \
                            'with %r' % (retval, args))

    def start(self):
        """Starts the webserver"""
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
        """Stops the webserver"""
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

    def repo_url(self):
        """Returns the url of the Subversion repository for this test
        environment.
        """
        if os.name == 'nt':
            return 'file:///' + self.repodir.replace("\\", "/")
        else:
            return 'file://' + self.repodir

    def get_trac_environment(self):
        """Returns a Trac environment object"""
        return open_environment(self.tracdir, use_cache=True)


