# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from __future__ import with_statement

import doctest
import os.path
import pkg_resources
import random
import re
import sys
import tempfile
import unittest

import trac
from trac import util
from trac.test import rmtree
from trac.util.tests import concurrency, datefmt, presentation, text, \
                            translation, html


class AtomicFileTestCase(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, 'trac-tempfile')

    def tearDown(self):
        rmtree(self.dir)

    def test_non_existing(self):
        with util.AtomicFile(self.path) as f:
            f.write('test content')
        self.assertTrue(f.closed)
        self.assertEqual('test content', util.read_file(self.path))

    def test_existing(self):
        util.create_file(self.path, 'Some content')
        self.assertEqual('Some content', util.read_file(self.path))
        with util.AtomicFile(self.path) as f:
            f.write('Some new content')
        self.assertTrue(f.closed)
        self.assertEqual('Some new content', util.read_file(self.path))

    if os.name != 'nt':
        def test_symbolic_link(self):
            link_path = os.path.join(self.dir, 'trac-tempfile-link')
            os.symlink(self.path, link_path)

            with util.AtomicFile(link_path) as f:
                f.write('test content')

            self.assertTrue(os.path.islink(link_path))
            self.assertEqual('test content', util.read_file(link_path))
            self.assertEqual('test content', util.read_file(self.path))

    if util.can_rename_open_file:
        def test_existing_open_for_reading(self):
            util.create_file(self.path, 'Initial file content')
            self.assertEqual('Initial file content', util.read_file(self.path))
            with open(self.path) as rf:
                with util.AtomicFile(self.path) as f:
                    f.write('Replaced content')
            self.assertTrue(rf.closed)
            self.assertTrue(f.closed)
            self.assertEqual('Replaced content', util.read_file(self.path))

    # FIXME: It is currently not possible to make this test pass on all
    # platforms and with all locales. Typically, it will fail on Linux with
    # LC_ALL=C.
    # Python 3 adds sys.setfilesystemencoding(), which could be used here
    # to remove the dependency on the locale. So the test is disabled until
    # we require Python 3.
    def _test_unicode_path(self):
        self.path = os.path.join(tempfile.gettempdir(), u'träc-témpfilè')
        with util.AtomicFile(self.path) as f:
            f.write('test content')
        self.assertTrue(f.closed)
        self.assertEqual('test content', util.read_file(self.path))


class PathTestCase(unittest.TestCase):

    def assert_below(self, path, parent):
        self.assertTrue(util.is_path_below(path.replace('/', os.sep),
                                           parent.replace('/', os.sep)))

    def assert_not_below(self, path, parent):
        self.assertFalse(util.is_path_below(path.replace('/', os.sep),
                                            parent.replace('/', os.sep)))

    def test_is_path_below(self):
        self.assert_below('/svn/project1', '/svn/project1')
        self.assert_below('/svn/project1/repos', '/svn/project1')
        self.assert_below('/svn/project1/sub/repos', '/svn/project1')
        self.assert_below('/svn/project1/sub/../repos', '/svn/project1')
        self.assert_not_below('/svn/project2/repos', '/svn/project1')
        self.assert_not_below('/svn/project2/sub/repos', '/svn/project1')
        self.assert_not_below('/svn/project1/../project2/repos',
                              '/svn/project1')
        self.assertTrue(util.is_path_below('repos', os.path.join(os.getcwd())))
        self.assertFalse(util.is_path_below('../sub/repos',
                                            os.path.join(os.getcwd())))


class RandomTestCase(unittest.TestCase):

    def setUp(self):
        self.state = random.getstate()

    def tearDown(self):
        random.setstate(self.state)

    def test_urandom(self):
        """urandom() returns random bytes"""
        for i in xrange(129):
            self.assertEqual(i, len(util.urandom(i)))
        # For a large enough sample, each value should appear at least once
        entropy = util.urandom(65536)
        values = set(ord(c) for c in entropy)
        self.assertEqual(256, len(values))

    def test_hex_entropy(self):
        """hex_entropy() returns random hex digits"""
        hex_digits = set('0123456789abcdef')
        for i in xrange(129):
            entropy = util.hex_entropy(i)
            self.assertEqual(i, len(entropy))
            self.assertEqual(set(), set(entropy) - hex_digits)

    def test_hex_entropy_global_state(self):
        """hex_entropy() not affected by global random generator state"""
        random.seed(0)
        data = util.hex_entropy(64)
        random.seed(0)
        self.assertNotEqual(data, util.hex_entropy(64))


