# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

"""Object for creating and destroying a Trac environment for testing purposes.
Provides some Trac environment-wide utility functions, and a way to call
:command:`trac-admin` without it being on the path."""

import locale
import os
import re
import sys
import time
from subprocess import call, Popen, PIPE, STDOUT

from trac.env import open_environment
from trac.test import EnvironmentStub, get_dburi, rmtree
from trac.tests.functional import logfile, trac_source_tree
from trac.tests.functional.better_twill import tc, ConnectError
from trac.util import terminate
from trac.util.compat import close_fds, wait_for_file_mtime_change
from trac.util.text import to_utf8

try:
    from configobj import ConfigObj
except ImportError:
    ConfigObj = None

# TODO: refactor to support testing multiple frontends, backends
#       (and maybe repositories and authentication).
#
#     Frontends::
#       tracd, ap2+mod_python, ap2+mod_wsgi, ap2+mod_fastcgi, ap2+cgi,
#       lighty+fastcgi, lighty+cgi, cherrypy+wsgi
#
#     Backends::
#       sqlite3+pysqlite2, postgres+psycopg2 python bindings,
#       mysql+mysqldb with server v4, mysql+mysqldb with server v5
#       (those need to test search escaping, among many other things like long
#       paths in browser and unicode chars being allowed/translating...)


