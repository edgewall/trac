# -*- coding: utf-8 -*-
#
# Copyright (C) 2006 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import htmlentitydefs
import os
import re
import unittest

from genshi.core import Stream
from genshi.input import HTMLParser, XML

from trac.test import EnvironmentStub, Mock

from trac.mimeview.api import Mimeview
from trac.mimeview.patch import PatchRenderer
from trac.web.chrome import Chrome
from trac.web.href import Href


class PatchRendererTestCase(unittest.TestCase):

    def setUp(self):
        env = EnvironmentStub(enable=[Chrome, PatchRenderer])
        self.patch = Mimeview(env).renderers[0]
        self.req = Mock(base_path='',environ={},
                        abs_href=Href('/'), href=Href('/'),
                        perm=None, authname=None, tz=None)
        patch_html = open(os.path.join(os.path.split(__file__)[0],
                                       'patch.html'))
        self.patch_html = Stream(list(HTMLParser(patch_html)))

    def _expected(self, expected_id):
        return self.patch_html.select('//div[@id="%s"]/div' % expected_id)

    def _test(self, expected_id, result):
        expected = str(self._expected(expected_id)).splitlines()
        result = str(XML(result)).splitlines()
        for exp, res in zip(expected, result):
            self.assertEquals(exp, res)
        self.assertEquals(len(expected), len(result))

    def test_simple(self):
        """
        Simple patch rendering
        """
        result = self.patch.render(self.req, None, """
--- README.orig 2006-10-27 14:42:04.062500000 +0200
+++ README      2006-10-27 14:42:28.125000000 +0200
@@ -1,5 +1,5 @@
 ----
-base
-base
-base
+be
+the base
+base modified
 .
""")
        self.assertTrue(result)
        self._test('simple', result)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(PatchRendererTestCase, 'test'))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
