# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2020 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import os
import re
import sys
import textwrap
import unittest
from pkg_resources import parse_version

from trac.mimeview.api import LineNumberAnnotator, Mimeview
from trac.test import EnvironmentStub, MockRequest
from trac.util import get_pkginfo
from trac.web.chrome import Chrome, web_context
from trac.wiki.formatter import format_to_html

try:
    import pygments
except ImportError:
    pygments = None
else:
    from trac.mimeview.pygments import PygmentsRenderer
    pygments_version = parse_version(get_pkginfo(pygments).get('version'))


class PygmentsRendererTestCase(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.env = EnvironmentStub(enable=[Chrome, LineNumberAnnotator,
                                           PygmentsRenderer])
        self.pygments = Mimeview(self.env).renderers[0]
        self.req = MockRequest(self.env)
        self.context = web_context(self.req)
        self.pygments_html = {}
        testcase = []
        html_file = os.path.join(os.path.dirname(__file__), 'pygments.data')
        with open(html_file, 'r', encoding='utf-8') as f:
            for line in f.readlines():
                if line.startswith('#'):
                    self.pygments_html[line[1:].strip()] = testcase = []
                else:
                    testcase.append(line.rstrip())

    @property
    def python_mimetype(self):
        if pygments_version >= parse_version('2.5.0'):
            return 'text/x-python2'
        else:
            return 'text/x-python'

    def _expected(self, expected_id):
        return self.pygments_html[expected_id]

    def _test(self, expected_id, result):
        expected = self._expected(expected_id)
        result = str(result).splitlines()
        # from pprint import pformat
        # print("\nE: " + expected_id + "\n" + pformat(expected))
        # print("\nR: " + expected_id + "\n" + pformat(result))
        def split(s):
            sp = re.split('(>)', s)
            return [a + b for (a, b) in zip(sp[0::2], sp[1::2])]
        for exp, res in zip(expected, result):
            self.assertEqual(split(exp), split(res))
        self.assertEqual(len(expected), len(result))

    def test_python_hello(self):
        """
        Simple Python highlighting with Pygments (direct)
        """
        result = self.pygments.render(self.context, self.python_mimetype,
                                      textwrap.dedent("""\
            def hello():
                    return "Hello World!"
            """))
        self.assertTrue(result)
        if pygments_version < parse_version('2.1'):
            self._test('python_hello', result)
        else:
            self._test('python_hello_pygments_2.1plus', result)

    def test_python_hello_mimeview(self):
        """
        Simple Python highlighting with Pygments (through Mimeview.render)
        """
        result = Mimeview(self.env).render(self.context, self.python_mimetype,
                                           textwrap.dedent("""
            def hello():
                    return "Hello World!"
            """))
        self.assertTrue(result)
        if pygments_version < parse_version('2.1'):
            self._test('python_hello_mimeview', result)
        else:
            self._test('python_hello_mimeview_pygments_2.1plus', result)

    def test_python_with_lineno(self):
        result = format_to_html(self.env, self.context, textwrap.dedent("""\
            {{{#!%s lineno
            print 'this is a python sample'
            a = b+3
            z = "this is a string"
            print 'this is the end of the python sample'
            }}}
            """ % self.python_mimetype))
        self.assertTrue(result)
        if pygments_version < parse_version('2.1'):
            self._test('python_with_lineno_1', result)
        else:
            self._test('python_with_lineno_1_pygments_2.1plus', result)

        result = format_to_html(self.env, self.context, textwrap.dedent("""\
            {{{#!%s lineno=3
            print 'this is a python sample'
            a = b+3
            z = "this is a string"
            print 'this is the end of the python sample'
            }}}
            """ % self.python_mimetype))
        self.assertTrue(result)
        if pygments_version < parse_version('2.1'):
            self._test('python_with_lineno_2', result)
        else:
            self._test('python_with_lineno_2_pygments_2.1plus', result)

    def test_python_with_lineno_and_markups(self):
        """Python highlighting with Pygments and lineno annotator
        """
        result = format_to_html(self.env, self.context, textwrap.dedent("""\
            {{{#!%s lineno=3 id=b marks=4-5
            print 'this is a python sample'
            a = b+3
            z = "this is a string"
            print 'this is the end of the python sample'
            }}}
            """ % self.python_mimetype))
        self.assertTrue(result)
        if pygments_version < parse_version('2.1'):
            self._test('python_with_lineno_and_markups', result)
        else:
            self._test('python_with_lineno_and_markups_pygments_2.1plus',
                       result)

    def test_python_with_invalid_arguments(self):
        result = format_to_html(self.env, self.context, textwrap.dedent("""\
            {{{#!%s lineno=-10
            print 'this is a python sample'
            a = b+3
            z = "this is a string"
            print 'this is the end of the python sample'
            }}}
            """ % self.python_mimetype))
        self.assertTrue(result)
        if pygments_version < parse_version('2.1'):
            self._test('python_with_invalid_arguments_1', result)
        else:
            self._test('python_with_invalid_arguments_1_pygments_2.1plus',
                       result)

        result = format_to_html(self.env, self.context, textwrap.dedent("""\
            {{{#!%s lineno=a id=d marks=a-b
            print 'this is a python sample'
            a = b+3
            z = "this is a string"
            print 'this is the end of the python sample'
            }}}
            """ % self.python_mimetype))
        self.assertTrue(result)
        if pygments_version < parse_version('2.1'):
            self._test('python_with_invalid_arguments_2', result)
        else:
            self._test('python_with_invalid_arguments_2_pygments_2.1plus',
                       result)

    def test_pygments_lexer_options(self):
        self.env.config.set('pygments-lexer',
                            'php.startinline', True)
        self.env.config.set('pygments-lexer',
                            'php.funcnamehighlighting', False)
        result = format_to_html(self.env, self.context, textwrap.dedent("""
            {{{#!php
            if (class_exists('MyClass')) {
                $myclass = new MyClass();
            }
            }}}
            """))
        self.assertTrue(result)
        self._test('pygments_lexer_options', result)

    def test_pygments_lexer_arguments(self):
        result = format_to_html(self.env, self.context, textwrap.dedent("""
            {{{#!php startinline=True funcnamehighlighting=False
            if (class_exists('MyClass')) {
                $myclass = new MyClass();
            }
            }}}
            """))
        self.assertTrue(result)
        self._test('pygments_lexer_arguments', result)

    def test_pygments_lexer_arguments_override_options(self):
        self.env.config.set('pygments-lexer',
                            'php.startinline', True)
        self.env.config.set('pygments-lexer',
                            'php.funcnamehighlighting', False)
        result = format_to_html(self.env, self.context, textwrap.dedent("""
            {{{#!php funcnamehighlighting=True
            if (class_exists('MyClass')) {
                $myclass = new MyClass();
            }
            }}}
            """))
        self.assertTrue(result)
        self._test('pygments_lexer_arguments_override_options', result)

    def test_newline_content(self):
        """Regression test for newline-stripping behavior in Pygments.

        https://trac.edgewall.org/ticket/7705
        """
        result = self.pygments.render(self.context, self.python_mimetype,
                                      '\n\n\n\n')
        self.assertTrue(result)
        t = result

        self.assertEqual("\n\n\n\n", t)

    def test_empty_content(self):
        """
        A '\n' token is generated for an empty file, so we have to bypass
        pygments when rendering empty files.
        """
        result = self.pygments.render(self.context, self.python_mimetype, '')
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


def test_suite():
    suite = unittest.TestSuite()
    if pygments:
        suite.addTest(unittest.makeSuite(PygmentsRendererTestCase))
    else:
        print('SKIP: mimeview/tests/pygments (no pygments installed)')
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
