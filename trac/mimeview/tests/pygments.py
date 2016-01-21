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

from __future__ import absolute_import

import os
import unittest
from pkg_resources import parse_version

from genshi.core import Stream, TEXT
from genshi.input import HTMLParser

try:
    import pygments
    have_pygments = True
except ImportError:
    have_pygments = False

import trac.tests.compat
from trac.mimeview.api import Mimeview
if have_pygments:
    from trac.mimeview.pygments import PygmentsRenderer
from trac.test import EnvironmentStub, Mock
from trac.util import get_pkginfo
from trac.web.chrome import Chrome, web_context
from trac.web.href import Href


if have_pygments:
    pygments_version = parse_version(get_pkginfo(pygments).get('version'))


class PygmentsRendererTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=[Chrome, PygmentsRenderer])
        self.pygments = Mimeview(self.env).renderers[0]
        self.req = Mock(base_path='', chrome={}, args={},
                        abs_href=Href('/'), href=Href('/'),
                        session={}, perm=None, authname=None, tz=None)
        self.context = web_context(self.req)
        pygments_html = open(os.path.join(os.path.split(__file__)[0],
                                       'pygments.html'))
        self.pygments_html = Stream(list(HTMLParser(pygments_html, encoding='utf-8')))

    def _expected(self, expected_id):
        return self.pygments_html.select(
            '//div[@id="%s"]/*|//div[@id="%s"]/text())' %
            (expected_id, expected_id))

    def _test(self, expected_id, result):
        expected = str(self._expected(expected_id))
        result = str(result)
        #print "\nE: " + repr(expected)
        #print "\nR: " + repr(result)
        expected, result = expected.splitlines(), result.splitlines()
        for exp, res in zip(expected, result):
            self.assertEqual(exp, res)
        self.assertEqual(len(expected), len(result))

    def test_python_hello(self):
        """
        Simple Python highlighting with Pygments (direct)
        """
        result = self.pygments.render(self.context, 'text/x-python', """
def hello():
        return "Hello World!"
""")
        self.assertTrue(result)
        if pygments_version < parse_version('2.1'):
            self._test('python_hello', result)
        else:
            self._test('python_hello_pygments_2.1plus', result)

    def test_python_hello_mimeview(self):
        """
        Simple Python highlighting with Pygments (through Mimeview.render)
        """
        result = Mimeview(self.env).render(self.context, 'text/x-python', """
def hello():
        return "Hello World!"
""")
        self.assertTrue(result)
        if pygments_version < parse_version('2.1'):
            self._test('python_hello_mimeview', result)
        else:
            self._test('python_hello_mimeview_pygments_2.1plus', result)

    def test_newline_content(self):
        """
        The behavior of Pygments changed post-Pygments 0.11.1, and now
        contains all four newlines.  In Pygments 0.11.1 and prior, it only
        has three since stripnl defaults to True.

        See http://trac.edgewall.org/ticket/7705.
        """
        from pkg_resources import parse_version, get_distribution

        result = self.pygments.render(self.context, 'text/x-python', '\n\n\n\n')
        self.assertTrue(result)
        t = "".join([r[1] for r in result if r[0] is TEXT])

        if parse_version(pygments.__version__) > parse_version('0.11.1') \
           or pygments.__version__ == '0.11.1' and 'dev' in \
           get_distribution('Pygments').version:
            self.assertEqual("\n\n\n\n", t)
        else:
            self.assertEqual("\n\n\n", t)

    def test_empty_content(self):
        """
        A '\n' token is generated for an empty file, so we have to bypass
        pygments when rendering empty files.
        """
        result = self.pygments.render(self.context, 'text/x-python', '')
        self.assertIsNone(result)

    def test_extra_mimetypes(self):
        """
        The text/x-ini mimetype is normally not known by Trac, but
        Pygments supports it.
        """
        mimeview = Mimeview(self.env)
        self.assertIn(mimeview.get_mimetype('file.ini'),
                      ('text/x-ini; charset=utf-8',
                       'text/inf; charset=utf-8'))  # Pygment 2.1+
        self.assertIn(mimeview.get_mimetype('file.cfg'),
                      ('text/x-ini; charset=utf-8',
                       'text/inf; charset=utf-8'))  # Pygment 2.1+
        self.assertEqual('text/x-ini; charset=utf-8',
                         mimeview.get_mimetype('file.text/x-ini'))

def suite():
    suite = unittest.TestSuite()
    if have_pygments:
        suite.addTest(unittest.makeSuite(PygmentsRendererTestCase))
    else:
        print 'SKIP: mimeview/tests/pygments (no pygments installed)'
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
