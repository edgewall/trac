import os
import StringIO
import unittest

from Wiki import Formatter

class WikiTestCase(unittest.TestCase):
    def __init__(self, input, correct):
        unittest.TestCase.__init__(self, 'test')
        self.input = input
        self.correct = correct
    
    def test(self):
        """Testing WikiFormatter"""
        import Href
        class Environment:
            def __init__(self):
                self.href = Href.Href('/')
                
        out = StringIO.StringIO()
        Formatter(None, Environment()).format(self.input, out)
        if out.getvalue() != self.correct:
            print "'%s' != '%s'" % (out.getvalue(), correct)
            assert correct == out.getvalue()

def suite():
    suite = unittest.TestSuite()
    data = open(os.path.join(os.path.split(__file__)[0],
                             'wiki-tests.txt'), 'r').read()
    tests = data.split('=' * 30 + '\n')
    for test in tests:
        input, correct = test.split('-' * 30 + '\n')
        suite.addTest(WikiTestCase(input, correct))
    return suite
    
