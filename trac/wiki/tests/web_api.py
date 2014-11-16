# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 Edgewall Software
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
from cStringIO import StringIO

import trac.tests.compat
from trac.mimeview.patch import PatchRenderer
from trac.test import EnvironmentStub, Mock
from trac.web.api import RequestDone
from trac.web.href import Href
from trac.wiki.web_api import WikiRenderer


class WikiRendererTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.mod = WikiRenderer(self.env)

    def test_load_stylesheet(self):
        buf = StringIO()
        def send(data):
            buf.write(data)
            raise RequestDone

        text = """\
{{{#!text/x-diff
--- a/file.txt  2014-11-13 01:16:06 +0000
+++ b/file.txt  2014-11-13 01:16:06 +0000
@@ -1 +1 @@
-old line
+new line
}}}
"""
        req = Mock(method='POST', path_info='/wiki_render', session={},
                   args={'id': 'WikiStart', 'text': text},
                   abs_href=Href('http://example.com/'), href=Href('/'),
                   chrome={'links': {}, 'scripts': []}, perm=None,
                   authname=None, tz=None, send=send)
        self.assertTrue(self.mod.match_request(req))
        try:
            self.mod.process_request(req)
            self.fail('RequestDone not raised')
        except RequestDone:
            output = buf.getvalue()
            self.assertIn('<div class="code"><pre>', output)
            self.assertIn('jQuery.loadStyleSheet("'
                          '/chrome/common/css/diff.css"', output)


def suite():
    return unittest.makeSuite(WikiRendererTestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
