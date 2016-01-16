# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2013 Edgewall Software
# Copyright (C) 2005-2007 Christopher Lenz <cmlenz@gmx.de>
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

import os
import tempfile
import time
import unittest

import trac.tests.compat
from trac.config import *
from trac.core import Component, Interface, implements
from trac.test import Configuration, EnvironmentStub
from trac.util import create_file
from trac.util.compat import wait_for_file_mtime_change
from trac.util.datefmt import time_now


class ConfigurationTestCase(unittest.TestCase):

    def setUp(self):
        tmpdir = os.path.realpath(tempfile.gettempdir())
        self.filename = os.path.join(tmpdir, 'trac-test.ini')
        self.sitename = os.path.join(tmpdir, 'trac-site.ini')
        self.env = EnvironmentStub()
        self._write([])
        self._orig_registry = Option.registry
        Option.registry = {}

    def tearDown(self):
        Option.registry = self._orig_registry
        os.remove(self.filename)

    def _read(self):
        return Configuration(self.filename)

    def _write(self, lines, site=False):
        filename = self.sitename if site else self.filename
        wait_for_file_mtime_change(filename)
        with open(filename, 'w') as fileobj:
            fileobj.write(('\n'.join(lines + [''])).encode('utf-8'))

    def test_default(self):
        config = self._read()
        self.assertEqual('', config.get('a', 'option'))
        self.assertEqual('value', config.get('a', 'option', 'value'))

        class Foo(object):
            option_a = Option('a', 'option', 'value')

        self.assertEqual('value', config.get('a', 'option'))

    def test_default_bool(self):
        config = self._read()
        self.assertFalse(config.getbool('a', 'option'))
        self.assertTrue(config.getbool('a', 'option', 'yes'))
        self.assertTrue(config.getbool('a', 'option', 1))

        class Foo(object):
            option_a = Option('a', 'option', 'true')

        self.assertTrue(config.getbool('a', 'option'))

    def test_default_int(self):
        config = self._read()
        self.assertRaises(ConfigurationError,
                          config.getint, 'a', 'option', 'b')
        self.assertEqual(0, config.getint('a', 'option'))
        self.assertEqual(1, config.getint('a', 'option', '1'))
        self.assertEqual(1, config.getint('a', 'option', 1))

        class Foo(object):
            option_a = Option('a', 'option', '2')

        self.assertEqual(2, config.getint('a', 'option'))

    def test_default_float(self):
        config = self._read()
        self.assertRaises(ConfigurationError,
                          config.getfloat, 'a', 'option', 'b')
        self.assertEqual(0.0, config.getfloat('a', 'option'))
        self.assertEqual(1.2, config.getfloat('a', 'option', '1.2'))
        self.assertEqual(1.2, config.getfloat('a', 'option', 1.2))
        self.assertEqual(1.0, config.getfloat('a', 'option', 1))

        class Foo(object):
            option_a = Option('a', 'option', '2.5')

        self.assertEqual(2.5, config.getfloat('a', 'option'))

    def test_default_path(self):
        config = self._read()
        class Foo(object):
            option_a = PathOption('a', 'opt1', 'file.ini')
            option_b = PathOption('a', 'opt2', '/somewhere/file.ini')
        self.assertEqual('file.ini', config.get('a', 'opt1'))
        self.assertNotEquals('file.ini', config.getpath('a', 'opt1'))
        self.assertTrue(os.path.isabs(config.getpath('a', 'opt1')))
        self.assertEqual('/somewhere/file.ini', os.path.splitdrive(
                         config.getpath('a', 'opt2'))[1].replace('\\', '/'))
        self.assertEqual('/none.ini', os.path.splitdrive(
                         config.getpath('a', 'opt3',
                                        '/none.ini'))[1].replace('\\', '/'))
        self.assertNotEquals('none.ini', config.getpath('a', 'opt3', 'none.ini'))

    def test_read_and_get(self):
        self._write(['[a]', 'option = x'])
        config = self._read()
        self.assertEqual('x', config.get('a', 'option'))
        self.assertEqual('x', config.get('a', 'option', 'y'))
        self.assertEqual('y', config.get('b', 'option2', 'y'))

    def test_read_and_get_unicode(self):
        self._write([u'[ä]', u'öption = x'])
        config = self._read()
        self.assertEqual('x', config.get(u'ä', u'öption'))
        self.assertEqual('x', config.get(u'ä', u'öption', 'y'))
        self.assertEqual('y', config.get('b', u'öption2', 'y'))

    def test_read_and_getbool(self):
        self._write(['[a]', 'option = yes', 'option2 = true',
                     'option3 = eNaBlEd', 'option4 = on',
                     'option5 = 1', 'option6 = 123', 'option7 = 123.456',
                     'option8 = disabled', 'option9 = 0', 'option10 = 0.0'])
        config = self._read()
        self.assertTrue(config.getbool('a', 'option'))
        self.assertTrue(config.getbool('a', 'option', False))
        self.assertTrue(config.getbool('a', 'option2'))
        self.assertTrue(config.getbool('a', 'option3'))
        self.assertTrue(config.getbool('a', 'option4'))
        self.assertTrue(config.getbool('a', 'option5'))
        self.assertTrue(config.getbool('a', 'option6'))
        self.assertTrue(config.getbool('a', 'option7'))
        self.assertFalse(config.getbool('a', 'option8'))
        self.assertFalse(config.getbool('a', 'option9'))
        self.assertFalse(config.getbool('a', 'option10'))
        self.assertFalse(config.getbool('b', 'option_b'))
        self.assertFalse(config.getbool('b', 'option_b', False))
        self.assertFalse(config.getbool('b', 'option_b', 'disabled'))

    def test_read_and_getint(self):
        self._write(['[a]', 'option = 42'])
        config = self._read()
        self.assertEqual(42, config.getint('a', 'option'))
        self.assertEqual(42, config.getint('a', 'option', 25))
        self.assertEqual(0, config.getint('b', 'option2'))
        self.assertEqual(25, config.getint('b', 'option2', 25))
        self.assertEqual(25, config.getint('b', 'option2', '25'))

    def test_read_and_getfloat(self):
        self._write(['[a]', 'option = 42.5'])
        config = self._read()
        self.assertEqual(42.5, config.getfloat('a', 'option'))
        self.assertEqual(42.5, config.getfloat('a', 'option', 25.3))
        self.assertEqual(0, config.getfloat('b', 'option2'))
        self.assertEqual(25.3, config.getfloat('b', 'option2', 25.3))
        self.assertEqual(25.0, config.getfloat('b', 'option2', 25))
        self.assertEqual(25.3, config.getfloat('b', 'option2', '25.3'))

    def test_read_and_getlist(self):
        self._write(['[a]', 'option = foo, bar, baz'])
        config = self._read()
        self.assertEqual(['foo', 'bar', 'baz'],
                         config.getlist('a', 'option'))
        self.assertEqual([],
                         config.getlist('b', 'option2'))
        self.assertEqual(['foo', 'bar', 'baz'],
                         config.getlist('b', 'option2',
                                        ['foo', 'bar', 'baz']))
        self.assertEqual(['foo', 'bar', 'baz'],
                         config.getlist('b', 'option2', 'foo, bar, baz'))

    def test_read_and_getlist_sep(self):
        self._write(['[a]', 'option = foo | bar | baz'])
        config = self._read()
        self.assertEqual(['foo', 'bar', 'baz'],
                         config.getlist('a', 'option', sep='|'))

    def test_read_and_getlist_keep_empty(self):
        self._write(['[a]', 'option = ,bar,baz'])
        config = self._read()
        self.assertEqual(['bar', 'baz'], config.getlist('a', 'option'))
        self.assertEqual(['', 'bar', 'baz'],
                         config.getlist('a', 'option', keep_empty=True))

    def test_read_and_getlist_false_values(self):
        config = self._read()
        values = [None, False, '', 'foo', u'', u'bar',
                  0, 0L, 0.0, 0j, 42, 43.0]
        self.assertEqual([False, 'foo', u'bar', 0, 0L, 0.0, 0j, 42, 43.0],
                         config.getlist('a', 'false', values))
        self.assertEqual(values, config.getlist('a', 'false', values,
                                                keep_empty=True))

    def test_read_and_choice(self):
        self._write(['[a]', 'option = 2', 'invalid = d'])
        config = self._read()

        class Foo(object):
            # enclose in parentheses to avoid messages extraction
            option = (ChoiceOption)('a', 'option', ['Item1', 2, '3'])
            other = (ChoiceOption)('a', 'other', [1, 2, 3])
            invalid = (ChoiceOption)('a', 'invalid', ['a', 'b', 'c'])

            def __init__(self):
                self.config = config

        foo = Foo()
        self.assertEqual('2', foo.option)
        self.assertEqual('1', foo.other)
        self.assertRaises(ConfigurationError, getattr, foo, 'invalid')

    def test_read_and_getextensionoption(self):
        self._write(['[a]', 'option = ImplA', 'invalid = ImplB'])
        config = self._read()

        class IDummy(Interface):
            pass

        class ImplA(Component):
            implements(IDummy)

        class Foo(Component):
            default1 = (ExtensionOption)('a', 'default1', IDummy)
            default2 = (ExtensionOption)('a', 'default2', IDummy, 'ImplA')
            default3 = (ExtensionOption)('a', 'default3', IDummy, 'ImplB')
            option = (ExtensionOption)('a', 'option', IDummy)
            option2 = (ExtensionOption)('a', 'option', IDummy, 'ImplB')
            invalid = (ExtensionOption)('a', 'invalid', IDummy)

            def __init__(self):
                self.config = config

        foo = Foo(self.env)
        self.assertRaises(ConfigurationError, getattr, foo, 'default1')
        self.assertIsInstance(foo.default2, ImplA)
        self.assertRaises(ConfigurationError, getattr, foo, 'default3')
        self.assertIsInstance(foo.option, ImplA)
        self.assertIsInstance(foo.option2, ImplA)
        self.assertRaises(ConfigurationError, getattr, foo, 'invalid')

    def test_read_and_getorderedextensionsoption(self):
        self._write(['[a]', 'option = ImplA, ImplB',
                     'invalid = ImplB, ImplD'])
        config = self._read()

        class IDummy(Interface):
            pass

        class ImplA(Component):
            implements(IDummy)

        class ImplB(Component):
            implements(IDummy)

        class ImplC(Component):
            implements(IDummy)

        class Foo(Component):
            # enclose in parentheses to avoid messages extraction
            default1 = (OrderedExtensionsOption)('a', 'default1', IDummy,
                                                 include_missing=False)
            default2 = (OrderedExtensionsOption)('a', 'default2', IDummy)
            default3 = (OrderedExtensionsOption)('a', 'default3', IDummy,
                                                 'ImplB, ImplC',
                                                 include_missing=False)
            option = (OrderedExtensionsOption)('a', 'option', IDummy,
                                               include_missing=False)
            invalid = (OrderedExtensionsOption)('a', 'invalid', IDummy)

            def __init__(self):
                self.config = config

        foo = Foo(self.env)
        self.assertEqual([], foo.default1)
        self.assertEqual(3, len(foo.default2))
        self.assertIsInstance(foo.default2[0], ImplA)
        self.assertIsInstance(foo.default2[1], ImplB)
        self.assertIsInstance(foo.default2[2], ImplC)
        self.assertEqual(2, len(foo.default3))
        self.assertIsInstance(foo.default3[0], ImplB)
        self.assertIsInstance(foo.default3[1], ImplC)
        self.assertEqual(2, len(foo.option))
        self.assertIsInstance(foo.option[0], ImplA)
        self.assertIsInstance(foo.option[1], ImplB)
        self.assertRaises(ConfigurationError, getattr, foo, 'invalid')

    def test_getpath(self):
        base = os.path.dirname(self.filename)
        config = self._read()
        config.set('a', 'path_a', os.path.join(base, 'here', 'absolute.txt'))
        config.set('a', 'path_b', 'thisdir.txt')
        config.set('a', 'path_c', os.path.join(os.pardir, 'parentdir.txt'))
        self.assertEqual(os.path.join(base, 'here', 'absolute.txt'),
                         config.getpath('a', 'path_a'))
        self.assertEqual(os.path.join(base, 'thisdir.txt'),
                         config.getpath('a', 'path_b'))
        self.assertEqual(os.path.join(os.path.dirname(base), 'parentdir.txt'),
                         config.getpath('a', 'path_c'))

    def test_set_raises(self):
        class Foo(object):
            option = Option('a', 'option', 'value')

        f = Foo()
        self.assertRaises(AttributeError, setattr, f, 'option',
                          Option('a', 'option2', 'value2'))

    def test_set_and_save(self):
        config = self._read()
        config.set('b', u'öption0', 'y')
        config.set(u'aä', 'öption0', 'x')
        config.set('aä', 'option2', "Voilà l'été")  # UTF-8
        config.set(u'aä', 'option1', u"Voilà l'été") # unicode
        # Note: the following would depend on the locale.getpreferredencoding()
        # config.set('a', 'option3', "Voil\xe0 l'\xe9t\xe9") # latin-1
        self.assertEqual('x', config.get(u'aä', u'öption0'))
        self.assertEqual(u"Voilà l'été", config.get(u'aä', 'option1'))
        self.assertEqual(u"Voilà l'été", config.get(u'aä', 'option2'))
        config.save()

        configfile = open(self.filename, 'r')
        self.assertEqual(['# -*- coding: utf-8 -*-\n',
                          '\n',
                          '[aä]\n',
                          "option1 = Voilà l'été\n",
                          "option2 = Voilà l'été\n",
                          'öption0 = x\n',
                          # "option3 = VoilÃ  l'Ã©tÃ©\n",
                          '\n',
                          '[b]\n',
                          'öption0 = y\n',
                          '\n'],
                         configfile.readlines())
        configfile.close()
        config2 = Configuration(self.filename)
        self.assertEqual('x', config2.get(u'aä', u'öption0'))
        self.assertEqual(u"Voilà l'été", config2.get(u'aä', 'option1'))
        self.assertEqual(u"Voilà l'été", config2.get(u'aä', 'option2'))
        # self.assertEqual(u"Voilà l'été", config2.get('a', 'option3'))

    def test_set_and_save_inherit(self):
        def testcb():
            self._write(['[a]', 'option = x'], site=True)
            config = self._read()
            config.set('a', 'option2', "Voilà l'été")  # UTF-8
            config.set('a', 'option1', u"Voilà l'été") # unicode
            self.assertEqual('x', config.get('a', 'option'))
            self.assertEqual(u"Voilà l'été", config.get('a', 'option1'))
            self.assertEqual(u"Voilà l'été", config.get('a', 'option2'))
            config.save()

            configfile = open(self.filename, 'r')
            self.assertEqual(['# -*- coding: utf-8 -*-\n',
                              '\n',
                              '[a]\n',
                              "option1 = Voilà l'été\n",
                              "option2 = Voilà l'été\n",
                              '\n',
                              '[inherit]\n',
                              "file = trac-site.ini\n",
                              '\n'],
                             configfile.readlines())
            configfile.close()
            config2 = Configuration(self.filename)
            self.assertEqual('x', config2.get('a', 'option'))
            self.assertEqual(u"Voilà l'été", config2.get('a', 'option1'))
            self.assertEqual(u"Voilà l'été", config2.get('a', 'option2'))
        self._test_with_inherit(testcb)

    def test_simple_remove(self):
        self._write(['[a]', 'option = x'])
        config = self._read()
        config.get('a', 'option') # populates the cache
        config.set(u'aä', u'öption', u'öne')
        config.remove('a', 'option')
        self.assertEqual('', config.get('a', 'option'))
        config.remove(u'aä', u'öption')
        self.assertEqual('', config.get('aä', 'öption'))
        config.remove('a', 'option2') # shouldn't fail
        config.remove('b', 'option2') # shouldn't fail

    def test_sections(self):
        self._write(['[a]', 'option = x', '[b]', 'option = y'])
        config = self._read()
        self.assertEqual(['a', 'b'], config.sections())

        class Foo(object):
            # enclose in parentheses to avoid messages extraction
            section_c = (ConfigSection)('c', 'Doc for c')
            option_c = Option('c', 'option', 'value')

        self.assertEqual(['a', 'b', 'c'], config.sections())
        foo = Foo()
        foo.config = config
        self.assertTrue(foo.section_c is config['c'])
        self.assertEqual('value', foo.section_c.get('option'))

    def test_sections_unicode(self):
        self._write([u'[aä]', u'öption = x', '[b]', 'option = y'])
        config = self._read()
        self.assertEqual([u'aä', 'b'], config.sections())

        class Foo(object):
            option_c = Option(u'cä', 'option', 'value')

        self.assertEqual([u'aä', 'b', u'cä'], config.sections())

    def test_options(self):
        self._write(['[a]', 'option = x', '[b]', 'option = y'])
        config = self._read()
        self.assertEqual(('option', 'x'), iter(config.options('a')).next())
        self.assertEqual(('option', 'y'), iter(config.options('b')).next())
        self.assertRaises(StopIteration, iter(config.options('c')).next)
        self.assertEqual('option', iter(config['a']).next())
        self.assertEqual('option', iter(config['b']).next())
        self.assertRaises(StopIteration, iter(config['c']).next)

        class Foo(object):
            option_a = Option('a', 'b', 'c')

        self.assertEqual([('option', 'x'), ('b', 'c')],
                         list(config.options('a')))

    def test_options_unicode(self):
        self._write([u'[ä]', u'öption = x', '[b]', 'option = y'])
        config = self._read()
        self.assertEqual((u'öption', 'x'), iter(config.options(u'ä')).next())
        self.assertEqual(('option', 'y'), iter(config.options('b')).next())
        self.assertRaises(StopIteration, iter(config.options('c')).next)
        self.assertEqual(u'öption', iter(config['ä']).next())

        class Foo(object):
            option_a = Option(u'ä', u'öption2', 'c')

        self.assertEqual([(u'öption', 'x'), (u'öption2', 'c')],
                         list(config.options(u'ä')))

    def test_has_option(self):
        config = self._read()
        self.assertFalse(config.has_option('a', 'option'))
        self.assertFalse('option' in config['a'])
        self._write(['[a]', 'option = x'])
        config = self._read()
        self.assertTrue(config.has_option('a', 'option'))
        self.assertTrue('option' in config['a'])

        class Foo(object):
            option_a = Option('a', 'option2', 'x2')

        self.assertTrue(config.has_option('a', 'option2'))

    def test_has_option_unicode(self):
        config = self._read()
        self.assertFalse(config.has_option(u'ä', u'öption'))
        self.assertFalse(u'öption' in config[u'ä'])
        self._write([u'[ä]', u'öption = x'])
        config = self._read()
        self.assertTrue(config.has_option(u'ä', u'öption'))
        self.assertTrue(u'öption' in config[u'ä'])

        class Foo(object):
            option_a = Option(u'ä', u'öption2', 'x2')

        self.assertTrue(config.has_option(u'ä', u'öption2'))

    def test_reparse(self):
        self._write(['[a]', 'option = x'])
        config = self._read()
        self.assertEqual('x', config.get('a', 'option'))

        self._write(['[a]', 'option = y'])
        config.parse_if_needed()
        self.assertEqual('y', config.get('a', 'option'))

    def test_inherit_reparse(self):
        def testcb():
            self._write(['[a]', 'option = x'], site=True)
            config = self._read()
            self.assertEqual('x', config.get('a', 'option'))

            self._write(['[a]', 'option = y'], site=True)
            config.parse_if_needed()
            self.assertEqual('y', config.get('a', 'option'))
        self._test_with_inherit(testcb)

    def test_inherit_one_level(self):
        def testcb():
            self._write(['[a]', 'option = x'], site=True)
            config = self._read()
            self.assertEqual('x', config.get('a', 'option'))
            self.assertEqual(['a', 'inherit'], config.sections())
            config.remove('a', 'option') # Should *not* remove option in parent
            self.assertEqual('x', config.get('a', 'option'))
            self.assertEqual([('option', 'x')], list(config.options('a')))
            self.assertTrue('a' in config)
        self._test_with_inherit(testcb)

    def test_inherit_multiple(self):
        class Foo(object):
            option_b = Option('b', 'option2', 'default')
        base = os.path.dirname(self.filename)
        relsite1 = os.path.join('sub1', 'trac-site1.ini')
        site1 = os.path.join(base, relsite1)
        relsite2 = os.path.join('sub2', 'trac-site2.ini')
        site2 = os.path.join(base, relsite2)
        os.mkdir(os.path.dirname(site1))
        create_file(site1, '[a]\noption1 = x\n'
                           '[c]\noption = 1\npath1 = site1\n')
        try:
            os.mkdir(os.path.dirname(site2))
            create_file(site2, '[b]\noption2 = y\n'
                               '[c]\noption = 2\npath2 = site2\n')
            try:
                self._write(['[inherit]',
                             'file = %s, %s' % (relsite1, relsite2)])
                config = self._read()
                self.assertEqual('x', config.get('a', 'option1'))
                self.assertEqual('y', config.get('b', 'option2'))
                self.assertEqual('1', config.get('c', 'option'))
                self.assertEqual(os.path.join(base, 'site1'),
                                 config.getpath('c', 'path1'))
                self.assertEqual(os.path.join(base, 'site2'),
                                 config.getpath('c', 'path2'))
                self.assertEqual('',
                                 config.getpath('c', 'path3'))
                self.assertEqual(os.path.join(base, 'site4'),
                                 config.getpath('c', 'path4', 'site4'))
            finally:
                os.remove(site2)
                os.rmdir(os.path.dirname(site2))
        finally:
            os.remove(site1)
            os.rmdir(os.path.dirname(site1))

    def test_option_with_raw_default(self):
        class Foo(object):
            # enclose in parentheses to avoid messages extraction
            option_none = (Option)('a', 'none', None)
            option_blah = (Option)('a', 'blah', u'Blàh!')
            option_true = (BoolOption)('a', 'true', True)
            option_false = (BoolOption)('a', 'false', False)
            option_list = (ListOption)('a', 'list', ['#cc0', 4.2, 42L, 0, None,
                                                     True, False, None],
                                       sep='|')
            option_choice = (ChoiceOption)('a', 'choice', [-42, 42])

        config = self._read()
        config.set_defaults()
        config.save()
        with open(self.filename, 'r') as f:
            self.assertEqual('# -*- coding: utf-8 -*-\n',            f.next())
            self.assertEqual('\n',                                   f.next())
            self.assertEqual('[a]\n',                                f.next())
            self.assertEqual('blah = Blàh!\n',                       f.next())
            self.assertEqual('choice = -42\n',                       f.next())
            self.assertEqual('false = disabled\n',                   f.next())
            self.assertEqual('list = #cc0|4.2|42|0||enabled|disabled|\n',
                             f.next())
            self.assertEqual('# none = <inherited>\n',               f.next())
            self.assertEqual('true = enabled\n',                     f.next())
            self.assertEqual('\n',                                   f.next())
            self.assertRaises(StopIteration, f.next)

    def test_unicode_option_with_raw_default(self):
        class Foo(object):
            # enclose in parentheses to avoid messages extraction
            option_none = (Option)(u'résumé', u'nöné', None)
            option_blah = (Option)(u'résumé', u'bláh', u'Blàh!')
            option_true = (BoolOption)(u'résumé', u'trüé', True)
            option_false = (BoolOption)(u'résumé', u'fálsé', False)
            option_list = (ListOption)(u'résumé', u'liśt',
                                       [u'#ccö', 4.2, 42L, 0, None, True,
                                        False, None],
                                       sep='|')
            option_choice = (ChoiceOption)(u'résumé', u'chöicé', [-42, 42])

        config = self._read()
        config.set_defaults()
        config.save()
        with open(self.filename, 'r') as f:
            self.assertEqual('# -*- coding: utf-8 -*-\n',            f.next())
            self.assertEqual('\n',                                   f.next())
            self.assertEqual('[résumé]\n',                           f.next())
            self.assertEqual('bláh = Blàh!\n',                       f.next())
            self.assertEqual('chöicé = -42\n',                       f.next())
            self.assertEqual('fálsé = disabled\n',                   f.next())
            self.assertEqual('liśt = #ccö|4.2|42|0||enabled|disabled|\n',
                             f.next())
            self.assertEqual('# nöné = <inherited>\n',               f.next())
            self.assertEqual('trüé = enabled\n',                     f.next())
            self.assertEqual('\n',                                   f.next())
            self.assertRaises(StopIteration, f.next)

    def test_save_changes_mtime(self):
        """Test that each save operation changes the file modification time."""
        class Foo(object):
            IntOption('section', 'option', 1)
        sconfig = self._read()
        sconfig.set_defaults()
        sconfig.save()
        rconfig = self._read()
        self.assertEqual(1, rconfig.getint('section', 'option'))
        sconfig.set('section', 'option', 2)
        time.sleep(1.0 - time_now() % 1.0)
        sconfig.save()
        rconfig.parse_if_needed()
        self.assertEqual(2, rconfig.getint('section', 'option'))

    def test_touch_changes_mtime(self):
        """Test that each touch command changes the file modification time."""
        config = self._read()
        time.sleep(1.0 - time_now() % 1.0)
        config.touch()
        mtime = os.stat(self.filename).st_mtime
        config.touch()
        self.assertNotEqual(mtime, os.stat(self.filename).st_mtime)

    def _test_with_inherit(self, testcb):
        try:
            self._write(['[inherit]', 'file = trac-site.ini'])
            testcb()
        finally:
            os.remove(self.sitename)


def suite():
    return unittest.makeSuite(ConfigurationTestCase)

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
