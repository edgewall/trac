#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2016-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import unittest

from trac.tests.functional import FunctionalTwillTestCaseSetup, tc


class TestSearchFilterSelection(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Check persistence of search filters in session (#11292)."""
        filters = ['milestone', 'changeset', 'ticket', 'wiki']
        def setfilters(checked):
            for i, f in enumerate(filters):
                tc.formvalue('fullsearch', f, checked[i])
        def checkfilters(checked):
            for i, f in enumerate(filters):
                is_checked = r'id="%s"[^>]* checked="checked"' % f
                if checked[i]:
                    tc.find(is_checked)
                else:
                    tc.notfind(is_checked)
        self._tester.go_to_front()
        # First sequence:
        tc.follow('^Search')
        seq_a = [True, False, True, False]
        setfilters(seq_a)
        tc.formvalue('fullsearch', 'q', 'anything...')
        tc.submit()
        # In the result page, the filters checkboxes reflect what's
        # been selected
        checkfilters(seq_a)
        # Now, this selection also persists after resetting the search page
        tc.follow('^Search')
        checkfilters(seq_a)
        # Second sequence:
        seq_b = [False, True, False, True]
        setfilters(seq_b)
        tc.formvalue('fullsearch', 'q', 'anything...')
        tc.submit()
        checkfilters(seq_b)
        tc.follow('^Search')
        checkfilters(seq_b)


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional
        suite = trac.tests.functional.functionalSuite()
    suite.addTest(TestSearchFilterSelection())
    return suite

test_suite = functionalSuite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
