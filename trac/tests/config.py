# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2018 Edgewall Software
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

import contextlib
import os
import tempfile
import time
import unittest

import trac.tests.compat
from trac.config import *
from trac.config import UnicodeConfigParser
from trac.core import Component, ComponentMeta, Interface, implements
from trac.test import Configuration, EnvironmentStub, rmtree
from trac.util import create_file, read_file
from trac.util.compat import wait_for_file_mtime_change
from trac.util.datefmt import time_now


def _write(filename, lines):
    wait_for_file_mtime_change(filename)
    create_file(filename, '\n'.join(lines + ['']).encode('utf-8'))


def _read(filename):
    return read_file(filename).decode('utf-8')


def readlines(filename):
    with open(filename, 'r') as f:
        return f.readlines()


class UnicodeParserTestCase(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.filename = os.path.join(self.tempdir, 'config.ini')
        _write(self.filename, [
            u'[ä]', u'öption = ÿ',
            u'[ä]', u'optīon = 1.1',
            u'[č]', u'ôption = ž',
            u'[č]', u'optïon = 1',
            u'[ė]', u'optioñ = true',
        ])
        self.parser = UnicodeConfigParser()
        self._read()

    def tearDown(self):
        rmtree(self.tempdir)

    def _write(self):
        with open(self.filename, 'w') as f:
            self.parser.write(f)

    def _read(self):
        self.parser.read(self.filename)

    def test_sections(self):
        self.assertEqual([u'ä', u'č', u'ė'], self.parser.sections())

    def test_add_section(self):
        self.parser.add_section(u'ē')
        self._write()
        self.assertEqual(
            u'[ä]\n'
            u'öption = ÿ\n'
            u'optīon = 1.1\n\n'
            u'[č]\n'
            u'ôption = ž\n'
            u'optïon = 1\n\n'
            u'[ė]\n'
            u'optioñ = true\n\n'
            u'[ē]\n\n', _read(self.filename))

    def test_has_section(self):
        self.assertTrue(self.parser.has_section(u'ä'))
        self.assertTrue(self.parser.has_section(u'č'))
        self.assertTrue(self.parser.has_section(u'ė'))
        self.assertFalse(self.parser.has_section(u'î'))

    def test_options(self):
        self.assertEqual([u'öption', u'optīon'], self.parser.options(u'ä'))
        self.assertEqual([u'ôption', u'optïon'], self.parser.options(u'č'))

    def test_get(self):
        self.assertEqual(u'ÿ', self.parser.get(u'ä', u'öption'))
        self.assertEqual(u'ž', self.parser.get(u'č', u'ôption'))

    def test_items(self):
        self.assertEqual([(u'öption', u'ÿ'), (u'optīon', u'1.1')],
                          self.parser.items(u'ä'))
        self.assertEqual([(u'ôption', u'ž'), (u'optïon', u'1')],
                         self.parser.items(u'č'))

    def test_getint(self):
        self.assertEqual(1, self.parser.getint(u'č', u'optïon'))

    def test_getfloat(self):
        self.assertEqual(1.1, self.parser.getfloat(u'ä', u'optīon'))

    def test_getboolean(self):
        self.assertTrue(self.parser.getboolean(u'ė', u'optioñ'))

    def test_has_option(self):
        self.assertTrue(self.parser.has_option(u'ä', u'öption'))
        self.assertTrue(self.parser.has_option(u'ä', u'optīon'))
        self.assertTrue(self.parser.has_option(u'č', u'ôption'))
        self.assertTrue(self.parser.has_option(u'č', u'optïon'))
        self.assertTrue(self.parser.has_option(u'ė', u'optioñ'))
        self.assertFalse(self.parser.has_option(u'î', u'optioñ'))

    def test_set(self):
        self.parser.set(u'ä', u'öption', u'ù')
        self.parser.set(u'ė', u'optiœn', None)
        self._write()
        self.assertEqual(
            u'[ä]\n'
            u'öption = ù\n'
            u'optīon = 1.1\n\n'
            u'[č]\n'
            u'ôption = ž\n'
            u'optïon = 1\n\n'
            u'[ė]\n'
            u'optioñ = true\n'
            u'optiœn = \n\n', _read(self.filename))

    def test_remove_option(self):
        self.parser.remove_option(u'ä', u'öption')
        self.parser.remove_option(u'ė', u'optioñ')
        self._write()
        self.assertEqual(
            u'[ä]\n'
            u'optīon = 1.1\n\n'
            u'[č]\n'
            u'ôption = ž\n'
            u'optïon = 1\n\n'
            u'[ė]\n\n', _read(self.filename))

    def test_remove_section(self):
        self.parser.remove_section(u'ä')
        self.parser.remove_section(u'ė')
        self._write()
        self.assertEqual(
            u'[č]\n'
            u'ôption = ž\n'
            u'optïon = 1\n\n', _read(self.filename))


class BaseTestCase(unittest.TestCase):

    def setUp(self):
        tmpdir = os.path.realpath(tempfile.gettempdir())
        self.filename = os.path.join(tmpdir, 'trac-test.ini')
        self.sitename = os.path.join(tmpdir, 'trac-site.ini')
        self.env = EnvironmentStub()
        self._write([])
        self._orig = {
            'ComponentMeta._components': ComponentMeta._components,
            'ComponentMeta._registry': ComponentMeta._registry,
            'ConfigSection.registry': ConfigSection.registry,
            'Option.registry': Option.registry,
        }
        ComponentMeta._components = list(ComponentMeta._components)
        ComponentMeta._registry = dict((interface, list(classes))
                                       for interface, classes
                                       in ComponentMeta._registry.iteritems())
        ConfigSection.registry = {}
        Option.registry = {}

    def tearDown(self):
        ComponentMeta._components = self._orig['ComponentMeta._components']
        ComponentMeta._registry = self._orig['ComponentMeta._registry']
        ConfigSection.registry = self._orig['ConfigSection.registry']
        Option.registry = self._orig['Option.registry']
        os.remove(self.filename)
        if os.path.exists(self.sitename):
            os.remove(self.sitename)

    def _read(self):
        return Configuration(self.filename)

    def _write(self, lines, site=False):
        filename = self.sitename if site else self.filename
        _write(filename, lines)

    @contextlib.contextmanager
    def inherited_file(self):
        try:
            self._write(['[inherit]', 'file = trac-site.ini'])
            yield
        finally:
            os.remove(self.sitename)


class ConfigurationTestCase(unittest.TestCase):

    def setUp(self):
        self.config = Configuration(None)
        self.config.parser.add_section(u'séction1')
        self.config.parser.set(u'séction1', u'öption1', u'cönfig-valué')
        self.config.parser.set(u'séction1', u'öption4', u'cönfig-valué')
        parent_config = Configuration(None)
        parent_config.parser.add_section(u'séction1')
        parent_config.parser.add_section(u'séction2')
        parent_config.parser.set(u'séction1', u'öption1', u'cönfig-valué')
        parent_config.parser.set(u'séction1', u'öption2', u'înherited-valué')
        parent_config.parser.set(u'séction2', u'öption2', u'înherited-valué')
        self.config.parents = [parent_config]

        class OptionClass(object):
            Option(u'séction1', u'öption1', u'dēfault-valué')
            Option(u'séction1', u'öption2', u'dēfault-valué')
            Option(u'séction1', u'öption3', u'dēfault-valué')
            Option(u'séction3', u'öption1', u'dēfault-valué')
            ConfigSection(u'séction4', u"Séction 4")

    def test_get_from_config(self):
        """Value is retrieved from the config."""
        self.assertEqual(u'cönfig-valué',
                         self.config.get(u'séction1', u'öption1'))

    def test_get_from_inherited(self):
        """Value not specified in the config is retrieved from the
        inherited config.
        """
        self.assertEqual(u'înherited-valué',
                         self.config.get(u'séction1', u'öption2'))

    def test_get_from_default(self):
        """Value not specified in the config or the inherited config
        is retrieved from the option default.
        """
        self.assertEqual(u'dēfault-valué',
                         self.config.get(u'séction1', u'öption3'))

    def test_get_is_cached(self):
        """Value is cached on first retrieval from the parser."""
        option1 = self.config.get(u'séction1', u'öption1')
        self.config.parser.set(u'séction1', u'öption1', u'cönfig-valué2')
        self.assertIs(self.config.get(u'séction1', u'öption1'), option1)

    def test_contains_from_config(self):
        """Contains returns `True` for section defined in config."""
        self.assertTrue(u'séction1' in self.config)

    def test_contains_from_inherited(self):
        """Contains returns `True` for section defined in inherited config."""
        self.assertTrue(u'séction2' in self.config)

    def test_contains_from_default(self):
        """Contains returns `True` for section defined in an option."""
        self.assertTrue(u'séction3' in self.config)

    def test_sections_with_default(self):
        """Sections including defaults."""
        sections = self.config.sections()
        self.assertIn(u'séction1', sections)
        self.assertIn(u'séction2', sections)
        self.assertIn(u'séction3', sections)
        self.assertNotIn(u'séction4', sections)

    def test_sections_without_default(self):
        """Sections without defaults."""
        sections = self.config.sections(defaults=False)
        self.assertIn(u'séction1', sections)
        self.assertIn(u'séction2', sections)
        self.assertNotIn(u'séction3', sections)
        self.assertNotIn(u'séction4', sections)

    def test_sections_with_empty(self):
        """Sections including empty."""
        sections = self.config.sections(defaults=False, empty=True)
        self.assertNotIn(u'séction3', sections)
        self.assertIn(u'séction4', sections)

    def test_remove_from_config(self):
        """Value is removed from configuration."""
        self.config.remove(u'séction1', u'öption4')
        parser = self.config.parser
        self.assertFalse(parser.has_option(u'séction1', u'öption4'))
        self.assertEqual('', self.config.get(u'séction1', u'öption4'))

    def test_remove_leaves_inherited_unchanged(self):
        """Value is not removed from inherited configuration."""
        self.config.remove(u'séction1', u'öption2')
        parser = self.config.parents[0].parser
        self.assertTrue(parser.has_option(u'séction1', u'öption1'))
        self.assertEqual(u'înherited-valué',
                         self.config.get(u'séction1', u'öption2'))


class IntegrationTestCase(BaseTestCase):

    def test_repr(self):
        self.assertEqual('<Configuration None>', repr(Configuration(None)))
        config = self._read()
        self.assertEqual("<Configuration %r>" % self.filename, repr(config))

    def test_default(self):
        config = self._read()
        self.assertEqual('', config.get('a', 'option'))
        self.assertEqual('value', config.get('a', 'option', 'value'))

        class Foo(object):
            str_option = Option('a', 'option', 'value')
            none_option = Option('b', 'option', None)
            int_option = IntOption('b', 'int_option', 0)
            bool_option = BoolOption('b', 'bool_option', False)
            float_option = FloatOption('b', 'float_option', 0.0)
            list_option = ListOption('b', 'list_option', [])

        self.assertEqual('value', config.get('a', 'option'))
        self.assertEqual('', config.get('b', 'option'))
        self.assertEqual('0', config.get('b', 'int_option'))
        self.assertEqual('disabled', config.get('b', 'bool_option'))
        self.assertEqual('0.0', config.get('b', 'float_option'))
        self.assertEqual('', config.get('b', 'list_option'))

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

    def test_read_and_getlist_multi_seps(self):
        self._write(['[a]', 'option = 42 foo,bar||baz,||blah'])
        config = self._read()

        expected = ['42', 'foo', 'bar', 'baz', 'blah']
        self.assertEqual(expected, config.getlist('a', 'option', '',
                                                  sep=(' ', ',', '||')))
        self.assertEqual(expected, config.getlist('a', 'option', '',
                                                  sep=[' ', ',', '||']))

        self.assertEqual(['42', 'foo', 'bar', 'baz', '', 'blah'],
                         config.getlist('a', 'option', '',
                                        sep=(' ', ',', '||'),
                                        keep_empty=True))

        expected = ['42 foo,bar', 'baz,', 'blah']
        self.assertEqual(expected, config.getlist('a', 'option', '',
                                                  sep=['||']))
        self.assertEqual(expected, config.getlist('a', 'option', '', sep='||'))

    def test_read_and_choice(self):
        self._write(['[a]', 'option = 2', 'invalid = d', 'case-insensitive = b',
                     u'[û]', u'èncoded = à'])
        config = self._read()

        class Foo(object):
            option = ChoiceOption('a', 'option', ['Item1', 2, '3'])
            other = ChoiceOption('a', 'other', [1, 2, 3])
            invalid = ChoiceOption('a', 'invalid', ['a', 'b', 'c'])
            encoded = ChoiceOption('a', u'èncoded', [u'à', u'ć', u'ē'])
            case_insensitive = ChoiceOption('a', 'case-insensitive',
                                            ['A', 'B', 'C'],
                                            case_sensitive=False)

            def __init__(self):
                self.config = config

        foo = Foo()
        self.assertEqual('2', foo.option)
        self.assertEqual('1', foo.other)
        self.assertRaises(ConfigurationError, getattr, foo, 'invalid')
        self.assertEqual(u'à', foo.encoded)
        config.set('a', u'èncoded', u'ć')
        self.assertEqual(u'ć', foo.encoded)
        self.assertEqual('B', foo.case_insensitive)

    def test_read_and_getextensionoption(self):
        self._write(['[a]', 'option = ImplA', 'invalid = ImplB'])
        config = self._read()

        class IDummy(Interface):
            pass

        class ImplA(Component):
            implements(IDummy)

        class Foo(Component):
            default1 = ExtensionOption('a', 'default1', IDummy)
            default2 = ExtensionOption('a', 'default2', IDummy, 'ImplA')
            default3 = ExtensionOption('a', 'default3', IDummy, 'ImplB')
            option = ExtensionOption('a', 'option', IDummy)
            option2 = ExtensionOption('a', 'option', IDummy, 'ImplB')
            invalid = ExtensionOption('a', 'invalid', IDummy)

            def __init__(self):
                self.config = config

        self.env.enable_component(ImplA)
        self.env.enable_component(Foo)

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
            default1 = OrderedExtensionsOption('a', 'default1', IDummy,
                                               include_missing=False)
            default2 = OrderedExtensionsOption('a', 'default2', IDummy)
            default3 = OrderedExtensionsOption('a', 'default3', IDummy,
                                               'ImplB, ImplC',
                                               include_missing=False)
            option = OrderedExtensionsOption('a', 'option', IDummy,
                                             include_missing=False)
            invalid = OrderedExtensionsOption('a', 'invalid', IDummy)

            def __init__(self):
                self.config = config

        self.env.enable_component(ImplA)
        self.env.enable_component(ImplB)
        self.env.enable_component(ImplC)
        self.env.enable_component(Foo)

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
        section = config['b']
        section.set('option1', None)
        section = config[u'aä']
        section.set('öption1', 'z')
        section.set('öption2', None)
        # Note: the following would depend on the locale.getpreferredencoding()
        # config.set('a', 'option3', "Voil\xe0 l'\xe9t\xe9") # latin-1
        self.assertEqual('x', config.get(u'aä', u'öption0'))
        self.assertEqual(u"Voilà l'été", config.get(u'aä', 'option1'))
        self.assertEqual(u"Voilà l'été", config.get(u'aä', 'option2'))
        self.assertEqual('', config.get('b', 'option1'))
        self.assertEqual('z', config.get(u'aä', 'öption1'))
        self.assertEqual('', config.get(u'aä', 'öption2'))
        config.save()

        self.assertEqual(['# -*- coding: utf-8 -*-\n',
                          '\n',
                          '[aä]\n',
                          "option1 = Voilà l'été\n",
                          "option2 = Voilà l'été\n",
                          'öption0 = x\n',
                          'öption1 = z\n',
                          'öption2 = \n',
                          # "option3 = VoilÃ  l'Ã©tÃ©\n",
                          '\n',
                          '[b]\n',
                          'option1 = \n',
                          'öption0 = y\n',
                          '\n'], readlines(self.filename))
        config2 = Configuration(self.filename)
        self.assertEqual('x', config2.get(u'aä', u'öption0'))
        self.assertEqual(u"Voilà l'été", config2.get(u'aä', 'option1'))
        self.assertEqual(u"Voilà l'été", config2.get(u'aä', 'option2'))
        # self.assertEqual(u"Voilà l'été", config2.get('a', 'option3'))

    def test_set_and_save_inherit(self):
        with self.inherited_file():
            self._write(['[a]', 'option = x'], site=True)
            config = self._read()
            config.set('a', 'option2', "Voilà l'été")  # UTF-8
            config.set('a', 'option1', u"Voilà l'été") # unicode
            self.assertEqual('x', config.get('a', 'option'))
            self.assertEqual(u"Voilà l'été", config.get('a', 'option1'))
            self.assertEqual(u"Voilà l'été", config.get('a', 'option2'))
            config.save()

            self.assertEqual(['# -*- coding: utf-8 -*-\n',
                              '\n',
                              '[a]\n',
                              "option1 = Voilà l'été\n",
                              "option2 = Voilà l'été\n",
                              '\n',
                              '[inherit]\n',
                              "file = trac-site.ini\n",
                              '\n'], readlines(self.filename))
            config2 = Configuration(self.filename)
            self.assertEqual('x', config2.get('a', 'option'))
            self.assertEqual(u"Voilà l'été", config2.get('a', 'option1'))
            self.assertEqual(u"Voilà l'été", config2.get('a', 'option2'))

    def test_set_and_save_inherit_remove_matching(self):
        """Options with values matching the inherited value are removed from
        the base configuration.
        """
        with self.inherited_file():
            self._write(['[a]', u'ôption = x'], site=True)
            config = self._read()
            self.assertEqual('x', config.get('a', u'ôption'))
            config.save()

            self.assertEqual(
                '# -*- coding: utf-8 -*-\n'
                '\n'
                '[inherit]\n'
                'file = trac-site.ini\n'
                '\n', read_file(self.filename))

            config.set('a', u'ôption', 'y')
            config.save()

            self.assertEqual(
                '# -*- coding: utf-8 -*-\n'
                '\n'
                '[a]\n'
                'ôption = y\n'
                '\n'
                '[inherit]\n'
                'file = trac-site.ini\n'
                '\n', read_file(self.filename))

            config.set('a', u'ôption', 'x')
            config.save()
            self.assertEqual(
                '# -*- coding: utf-8 -*-\n'
                '\n'
                '[inherit]\n'
                'file = trac-site.ini\n'
                '\n', read_file(self.filename))

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
            section_c = ConfigSection('c', 'Doc for c')
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
        with self.inherited_file():
            self._write(['[a]', 'option = x'], site=True)
            config = self._read()
            self.assertEqual('x', config.get('a', 'option'))

            self._write(['[a]', 'option = y'], site=True)
            config.parse_if_needed()
            self.assertEqual('y', config.get('a', 'option'))

    def test_inherit_one_level(self):
        with self.inherited_file():
            self._write(['[a]', 'option = x'], site=True)
            config = self._read()
            self.assertEqual('x', config.get('a', 'option'))
            self.assertEqual(['a', 'inherit'], config.sections())
            config.remove('a', 'option') # Should *not* remove option in parent
            self.assertEqual('x', config.get('a', 'option'))
            self.assertEqual([('option', 'x')], list(config.options('a')))
            self.assertTrue('a' in config)

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
            option_none = Option('a', 'none', None)
            option_blah = Option('a', 'blah', u'Blàh!')
            option_true = BoolOption('a', 'true', True)
            option_false = BoolOption('a', 'false', False)
            option_list1 = ListOption('a', 'list', ['#cc0', 4.2, 42L, 0, None,
                                                    True, False, None],
                                      sep='|', keep_empty=True)
            option_list2 = ListOption('a', 'list-seps',
                                      ['#cc0', 4.2, 42L, 0, None, True, False,
                                       None],
                                      sep=(',', '|'), keep_empty=True)
            option_choice = ChoiceOption('a', 'choice', [-42, 42])

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
            self.assertEqual('list-seps = #cc0,4.2,42,0,,enabled,disabled,\n',
                             f.next())
            self.assertEqual('none = \n',                            f.next())
            self.assertEqual('true = enabled\n',                     f.next())
            self.assertEqual('\n',                                   f.next())
            self.assertRaises(StopIteration, f.next)

    def test_unicode_option_with_raw_default(self):
        class Foo(object):
            option_none = Option(u'résumé', u'nöné', None)
            option_blah = Option(u'résumé', u'bláh', u'Blàh!')
            option_true = BoolOption(u'résumé', u'trüé', True)
            option_false = BoolOption(u'résumé', u'fálsé', False)
            option_list = ListOption(u'résumé', u'liśt',
                                     [u'#ccö', 4.2, 42L, 0, None, True,
                                        False, None],
                                     sep='|', keep_empty=True)
            option_choice = ChoiceOption(u'résumé', u'chöicé', [-42, 42])

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
            self.assertEqual('nöné = \n',                            f.next())
            self.assertEqual('trüé = enabled\n',                     f.next())
            self.assertEqual('\n',                                   f.next())
            self.assertRaises(StopIteration, f.next)

    def test_option_with_non_normal_default(self):
        class Foo(object):
            option_int_0 = IntOption('a', 'int-0', 0)
            option_float_0 = FloatOption('a', 'float-0', 0)
            option_bool_1 = BoolOption('a', 'bool-1', '1')
            option_bool_0 = BoolOption('a', 'bool-0', '0')
            option_bool_yes = BoolOption('a', 'bool-yes', 'yes')
            option_bool_no = BoolOption('a', 'bool-no', 'no')

        expected = [
            '# -*- coding: utf-8 -*-\n',
            '\n',
            '[a]\n',
            'bool-0 = disabled\n',
            'bool-1 = enabled\n',
            'bool-no = disabled\n',
            'bool-yes = enabled\n',
            'float-0 = 0.0\n',
            'int-0 = 0\n',
            '\n',
        ]

        config = self._read()
        config.set_defaults()
        config.save()
        self.assertEqual(expected, readlines(self.filename))

        config.set('a', 'bool-1', 'True')
        config.save()
        self.assertEqual(expected, readlines(self.filename))

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


class ConfigurationSetDefaultsTestCase(BaseTestCase):
    """Tests for the `set_defaults` method of the `Configuration` class."""

    def setUp(self):
        super(ConfigurationSetDefaultsTestCase, self).setUp()

        class CompA(Component):
            opt1 = Option('compa', 'opt1', 1)
            opt2 = Option('compa', 'opt2', 'a')

        class CompB(Component):
            opt3 = Option('compb', 'opt3', 2)
            opt4 = Option('compb', 'opt4', 'b')

    def test_component_module_no_match(self):
        """No defaults written if component doesn't match."""
        config = self._read()
        config.set_defaults(component='trac.tests.conf')
        config.save()

        with open(self.filename, 'r') as f:
            self.assertEqual('# -*- coding: utf-8 -*-\n', f.next())
            self.assertEqual('\n',                        f.next())
            self.assertRaises(StopIteration, f.next)

    def test_component_class_no_match(self):
        """No defaults written if module doesn't match."""
        config = self._read()
        config.set_defaults(component='trac.tests.conf.CompC')
        config.save()

        with open(self.filename, 'r') as f:
            self.assertEqual('# -*- coding: utf-8 -*-\n', f.next())
            self.assertEqual('\n',                        f.next())
            self.assertRaises(StopIteration, f.next)

    def test_component_module_match(self):
        """Defaults of components in matching module are written."""
        config = self._read()
        config.set_defaults(component='trac.tests.config')
        config.save()

        with open(self.filename, 'r') as f:
            self.assertEqual('# -*- coding: utf-8 -*-\n', f.next())
            self.assertEqual('\n',                        f.next())
            self.assertEqual('[compa]\n',                 f.next())
            self.assertEqual('opt1 = 1\n',                f.next())
            self.assertEqual('opt2 = a\n',                f.next())
            self.assertEqual('\n',                        f.next())
            self.assertEqual('[compb]\n',                 f.next())
            self.assertEqual('opt3 = 2\n',                f.next())
            self.assertEqual('opt4 = b\n',                f.next())
            self.assertEqual('\n',                        f.next())
            self.assertRaises(StopIteration, f.next)

    def test_component_module_wildcard_match(self):
        """Defaults of components in matching module are written.
        Trailing dot-star are stripped in performing match.
        """
        config = self._read()
        config.set_defaults(component='trac.tests.config.*')
        config.save()

        with open(self.filename, 'r') as f:
            self.assertEqual('# -*- coding: utf-8 -*-\n', f.next())
            self.assertEqual('\n',                        f.next())
            self.assertEqual('[compa]\n',                 f.next())
            self.assertEqual('opt1 = 1\n',                f.next())
            self.assertEqual('opt2 = a\n',                f.next())
            self.assertEqual('\n',                        f.next())
            self.assertEqual('[compb]\n',                 f.next())
            self.assertEqual('opt3 = 2\n',                f.next())
            self.assertEqual('opt4 = b\n',                f.next())
            self.assertEqual('\n',                        f.next())
            self.assertRaises(StopIteration, f.next)

    def test_component_class_match(self):
        """Defaults of matching component are written."""
        config = self._read()
        config.set_defaults(component='trac.tests.config.CompA')
        config.save()

        with open(self.filename, 'r') as f:
            self.assertEqual('# -*- coding: utf-8 -*-\n', f.next())
            self.assertEqual('\n',                        f.next())
            self.assertEqual('[compa]\n',                 f.next())
            self.assertEqual('opt1 = 1\n',                f.next())
            self.assertEqual('opt2 = a\n',                f.next())
            self.assertEqual('\n',                        f.next())
            self.assertRaises(StopIteration, f.next)

    def test_component_no_overwrite(self):
        """Values in configuration are not overwritten."""
        config = self._read()
        config.set('compa', 'opt1', 3)
        config.save()
        config.set_defaults(component='trac.tests.config.CompA')
        config.save()

        with open(self.filename, 'r') as f:
            self.assertEqual('# -*- coding: utf-8 -*-\n', f.next())
            self.assertEqual('\n',                        f.next())
            self.assertEqual('[compa]\n',                 f.next())
            self.assertEqual('opt1 = 3\n',                f.next())
            self.assertEqual('opt2 = a\n',                f.next())
            self.assertEqual('\n',                        f.next())
            self.assertRaises(StopIteration, f.next)

    def test_component_no_overwrite_parent(self):
        """Values in parent configuration are not overwritten."""
        parent_config = Configuration(self.sitename)
        parent_config.set('compa', 'opt1', 3)
        parent_config.save()
        config = self._read()
        config.set('inherit', 'file', 'trac-site.ini')
        config.save()
        config.parse_if_needed(True)
        config.set_defaults(component='trac.tests.config.CompA')
        config.save()

        with open(self.sitename, 'r') as f:
            self.assertEqual('# -*- coding: utf-8 -*-\n', f.next())
            self.assertEqual('\n',                        f.next())
            self.assertEqual('[compa]\n',                 f.next())
            self.assertEqual('opt1 = 3\n',                f.next())
            self.assertEqual('\n',                        f.next())
            self.assertRaises(StopIteration, f.next)

        with open(self.filename, 'r') as f:
            self.assertEqual('# -*- coding: utf-8 -*-\n', f.next())
            self.assertEqual('\n',                        f.next())
            self.assertEqual('[compa]\n',                 f.next())
            self.assertEqual('opt2 = a\n',                f.next())
            self.assertEqual('\n',                        f.next())
            self.assertEqual('[inherit]\n',               f.next())
            self.assertEqual('file = trac-site.ini\n',    f.next())
            self.assertEqual('\n',                        f.next())
            self.assertRaises(StopIteration, f.next)


class OptionDocTestCase(BaseTestCase):

    def test_config_section(self):
        class Dummy(object):
            section_a = ConfigSection('a', 'Doc for a')
            section_b = ConfigSection(
                'b', 'Doc for [%(page)s@%(version)d b]',
                doc_args={'page': 'WikiStart', 'version': 42})
            section_c = ConfigSection('c', '')

        self.assertEqual('Doc for a', Dummy.section_a.__doc__)
        self.assertEqual(None, Dummy.section_a.doc_args)
        self.assertEqual('Doc for a', Dummy.section_a.doc)
        self.assertEqual('Doc for [%(page)s@%(version)d b]',
                         Dummy.section_b.__doc__)
        self.assertEqual({'page': 'WikiStart', 'version': 42},
                         Dummy.section_b.doc_args)
        self.assertEqual('Doc for [WikiStart@42 b]', Dummy.section_b.doc)
        self.assertEqual('', Dummy.section_c.__doc__)
        self.assertEqual(None, Dummy.section_c.doc_args)
        self.assertEqual('', Dummy.section_c.doc)

    def test_options(self):
        class IDummy(Interface):
            pass
        class Dummy(Component):
            implements(IDummy)
            opt_nodoc = Option('a', 'option_nodoc', 'default')
            opt = Option(
                'a', 'option', 'default',
                doc='Doc for %(name)s', doc_args={'name': 'opt'})
            bool_opt = BoolOption(
                'a', 'bool_opt', 'false',
                doc='Doc for %(name)s', doc_args={'name': 'bool_opt'})
            int_opt = IntOption(
                'a', 'int_opt', '42',
                doc='Doc for %(name)s', doc_args={'name': 'int_opt'})
            float_opt = IntOption(
                'a', 'float_opt', '4.2',
                doc='Doc for %(name)s', doc_args={'name': 'float_opt'})
            list_opt = ListOption(
                'a', 'list_opt', 'foo,bar,baz',
                doc='Doc for %(name)s', doc_args={'name': 'list_opt'})
            path_opt = PathOption(
                'a', 'path_opt', 'trac.ini',
                doc='Doc for %(name)s', doc_args={'name': 'path_opt'})
            ext_opt = ExtensionOption(
                'a', 'ext_opt', IDummy, 'Dummy',
                doc='Doc for %(name)s', doc_args={'name': 'ext_opt'})
            ordered_ext_opt = OrderedExtensionsOption(
                'a', 'ordered_ext_opt', IDummy, 'Dummy,Dummy',
                doc='Doc for %(name)s', doc_args={'name': 'ordered_ext_opt'})

        self.assertEqual('', Dummy.opt_nodoc.__doc__)
        self.assertEqual(None, Dummy.opt_nodoc.doc_args)
        self.assertEqual('', Dummy.opt_nodoc.doc)
        self.assertEqual('Doc for %(name)s', Dummy.opt.__doc__)
        self.assertEqual({'name': 'opt'}, Dummy.opt.doc_args)
        self.assertEqual('Doc for opt', Dummy.opt.doc)
        self.assertEqual('Doc for %(name)s', Dummy.bool_opt.__doc__)
        self.assertEqual({'name': 'bool_opt'}, Dummy.bool_opt.doc_args)
        self.assertEqual('Doc for bool_opt', Dummy.bool_opt.doc)
        self.assertEqual('Doc for %(name)s', Dummy.int_opt.__doc__)
        self.assertEqual({'name': 'int_opt'}, Dummy.int_opt.doc_args)
        self.assertEqual('Doc for int_opt', Dummy.int_opt.doc)
        self.assertEqual('Doc for %(name)s', Dummy.float_opt.__doc__)
        self.assertEqual({'name': 'float_opt'}, Dummy.float_opt.doc_args)
        self.assertEqual('Doc for float_opt', Dummy.float_opt.doc)
        self.assertEqual('Doc for %(name)s', Dummy.list_opt.__doc__)
        self.assertEqual({'name': 'list_opt'}, Dummy.list_opt.doc_args)
        self.assertEqual('Doc for list_opt', Dummy.list_opt.doc)
        self.assertEqual('Doc for %(name)s', Dummy.path_opt.__doc__)
        self.assertEqual({'name': 'path_opt'}, Dummy.path_opt.doc_args)
        self.assertEqual('Doc for path_opt', Dummy.path_opt.doc)
        self.assertEqual('Doc for %(name)s', Dummy.ext_opt.__doc__)
        self.assertEqual({'name': 'ext_opt'}, Dummy.ext_opt.doc_args)
        self.assertEqual('Doc for ext_opt', Dummy.ext_opt.doc)
        self.assertEqual('Doc for %(name)s', Dummy.ordered_ext_opt.__doc__)
        self.assertEqual({'name': 'ordered_ext_opt'},
                         Dummy.ordered_ext_opt.doc_args)
        self.assertEqual('Doc for ordered_ext_opt', Dummy.ordered_ext_opt.doc)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(UnicodeParserTestCase))
    suite.addTest(unittest.makeSuite(ConfigurationTestCase))
    suite.addTest(unittest.makeSuite(IntegrationTestCase))
    if __name__ == 'trac.tests.config':
        suite.addTest(unittest.makeSuite(ConfigurationSetDefaultsTestCase))
    else:
        print("SKIP: trac.tests.config.ConfigurationSetDefaultsTestCase "
              "(__name__ is not trac.tests.config)")
    suite.addTest(unittest.makeSuite(OptionDocTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
