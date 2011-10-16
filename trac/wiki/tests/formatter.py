import difflib
import os
import re
import unittest
from datetime import datetime

from trac.core import *
from trac.mimeview import Context
from trac.test import Mock, MockPerm, EnvironmentStub
from trac.util.datefmt import utc
from trac.util.html import html
from trac.util.text import to_unicode
from trac.web.href import Href
from trac.wiki.api import IWikiSyntaxProvider
from trac.wiki.formatter import HtmlFormatter, InlineHtmlFormatter
from trac.wiki.macros import WikiMacroBase
from trac.wiki.model import WikiPage

# We need to supply our own macro because the real macros
# can not be loaded using our 'fake' environment.

class HelloWorldMacro(WikiMacroBase):
    """A dummy macro used by the unit test."""

    def expand_macro(self, formatter, name, content):
        return 'Hello World, args = ' + content

class DivHelloWorldMacro(WikiMacroBase):
    """A dummy macro returning a div block, used by the unit test."""

    def expand_macro(self, formatter, name, content):
        return '<div>Hello World, args = %s</div>' % content

class TableHelloWorldMacro(WikiMacroBase):
    """A dummy macro returning a table block, used by the unit test."""

    def expand_macro(self, formatter, name, content):
        return """
        <table><tr><th>Hello World</th><td>%s</td></tr></table>
        """ % content

class DivCodeMacro(WikiMacroBase):
    """A dummy macro returning a div block, used by the unit test."""

    def expand_macro(self, formatter, name, content):
        return '<div class="code">Hello World, args = %s</div>' % content

class DivCodeElementMacro(WikiMacroBase):
    """A dummy macro returning a Genshi Element, used by the unit test."""

    def expand_macro(self, formatter, name, content):
        return html.DIV('Hello World, args = ', content, class_="code")

class DivCodeStreamMacro(WikiMacroBase):
    """A dummy macro returning a Genshi Stream, used by the unit test."""

    def expand_macro(self, formatter, name, content):
        from genshi.template import MarkupTemplate
        tmpl = MarkupTemplate("""
        <div>Hello World, args = $args</div>
        """)
        return tmpl.generate(args=content)

class NoneMacro(WikiMacroBase):
    """A dummy macro returning `None`, used by the unit test."""

    def expand_macro(self, formatter, name, content):
        return None

class WikiProcessorSampleMacro(WikiMacroBase):
    def expand_macro(self, formatter, name, content, args):
        if args is None:
            return 'Called as a macro: ' + content
        else:
            return 'Called as a processor with params: <dl>%s</dl>' % \
                ''.join('<dt>%s</dt><dd>%s</dd>' % kv for kv in args.items()) \
                + content

class SampleResolver(Component):
    """A dummy macro returning a div block, used by the unit test."""

    implements(IWikiSyntaxProvider)

    def get_wiki_syntax(self):
        return []

    def get_link_resolvers(self):
        yield ('link', self._format_link)

    def _format_link(self, formatter, ns, target, label):
        kind, module = 'text', 'stuff'
        try:
            kind = int(target) % 2 and 'odd' or 'even'
            module = 'thing'
        except ValueError:
            pass
        return html.A(label, class_='%s resolver' % kind,
                      href=formatter.href(module, target))


