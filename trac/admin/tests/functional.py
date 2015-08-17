#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2009-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import unittest

from trac.tests.functional import FunctionalTwillTestCaseSetup, tc
from trac.util.text import unicode_to_base64


class AuthorizationTestCaseSetup(FunctionalTwillTestCaseSetup):
    def test_authorization(self, href, perms, h2_text):
        """Check permissions required to access an administration panel. A
        fine-grained permissions test will also be executed if ConfigObj is
        installed.

        :param href: the relative href of the administration panel
        :param perms: list or tuple of permissions required to access
                      the administration panel
        :param h2_text: the body of the h2 heading on the administration
                        panel"""
        self._tester.go_to_front()
        self._tester.logout()
        self._tester.login('user')
        if isinstance(perms, basestring):
            perms = (perms, )

        h2 = r'<h2>[ \t\n]*%s[ \t\n]*' \
             r'( <span class="trac-count">\(\d+\)</span>)?[ \t\n]*</h2>'
        try:
            for perm in perms:
                try:
                    tc.go(href)
                    tc.find("No administration panels available")
                    self._testenv.grant_perm('user', perm)
                    tc.go(href)
                    tc.find(h2 % h2_text)
                finally:
                    self._testenv.revoke_perm('user', perm)
                try:
                    tc.go(href)
                    tc.find("No administration panels available")
                    self._testenv.enable_authz_permpolicy({
                        href.strip('/').replace('/', ':', 1): {'user': perm},
                    })
                    tc.go(href)
                    tc.find(h2 % h2_text)
                except ImportError:
                    pass
                finally:
                    self._testenv.disable_authz_permpolicy()
        finally:
            self._tester.go_to_front()
            self._tester.logout()
            self._tester.login('admin')


