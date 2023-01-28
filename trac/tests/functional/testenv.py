# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2023 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

"""Object for creating and destroying a Trac environment for testing purposes.
Provides some Trac environment-wide utility functions, and a way to call
:command:`trac-admin` without it being on the path."""

import contextlib
import hashlib
import http.client
import io
import locale
import os
import re
import sys
import time
from subprocess import call, run, Popen, DEVNULL, PIPE, STDOUT

from trac.admin.api import AdminCommandManager
from trac.config import Configuration, ConfigurationAdmin, UnicodeConfigParser
from trac.db.api import DatabaseManager
from trac.env import open_environment
from trac.perm import PermissionAdmin
from trac.test import EnvironmentStub, get_dburi, rmtree
from trac.tests.contentgen import random_unique_camel
from trac.tests.functional import trac_source_tree
from trac.tests.functional.better_twill import tc
from trac.util import create_file, terminate
from trac.util.compat import close_fds, wait_for_file_mtime_change

# TODO: refactor to support testing multiple frontends, backends
#       (and maybe repositories and authentication).
#
#     Frontends::
#       tracd, ap2+mod_python, ap2+mod_wsgi, ap2+mod_fastcgi, ap2+cgi,
#       lighty+fastcgi, lighty+cgi, cherrypy+wsgi
#
#     Backends::
#       sqlite3+pysqlite2, postgres+psycopg2 python bindings,
#       mysql+pymysql with server v5
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
        self.server = None
        self.logfile = None
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
        # testing.log gets any unused output from subprocesses
        self.logfile = open(os.path.join(self.dirname, 'testing.log'), 'wb',
                            buffering=0)
        self.create_repo()

        config_file = os.path.join(self.dirname, 'config.ini')
        config = Configuration(config_file)
        repo_path = self.repo_path_for_initenv()
        if repo_path:
            config.set('repositories', '.dir', repo_path)
            config.set('repositories', '.type', self.repotype)
        for component in self.get_enabled_components():
            config.set('components', component, 'enabled')
        config.save()
        self._tracadmin('initenv', self.tracdir, self.dburi,
                        '--config=%s' % config_file)
        if call([sys.executable, '-m', 'contrib.htpasswd', '-c', '-b',
                 self.htpasswd, 'admin', 'admin'],
                close_fds=close_fds, cwd=self.command_cwd):
            raise Exception("Unable to setup admin password")
        self.adduser('user')
        self.adduser('joe')
        self.grant_perm('admin', 'TRAC_ADMIN')
        env = self.get_trac_environment()
        self.post_create(env)

    def close(self):
        self.stop()
        if self.logfile:
            self.logfile.close()
            self.logfile = None

    def adduser(self, user):
        """Add a user to the environment.  The password will be set to the
        same as username."""
        self._tracadmin('session', 'add', user)
        if call([sys.executable, '-m', 'contrib.htpasswd', '-b',
                 self.htpasswd, user, user],
                close_fds=close_fds, cwd=self.command_cwd):
            raise Exception('Unable to setup password for user "%s"' % user)

    def deluser(self, user):
        """Delete a user from the environment."""
        self._tracadmin('session', 'delete', user)
        if call([sys.executable, '-m', 'contrib.htpasswd', '-D',
                 self.htpasswd, user],
                close_fds=close_fds, cwd=self.command_cwd):
            raise Exception('Unable to remove password for user "%s"' % user)

    def grant_perm(self, user, perm):
        """Grant permission(s) to specified user. A single permission may
        be specified as a string, or multiple permissions may be
        specified as a list or tuple of strings."""
        env = self.get_trac_environment()
        if isinstance(perm, (list, tuple)):
            PermissionAdmin(env)._do_add(user, *perm)
        else:
            PermissionAdmin(env)._do_add(user, perm)
        # We need to force an environment reset, as this is necessary
        # for the permission change to take effect: grant only
        # invalidates the `DefaultPermissionStore._all_permissions`
        # cache, but the `DefaultPermissionPolicy.permission_cache` is
        # unaffected.
        env.config.touch()

    def revoke_perm(self, user, perm):
        """Revoke permission(s) from specified user. A single permission
        may be specified as a string, or multiple permissions may be
        specified as a list or tuple of strings."""
        env = self.get_trac_environment()
        if isinstance(perm, (list, tuple)):
            PermissionAdmin(env)._do_remove(user, *perm)
        else:
            PermissionAdmin(env)._do_remove(user, perm)
        # Force an environment reset (see grant_perm above)
        env.config.touch()

    def set_config(self, *args):
        """Calls trac-admin to set the value for the given option
        in `trac.ini`."""
        self._execute_command('config', 'set', *args)

    def get_config(self, *args):
        """Calls trac-admin to get the value for the given option
        in `trac.ini`."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self._execute_command('config', 'get', *args)
        return out.getvalue()

    def remove_config(self, *args):
        """Calls trac-admin to remove the value for the given option
        in `trac.ini`."""
        self._execute_command('config', 'remove', *args)

    def add_milestone(self, name=None, due=None):
        return self._add_ticket_field_value('milestone', name, due)

    def add_component(self, name=None, owner=None):
        return self._add_ticket_field_value('component', name, owner)

    def add_version(self, name=None, time=None):
        return self._add_ticket_field_value('version', name, time)

    def add_severity(self, name=None):
        return self._add_ticket_field_value('severity', name)

    def add_priority(self, name=None):
        return self._add_ticket_field_value('priority', name)

    def add_resolution(self, name=None):
        return self._add_ticket_field_value('resolution', name)

    def add_ticket_type(self, name=None):
        return self._add_ticket_field_value('ticket_type', name)

    def _add_ticket_field_value(self, field, name, *args):
        if name is None:
            name = random_unique_camel()
        self._execute_command(field, 'add', name, *args)
        return name

    def _tracadmin(self, *args):
        """Internal utility method for calling trac-admin"""
        proc = run([sys.executable, '-m', 'trac.admin.console',
                    self.tracdir] + list(args),
                   stdin=DEVNULL, stdout=PIPE, stderr=STDOUT,
                   close_fds=close_fds, cwd=self.command_cwd)
        if proc.stderr:
            self.logfile.write(proc.stderr)
        out = str(proc.stdout, 'utf-8')
        if proc.returncode:
            print(out)
            raise Exception("Failed while running trac-admin with arguments "
                            "%r.\nExitcode: %s \n%s"
                            % (args, proc.returncode, proc.stderr))
        else:
            return out

    def _execute_command(self, *args):
        env = self.get_trac_environment()
        AdminCommandManager(env).execute_command(*args)

    def start(self):
        """Starts the webserver, and waits for it to come up."""
        args = [sys.executable, '-m', 'trac.web.standalone']
        options = ["--port=%s" % self.port, "-s", "--hostname=127.0.0.1",
                   "--basic-auth=trac,%s," % self.htpasswd]
        if 'TRAC_TEST_TRACD_OPTIONS' in os.environ:
            options += os.environ['TRAC_TEST_TRACD_OPTIONS'].split()
        self.server = Popen(args + options + [self.tracdir],
                            stdout=self.logfile, stderr=self.logfile,
                            close_fds=close_fds,
                            cwd=self.command_cwd)
        # Verify that the server is listening
        conn = http.client.HTTPConnection('127.0.0.1', self.port)
        try:
            timeout = 30
            while timeout:
                try:
                    conn.connect()
                    break
                except OSError:
                    time.sleep(1)
                timeout -= 1
            else:
                raise Exception('Timed out waiting for server to start.')
        finally:
            conn.close()
        tc.go(self.url)
        tc.url(self.url, regexp=False)

    def stop(self):
        """Stops the webserver, if running

        FIXME: probably needs a nicer way to exit for coverage to work
        """
        if self.server:
            terminate(self.server.pid)
            self.server.wait()
            self.server = None

    def restart(self):
        """Restarts the webserver"""
        self.stop()
        self.start()

    def get_trac_environment(self):
        """Returns a Trac environment object"""
        return open_environment(self.tracdir, use_cache=True)

    def repo_path_for_initenv(self):
        """Default to no repository"""
        return None

    def call_in_dir(self, dir, args, environ=None):
        proc = Popen(args, stdout=PIPE, stderr=self.logfile,
                     close_fds=close_fds, cwd=dir, env=environ)
        (data, _) = proc.communicate()
        if proc.wait():
            raise Exception('Unable to run command %s in %s' %
                            (args, dir))
        self.logfile.write(data)
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
        if filename is None:
            filename = 'authz-' + hashlib.md5(repr(authz_content).
                                              encode('utf-8')).hexdigest()[:9]
        env = self.get_trac_environment()
        authz_file = os.path.join(env.conf_dir, filename)
        if os.path.exists(authz_file):
            wait_for_file_mtime_change(authz_file)
        if isinstance(authz_content, str):
            authz_content = [line.strip() + '\n'
                             for line in authz_content.strip().splitlines()]
            authz_content = ['# -*- coding: utf-8 -*-\n'] + authz_content
            create_file(authz_file, authz_content)
        else:
            parser = UnicodeConfigParser()
            for section, options in authz_content.items():
                parser.add_section(section)
                for key, value in options.items():
                    parser.set(section, key, value)
            with open(authz_file, 'w', encoding='utf-8') as f:
                parser.write(f)
        permission_policies = env.config.get('trac', 'permission_policies')
        env.config.set('trac', 'permission_policies',
                       'AuthzPolicy, ' + permission_policies)
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
