# -*- coding: utf-8 -*-
#
# Copyright (C) 2009-2014 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os
import re
from subprocess import call

from testenv import FunctionalTestEnvironment
from trac.util.compat import close_fds


class SvnFunctionalTestEnvironment(FunctionalTestEnvironment):
    def work_dir(self):
        return os.path.join(self.dirname, 'workdir')

    def repo_path(self, filename):
        return os.path.join(self.dirname, filename)

    def repo_path_for_initenv(self):
        return self.repo_path('repo')

    def create_repo(self):
        """
        Initialize a repo of the type :attr:`self.repotype`.
        """
        self.svnadmin_create()
        if call(['svn', 'co', self.repo_url(), self.work_dir()],
                stdout=self.logfile, stderr=self.logfile,
                close_fds=close_fds):
            raise Exception('Checkout from %s failed.' % self.repo_url())

    def destroy_repo(self):
        """The deletion of the test environment will remove the
        repo as well."""
        pass

    def post_create(self, env):
        """Hook for modifying the environment after creation."""
        self._tracadmin('config', 'set', 'repositories',
                        '.sync_per_request', '1')

    def repo_url(self):
        """Returns the url of the Subversion repository for this test
        environment.
        """
        repodir = self.repo_path_for_initenv()
        if os.name == 'nt':
            return 'file:///' + repodir.replace("\\", "/")
        else:
            return 'file://' + repodir

    def svnadmin_create(self, filename=None):
        """Subversion helper to create a new repository."""
        if filename is None:
            path = self.repo_path_for_initenv()
        else:
            path = self.repo_path(filename)
        if call(["svnadmin", "create", path],
                stdout=self.logfile, stderr=self.logfile, close_fds=close_fds):
            raise Exception('unable to create subversion repository: %r' %
                            path)
        return path

    def svn_mkdir(self, paths, msg, username='admin'):
        """Subversion helper to create a new directory within the main
        repository.  Operates directly on the repository url, so a working
        copy need not exist.

        Example::

            self._testenv.svn_mkdir(["abc", "def"], "Add dirs")

        """
        self.call_in_workdir(['svn', '--username=%s' % username,
                              'mkdir', '-m', msg]
                             + [self.repo_url() + '/' + d for d in paths])
        self.call_in_workdir(['svn', 'update'])

    def svn_add(self, filename, data, msg=None, username='admin'):
        """Subversion helper to add a file to the given path within the main
        repository.

        Example::

            self._testenv.svn_add("root.txt", "Hello World")

        """
        f = open(os.path.join(self.work_dir(), filename), 'w')
        f.write(data)
        f.close()
        self.call_in_workdir(['svn', 'add', filename])
        environ = os.environ.copy()
        environ['LC_ALL'] = 'C'     # Force English messages in svn
        msg = 'Add %s' % filename if msg is None else msg
        output = self.call_in_workdir(['svn', '--username=%s' % username,
                                       'commit', '-m', msg, filename],
                                      environ=environ)
        try:
            revision = re.search(r'Committed revision ([0-9]+)\.',
                                 output).group(1)
        except Exception as e:
            args = e.args + (output, )
            raise Exception(*args)
        return int(revision)

    def call_in_workdir(self, args, environ=None):
        return self.call_in_dir(self.work_dir(), args, environ)
