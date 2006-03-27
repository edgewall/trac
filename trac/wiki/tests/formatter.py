import os
import inspect
import StringIO
import unittest

from trac.core import *
from trac.test import Mock
from trac.wiki.formatter import Formatter, OneLinerFormatter
from trac.wiki.macros import WikiMacroBase


class HelloWorldMacro(WikiMacroBase):
    """
    A dummy macro used by the unit test. We need to supply our own macro
    because the real HelloWorld-macro can not be loaded using our
    'fake' environment.
    """

    def render_macro(self, req, name, content):
        return 'Hello World, args = ' + content

class DivHelloWorldMacro(WikiMacroBase):
    """
    A dummy macro returning a div block, used by the unit test.
    We need to supply our own macro because the real HelloWorld-macro
    can not be loaded using our 'fake' environment.
    """

    def render_macro(self, req, name, content):
        return '<div>Hello World, args = %s</div>' % content


class WikiTestCase(unittest.TestCase):

    def __init__(self, input, correct, file, line):
        unittest.TestCase.__init__(self, 'test')
        self.input = input
        self.correct = correct
        self.file = file
        self.line = line
    
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
                self.path = ''
                # -- intertrac support
                self.siblings = {}
                self.config.set('intertrac', 'trac.title', "Trac's Trac")
                self.config.set('intertrac', 'trac.url',
                                "http://projects.edgewall.com/trac")
                self.config.set('intertrac', 't', 'trac')
            def component_activated(self, component):
                component.env = self
                component.config = self.config
                component.log = self.log
            def get_db_cnx(self):
                return db
            def get_repository(self):
                return Mock(get_changeset=lambda x: self._get_changeset(x))
            def _get_changeset(self, x):
                raise TracError("No changeset")

        # Load all the components that provide IWikiSyntaxProvider
        # implementations that are tested. Ideally those should be tested
        # in separate unit tests.
        import trac.versioncontrol.web_ui.browser
        import trac.versioncontrol.web_ui.changeset
        import trac.ticket.query
        import trac.ticket.report
        import trac.ticket.roadmap
        import trac.Search

        env = DummyEnvironment()

        out = StringIO.StringIO()
        formatter = self.formatter(env)
        formatter.format(self.input, out)
        v = out.getvalue().replace('\r','')
        try:
            self.assertEquals(self.correct, v)
        except AssertionError, e:
            raise AssertionError('%s\n\n%s:%s: for the input '
                                 '(formatter flavor was "%s")' \
                                 % (str(e), self.file, self.line,
                                    formatter.flavor))
        
    def formatter(self, env):
        return Formatter(env)


class OneLinerTestCase(WikiTestCase):
    def formatter(self, env):
        return OneLinerFormatter(env)


def suite():
    suite = unittest.TestSuite()
    file = os.path.join(os.path.split(__file__)[0], 'wiki-tests.txt')
    data = open(file, 'r').read().decode('utf-8')
    tests = data.split('=' * 30 + '\n')
    line = 1
    for test in tests:
        input, page, oneliner = test.split('-' * 30 + '\n')
        suite.addTest(WikiTestCase(input, page, file, line))
        if oneliner:
            suite.addTest(OneLinerTestCase(input, oneliner[:-1], file, line))
        line += len(test.split('\n'))
    return suite

if __name__ == '__main__':
    runner = unittest.TextTestRunner()
    runner.run(suite())
