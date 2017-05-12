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
from xml.etree import ElementTree

from trac.test import EnvironmentStub, MockRequest
from trac.mimeview.txtl import TextileRenderer, has_textile
from trac.web.chrome import web_context


class TextileRendererTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=[TextileRenderer])
        self.env.config.set('wiki', 'safe_schemes', 'https, http, data')
        self.renderer = TextileRenderer(self.env)
        self.req = MockRequest(self.env)
        self.context = web_context(self.req)

    def tearDown(self):
        self.env.reset_db()

    def _render(self, text):
        result = self.renderer.render(self.context, 'textile', text)
        self.assertEqual(unicode, type(result))
        return result

    def _parse_xml(self, source):
        return ElementTree.fromstring(source.encode('utf-8'))

    def test_image(self):
        result = self._render(u"""\
!https://example.org/foo.png! uníćode
!//example.net/foo.png!       uníćode
!/path/to/foo.png!            uníćode
!foo.png!                     uníćode
!data:image/png,foo!          uníćode
""")
        tree = self._parse_xml(result)
        elements = tree.findall('img')
        self.assertEqual(elements[0].get('src'), 'https://example.org/foo.png')
        self.assertEqual(elements[0].get('crossorigin'), 'anonymous')
        self.assertEqual(elements[1].get('src'), '//example.net/foo.png')
        self.assertEqual(elements[1].get('crossorigin'), 'anonymous')
        self.assertEqual(elements[2].get('src'), '/path/to/foo.png')
        self.assertEqual(elements[2].get('crossorigin'), None)
        self.assertEqual(elements[3].get('src'), 'foo.png')
        self.assertEqual(elements[3].get('crossorigin'), None)
        self.assertIn(elements[4].get('src'), ['data:image/png,foo', '#'])
        self.assertEqual(elements[4].get('crossorigin'), None)

    def test_style(self):
        result = self._render(u"""\
*{background:url(https://example.org/foo.png)}uníćode*
*{background:url(//example.net/foo.png)      }uníćode*
*{background:url(/path/to/foo.png)           }uníćode*
*{background:url(./foo.png)                  }uníćode*
*{background:url(foo.png)                    }uníćode*
*{background:url(data:image/png,foo)         }uníćode*
""")
        self.assertNotIn('url(https://example.org/foo.png)', result)
        self.assertNotIn('url(//example.net/foo.png)', result)
        self.assertIn('url(/path/to/foo.png)', result)
        self.assertIn('url(./foo.png)', result)
        self.assertIn('url(foo.png)', result)
        self.assertIn('url(data:image/png,foo)', result)

    def test_html(self):
        result = self._render(u"""\
<a href="ftp://example.org/">unsafe</a>
<img src="//example.org/foo.png" />
<span style="background-image:url(http://example.org/foo.png)">unsafe</span>
""")
        self.assertNotIn('href="ftp://', result)
        self.assertNotIn('<img src="//example.org/foo.png" />', result)
        self.assertIn('<img src="//example.org/foo.png" '
                      'crossorigin="anonymous" />', result)
        self.assertNotIn('url(http://example.org/foo.png)', result)
        self.assertIn('<span>unsafe</span>', result)


def test_suite():
    suite = unittest.TestSuite()
    if has_textile:
        suite.addTest(unittest.makeSuite(TextileRendererTestCase))
    else:
        print('SKIP: mimeview/tests/txtl (no textile installed)')
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
