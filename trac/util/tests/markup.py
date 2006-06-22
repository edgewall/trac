# -*- encoding: utf-8 -*-

import doctest
from HTMLParser import HTMLParseError
import unittest

from trac.util.markup import escape, html, unescape, Element, Markup


class MarkupTestCase(unittest.TestCase):

    def test_escape(self):
        markup = escape('<b>"&"</b>')
        assert isinstance(markup, Markup)
        self.assertEquals('&lt;b&gt;&#34;&amp;&#34;&lt;/b&gt;', markup)

    def test_escape_noquotes(self):
        markup = escape('<b>"&"</b>', quotes=False)
        assert isinstance(markup, Markup)
        self.assertEquals('&lt;b&gt;"&amp;"&lt;/b&gt;', markup)

    def test_unescape_markup(self):
        string = '<b>"&"</b>'
        markup = Markup.escape(string)
        assert isinstance(markup, Markup)
        self.assertEquals(string, unescape(markup))

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
        assert isinstance(markup, unicode)
        self.assertEquals('foo<b>bar</b>', markup)

    def test_mod(self):
        markup = Markup('<b>%s</b>') % '&'
        assert isinstance(markup, Markup)
        self.assertEquals('<b>&amp;</b>', markup)

    def test_mod_multi(self):
        markup = Markup('<b>%s</b> %s') % ('&', 'boo')
        assert isinstance(markup, Markup)
        self.assertEquals('<b>&amp;</b> boo', markup)

    def test_mul(self):
        markup = Markup('<b>foo</b>') * 2
        assert isinstance(markup, Markup)
        self.assertEquals('<b>foo</b><b>foo</b>', markup)

    def test_join(self):
        markup = Markup('<br />').join(['foo', '<bar />', Markup('<baz />')])
        assert isinstance(markup, Markup)
        self.assertEquals('foo<br />&lt;bar /&gt;<br /><baz />', markup)

    def test_stripentities_all(self):
        markup = Markup('&amp; &#106;').stripentities()
        assert isinstance(markup, Markup)
        self.assertEquals('& j', markup)

    def test_stripentities_keepxml(self):
        markup = Markup('<a href="#">fo<br />o</a>').striptags()
        assert isinstance(markup, Markup)
        self.assertEquals('foo', markup)

    def test_striptags_empty(self):
        markup = Markup('<br />').striptags()
        assert isinstance(markup, Markup)
        self.assertEquals('', markup)

    def test_striptags_mid(self):
        markup = Markup('<a href="#">fo<br />o</a>').striptags()
        assert isinstance(markup, Markup)
        self.assertEquals('foo', markup)

    def test_sanitize_unchanged(self):
        markup = Markup('<a href="#">fo<br />o</a>')
        self.assertEquals('<a href="#">fo<br />o</a>', markup.sanitize())

    def test_sanitize_escape_text(self):
        markup = Markup('<a href="#">fo&amp;</a>')
        self.assertEquals('<a href="#">fo&amp;</a>', markup.sanitize())
        markup = Markup('<a href="#">&lt;foo&gt;</a>')
        self.assertEquals('<a href="#">&lt;foo&gt;</a>', markup.sanitize())

    def test_sanitize_entityref_text(self):
        markup = Markup('<a href="#">fo&ouml;</a>')
        self.assertEquals(u'<a href="#">foö</a>', markup.sanitize())

    def test_sanitize_escape_attr(self):
        markup = Markup('<div title="&lt;foo&gt;"></div>')
        self.assertEquals('<div title="&lt;foo&gt;"></div>', markup.sanitize())

    def test_sanitize_close_empty_tag(self):
        markup = Markup('<a href="#">fo<br>o</a>')
        self.assertEquals('<a href="#">fo<br />o</a>', markup.sanitize())

    def test_sanitize_invalid_entity(self):
        markup = Markup('&junk;')
        self.assertEquals('&amp;junk;', markup.sanitize())

    def test_sanitize_remove_script_elem(self):
        markup = Markup('<script>alert("Foo")</script>')
        self.assertEquals('', markup.sanitize())
        markup = Markup('<SCRIPT SRC="http://example.com/"></SCRIPT>')
        self.assertEquals('', markup.sanitize())
        markup = Markup('<SCR\0IPT>alert("foo")</SCR\0IPT>')
        self.assertRaises(HTMLParseError, markup.sanitize)
        markup = Markup('<SCRIPT&XYZ SRC="http://example.com/"></SCRIPT>')
        self.assertRaises(HTMLParseError, markup.sanitize)

    def test_sanitize_remove_onclick_attr(self):
        markup = Markup('<div onclick=\'alert("foo")\' />')
        self.assertEquals('<div></div>', markup.sanitize())

    def test_sanitize_remove_style_scripts(self):
        # Inline style with url() using javascript: scheme
        markup = Markup('<DIV STYLE=\'background: url(javascript:alert("foo"))\'>')
        self.assertEquals('<div>', markup.sanitize())
        # Inline style with url() using javascript: scheme, using control char
        markup = Markup('<DIV STYLE=\'background: url(&#1;javascript:alert("foo"))\'>')
        self.assertEquals('<div>', markup.sanitize())
        # Inline style with url() using javascript: scheme, in quotes
        markup = Markup('<DIV STYLE=\'background: url("javascript:alert(foo)")\'>')
        self.assertEquals('<div>', markup.sanitize())
        # IE expressions in CSS not allowed
        markup = Markup('<DIV STYLE=\'width: expression(alert("foo"));\'>')
        self.assertEquals('<div>', markup.sanitize())
        markup = Markup('<DIV STYLE=\'background: url(javascript:alert("foo"));'
                                     'color: #fff\'>')
        self.assertEquals('<div style="color: #fff">', markup.sanitize())

    def test_sanitize_remove_src_javascript(self):
        markup = Markup('<img src=\'javascript:alert("foo")\'>')
        self.assertEquals('<img />', markup.sanitize())
        # Case-insensitive protocol matching
        markup = Markup('<IMG SRC=\'JaVaScRiPt:alert("foo")\'>')
        self.assertEquals('<img />', markup.sanitize())
        # Grave accents (not parsed)
        markup = Markup('<IMG SRC=`javascript:alert("RSnake says, \'foo\'")`>')
        self.assertRaises(HTMLParseError, markup.sanitize)
        # Protocol encoded using UTF-8 numeric entities
        markup = Markup('<IMG SRC=\'&#106;&#97;&#118;&#97;&#115;&#99;&#114;&#105;'
                        '&#112;&#116;&#58;alert("foo")\'>')
        self.assertEquals('<img />', markup.sanitize())
        # Protocol encoded using UTF-8 numeric entities without a semicolon
        # (which is allowed because the max number of digits is used)
        markup = Markup('<IMG SRC=\'&#0000106&#0000097&#0000118&#0000097'
                        '&#0000115&#0000099&#0000114&#0000105&#0000112&#0000116'
                        '&#0000058alert("foo")\'>')
        self.assertEquals('<img />', markup.sanitize())
        # Protocol encoded using UTF-8 numeric hex entities without a semicolon
        # (which is allowed because the max number of digits is used)
        markup = Markup('<IMG SRC=\'&#x6A&#x61&#x76&#x61&#x73&#x63&#x72&#x69'
                        '&#x70&#x74&#x3A;alert("foo")\'>')
        self.assertEquals('<img />', markup.sanitize())
        # Embedded tab character in protocol
        markup = Markup('<IMG SRC=\'jav\tascript:alert("foo");\'>')
        self.assertEquals('<img />', markup.sanitize())
        # Embedded tab character in protocol, but encoded this time
        markup = Markup('<IMG SRC=\'jav&#x09;ascript:alert("foo");\'>')
        self.assertEquals('<img />', markup.sanitize())


class TagsTestCase(unittest.TestCase):

    def test_link(self):
        link = html.A('Bar', href='#', title='Foo', accesskey=None)
        bits = link.serialize()
        self.assertEqual(u'<a href="#" title="Foo">', bits.next())
        self.assertEqual(u'Bar', bits.next())
        self.assertEqual(u'</a>', bits.next())


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(MarkupTestCase, 'test'))
    suite.addTest(doctest.DocTestSuite(Element.__module__))
    suite.addTest(unittest.makeSuite(TagsTestCase, 'test'))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