class FunctionalTestEnvironment(object):
    """Common location for convenience functions that work with the test
    environment on Trac.  Subclass this and override some methods if you are
    using a different :term:`VCS`.

    :class:`FunctionalTestEnvironment` requires a `dirname` in which
    the test repository and Trac environment will be created, `port`
    for the :command:`tracd` webserver to run on, and the `url` which
    can access this (usually ``localhost``).
    """

    def __init__(self, dirname, port, url):
        """Create a :class:`FunctionalTestEnvironment`, see the class itself
        for parameter information."""
        self.trac_src = trac_source_tree
        self.url = url
        self.command_cwd = os.path.normpath(os.path.join(dirname, '..'))
        self.dirname = os.path.abspath(dirname)
        self.tracdir = os.path.join(self.dirname, "trac")
        self.htpasswd = os.path.join(self.dirname, "htpasswd")
        self.port = port
        self.pid = None
        self.init()
        self.destroy()
        time.sleep(0.1) # Avoid race condition on Windows
        self.create()
        locale.setlocale(locale.LC_ALL, '')

    @property
    def dburi(self):
        dburi = get_dburi()
        if dburi == 'sqlite::memory:':
            # functional tests obviously can't work with the in-memory database
            dburi = 'sqlite:db/trac.db'
        return dburi

    def destroy(self):
        """Remove all of the test environment data."""
        env = EnvironmentStub(path=self.tracdir, destroying=True)
        env.destroy_db()
        env.shutdown()

        self.destroy_repo()
        if os.path.exists(self.dirname):
            rmtree(self.dirname)

    repotype = 'svn'

    def init(self):
        """ Hook for modifying settings or class attributes before
        any methods are called. """
        pass

    def create_repo(self):
        """Hook for creating the repository."""
        # The default test environment does not include a source repo

    def destroy_repo(self):
        """Hook for removing the repository."""
        # The default test environment does not include a source repo

    def post_create(self, env):
        """Hook for modifying the environment after creation.  For example, to
        set configuration like:
        ::

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
        return ['tracopt.versioncontrol.svn.*']

    def create(self):
        """Create a new test environment.
        This sets up Trac, calls :meth:`create_repo` and sets up
        authentication.
        """
        os.mkdir(self.dirname)
        self.create_repo()

        self._tracadmin('initenv', self.tracdir, self.dburi, self.repotype,
                        self.repo_path_for_initenv())
        if call([sys.executable,
                 os.path.join(self.trac_src, 'contrib', 'htpasswd.py'), "-c",
                 "-b", self.htpasswd, "admin", "admin"], close_fds=close_fds,
                cwd=self.command_cwd):
            raise Exception('Unable to setup admin password')
        self.adduser('user')
        self.adduser('joe')
        self.grant_perm('admin', 'TRAC_ADMIN')
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
        user = to_utf8(user)
        self._tracadmin('session', 'add', user)
        if call([sys.executable, os.path.join(self.trac_src, 'contrib',
                 'htpasswd.py'), '-b', self.htpasswd,
                 user, user], close_fds=close_fds, cwd=self.command_cwd):
            raise Exception('Unable to setup password for user "%s"' % user)

    def deluser(self, user):
        """Delete a user from the environment."""
        user = to_utf8(user)
        self._tracadmin('session', 'delete', user)
        if call([sys.executable, os.path.join(self.trac_src, 'contrib',
                 'htpasswd.py'), '-D', self.htpasswd, user],
                close_fds=close_fds, cwd=self.command_cwd):
            raise Exception('Unable to remove password for user "%s"' % user)

    def grant_perm(self, user, perm):
        """Grant permission(s) to specified user. A single permission may
        be specified as a string, or multiple permissions may be
        specified as a list or tuple of strings."""
        if isinstance(perm, (list, tuple)):
            self._tracadmin('permission', 'add', user, *perm)
        else:
            self._tracadmin('permission', 'add', user, perm)
        # We need to force an environment reset, as this is necessary
        # for the permission change to take effect: grant only
        # invalidates the `DefaultPermissionStore._all_permissions`
        # cache, but the `DefaultPermissionPolicy.permission_cache` is
        # unaffected.
        self.get_trac_environment().config.touch()

    def revoke_perm(self, user, perm):
        """Revoke permission(s) from specified user. A single permission
        may be specified as a string, or multiple permissions may be
        specified as a list or tuple of strings."""
        if isinstance(perm, (list, tuple)):
            self._tracadmin('permission', 'remove', user, *perm)
        else:
            self._tracadmin('permission', 'remove', user, perm)
        # Force an environment reset (see grant_perm above)
        self.get_trac_environment().config.touch()

    def set_config(self, *args):
        """Calls trac-admin to get the value for the given option
        in `trac.ini`."""
        self._tracadmin('config', 'set', *args)

    def get_config(self, *args):
        """Calls trac-admin to set the value for the given option
        in `trac.ini`."""
        return self._tracadmin('config', 'get', *args)

    def remove_config(self, *args):
        """Calls trac-admin to remove the value for the given option
        in `trac.ini`."""
        return self._tracadmin('config', 'remove', *args)

    def _tracadmin(self, *args):
        """Internal utility method for calling trac-admin"""
        proc = Popen([sys.executable, os.path.join(self.trac_src, 'trac',
                      'admin', 'console.py'), self.tracdir],
                     stdin=PIPE, stdout=PIPE, stderr=STDOUT,
                     close_fds=close_fds, cwd=self.command_cwd)
        if args:
            if any('\n' in arg for arg in args):
                raise Exception(
                    "trac-admin in interactive mode doesn't support "
                    "arguments with newline characters: %r" % (args,))
            # Don't quote first token which is sub-command name
            input = ' '.join(('"%s"' % to_utf8(arg) if idx else arg)
                             for idx, arg in enumerate(args))
        else:
            input = None
        out = proc.communicate(input=input)[0]
        if proc.returncode:
            print(out)
            logfile.write(out)
            raise Exception("Failed while running trac-admin with arguments %r.\n"
                            "Exitcode: %s \n%s"
                            % (args, proc.returncode, out))
        else:
            # trac-admin is started in interactive mode, so we strip away
            # everything up to the to the interactive prompt
            return re.split(r'\r?\nTrac \[[^]]+\]> ', out, 2)[1]

    def start(self):
        """Starts the webserver, and waits for it to come up."""
        if 'FIGLEAF' in os.environ:
            exe = os.environ['FIGLEAF']
            if ' ' in exe: # e.g. 'coverage run'
                args = exe.split()
            else:
                args = [exe]
        else:
            args = [sys.executable]
        options = ["--port=%s" % self.port, "-s", "--hostname=127.0.0.1",
                   "--basic-auth=trac,%s," % self.htpasswd]
        if 'TRAC_TEST_TRACD_OPTIONS' in os.environ:
            options += os.environ['TRAC_TEST_TRACD_OPTIONS'].split()
        args.append(os.path.join(self.trac_src, 'trac', 'web',
                                 'standalone.py'))
        server = Popen(args + options + [self.tracdir],
                       stdout=logfile, stderr=logfile,
                       close_fds=close_fds,
                       cwd=self.command_cwd)
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
        """Stops the webserver, if running

        FIXME: probably needs a nicer way to exit for coverage to work
        """
        if self.pid:
            terminate(self)

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

    def call_in_dir(self, dir, args, environ=None):
        proc = Popen(args, stdout=PIPE, stderr=logfile,
                     close_fds=close_fds, cwd=dir, env=environ)
        (data, _) = proc.communicate()
        if proc.wait():
            raise Exception('Unable to run command %s in %s' %
                            (args, dir))
        logfile.write(data)
        return data

    def enable_authz_permpolicy(self, authz_content, filename=None):
        """Enables the Authz permissions policy. The `authz_content` will
        be written to `filename`, and may be specified in a triple-quoted
        string.::

           [wiki:WikiStart@*]
           * = WIKI_VIEW
           [wiki:PrivatePage@*]
           john = WIKI_VIEW
           * = !WIKI_VIEW

        `authz_content` may also be a dictionary of dictionaries specifying
        the sections and key/value pairs of each section, however this form
        should only be used when the order of the entries in the file is not
        important, as the order cannot be known.::

           {
            'wiki:WikiStart@*': {'*': 'WIKI_VIEW'},
            'wiki:PrivatePage@*': {'john': 'WIKI_VIEW', '*': '!WIKI_VIEW'},
           }

        The `filename` parameter is optional, and if omitted a filename will
        be generated by computing a hash of `authz_content`, prefixed with
        "authz-".
        """
        if not ConfigObj:
            raise ImportError("Can't enable authz permissions policy. " +
                              "ConfigObj not installed.")
        if filename is None:
            from hashlib import md5
            filename = 'authz-' + md5(str(authz_content)).hexdigest()[0:9]
        env = self.get_trac_environment()
        permission_policies = env.config.get('trac', 'permission_policies')
        env.config.set('trac', 'permission_policies',
                       'AuthzPolicy, ' + permission_policies)
        authz_file = os.path.join(env.conf_dir, filename)
        if isinstance(authz_content, basestring):
            authz_content = [line.strip() for line in
                             authz_content.strip().splitlines()]
        authz_config = ConfigObj(authz_content, encoding='utf8',
                                 write_empty_values=True, indent_type='')
        authz_config.filename = authz_file
        wait_for_file_mtime_change(authz_file)
        authz_config.write()
        env.config.set('authz_policy', 'authz_file', authz_file)
        env.config.set('components', 'tracopt.perm.authz_policy.*', 'enabled')
        env.config.save()

    def disable_authz_permpolicy(self):
        """Disables the Authz permission policy."""
        env = self.get_trac_environment()
        permission_policies = env.config.get('trac', 'permission_policies')
        pp_list = [p.strip() for p in permission_policies.split(',')]
        if 'AuthzPolicy' in pp_list:
            pp_list.remove('AuthzPolicy')
        permission_policies = ', '.join(pp_list)
        env.config.set('trac', 'permission_policies', permission_policies)
        env.config.remove('authz_policy', 'authz_file')
        env.config.remove('components', 'tracopt.perm.authz_policy.*')
        env.config.save()
