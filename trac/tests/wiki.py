from trac.WikiFormatter import Formatter

import os
import StringIO
import unittest


class WikiTestCase(unittest.TestCase):

    def __init__(self, input, correct):
        unittest.TestCase.__init__(self, 'test')
        self.input = input
        self.correct = correct
    
    def test(self):
        """Testing WikiFormatter"""
        from trac import Href, Mimeview, Logging
        class Environment:
            def __init__(self):
                self.log = Logging.logger_factory('null')
                self.get_config = lambda x,y,z=None: z
                self.href = Href.Href('/')
                self.abs_href = Href.Href('http://www.example.com/')
                self._wiki_pages = {}
                self.mimeview = Mimeview.Mimeview(self)
        class Cursor:
            def execute(self, *kwargs): pass
            def fetchone(self): return []
        class Connection:
            def cursor(self):
                return Cursor()

        out = StringIO.StringIO()
        Formatter(None, Environment(), Connection()).format(self.input, out)
        v = out.getvalue().replace('\r','')
        self.assertEquals(self.correct, v)

def suite():
    suite = unittest.TestSuite()
    data = open(os.path.join(os.path.split(__file__)[0],
                             'wiki-tests.txt'), 'r').read()
    tests = data.split('=' * 30 + '\n')
    for test in tests:
        input, correct = test.split('-' * 30 + '\n')
        suite.addTest(WikiTestCase(input, correct))
    return suite

if __name__ == '__main__':
    runner = unittest.TextTestRunner()
    runner.run(suite())
