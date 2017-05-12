# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Edgewall Software
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

from trac.test import EnvironmentStub, MockRequest
from trac.mimeview.rst import ReStructuredTextRenderer, has_docutils
from trac.web.chrome import web_context


class ReStructuredTextRendererTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=[ReStructuredTextRenderer])
        self.renderer = ReStructuredTextRenderer(self.env)
        self.req = MockRequest(self.env)
        self.context = web_context(self.req)

    def tearDown(self):
        self.env.reset_db()

    def _render(self, text):
        return self.renderer.render(self.context, 'rst', text)

    _rst_text = """
{{{#!rst
`javascript link`_.
`call link`_.
`relative link`_.
`normal link`_.

.. _javascript link: javascript:alert(42)
.. _call link: call:01234567890
.. _relative link: /path/to/index.html
.. _normal link: https://example.org/
}}}
"""

    def test_safe_schemes(self):
        result = self._render(self._rst_text)
        self.assertNotIn(' href="javascript:alert(42)"', result)
        self.assertNotIn(' href="call:01234567890"', result)
        self.assertIn(' href="/path/to/index.html"', result)
        self.assertIn(' href="https://example.org/"', result)

    def test_call_in_safe_schemes(self):
        self.env.config.set('wiki', 'safe_schemes', 'call')
        result = self._render(self._rst_text)
        self.assertNotIn(' href="javascript:alert(42)"', result)
        self.assertIn(' href="call:01234567890"', result)
        self.assertIn(' href="/path/to/index.html"', result)
        self.assertNotIn(' href="https://example.org/"', result)

    def test_render_unsafe_content(self):
        self.env.config.set('wiki', 'render_unsafe_content', 'enabled')
        self.env.config.set('wiki', 'safe_schemes', '')
        result = self._render(self._rst_text)
        self.assertIn(' href="javascript:alert(42)"', result)
        self.assertIn(' href="call:01234567890"', result)
        self.assertIn(' href="/path/to/index.html"', result)
        self.assertIn(' href="https://example.org/"', result)

    def test_cross_origin_images(self):
        def test (directive):
            result = self._render("""
.. %(directive)s:: https://example.org/foo.png
   :alt:
.. %(directive)s:: //example.net/foo.png
   :alt:
.. %(directive)s:: /path/to/foo.png
   :alt:
.. %(directive)s:: ./foo.png
   :alt:
.. %(directive)s:: foo.png
   :alt:
.. %(directive)s:: data:image/png,foo
   :alt:
""" % {'directive': directive})
            self.assertIn('<img crossorigin="anonymous" alt="" '
                          'src="https://example.org/foo.png" />', result)
            self.assertIn('<img crossorigin="anonymous" alt="" '
                          'src="//example.net/foo.png" />', result)
            self.assertIn('<img alt="" src="/path/to/foo.png" />', result)
            self.assertIn('<img alt="" src="./foo.png" />', result)
            self.assertIn('<img alt="" src="foo.png" />', result)
            self.assertIn('<img alt="" src="data:image/png,foo" />', result)

        test('image')
        test('figure')


def test_suite():
    suite = unittest.TestSuite()
    if has_docutils:
        suite.addTest(unittest.makeSuite(ReStructuredTextRendererTestCase))
    else:
        print('SKIP: mimeview/tests/rst (no docutils installed)')
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
