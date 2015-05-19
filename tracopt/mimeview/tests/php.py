# -*- coding: utf-8 -*-
#
# Copyright (C)2006-2009 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from StringIO import StringIO
import unittest

from trac.mimeview.api import Mimeview
from trac.test import EnvironmentStub, locate
from tracopt.mimeview.php import PhpDeuglifier, PHPRenderer


class PhpDeuglifierTestCase(unittest.TestCase):

    def test_nomarkup(self):
        self.assertEqual('asd', PhpDeuglifier().format('asd'))

    def test_rewrite_span(self):
        self.assertEqual('<span class="code-comment">asd</span>',
            PhpDeuglifier().format('<span style="color: #FF8000">asd</span>'))
        self.assertEqual('<span class="code-lang">asd</span>',
            PhpDeuglifier().format('<span style="color: #0000BB">asd</span>'))
        self.assertEqual('<span class="code-keyword">asd</span>',
            PhpDeuglifier().format('<span style="color: #007700">asd</span>'))
        self.assertEqual('<span class="code-string">asd</span>',
            PhpDeuglifier().format('<span style="color: #DD0000">asd</span>'))

    def test_rewrite_font(self):
        self.assertEqual('<span class="code-comment">asd</span>',
            PhpDeuglifier().format('<font color="#FF8000">asd</font>'))
        self.assertEqual('<span class="code-lang">asd</span>',
            PhpDeuglifier().format('<font color="#0000BB">asd</font>'))
        self.assertEqual('<span class="code-keyword">asd</span>',
            PhpDeuglifier().format('<font color="#007700">asd</font>'))
        self.assertEqual('<span class="code-string">asd</span>',
            PhpDeuglifier().format('<font color="#DD0000">asd</font>'))

    def test_reorder_br(self):
        """
        Regression test for #3326 point 2 (close tags after line break)
        """
        self.assertEqual('<span class="code-lang"></span><br />',
            PhpDeuglifier().format(
                '<span style="color: #0000BB"><br /></span>'))
        self.assertEqual('<span class="code-lang"></span><br /><br />',
            PhpDeuglifier().format(
                '<span style="color: #0000BB"><br /><br /></span>'))


class PhpRendererTestCase(unittest.TestCase):

    def _test_render(self, stuff, type="string"):
        env = EnvironmentStub(enable=[PHPRenderer])
        m = Mimeview(env)
        r = m.renderers[0]
        if type == "string":
            s = stuff
        elif type == "file":
            s = StringIO(stuff)
        else:
            raise NotImplementedException(
                "Pass either type=file or type=string")
        result = list(r.render(None, None, s))
        return result

    def test_boring_string(self):
        """
        Simple regression test for #3624 (php chops off the last line)
        """
        result = self._test_render('asd')
        self.assertEqual('asd', result[0])
        self.assertEqual(1, len(result))

    def test_boring_filelike(self):
        """
        Regression test for #3261 (treats content as string) # FIXME see #3332
        """
        result = self._test_render('asd', 'file')
        self.assertEqual('asd', result[0])
        self.assertEqual(1, len(result))

    def test_simple_string(self):
        result = self._test_render('<?php\n?>')
        self.assertEqual('<span class="code-lang">&lt;?php', result[0])
        self.assertEqual('?&gt;</span>', result[1])
        self.assertEqual(2, len(result))

    def test_simple_unicode(self):
        result = self._test_render(u'<?php echo "\u00e9"; ?>')
        self.assertEqual(u'<span class="code-lang">&lt;?php </span>'
                         u'<span class="code-keyword">echo </span>'
                         u'<span class="code-string">"é"</span>'
                         u'<span class="code-keyword">; </span>'
                         u'<span class="code-lang">?&gt;</span>', result[0])
        self.assertEqual(1, len(result))
    
    def test_way_too_many_nbsp(self):
        """
        Regression test for a tiny part of #1676
        """
        result = self._test_render('<?php\n    ?>')
        self.assertEqual('<span class="code-lang">&lt;?php', result[0])
        self.assertEqual('    ?&gt;</span>', result[1])
        self.assertEqual(2, len(result))

    def test_deuglified_reorder_br(self):
        """
        If the reordering of <br /> and the subsequent orphan </span>
        isn't working, the </span> appears at the beginning of the third
        line instead of the end of the second.
        """
        result = self._test_render('<?php\n$x="asd";\n?>')
        self.assertEqual('<span class="code-lang">&lt;?php', result[0])
        self.assertEqual('$x</span><span class="code-keyword">=</span>'
            '<span class="code-string">"asd"</span>'
            '<span class="code-keyword">;</span>', result[1])
        self.assertEqual('<span class="code-lang">?&gt;</span>', result[2])
        self.assertEqual(3, len(result))

    def test_keeps_last_line(self):
        """
        More complex regression test for #3624 (php chops off the last line)
        """
        result = self._test_render('<p />\n<p />')
        self.assertEqual('&lt;p /&gt;', result[0])
        self.assertEqual('&lt;p /&gt;', result[1])
        self.assertEqual(2, len(result))


def suite():
    suite = unittest.TestSuite()
    php = locate("php")
    if php:
        suite.addTest(unittest.makeSuite(PhpDeuglifierTestCase, 'test'))
        suite.addTest(unittest.makeSuite(PhpRendererTestCase, 'test'))
    else:
        print("SKIP: tracopt/mimeview/tests/php.py (php cli binary, 'php', "
              "not found)")
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
