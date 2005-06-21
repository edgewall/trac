
import os
import inspect
import StringIO
import unittest

from trac.core import *
from trac.wiki.formatter import Formatter
from trac.wiki.api import IWikiMacroProvider


class DummyHelloWorldMacro(Component):
    """
    A dummy macro used by the unit test. We need to supply our own macro
    because the real HelloWorld-macro can not be loaded using our
    'fake' environment.
    """
    implements(IWikiMacroProvider)

    def get_macros(self):
        yield 'HelloWorld'

    def get_macro_description(self, name):
        return inspect.getdoc(MacroListMacro)

    def render_macro(self, req, name, content):
        return 'Hello World, args = ' + content


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
