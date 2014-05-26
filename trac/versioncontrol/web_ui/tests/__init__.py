# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2014 Edgewall Software
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

from trac.versioncontrol.web_ui.tests import browser, changeset, log, \
                                             wikisyntax


def suite():
    suite = unittest.TestSuite()
    suite.addTest(browser.suite())
    suite.addTest(changeset.suite())
    suite.addTest(log.suite())
    suite.addTest(wikisyntax.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
