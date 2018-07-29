# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os
import unittest

from genshi.core import Stream
from genshi.input import HTMLParser, XML

from trac.mimeview.api import Mimeview
from trac.mimeview.patch import PatchRenderer
from trac.test import EnvironmentStub, MockRequest
from trac.web.chrome import Chrome, web_context


class PatchRendererTestCase(unittest.TestCase):

    def setUp(self):
        env = EnvironmentStub(enable=[Chrome, PatchRenderer])
        req = MockRequest(env)
        self.context = web_context(req)
        self.patch = Mimeview(env).renderers[0]
        patch_html = open(os.path.join(os.path.split(__file__)[0],
                                       'patch.html'))
        self.patch_html = Stream(list(HTMLParser(patch_html, encoding='utf-8')))

    def _expected(self, expected_id):
        return self.patch_html.select('//div[@id="%s"]/div' % expected_id)

    def _test(self, expected_id, result):
        expected = self._expected(expected_id).render(encoding='utf-8')
        result = XML(result.render(encoding='utf-8')).render(encoding='utf-8')
        expected, result = expected.splitlines(), result.splitlines()
        for exp, res in zip(expected, result):
            self.assertEqual(exp, res)
        self.assertEqual(len(expected), len(result))

    def test_simple(self):
        """
        Simple patch rendering
        """
        result = self.patch.render(self.context, None, """
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

    def test_no_newline_in_base(self):
        """
        Simple regression test for #4027 ("No newline at end of file")
        """
        result = self.patch.render(self.context, None, """
--- nonewline   2006-10-27 08:36:48.453125000 +0200
+++ newline     2006-10-27 08:36:57.187500000 +0200
@@ -1 +1 @@
-ONELINE
\ No newline at end of file
+ONELINE
""")
        self.assertTrue(result)
        self._test('no_newline_in_base', result)

    def test_no_newline_in_changed(self):
        """
        Another simple regression test for #4027 ("No newline at end of file")
        """
        result = self.patch.render(self.context, None, """
--- newline     2006-10-27 08:36:57.187500000 +0200
+++ nonewline   2006-10-27 08:36:48.453125000 +0200
@@ -1 +1 @@
-ONELINE
+ONELINE
\ No newline at end of file
""")
        self.assertTrue(result)
        self._test('no_newline_in_changed', result)
    def test_diff_to_hdf_expandtabs(self):
        """Regression test related to #4557"""
        changes = self.patch._diff_to_hdf(
            ['--- hello.c 1',
             '+++ hello.c 2',
             '@@ -1 +1 @@',
             '-aa\tb',
             '+aaxb'], 8)
        self.assertEqual('aa<del>&nbsp; &nbsp; &nbsp; </del>b',
                         str(changes[0]['diffs'][0][0]['base']['lines'][0]))
        self.assertEqual('aa<ins>x</ins>b',
                         str(changes[0]['diffs'][0][0]['changed']['lines'][0]))

    def test_diff_to_hdf_leading_ws(self):
        """Regression test related to #5795"""
        changes = self.patch._diff_to_hdf(
            ['--- hello.c 1',
             '+++ hello.c 2',
             '@@ -1 +1 @@',
             '-*a',
             '+ *a'], 8)
        self.assertEqual('<del></del>*a',
                         str(changes[0]['diffs'][0][0]['base']['lines'][0]))
        self.assertEqual('<ins>&nbsp;</ins>*a',
                         str(changes[0]['diffs'][0][0]['changed']['lines'][0]))

    def test_range_information_with_no_lines(self):
        result = self.patch.render(self.context, None, """
Index: filename.txt
===================================================================
--- filename.txt
+++ filename.txt
@@ -14,7 +14,7 @@
""")
        self.assertTrue(result)
        self._test('range_information_with_no_lines', result)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(PatchRendererTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
