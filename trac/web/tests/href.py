# -*- coding: utf-8 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

from trac.web import href

import sys
import unittest


def suite():
    try:
        from doctest import DocTestSuite
        return DocTestSuite(href)
    except ImportError:
        print>>sys.stderr, "DocTestSuite not available, skipping href tests"
        return unittest.TestSuite()

if __name__ == '__main__':
    runner = unittest.TextTestRunner()
    runner.run(suite())
