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

import trac.tests.compat
from trac.mimeview.patch import PatchRenderer
from trac.test import EnvironmentStub, MockRequest
from trac.web.api import RequestDone
from trac.wiki.web_api import WikiRenderer


class WikiRendererTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.mod = WikiRenderer(self.env)

    def test_load_stylesheet(self):
        text = """\
{{{#!text/x-diff
--- a/file.txt  2014-11-13 01:16:06 +0000
+++ b/file.txt  2014-11-13 01:16:06 +0000
@@ -1 +1 @@
-old line
+new line
}}}
"""
        req = MockRequest(self.env, method='POST', path_info='/wiki_render',
                          args={'id': 'WikiStart', 'text': text})

        self.assertTrue(self.mod.match_request(req))
        try:
            self.mod.process_request(req)
            self.fail('RequestDone not raised')
        except RequestDone:
            output = req.response_sent.getvalue()
            self.assertIn('<div class="wiki-code">', output)
            self.assertIn('<table class="trac-diff inline"', output)
            self.assertIn('jQuery.loadStyleSheet("'
                          '/trac.cgi/chrome/common/css/diff.css"', output)


def test_suite():
    return unittest.makeSuite(WikiRendererTestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
