# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2018 Edgewall Software
# Copyright (C) 2006 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import doctest
import unittest

from trac.core import TracError
from trac.util import presentation


class ToJsonTestCase(unittest.TestCase):

    def test_simple_types(self):
        self.assertEqual('42', presentation.to_json(42))
        self.assertEqual('123.456', presentation.to_json(123.456))
        self.assertEqual('true', presentation.to_json(True))
        self.assertEqual('false', presentation.to_json(False))
        self.assertEqual('null', presentation.to_json(None))
        self.assertEqual('"String"', presentation.to_json('String'))
        self.assertEqual(r'"a \" quote"', presentation.to_json('a " quote'))
        self.assertEqual('''"a ' single quote"''',
                         presentation.to_json("a ' single quote"))
        self.assertEqual(r'"\u003cb\u003e\u0026\u003c/b\u003e"',
                         presentation.to_json('<b>&</b>'))
        self.assertEqual(r'"\n\r\u2028\u2029"',
                         presentation.to_json(u'\x0a\x0d\u2028\u2029'))

    def test_compound_types(self):
        self.assertEqual('[1,2,[true,false]]',
                         presentation.to_json([1, 2, [True, False]]))
        self.assertEqual(r'{"one":1,"other":[null,0],'
                         r'''"three":[3,"\u0026\u003c\u003e'"],'''
                         r'"two":2,"\u2028\n":"\u2029\r"}',
                         presentation.to_json({"one": 1, "two": 2,
                                               "other": [None, 0],
                                               "three": [3, "&<>'"],
                                               u"\u2028\x0a": u"\u2029\x0d"}))


class PaginatorTestCase(unittest.TestCase):

    def test_paginate(self):
        """List of objects is paginated."""
        items = range(0, 20)
        paginator = presentation.Paginator(items, 1)

        self.assertEqual(1, paginator.page)
        self.assertEqual(10, paginator.max_per_page)
        self.assertEqual(20, paginator.num_items)
        self.assertEqual(2, paginator.num_pages)
        self.assertEqual((10, 20), paginator.span)

    def test_page_out_of_range_raises_exception(self):
        """Out of range value for page raises a `TracError`."""
        items = range(0, 20)

        self.assertRaises(TracError, presentation.Paginator, items, 2)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(doctest.DocTestSuite(presentation))
    suite.addTest(unittest.makeSuite(ToJsonTestCase))
    suite.addTest(unittest.makeSuite(PaginatorTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