class WikiTestCase(unittest.TestCase):

    generate_opts = {}

    def __init__(self, title, input, correct, file, line, setup=None,
                 teardown=None, context=None):
        unittest.TestCase.__init__(self, 'test')
        self.title = title
        self.input = input
        self.correct = correct
        self.file = file
        self.line = line
        self._setup = setup
        self._teardown = teardown

        req = Mock(href=Href('/'), abs_href=Href('http://www.example.com/'),
                   authname='anonymous', perm=MockPerm(), tz=None, args={})
        if context:
            if isinstance(context, tuple):
                context = Context.from_request(req, *context)
        else:
            context = Context.from_request(req, 'wiki', 'WikiStart')
        self.context = context

        all_test_components = [
                HelloWorldMacro, DivHelloWorldMacro, TableHelloWorldMacro, 
                DivCodeMacro, DivCodeElementMacro, DivCodeStreamMacro, 
                NoneMacro, WikiProcessorSampleMacro, SampleResolver]
        self.env = EnvironmentStub(enable=['trac.*'] + all_test_components)
        # -- macros support
        self.env.path = ''
        # -- intertrac support
        self.env.config.set('intertrac', 'trac.title', "Trac's Trac")
        self.env.config.set('intertrac', 'trac.url',
                            "http://trac.edgewall.org")
        self.env.config.set('intertrac', 't', 'trac')
        self.env.config.set('intertrac', 'th.title', "Trac Hacks")
        self.env.config.set('intertrac', 'th.url',
                            "http://trac-hacks.org")
        self.env.config.set('intertrac', 'th.compat', 'false')
        # -- safe schemes
        self.env.config.set('wiki', 'safe_schemes',
                            'file,ftp,http,https,svn,svn+ssh,'
                            'rfc-2396.compatible,rfc-2396+under_score')

        # TODO: remove the following lines in order to discover
        #       all the places were we should use the req.href
        #       instead of env.href
        self.env.href = req.href
        self.env.abs_href = req.abs_href

    def setUp(self):
        wiki = WikiPage(self.env)
        wiki.name = 'WikiStart'
        wiki.text = '--'
        wiki.save('joe', 'Entry page', '::1', datetime.now(utc))
        if self._setup:
            self._setup(self)

    def tearDown(self):
        self.env.reset_db()
        if self._teardown:
            self._teardown(self)

    def test(self):
        """Testing WikiFormatter"""
        formatter = self.formatter()
        v = unicode(formatter.generate(**self.generate_opts))
        v = v.replace('\r', '').replace(u'\u200b', '')
        try:
            self.assertEquals(self.correct, v)
        except AssertionError, e:
            msg = to_unicode(e)
            match = re.match(r"u?'(.*)' != u?'(.*)'", msg)
            if match:
                g1 = ["%s\n" % x for x in match.group(1).split(r'\n')]
                g2 = ["%s\n" % x for x in match.group(2).split(r'\n')]
                expected = ''.join(g1)
                actual = ''.join(g2)
                wiki = repr(self.input).replace(r'\n', '\n')
                diff = ''.join(list(difflib.unified_diff(g1, g2, 'expected',
                                                         'actual')))
                # Tip: sometimes, 'expected' and 'actual' differ only by 
                #      whitespace, so it can be useful to visualize them, e.g.
                # expected = expected.replace(' ', '.')
                # actual = actual.replace(' ', '.')
                def info(*args):
                    return '\n========== %s: ==========\n%s' % args
                msg = info('expected', expected)
                msg += info('actual', actual)
                msg += info('wiki', ''.join(wiki))
                msg += info('diff', diff)
            raise AssertionError( # See below for details
                '%s\n\n%s:%s: "%s" (%s flavor)' \
                % (msg, self.file, self.line, self.title, formatter.flavor))

    def formatter(self):
        return HtmlFormatter(self.env, self.context, self.input)

    def shortDescription(self):
        return 'Test ' + self.title


class OneLinerTestCase(WikiTestCase):
    def formatter(self):
        return InlineHtmlFormatter(self.env, self.context, self.input)

class EscapeNewLinesTestCase(WikiTestCase):
    generate_opts = {'escape_newlines': True}
    def formatter(self):
        return HtmlFormatter(self.env, self.context, self.input)


def suite(data=None, setup=None, file=__file__, teardown=None, context=None):
    suite = unittest.TestSuite()
    def add_test_cases(data, filename):
        tests = re.compile('^(%s.*)$' % ('=' * 30), re.MULTILINE).split(data)
        next_line = 1
        line = 0
        for title, test in zip(tests[1::2], tests[2::2]):
            title = title.lstrip('=').strip()            
            if line != next_line:
                line = next_line
            if not test or test == '\n':
                continue
            next_line += len(test.split('\n')) - 1
            if 'SKIP' in title or 'WONTFIX' in title:
                continue
            blocks = test.split('-' * 30 + '\n')
            page_escape_nl = oneliner = None
            if len(blocks) < 4:
                blocks.extend([None,] * (4 - len(blocks)))
            input, page, oneliner, page_escape_nl = blocks[:4]
            if page:
                page = WikiTestCase(
                    title, input, page, filename, line, setup,
                    teardown, context)
            if oneliner:
                oneliner = OneLinerTestCase(
                    title, input, oneliner[:-1], filename, line, setup,
                    teardown, context)
            if page_escape_nl:
                page_escape_nl = EscapeNewLinesTestCase(
                    title, input, page_escape_nl, filename, line, setup,
                    teardown, context)
            for tc in [page, oneliner, page_escape_nl]:
                if tc:
                    suite.addTest(tc)
    if data:
        add_test_cases(data, file)
    else:
        for f in ('wiki-tests.txt', 'wikicreole-tests.txt'):
            testfile = os.path.join(os.path.split(file)[0], f)
            if os.path.exists(testfile):
                data = open(testfile, 'r').read().decode('utf-8')
                add_test_cases(data, testfile)
            else:
                print 'no ', testfile
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
