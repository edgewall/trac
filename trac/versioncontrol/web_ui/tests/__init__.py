# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

import unittest

from trac.versioncontrol.web_ui.tests import browser, changeset, log, util, \
                                             wikisyntax


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(browser.test_suite())
    suite.addTest(changeset.test_suite())
    suite.addTest(log.test_suite())
    suite.addTest(util.test_suite())
    suite.addTest(wikisyntax.test_suite())
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
