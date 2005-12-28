from trac.util import Markup

import unittest


class MarkupTestCase(unittest.TestCase):

    def test_escape(self):
        markup = Markup.escape('<b>"&"</b>')
        assert isinstance(markup, Markup)
        self.assertEquals('&lt;b&gt;&#34;&amp;&#34;&lt;/b&gt;', markup)

    def test_escape_noquotes(self):
        markup = Markup.escape('<b>"&"</b>', quotes=False)
        assert isinstance(markup, Markup)
        self.assertEquals('&lt;b&gt;"&amp;"&lt;/b&gt;', markup)

    def test_add_str(self):
        markup = Markup('<b>foo</b>') + '<br/>'
        assert isinstance(markup, Markup)
        self.assertEquals('<b>foo</b>&lt;br/&gt;', markup)

    def test_add_markup(self):
        markup = Markup('<b>foo</b>') + Markup('<br/>')
        assert isinstance(markup, Markup)
        self.assertEquals('<b>foo</b><br/>', markup)

    def test_add_reverse(self):
        markup = 'foo' + Markup('<b>bar</b>')
        assert isinstance(markup, str)
        self.assertEquals('foo<b>bar</b>', markup)

    def test_mul(self):
        markup = Markup('<b>foo</b>') * 2
        assert isinstance(markup, Markup)
        self.assertEquals('<b>foo</b><b>foo</b>', markup)

    def test_join(self):
        markup = Markup('<br />').join(['foo', '<bar />', Markup('<baz />')])
        assert isinstance(markup, Markup)
        self.assertEquals('foo<br />&lt;bar /&gt;<br /><baz />', markup)

    def test_striptags_empty(self):
        markup = Markup('<br />').striptags()
        assert isinstance(markup, Markup)
        self.assertEquals('', markup)

    def test_striptags_mid(self):
        markup = Markup('<a href="#">fo<br />o</a>').striptags()
        assert isinstance(markup, Markup)
        self.assertEquals('foo', markup)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(MarkupTestCase, 'test'))
    return suite

if __name__ == '__main__':
    unittest.main()
