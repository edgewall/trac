# -*- coding: iso-8859-1 -*-
#
# Copyright (C) 2006 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.

import unittest

from trac.mimeview.api import _html_splitlines


class MimeviewTestCase(unittest.TestCase):

    def test_html_splitlines_without_markup(self):
        lines = ['line 1', 'line 2']
        self.assertEqual(lines, list(_html_splitlines(lines)))

    def test_html_splitlines_with_markup(self):
        lines = ['<p><b>Hi', 'How are you</b></p>']
        result = list(_html_splitlines(lines))
        self.assertEqual('<p><b>Hi</b></p>', result[0])
        self.assertEqual('<p><b>How are you</b></p>', result[1])

    def test_html_splitlines_with_multiline(self):
        """
        Regression test for http://projects.edgewall.com/trac/ticket/2655
        """
        lines = ['<span class="p_tripledouble">"""',
                'a <a href="http://google.com">http://google.com</a>/',
                'Test', 'Test', '"""</span>']
        result = list(_html_splitlines(lines))
        self.assertEqual('<span class="p_tripledouble">"""</span>', result[0])
        self.assertEqual('<span class="p_tripledouble">a '
                         '<a href="http://google.com">http://google.com</a>/'
                         '</span>', result[1])
        self.assertEqual('<span class="p_tripledouble">Test</span>', result[2])
        self.assertEqual('<span class="p_tripledouble">Test</span>', result[3])
        self.assertEqual('<span class="p_tripledouble">"""</span>', result[4])


def suite():
    return unittest.makeSuite(MimeviewTestCase, 'test')

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