class ContentDispositionTestCase(unittest.TestCase):

    def test_filename(self):
        self.assertEqual('attachment; filename=myfile.txt',
                         util.content_disposition('attachment', 'myfile.txt'))
        self.assertEqual('attachment; filename=a%20file.txt',
                         util.content_disposition('attachment', 'a file.txt'))

    def test_no_filename(self):
        self.assertEqual('inline', util.content_disposition('inline'))
        self.assertEqual('attachment', util.content_disposition('attachment'))

    def test_no_type(self):
        self.assertEqual('filename=myfile.txt',
                         util.content_disposition(filename='myfile.txt'))
        self.assertEqual('filename=a%20file.txt',
                         util.content_disposition(filename='a file.txt'))


class SafeReprTestCase(unittest.TestCase):
    def test_normal_repr(self):
        for x in ([1, 2, 3], "été", u"été"):
            self.assertEqual(repr(x), util.safe_repr(x))

    def test_buggy_repr(self):
        class eh_ix(object):
            def __repr__(self):
                return 1 + "2"
        self.assertRaises(Exception, repr, eh_ix())
        sr = util.safe_repr(eh_ix())
        sr = re.sub('[A-F0-9]{4,}', 'ADDRESS', sr)
        sr = re.sub(r'__main__|trac\.util\.tests(\.__init__)?', 'MODULE', sr)
        self.assertEqual("<MODULE.eh_ix object at 0xADDRESS "
                         "(repr() error: TypeError: unsupported operand "
                         "type(s) for +: 'int' and 'str')>", sr)


