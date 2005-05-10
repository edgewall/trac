from trac.wiki.formatter import Formatter

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

        # Environment stub
        from trac.core import ComponentManager
        from trac.config import Configuration
        from trac.log import logger_factory
        from trac.test import InMemoryDatabase
        from trac.web.href import Href

        db = InMemoryDatabase()

        class DummyEnvironment(ComponentManager):
            def __init__(self):
                ComponentManager.__init__(self)
                self.log = logger_factory('null')
                self.config = Configuration(None)
                self.href = Href('/')
                self.abs_href = Href('http://www.example.com/')
                self._wiki_pages = {}
                self.path = ''
            def component_activated(self, component):
                component.env = self
                component.config = self.config
                component.log = self.log
            def get_db_cnx(self):
                return db

        # Provide a test mime viewer
        from trac.core import Component, implements
        from trac.mimeview.api import IHTMLPreviewRenderer
        class TestRenderer(Component):
            implements(IHTMLPreviewRenderer)
            def get_quality_ratio(self, mimetype):
                if mimetype == 'application/x-test':
                    return 8
                return 0
            def render(self, req, mimetype, content, filename=None, rev=None):
                return '<pre>' + '\nTESTING: '.join(content.splitlines()) + \
                       '</pre>\n'

        env = DummyEnvironment()
        out = StringIO.StringIO()
        Formatter(env).format(self.input, out)
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
