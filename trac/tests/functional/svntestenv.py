import os
import re
from subprocess import call

from testenv import FunctionalTestEnvironment
from trac.tests.functional.compat import close_fds
from trac.tests.functional import logfile

class SvnFunctionalTestEnvironment(FunctionalTestEnvironment):
    def work_dir(self):
        return os.path.join(self.dirname, 'workdir')

    def repo_path_for_initenv(self):
        return os.path.join(self.dirname, 'repo')

    def create_repo(self):
        """
        Initialize a repo of the type :attr:`self.repotype`.
        """
        if call(["svnadmin", "create", self.repo_path_for_initenv()],
                 stdout=logfile, stderr=logfile, close_fds=close_fds):
            raise Exception('unable to create subversion repository')
        if call(['svn', 'co', self.repo_url(), self.work_dir()], stdout=logfile,
                 stderr=logfile, close_fds=close_fds):
            raise Exception('Checkout from %s failed.' % self.repo_url())

    def destroy_repo(self):
        """The deletion of the testenvironment will remove the repo as well."""
        pass

    def repo_url(self):
        """Returns the url of the Subversion repository for this test
        environment.
        """
        repodir = self.repo_path_for_initenv()
        if os.name == 'nt':
            return 'file:///' + repodir.replace("\\", "/")
        else:
            return 'file://' + repodir

    def svn_mkdir(self, paths, msg, username='admin'):
        """Subversion helper to create a new directory within the main
        repository.  Operates directly on the repository url, so a working
        copy need not exist.

        Example::

            self._testenv.svn_mkdir(["abc", "def"], "Add dirs")

        """
        self.call_in_workdir(['svn', '--username=%s' % username, 'mkdir', '-m', msg]
                + [self.repo_url() + '/' + d for d in paths])
        self.call_in_workdir(['svn', 'update'])

    def svn_add(self, filename, data):
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
        output = self.call_in_workdir(['svn', '--username=admin', 'commit', '-m',
                        'Add %s' % filename, filename], environ=environ)
        try:
            revision = re.search(r'Committed revision ([0-9]+)\.',
                                 output).group(1)
        except Exception, e:
            args = e.args + (output, )
            raise Exception(*args)
        return int(revision)

