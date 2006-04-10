# -*- encoding: utf-8 -*-

import doctest
import unittest

from trac.util import to_unicode

class ToUnicodeTestCase(unittest.TestCase):

    def test_explicit(self):
        uc = to_unicode('\xc3\xa7', 'utf-8')
        assert isinstance(uc, unicode)
        self.assertEquals(u'\xe7', uc)

    def test_explicit_lossy(self):
        uc = to_unicode('\xc3', 'utf-8')
        assert isinstance(uc, unicode)
        self.assertEquals(u'\ufffd', uc)

    def test_explicit_lossless(self):
        uc = to_unicode('\xc3', 'utf-8', lossy=False)
        assert isinstance(uc, unicode)
        self.assertEquals(u'\xc3', uc)

    def test_implicit(self):
        uc = to_unicode('\xc3\xa7')
        assert isinstance(uc, unicode)
        self.assertEquals(u'\xe7', uc)

#     Note: the following test depends on the locale.getpreferredencoding()
#
#     def test_implicit_lossy(self):
#         uc = to_unicode('\xc3')
#         assert isinstance(uc, unicode)
#         self.assertEquals(u'\xc3', uc)
        
    def test_implicit_lossless(self):
        uc = to_unicode('\xc3', None, lossy=False)
        assert isinstance(uc, unicode)
        self.assertEquals(u'\xc3', uc)

def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ToUnicodeTestCase, 'test'))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