class SetuptoolsUtilsTestCase(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        sys.path.append(self.dir)

    def tearDown(self):
        sys.path.remove(self.dir)
        rmtree(self.dir)

    def test_get_module_path(self):
        self.assertEqual(util.get_module_path(trac),
                         util.get_module_path(util))

    def test_get_pkginfo_trac(self):
        pkginfo = util.get_pkginfo(trac)
        self.assertEqual(trac.__version__, pkginfo.get('version'))
        self.assertNotEqual({}, pkginfo)

    def test_get_pkginfo_non_toplevel(self):
        from trac import core
        import tracopt
        pkginfo = util.get_pkginfo(trac)
        self.assertEqual(pkginfo, util.get_pkginfo(util))
        self.assertEqual(pkginfo, util.get_pkginfo(core))
        self.assertEqual(pkginfo, util.get_pkginfo(tracopt))

    def test_get_pkginfo_genshi(self):
        try:
            import genshi
            import genshi.core
            dist = pkg_resources.get_distribution('Genshi')
        except:
            pass
        else:
            pkginfo = util.get_pkginfo(genshi)
            self.assertNotEqual({}, pkginfo)
            self.assertEqual(pkginfo, util.get_pkginfo(genshi.core))

    def test_get_pkginfo_babel(self):
        try:
            import babel
            import babel.core
            dist = pkg_resources.get_distribution('Babel')
        except:
            pass
        else:
            pkginfo = util.get_pkginfo(babel)
            self.assertNotEqual({}, pkginfo)
            self.assertEqual(pkginfo, util.get_pkginfo(babel.core))

    def test_get_pkginfo_mysqldb(self):
        # MySQLdb's package name is "MySQL-Python"
        try:
            import MySQLdb
            import MySQLdb.cursors
            dist = pkg_resources.get_distribution('MySQL-Python')
            dist.get_metadata('top_level.txt')
        except:
            pass
        else:
            pkginfo = util.get_pkginfo(MySQLdb)
            self.assertNotEqual({}, pkginfo)
            self.assertEqual(pkginfo, util.get_pkginfo(MySQLdb.cursors))

    def test_get_pkginfo_psycopg2(self):
        # python-psycopg2 deb package doesn't provide SOURCES.txt and
        # top_level.txt
        try:
            import psycopg2
            import psycopg2.extensions
            dist = pkg_resources.get_distribution('psycopg2')
        except:
            pass
        else:
            pkginfo = util.get_pkginfo(psycopg2)
            self.assertNotEqual({}, pkginfo)
            self.assertEqual(pkginfo, util.get_pkginfo(psycopg2.extensions))

    def test_file_metadata(self):
        pkgname = 'TestModule_' + util.hex_entropy(16)
        modname = pkgname.lower()
        with open(os.path.join(self.dir, pkgname + '-0.1.egg-info'), 'w') as f:
            f.write('Metadata-Version: 1.1\n'
                    'Name: %(pkgname)s\n'
                    'Version: 0.1\n'
                    'Author: Joe\n'
                    'Author-email: joe@example.org\n'
                    'Home-page: http://example.org/\n'
                    'Summary: summary.\n'
                    'Description: description.\n'
                    'Provides: %(modname)s\n'
                    'Provides: %(modname)s.foo\n'
                    % {'pkgname': pkgname, 'modname': modname})
        os.mkdir(os.path.join(self.dir, modname))
        for name in ('__init__.py', 'bar.py', 'foo.py'):
            with open(os.path.join(self.dir, modname, name), 'w') as f:
                f.write('# -*- coding: utf-8 -*-\n')

        mod = __import__(modname, {}, {}, ['bar', 'foo'])
        pkginfo = util.get_pkginfo(mod)
        self.assertEqual('0.1', pkginfo['version'])
        self.assertEqual('Joe', pkginfo['author'])
        self.assertEqual('joe@example.org', pkginfo['author_email'])
        self.assertEqual('http://example.org/', pkginfo['home_page'])
        self.assertEqual('summary.', pkginfo['summary'])
        self.assertEqual('description.', pkginfo['description'])
        self.assertEqual(pkginfo, util.get_pkginfo(mod.bar))
        self.assertEqual(pkginfo, util.get_pkginfo(mod.foo))


class LazyClass(object):
    @util.lazy
    def f(self):
        return object()


class LazyTestCase(unittest.TestCase):

    def setUp(self):
        self.obj = LazyClass()

    def test_lazy_get(self):
        f = self.obj.f
        self.assertTrue(self.obj.f is f)

    def test_lazy_set(self):
        self.obj.f = 2
        self.assertEqual(2, self.obj.f)

    def test_lazy_del(self):
        f = self.obj.f
        del self.obj.f
        self.assertFalse(self.obj.f is f)


class FileTestCase(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.filename = os.path.join(self.dir, 'trac-tempfile')
        self.data = 'Lorem\ripsum\ndolor\r\nsit\namet,\rconsectetur\r\n'

    def tearDown(self):
        rmtree(self.dir)

    def test_create_and_read_file(self):
        util.create_file(self.filename, self.data, 'wb')
        with open(self.filename, 'rb') as f:
            self.assertEqual(self.data, f.read())
        self.assertEqual(self.data, util.read_file(self.filename, 'rb'))

    def test_touch_file(self):
        util.create_file(self.filename, self.data, 'wb')
        util.touch_file(self.filename)
        with open(self.filename, 'rb') as f:
            self.assertEqual(self.data, f.read())

    def test_missing(self):
        util.touch_file(self.filename)
        self.assertTrue(os.path.isfile(self.filename))
        self.assertEqual(0, os.path.getsize(self.filename))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(AtomicFileTestCase))
    suite.addTest(unittest.makeSuite(PathTestCase))
    suite.addTest(unittest.makeSuite(RandomTestCase))
    suite.addTest(unittest.makeSuite(ContentDispositionTestCase))
    suite.addTest(unittest.makeSuite(SafeReprTestCase))
    suite.addTest(unittest.makeSuite(SetuptoolsUtilsTestCase))
    suite.addTest(unittest.makeSuite(LazyTestCase))
    suite.addTest(unittest.makeSuite(FileTestCase))
    suite.addTest(concurrency.suite())
    suite.addTest(datefmt.suite())
    suite.addTest(presentation.suite())
    suite.addTest(doctest.DocTestSuite(util))
    suite.addTest(text.suite())
    suite.addTest(translation.suite())
    suite.addTest(html.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
