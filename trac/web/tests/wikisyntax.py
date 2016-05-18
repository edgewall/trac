# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2013 Edgewall Software
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

from trac.wiki.tests import formatter

TEST_CASES = """
============================== htdocs: links resolver
htdocs:release-1.0.tar.gz

[htdocs:release-1.0.tar.gz Release 1.0]
------------------------------
<p>
<a href="/chrome/site/release-1.0.tar.gz">htdocs:release-1.0.tar.gz</a>
</p>
<p>
<a href="/chrome/site/release-1.0.tar.gz">Release 1.0</a>
</p>
------------------------------
"""

def test_suite():
    return formatter.test_suite(TEST_CASES, file=__file__)

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
