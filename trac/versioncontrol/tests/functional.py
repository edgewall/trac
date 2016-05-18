#!/usr/bin/env python
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

import os
import tempfile
import unittest

from trac.admin.tests.functional import AuthorizationTestCaseSetup
from trac.tests.contentgen import random_page, random_word, \
                                  random_unique_camel
from trac.tests.functional import FunctionalTwillTestCaseSetup, has_svn, \
                                  internal_error, tc


class TestAdminRepositoryAuthorization(AuthorizationTestCaseSetup):
    def runTest(self):
        """Check permissions required to access the Version Control
        Repositories panel."""
        self.test_authorization('/admin/versioncontrol/repository',
                                'VERSIONCONTROL_ADMIN', "Manage Repositories")


class TestAdminInvalidRepository(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Repository with an invalid path is rendered with an error
        message on the repository admin page.
        """
        self._tester.go_to_admin("Repositories")
        tc.formvalue('trac-addrepos', 'name', 'InvalidRepos')
        tc.formvalue('trac-addrepos', 'dir', '/the/invalid/path')
        tc.submit()
        tc.find((u'<span class="missing" title="[^"]*">'
                 u'/the/\u200binvalid/\u200bpath</span>').encode('utf-8'))


class TestEmptySvnRepo(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Check empty repository"""
        browser_url = self._tester.url + '/browser'
        tc.go(browser_url)
        tc.url(browser_url)
        # This tests the current behavior; I'm not sure it's the best
        # behavior.
        tc.follow('Last Change')
        tc.find('Error: No such changeset')
        tc.back()
        tc.follow('Revision Log')
        tc.notfind('Error: Nonexistent path')


class TestRepoCreation(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Create a directory tree in the repository"""
        # This should probably use the svn bindings...
        directories = []
        for component in ('component1', 'component2'):
            directories.append(component)
            for subdir in ('branches', 'tags', 'trunk'):
                directories.append('/'.join([component, subdir]))
        commit_message = 'Create component trees.'
        self._testenv.svn_mkdir(directories, commit_message)

        browser_url = self._tester.url + '/browser'
        tc.go(browser_url)
        tc.url(browser_url)
        tc.find('component1')
        tc.find('component2')
        tc.follow('Last Change')
        tc.url(self._tester.url + '/changeset/1/')
        tc.find(commit_message)
        for directory in directories:
            tc.find(directory)
        tc.back()
        tc.follow('Revision Log')
        # (Note that our commit log message is short enough to avoid
        # truncation.)
        tc.find(commit_message)
        tc.follow('Timeline')
        # (Note that our commit log message is short enough to avoid
        # truncation.)
        tc.find(commit_message)
        tc.formvalue('prefs', 'ticket', False)
        tc.formvalue('prefs', 'milestone', False)
        tc.formvalue('prefs', 'wiki', False)
        tc.submit()
        tc.find('by.*admin')
        # (Note that our commit log message is short enough to avoid
        # truncation.)
        tc.find(commit_message)


class TestRepoBrowse(FunctionalTwillTestCaseSetup):
    # TODO: move this out to a subversion-specific testing module
    def runTest(self):
        """Add a file to the repository and verify it is in the browser"""
        # Add a file to Subversion
        tempfilename = random_word() + '_repo_browse.txt'
        fulltempfilename = 'component1/trunk/' + tempfilename
        revision = self._testenv.svn_add(fulltempfilename, random_page())

        # Verify that it appears in the browser view:
        browser_url = self._tester.url + '/browser'
        tc.go(browser_url)
        tc.url(browser_url)
        tc.find('component1')
        tc.follow('component1')
        tc.follow('trunk')
        tc.follow(tempfilename)
        self._tester.quickjump('[%s]' % revision)
        tc.find('Changeset %s' % revision)
        tc.find('admin')
        tc.find('Add %s' % fulltempfilename)
        tc.find('1 added')
        tc.follow('Timeline')
        tc.find('Add %s' % fulltempfilename)


class TestNewFileLog(FunctionalTwillTestCaseSetup):
    # TODO: move this out to a subversion-specific testing module
    def runTest(self):
        """Verify browser log for a new file"""
        tempfilename = random_word() + '_new.txt'
        fulltempfilename = 'component1/trunk/' + tempfilename
        revision = self._testenv.svn_add(fulltempfilename, '')
        tc.go(self._tester.url + '/log/' + fulltempfilename)
        tc.find('@%d' % revision)
        tc.find('Add %s' % fulltempfilename)


class RegressionTestTicket5819(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5819
        Events with identical dates are reversed in timeline
        """
        # Multiple events very close together
        files = ['a', 'b', 'c', 'd']
        for filename in files:
            # We do a mkdir because it's easy.
            self._testenv.svn_mkdir(['component1/trunk/' + filename],
                     'Create component1/%s' % filename)
        self._tester.go_to_timeline()
        # They are supposed to show up in d, c, b, a order.
        components = '.*'.join(['Create component1/%s' % f for f in
                                      reversed(files)])
        tc.find(components, 's')


class RegressionTestTicket11186(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11186
        TracError should be raised when repository with name already exists
        """
        self._tester.go_to_admin()
        tc.follow("\\bRepositories\\b")
        tc.url(self._tester.url + '/admin/versioncontrol/repository')
        name = random_word()
        tc.formvalue('trac-addrepos', 'name', name)
        tc.formvalue('trac-addrepos', 'dir', '/var/svn/%s' % name)
        tc.submit()
        tc.find('The repository "%s" has been added.' % name)
        tc.formvalue('trac-addrepos', 'name', name)
        tc.formvalue('trac-addrepos', 'dir', '/var/svn/%s' % name)
        tc.submit()
        tc.find('The repository "%s" already exists.' % name)
        tc.notfind(internal_error)


class RegressionTestTicket11186Alias(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11186 alias
        TracError should be raised when repository alias with name already
        exists
        """
        self._tester.go_to_admin()
        tc.follow("\\bRepositories\\b")
        tc.url(self._tester.url + '/admin/versioncontrol/repository')
        word = random_word()
        target = '%s_repos' % word
        name = '%s_alias' % word
        tc.formvalue('trac-addrepos', 'name', target)
        tc.formvalue('trac-addrepos', 'dir', '/var/svn/%s' % target)
        tc.submit()
        tc.find('The repository "%s" has been added.' % target)
        tc.formvalue('trac-addalias', 'name', name)
        tc.formvalue('trac-addalias', 'alias', target)
        tc.submit()
        tc.find('The alias "%s" has been added.' % name)
        tc.formvalue('trac-addalias', 'name', name)
        tc.formvalue('trac-addalias', 'alias', target)
        tc.submit()
        tc.find('The alias "%s" already exists.' % name)
        tc.notfind(internal_error)


class RegressionTestRev5877(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of the source browser fix in r5877"""
        tc.go(self._tester.url + '/browser?range_min_secs=1')
        tc.notfind(internal_error)


class RegressionTestTicket11194(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11194
        TracError should be raised when repository with name already exists
        """
        self._tester.go_to_admin()
        tc.follow("\\bRepositories\\b")
        tc.url(self._tester.url + '/admin/versioncontrol/repository')

        word = random_word()
        names = ['%s_%d' % (word, n) for n in xrange(3)]
        tc.formvalue('trac-addrepos', 'name', names[0])
        tc.formvalue('trac-addrepos', 'dir', '/var/svn/%s' % names[0])
        tc.submit()
        tc.notfind(internal_error)

        tc.formvalue('trac-addrepos', 'name', names[1])
        tc.formvalue('trac-addrepos', 'dir', '/var/svn/%s' % names[1])
        tc.submit()
        tc.notfind(internal_error)

        tc.follow('\\b' + names[1] + '\\b')
        tc.url(self._tester.url + '/admin/versioncontrol/repository/' + names[1])
        tc.formvalue('edit', 'name', names[2])
        tc.submit('save')
        tc.notfind(internal_error)
        tc.url(self._tester.url + '/admin/versioncontrol/repository')

        tc.follow('\\b' + names[2] + '\\b')
        tc.url(self._tester.url + '/admin/versioncontrol/repository/' + names[2])
        tc.formvalue('edit', 'name', names[0])
        tc.submit('save')
        tc.find('The repository "%s" already exists.' % names[0])
        tc.notfind(internal_error)


class RegressionTestTicket11346(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11346
        fix for log: link with revision ranges included oldest wrongly
        showing HEAD revision
        """
        # create new 3 revisions
        self._testenv.svn_mkdir(['ticket11346'], '')
        for i in (1, 2):
            rev = self._testenv.svn_add('ticket11346/file%d.txt' % i, '')
        tc.go(self._tester.url + '/log?revs=1-2')
        tc.find('@1')
        tc.find('@2')
        tc.notfind('@3')
        tc.notfind('@%d' % rev)


class RegressionTestTicket11355(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11355
        Save with no changes should redirect back to the repository listing.
        """
        # Add a repository
        self._tester.go_to_admin("Repositories")
        name = random_unique_camel()
        dir = os.path.join(tempfile.gettempdir(), name.lower())
        tc.formvalue('trac-addrepos', 'name', name)
        tc.formvalue('trac-addrepos', 'dir', dir)
        tc.submit('add_repos')
        tc.find('The repository "%s" has been added.' % name)

        # Save unmodified form and redirect back to listing page
        tc.follow(r"\b%s\b" % name)
        tc.url(self._tester.url + '/admin/versioncontrol/repository/' + name)
        tc.submit('save', formname='edit')
        tc.url(self._tester.url + '/admin/versioncontrol/repository')
        tc.find("Your changes have been saved.")

        # Warning is added when repository dir is not an absolute path
        tc.follow(r"\b%s\b" % name)
        tc.url(self._tester.url + '/admin/versioncontrol/repository/' + name)
        tc.formvalue('edit', 'dir', os.path.basename(dir))
        tc.submit('save')
        tc.url(self._tester.url + '/admin/versioncontrol/repository/' + name)
        tc.find('The repository directory must be an absolute path.')


class RegressionTestTicket11438(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11438
        fix for log: link with revision ranges included "head" keyword
        """
        rev = self._testenv.svn_mkdir(['ticket11438'], '')
        rev = self._testenv.svn_add('ticket11438/file1.txt', '')
        rev = self._testenv.svn_add('ticket11438/file2.txt', '')
        tc.go(self._tester.url + '/intertrac/log:@%d:head' % (rev - 1))
        tc.url(self._tester.url + r'/log/\?revs=' + str(rev - 1) + '-head')
        tc.notfind('@%d' % (rev + 1))
        tc.find('@%d' % rev)
        tc.find('@%d' % (rev - 1))
        tc.notfind('@%d' % (rev - 2))


class RegressionTestTicket11584(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11584
        don't raise NoSuchChangeset for empty repository if no "rev" parameter
        """
        repo_path = self._testenv.svnadmin_create('repo-t11584')

        self._tester.go_to_admin()
        tc.follow("\\bRepositories\\b")
        tc.url(self._tester.url + '/admin/versioncontrol/repository')

        tc.formvalue('trac-addrepos', 'name', 't11584')
        tc.formvalue('trac-addrepos', 'dir', repo_path)
        tc.submit()
        tc.notfind(internal_error)
        self._testenv._tracadmin('repository', 'sync', 't11584')

        browser_url = self._tester.url + '/browser/t11584'
        tc.go(browser_url)
        tc.url(browser_url)
        tc.notfind('Error: No such changeset')


class RegressionTestTicket11618(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11618
        fix for malformed `readonly="True"` attribute in repository admin.
        """
        env = self._testenv.get_trac_environment()
        env.config.set('repositories', 't11618.dir',
                       self._testenv.repo_path_for_initenv())
        env.config.save()
        try:
            self._tester.go_to_admin()
            tc.follow(r'\bRepositories\b')
            tc.url(self._tester.url + '/admin/versioncontrol/repository')
            tc.follow(r'\bt11618\b')
            tc.url(self._tester.url + '/admin/versioncontrol/repository/t11618')
            tc.notfind(' readonly="True"')
            tc.find(' readonly="readonly"')
        finally:
            env.config.remove('repositories', 't11618.dir')
            env.config.save()


class RegressionTestTicket11777(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11777
        fix for raw revisions in search results.
        """
        self._testenv.svn_mkdir(['ticket11777'], '')
        rev = self._testenv.svn_add('ticket11777/file1.txt', 'data',
                                    'ticket-11777')
        tc.go(self._tester.url +
              '/search?q=ticket-11777&noquickjump=1&changeset=on')
        tc.notfind(r'\[%010d\]: ticket-11777' % rev)
        tc.find(r'\[%d\]: ticket-11777' % rev)
        tc.find(' href="/changeset/%d"' % rev)


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional
        suite = trac.tests.functional.functionalSuite()
    if has_svn:
        suite.addTest(TestAdminRepositoryAuthorization())
        suite.addTest(RegressionTestTicket11355())
        suite.addTest(TestAdminInvalidRepository())
        suite.addTest(TestEmptySvnRepo())
        suite.addTest(TestRepoCreation())
        suite.addTest(TestRepoBrowse())
        suite.addTest(TestNewFileLog())
        suite.addTest(RegressionTestTicket5819())
        suite.addTest(RegressionTestTicket11186())
        suite.addTest(RegressionTestTicket11186Alias())
        suite.addTest(RegressionTestTicket11194())
        suite.addTest(RegressionTestTicket11346())
        suite.addTest(RegressionTestTicket11438())
        suite.addTest(RegressionTestTicket11584())
        suite.addTest(RegressionTestTicket11618())
        suite.addTest(RegressionTestTicket11777())
        suite.addTest(RegressionTestRev5877())
    else:
        print("SKIP: versioncontrol/tests/functional.py (no svn bindings)")

    return suite


test_suite = functionalSuite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