class TestBasicSettings(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Check basic settings."""
        self._tester.go_to_admin()
        tc.formvalue('modbasic', 'url', 'https://my.example.com/something')
        tc.submit()
        tc.find('https://my.example.com/something')

        try:
            tc.formvalue('modbasic', 'default_dateinfo_format', 'absolute')
            tc.submit()
            tc.find(r'<option selected="selected" value="absolute">')
            tc.formvalue('modbasic', 'default_dateinfo_format', 'relative')
            tc.submit()
            tc.find(r'<option selected="selected" value="relative">')
        finally:
            self._testenv.set_config('trac', 'default_dateinfo_format', '')
            self._tester.go_to_admin()
            tc.find(r'<option value="relative">')
            tc.find(r'<option value="absolute">')


class TestBasicSettingsAuthorization(AuthorizationTestCaseSetup):
    def runTest(self):
        """Check permissions required to access Basic Settings panel."""
        self.test_authorization('/admin/general/basics', 'TRAC_ADMIN',
                                "Basic Settings")


class TestLoggingNone(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Turn off logging."""
        # For now, we just check that it shows up.
        self._tester.go_to_admin("Logging")
        tc.find('trac.log')
        tc.formvalue('modlog', 'log_type', 'none')
        tc.submit()
        tc.find('selected="selected">None</option')


class TestLoggingAuthorization(AuthorizationTestCaseSetup):
    def runTest(self):
        """Check permissions required to access Logging panel."""
        self.test_authorization('/admin/general/logging', 'TRAC_ADMIN',
                                "Logging")


class TestLoggingToFile(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Turn logging back on."""
        # For now, we just check that it shows up.
        self._tester.go_to_admin("Logging")
        tc.find('trac.log')
        tc.formvalue('modlog', 'log_type', 'file')
        tc.formvalue('modlog', 'log_file', 'trac.log2')
        tc.formvalue('modlog', 'log_level', 'INFO')
        tc.submit()
        tc.find('selected="selected">File</option')
        tc.find('id="log_file".*value="trac.log2"')
        tc.find('selected="selected">INFO</option>')


class TestLoggingToFileNormal(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Setting logging back to normal."""
        # For now, we just check that it shows up.
        self._tester.go_to_admin("Logging")
        tc.find('trac.log')
        tc.formvalue('modlog', 'log_file', 'trac.log')
        tc.formvalue('modlog', 'log_level', 'DEBUG')
        tc.submit()
        tc.find('selected="selected">File</option')
        tc.find('id="log_file".*value="trac.log"')
        tc.find('selected="selected">DEBUG</option>')


class TestPermissionsAuthorization(AuthorizationTestCaseSetup):
    def runTest(self):
        """Check permissions required to access Permissions panel."""
        self.test_authorization('/admin/general/perm',
                                ('PERMISSION_GRANT', 'PERMISSION_REVOKE'),
                                "Manage Permissions and Groups")


class TestCreatePermissionGroup(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Create a permissions group"""
        self._tester.go_to_admin("Permissions")
        tc.find('Manage Permissions')
        tc.formvalue('addperm', 'gp_subject', 'somegroup')
        tc.formvalue('addperm', 'action', 'REPORT_CREATE')
        tc.submit()
        somegroup = unicode_to_base64('somegroup')
        REPORT_CREATE = unicode_to_base64('REPORT_CREATE')
        tc.find('%s:%s' % (somegroup, REPORT_CREATE))


class TestAddUserToGroup(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Add a user to a permissions group"""
        self._tester.go_to_admin("Permissions")
        tc.find('Manage Permissions')
        tc.formvalue('addsubj', 'sg_subject', 'authenticated')
        tc.formvalue('addsubj', 'sg_group', 'somegroup')
        tc.submit()
        authenticated = unicode_to_base64('authenticated')
        somegroup = unicode_to_base64('somegroup')
        tc.find('%s:%s' % (authenticated, somegroup))

        revoke_checkbox = '%s:%s' % (unicode_to_base64('anonymous'),
                                     unicode_to_base64('PERMISSION_GRANT'))
        tc.formvalue('addperm', 'gp_subject', 'anonymous')
        tc.formvalue('addperm', 'action', 'PERMISSION_GRANT')
        tc.submit()
        tc.find(revoke_checkbox)
        self._testenv.get_trac_environment().config.touch()
        self._tester.logout()
        self._tester.go_to_admin("Permissions")
        try:
            tc.formvalue('addsubj', 'sg_subject', 'someuser')
            tc.formvalue('addsubj', 'sg_group', 'authenticated')
            tc.submit()
            tc.find("The subject someuser was not added to the "
                    "group authenticated because the group has "
                    "TICKET_CHGPROP permission and users cannot "
                    "grant permissions they don't possess.")
        finally:
            self._tester.login('admin')
            self._tester.go_to_admin("Permissions")
            tc.formvalue('revokeform', 'sel', revoke_checkbox)
            tc.submit()
            tc.notfind(revoke_checkbox)


class TestRemoveUserFromGroup(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Remove a user from a permissions group"""
        self._tester.go_to_admin("Permissions")
        tc.find('Manage Permissions')
        authenticated = unicode_to_base64('authenticated')
        somegroup = unicode_to_base64('somegroup')
        tc.find('%s:%s' % (authenticated, somegroup))
        tc.formvalue('revokeform', 'sel', '%s:%s' % (authenticated, somegroup))
        tc.submit()
        tc.notfind('%s:%s' % (authenticated, somegroup))


class TestRemovePermissionGroup(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Remove a permissions group"""
        self._tester.go_to_admin("Permissions")
        tc.find('Manage Permissions')
        somegroup = unicode_to_base64('somegroup')
        REPORT_CREATE = unicode_to_base64('REPORT_CREATE')
        tc.find('%s:%s' % (somegroup, REPORT_CREATE))
        tc.formvalue('revokeform', 'sel', '%s:%s' % (somegroup, REPORT_CREATE))
        tc.submit()
        tc.notfind('%s:%s' % (somegroup, REPORT_CREATE))
        tc.notfind(somegroup)


class TestPluginSettings(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Check plugin settings."""
        self._tester.go_to_admin("Plugins")
        tc.find('Manage Plugins')
        tc.find('Install Plugin')


class TestPluginsAuthorization(AuthorizationTestCaseSetup):
    def runTest(self):
        """Check permissions required to access Logging panel."""
        self.test_authorization('/admin/general/plugin', 'TRAC_ADMIN',
                                "Manage Plugins")


class RegressionTestTicket10752(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/10752
        Permissions on the web admin page should be greyed out when they
        are no longer defined.
        """
        env = self._testenv.get_trac_environment()
        try:
            env.db_transaction("INSERT INTO permission VALUES (%s,%s)",
                               ('user', 'NOTDEFINED_PERMISSION'))
        except env.db_exc.IntegrityError:
            pass
        env.config.touch()

        self._tester.go_to_admin("Permissions")
        tc.find('<span class="missing" '
                'title="NOTDEFINED_PERMISSION is no longer defined">'
                'NOTDEFINED_PERMISSION</span>')
        tc.notfind('<input type="checkbox" [^>]+ disabled="disabled"')
        tc.notfind('<input type="checkbox" [^>]+'
                   'title="You don\'t have permission to revoke this action" '
                   '[^>]+>')


class RegressionTestTicket11069(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11069
        The permissions list should only be populated with permissions that
        the user can grant."""
        self._tester.go_to_front()
        self._tester.logout()
        self._tester.login('user')
        self._testenv.grant_perm('user', 'PERMISSION_GRANT')
        env = self._testenv.get_trac_environment()
        from trac.perm import PermissionSystem
        user_perms = PermissionSystem(env).get_user_permissions('user')
        all_actions = PermissionSystem(env).get_actions()
        try:
            self._tester.go_to_admin("Permissions")
            for action in all_actions:
                option = r"<option>%s</option>" % action
                if action in user_perms and user_perms[action] is True:
                    tc.find(option)
                else:
                    tc.notfind(option)
        finally:
            self._testenv.revoke_perm('user', 'PERMISSION_GRANT')
            self._tester.go_to_front()
            self._tester.logout()
            self._tester.login('admin')


class RegressionTestTicket11095(FunctionalTwillTestCaseSetup):
    """Test for regression of http://trac.edgewall.org/ticket/11095
    The permission is truncated if it overflows the available space (CSS)
    and the full permission name is shown in the title on hover.
    """
    def runTest(self):
        self._tester.go_to_admin("Permissions")
        tc.find('<span title="MILESTONE_VIEW">MILESTONE_VIEW</span>')
        tc.find('<span title="WIKI_VIEW">WIKI_VIEW</span>')


class RegressionTestTicket11117(FunctionalTwillTestCaseSetup):
    """Test for regression of http://trac.edgewall.org/ticket/11117
    Hint should be shown on the Basic Settings admin panel when pytz is not
    installed.
    """
    def runTest(self):
        self._tester.go_to_admin("Basic Settings")
        pytz_hint = "Install pytz for a complete list of timezones."
        from trac.util.datefmt import pytz
        if pytz is None:
            tc.find(pytz_hint)
        else:
            tc.notfind(pytz_hint)


class RegressionTestTicket11257(FunctionalTwillTestCaseSetup):
    """Test for regression of http://trac.edgewall.org/ticket/11257
    Hints should be shown on the Basic Settings admin panel when Babel is not
    installed.
    """
    def runTest(self):
        from trac.util.translation import get_available_locales, has_babel

        babel_hint_lang = "Install Babel for extended language support."
        babel_hint_date = "Install Babel for localized date formats."
        catalog_hint = "Message catalogs have not been compiled."
        language_select = '<select name="default_language">'
        disabled_language_select = \
            '<select name="default_language" disabled="disabled" ' \
            'title="Translations are currently unavailable">'

        self._tester.go_to_admin("Basic Settings")
        if has_babel:
            tc.notfind(babel_hint_lang)
            tc.notfind(babel_hint_date)
            if get_available_locales():
                tc.find(language_select)
                tc.notfind(catalog_hint)
            else:
                tc.find(disabled_language_select)
                tc.find(catalog_hint)
        else:
            tc.find(disabled_language_select)
            tc.find(babel_hint_lang)
            tc.find(babel_hint_date)
            tc.notfind(catalog_hint)


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional
        suite = trac.tests.functional.functionalSuite()
    suite.addTest(TestBasicSettings())
    suite.addTest(TestBasicSettingsAuthorization())
    suite.addTest(TestLoggingNone())
    suite.addTest(TestLoggingAuthorization())
    suite.addTest(TestLoggingToFile())
    suite.addTest(TestLoggingToFileNormal())
    suite.addTest(TestPermissionsAuthorization())
    suite.addTest(TestCreatePermissionGroup())
    suite.addTest(TestAddUserToGroup())
    suite.addTest(TestRemoveUserFromGroup())
    suite.addTest(TestRemovePermissionGroup())
    suite.addTest(TestPluginSettings())
    suite.addTest(TestPluginsAuthorization())
    suite.addTest(RegressionTestTicket10752())
    suite.addTest(RegressionTestTicket11069())
    suite.addTest(RegressionTestTicket11095())
    suite.addTest(RegressionTestTicket11117())
    suite.addTest(RegressionTestTicket11257())
    return suite


suite = functionalSuite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
