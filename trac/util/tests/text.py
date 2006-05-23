# -*- encoding: utf-8 -*-

import doctest
import unittest

from trac.util.text import to_unicode

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

    def test_from_exception_using_unicode_args(self):
        u = u'\uB144'
        try:
            raise ValueError, '%s is not a number.' % u
        except ValueError, e:
            self.assertEquals(u'\uB144 is not a number.', to_unicode(e))

    def test_from_exception_using_str_args(self):
        u = u'Das Ger\xe4t oder die Ressource ist belegt'
        try:
            raise ValueError, u.encode('utf-8')
        except ValueError, e:
            self.assertEquals(u, to_unicode(e))

    def test_from_exception_using_str(self):
        class PermissionError(StandardError):
            def __str__(self):
                return u'acc\xe8s interdit'
        try:
            raise PermissionError()
        except PermissionError, e:
            self.assertEquals(u'acc\xe8s interdit', to_unicode(e))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ToUnicodeTestCase, 'test'))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
