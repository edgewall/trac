import os
import StringIO
import unittest

from Diff import get_change_extent

class DiffTestCase(unittest.TestCase):
    
    def test_get_change_extent(self):
        """Testing get_change_extent()"""
        assert get_change_extent('xxx', 'xxx') == (3, 0)
        assert get_change_extent('', 'xxx') == (0, 0)
        assert get_change_extent('xxx', '') == (0, 0)
        assert get_change_extent('xxx', 'yyy') == (0, 0)
        assert get_change_extent('xxx', 'xyx') == (1, -1)
        assert get_change_extent('xxx', 'xyyyx') == (1, -1)
        assert get_change_extent('xy', 'xzz') == (1, 0)
        assert get_change_extent('xyx', 'xzzx') == (1, -1)
        assert get_change_extent('xzzx', 'xyx') == (1, -1)

def suite():
    return unittest.makeSuite(DiffTestCase, 'test')
