# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os
import unittest

from genshi.template import MarkupTemplate
from trac.core import Component, TracError, implements
from trac.util.html import html
from trac.util.translation import tag_
from trac.wiki.api import IWikiSyntaxProvider
from trac.wiki.formatter import MacroError, ProcessorError
from trac.wiki.macros import WikiMacroBase
from trac.wiki.test import wikisyntax_test_suite


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


class ValueErrorWithUtf8Macro(WikiMacroBase):

    def expand_macro(self, formatter, name, content, args):
        raise ValueError(content.encode('utf-8'))


class TracErrorWithUnicodeMacro(WikiMacroBase):

    def expand_macro(self, formatter, name, content, args):
        raise TracError(unicode(content))


class MacroErrorWithFragmentMacro(WikiMacroBase):

    def expand_macro(self, formatter, name, content, args=None):
        raise MacroError(tag_("The content: %(content)s",
                              content=html.code(content)))


class ProcessorErrorWithFragmentMacro(WikiMacroBase):

    def expand_macro(self, formatter, name, content, args=None):
        raise ProcessorError(tag_("The content: %(content)s",
                                  content=html.code(content)))


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
            kind = 'odd' if int(target) % 2 else 'even'
            module = 'thing'
        except ValueError:
            pass
        return html.A(label, class_='%s resolver' % kind,
                      href=formatter.href(module, target))


def suite(data=None, setup=None, file=__file__, teardown=None, context=None):
    """Retained for backward-compatibility.

    :since 1.2: Deprecated and will be removed in 1.3.1
    """
    return test_suite(data, setup, file, teardown, context)


def test_suite(data=None, setup=None, file=__file__, teardown=None,
               context=None):
    suite = unittest.TestSuite()

    if data:
        suite.addTest(wikisyntax_test_suite(data, setup, file, teardown,
                                            context))
    else:
        for filename in ('wiki-tests.txt', 'wikicreole-tests.txt'):
            filepath = os.path.join(os.path.dirname(file), filename)
            suite.addTest(wikisyntax_test_suite(data, setup, filepath,
                                                teardown, context))
    return suite


if __name__ == '__main__':  # pragma: no cover
    unittest.main(defaultTest='test_suite')
