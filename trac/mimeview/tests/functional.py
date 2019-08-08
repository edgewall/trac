#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

from __future__ import absolute_import

import unittest
try:
    import pygments
    have_pygments = True
except ImportError:
    have_pygments = False

from trac.tests.functional import FunctionalTwillTestCaseSetup, tc


class TestSyntaxHighlightingPreferences(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Set preferences for syntax highlighting."""
        self._tester.go_to_preferences("Syntax Highlighting")
        tc.find('<option selected="selected" value="trac">')
        tc.formvalue('userprefs', 'style', 'Emacs')
        tc.submit()
        tc.find('<option selected="selected" value="emacs">')


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional
        suite = trac.tests.functional.functionalSuite()
    if have_pygments:
        suite.addTest(TestSyntaxHighlightingPreferences())
    return suite


test_suite = functionalSuite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
