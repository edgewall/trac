#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Edgewall Software
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


class TestSyntaxHighlightingPreferences(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Set preferences for syntax highlighting."""
        self._tester.go_to_preferences("Syntax Highlighting")
        tc.find('<option value="trac" selected="selected">')
        tc.formvalue('userprefs', 'style', 'Emacs')
        tc.submit()
        tc.find('<option value="emacs" selected="selected">')


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional
        suite = trac.tests.functional.functionalSuite()
    suite.addTest(TestSyntaxHighlightingPreferences())
    return suite


suite = functionalSuite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
