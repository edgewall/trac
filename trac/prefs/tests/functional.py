#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2014 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import re
import unittest

from trac.tests.functional import FunctionalTwillTestCaseSetup, \
                                  internal_error, tc


#TODO: split this into multiple smaller testcases
class TestPreferences(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Set preferences for admin user"""
        self._tester.go_to_preferences()
        try:
            tc.notfind('Your preferences have been saved.')
            tc.formvalue('userprefs', 'name', ' System Administrator ')
            tc.formvalue('userprefs', 'email', ' admin@example.com ')
            tc.submit()
            tc.find('Your preferences have been saved.')
            self._tester.go_to_preferences("Localization")
            tc.formvalue('userprefs', 'tz', 'GMT -10:00')
            tc.submit()
            tc.find('Your preferences have been saved.')
            self._tester.go_to_preferences()
            tc.notfind('Your preferences have been saved.')
            tc.find('value="System Administrator"')
            tc.find(r'value="admin@example\.com"')
            self._tester.go_to_preferences("Localization")
            tc.find('GMT -10:00')
        finally:
            self._tester.go_to_preferences()
            tc.formvalue('userprefs', 'name', '')
            tc.formvalue('userprefs', 'email', '')
            tc.submit()
            tc.find('Your preferences have been saved.')


class TestDefaultHandler(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Set default handler."""

        # Project default_handler is selected.
        self._tester.go_to_preferences("User Interface")
        tc.notfind(r'<option[^>]+selected="selected"')
        tc.find("Default \(WikiModule\)")

        try:
            # Project default handler still selected after value is changed.
            hint = "SearchModule is not a valid IRequestHandler or is not" \
                   " enabled\."
            self._testenv.set_config('trac', 'default_handler',
                                     'SearchModule')
            self._tester.go_to_preferences("User Interface")
            tc.notfind('<option[^>]+selected="selected"')
            tc.find("Default \(SearchModule\)")
            tc.notfind(hint)

            # Project default handler still selected after module is disabled.
            component = 'trac.search.web_ui.*'
            self._testenv.set_config('components', component, 'disabled')
            self._tester.go_to_preferences("User Interface")
            try:
                tc.notfind('<option[^>]+selected="selected"')
                tc.find(r"Default \(SearchModule\)")
                tc.find(hint)
            finally:
                self._testenv.remove_config('components', component)
        finally:
            self._testenv.set_config('trac', 'default_handler', 'WikiModule')

        # Set session default handler and navigate to base URL.
        tc.formvalue('userprefs', 'default_handler', 'TimelineModule')
        tc.submit()
        tc.find("Your preferences have been saved\.")
        tc.find('<option[^>]+selected="selected"[^>]+TimelineModule')
        self._tester.go_to_front()
        tc.find("<h1>Timeline</h1>")

        # Clear session default handler.
        self._tester.go_to_preferences("User Interface")
        tc.formvalue('userprefs', 'default_handler', '')
        tc.submit()
        tc.find("Your preferences have been saved\.")
        tc.notfind(r'<option[^>]+selected="selected"')
        tc.find("Default \(WikiModule\)")


class RegressionTestRev5785(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of the fix in r5785"""
        self._tester.go_to_preferences()
        tc.submit('logout', 'logout')
        tc.notfind(internal_error)  # See [5785]
        tc.follow('Login')


class RegressionTestTicket5765(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5765
        Unable to turn off 'Enable access keys' in Preferences
        """
        self._tester.go_to_preferences("User Interface")
        tc.formvalue('userprefs', 'accesskeys', True)
        tc.submit()
        tc.find('name="accesskeys".*checked="checked"')
        tc.formvalue('userprefs', 'accesskeys', False)
        tc.submit()
        tc.notfind('name="accesskeys".*checked="checked"')


class RegressionTestTicket11319(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11319
        Only alphanumeric characters can be used for session key in advanced
        panel.
        """
        try:
            self._tester.logout()
            self._tester.go_to_preferences('Advanced')
            tc.formvalue('userprefs', 'newsid', 'śeśśion_id')
            tc.submit('change')
            tc.notfind(internal_error)
            tc.find('Session ID must be alphanumeric')
            self._tester.go_to_preferences('Advanced')
            tc.formvalue('userprefs', 'loadsid', 'śeśśion_id')
            tc.submit('restore')
            tc.notfind(internal_error)
            tc.find('Session ID must be alphanumeric')
        finally:
            self._tester.login('admin')


class RegressionTestTicket11337(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11337
        The language select will be disabled if Babel is not installed and a
        hint will be shown. The text of the hint is dependent on whether the
        user has TRAC_ADMIN and the message catalogs have been compiled.
        """
        from trac.util.translation import has_babel, get_available_locales

        babel_hint = "Install Babel for extended language support."
        catalog_hint = "Message catalogs have not been compiled."
        nonadmin_hint = r'\s+'.join("Please contact your Trac administrator "
                                    "to enable existing translations".split())
        language_select = '<select id="language" name="language">'
        disabled_language_select = \
            '<select id="language" name="language" disabled="disabled" ' \
            'title="Translations are currently unavailable">'

        self._tester.go_to_preferences("Localization")
        if has_babel:
            tc.notfind(babel_hint)
            if get_available_locales():
                tc.find(language_select)
                tc.notfind(babel_hint)
                tc.notfind(catalog_hint)
            else:
                tc.find(disabled_language_select)
                tc.find(catalog_hint)
                tc.notfind(babel_hint)
        else:
            tc.find(disabled_language_select)
            tc.find(babel_hint)
            tc.notfind(catalog_hint)
        tc.notfind(nonadmin_hint)

        # For users without TRAC_ADMIN, the Language tab should only be
        # present when Babel is installed
        self._tester.logout()
        self._tester.go_to_preferences("Localization")
        try:
            if has_babel and get_available_locales():
                tc.find(language_select)
                tc.notfind(nonadmin_hint)
            elif has_babel:
                tc.find(disabled_language_select)
                tc.find(nonadmin_hint)
            else:
                tc.find(disabled_language_select)
                tc.find(nonadmin_hint)
            tc.notfind(catalog_hint)
            tc.notfind(babel_hint)
        finally:
            self._tester.login('admin')


class RegressionTestTicket11515(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11515
        Show a notice message with new language setting after it is changed.
        """
        from trac.util.translation import has_babel, get_available_locales
        from pkg_resources import resource_exists, resource_filename

        if not has_babel:
            print("SKIP: RegressionTestTicket11515 (Babel not installed)")
            return
        if not resource_exists('trac', 'locale'):
            return
        locale_dir = resource_filename('trac', 'locale')
        from babel.support import Translations
        string = 'Your preferences have been saved.'
        translated = None
        for second_locale_id in get_available_locales():
            tx = Translations.load(locale_dir, second_locale_id)
            translated = tx.dgettext('messages', string)
            if string != translated:
                break  # the locale has a translation
        else:
            print("SKIP: RegressionTestTicket11515 "
                  "(Message catalogs not compiled)")
            return

        try:
            self._tester.go_to_preferences('Localization')
            tc.formvalue('userprefs', 'language', second_locale_id)
            tc.submit()
            tc.find(re.escape(translated))
            tc.find('<option selected="selected" value="%s">'
                    % second_locale_id)
        finally:
            tc.formvalue('userprefs', 'language', '')  # revert to default
            tc.submit()
            tc.find('Your preferences have been saved')


class RegressionTestTicket11531(FunctionalTwillTestCaseSetup):
    """Test for regression of http://trac.edgewall.org/ticket/11531
    PreferencesModule can be set as the default_handler."""
    def runTest(self):
        default_handler = self._testenv.get_config('trac', 'default_handler')
        self._testenv.set_config('trac', 'default_handler',
                                 'PreferencesModule')
        try:
            tc.go(self._tester.url)
            tc.notfind(internal_error)
            tc.find(r"\bPreferences\b")
        finally:
            self._testenv.set_config('trac', 'default_handler',
                                     default_handler)


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional
        suite = trac.tests.functional.functionalSuite()
    suite.addTest(TestPreferences())
    suite.addTest(TestDefaultHandler())
    suite.addTest(RegressionTestRev5785())
    suite.addTest(RegressionTestTicket5765())
    suite.addTest(RegressionTestTicket11319())
    suite.addTest(RegressionTestTicket11337())
    suite.addTest(RegressionTestTicket11515())
    suite.addTest(RegressionTestTicket11531())
    return suite


test_suite = functionalSuite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
