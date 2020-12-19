# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2020 Edgewall Software
# Copyright (C) 2005-2007 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import contextlib
import copy
import os
import time
import unittest

from trac.admin.console import TracAdmin
from trac.admin.test import TracAdminTestCaseBase
from trac.config import *
from trac.config import UnicodeConfigParser
from trac.core import Component, ComponentMeta, Interface, implements
from trac.test import Configuration, EnvironmentStub, mkdtemp, rmtree
from trac.util import create_file, read_file
from trac.util.compat import wait_for_file_mtime_change
from trac.util.datefmt import time_now


def _write(filename, lines):
    wait_for_file_mtime_change(filename)
    create_file(filename, '\n'.join(lines + ['']))


def _read(filename):
    return read_file(filename)


def readlines(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return f.readlines()


class UnicodeParserTestCase(unittest.TestCase):

    def setUp(self):
        self.tempdir = mkdtemp()
        self.filename = os.path.join(self.tempdir, 'config.ini')
        _write(self.filename, [
            '[ä]', 'öption = ÿ',
            '[ä]', 'optīon = 1.1',
            '[č]', 'ôption = ž',
            '[č]', 'optïon = 1',
            '[ė]', 'optioñ = true',
        ])
        self.parser = UnicodeConfigParser()
        self._read()

    def tearDown(self):
        rmtree(self.tempdir)

    def _write(self):
        with open(self.filename, 'w', encoding='utf-8') as f:
            self.parser.write(f)

    def _read(self):
        self.parser.read(self.filename)

    def test_sections(self):
        self.assertEqual(['ä', 'č', 'ė'], self.parser.sections())

    def test_add_section(self):
        self.parser.add_section('ē')
        self._write()
        self.assertEqual(
            '[ä]\n'
            'öption = ÿ\n'
            'optīon = 1.1\n\n'
            '[č]\n'
            'ôption = ž\n'
            'optïon = 1\n\n'
            '[ė]\n'
            'optioñ = true\n\n'
            '[ē]\n\n', _read(self.filename))

    def test_has_section(self):
        self.assertTrue(self.parser.has_section('ä'))
        self.assertTrue(self.parser.has_section('č'))
        self.assertTrue(self.parser.has_section('ė'))
        self.assertFalse(self.parser.has_section('î'))

    def test_options(self):
        self.assertEqual(['öption', 'optīon'], self.parser.options('ä'))
        self.assertEqual(['ôption', 'optïon'], self.parser.options('č'))

    def test_get(self):
        self.assertEqual('ÿ', self.parser.get('ä', 'öption'))
        self.assertEqual('ž', self.parser.get('č', 'ôption'))

    def test_items(self):
        self.assertEqual([('öption', 'ÿ'), ('optīon', '1.1')],
                          self.parser.items('ä'))
        self.assertEqual([('ôption', 'ž'), ('optïon', '1')],
                         self.parser.items('č'))

    def test_getint(self):
        self.assertEqual(1, self.parser.getint('č', 'optïon'))

    def test_getfloat(self):
        self.assertEqual(1.1, self.parser.getfloat('ä', 'optīon'))

    def test_getboolean(self):
        self.assertTrue(self.parser.getboolean('ė', 'optioñ'))

    def test_has_option(self):
        self.assertTrue(self.parser.has_option('ä', 'öption'))
        self.assertTrue(self.parser.has_option('ä', 'optīon'))
        self.assertTrue(self.parser.has_option('č', 'ôption'))
        self.assertTrue(self.parser.has_option('č', 'optïon'))
        self.assertTrue(self.parser.has_option('ė', 'optioñ'))
        self.assertFalse(self.parser.has_option('î', 'optioñ'))

    def test_set(self):
        self.parser.set('ä', 'öption', 'ù')
        self.parser.set('ė', 'optiœn', None)
        self._write()
        self.assertEqual(
            '[ä]\n'
            'öption = ù\n'
            'optīon = 1.1\n\n'
            '[č]\n'
            'ôption = ž\n'
            'optïon = 1\n\n'
            '[ė]\n'
            'optioñ = true\n'
            'optiœn = \n\n', _read(self.filename))

    def test_remove_option(self):
        self.parser.remove_option('ä', 'öption')
        self.parser.remove_option('ė', 'optioñ')
        self._write()
        self.assertEqual(
            '[ä]\n'
            'optīon = 1.1\n\n'
            '[č]\n'
            'ôption = ž\n'
            'optïon = 1\n\n'
            '[ė]\n\n', _read(self.filename))

    def test_remove_section(self):
        self.parser.remove_section('ä')
        self.parser.remove_section('ė')
        self._write()
        self.assertEqual(
            '[č]\n'
            'ôption = ž\n'
            'optïon = 1\n\n', _read(self.filename))


class BaseTestCase(unittest.TestCase):

    def setUp(self):
        self.tmpdir = mkdtemp()
        self.filename = os.path.join(self.tmpdir, 'trac-test.ini')
        self.sitename = os.path.join(self.tmpdir, 'trac-site.ini')
        self.env = EnvironmentStub()
        self._write([])
        self._orig = {
            'ComponentMeta._components': ComponentMeta._components,
            'ComponentMeta._registry': ComponentMeta._registry,
            'ConfigSection.registry': ConfigSection.registry,
            'Option.registry': Option.registry,
        }
        ComponentMeta._components = list(ComponentMeta._components)
        ComponentMeta._registry = {interface: list(classes)
                                   for interface, classes
                                   in ComponentMeta._registry.items()}
        ConfigSection.registry = {}
        Option.registry = {}

    def tearDown(self):
        ComponentMeta._components = self._orig['ComponentMeta._components']
        ComponentMeta._registry = self._orig['ComponentMeta._registry']
        ConfigSection.registry = self._orig['ConfigSection.registry']
        Option.registry = self._orig['Option.registry']
        rmtree(self.tmpdir)

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
        self.config.parser.add_section('séction1')
        self.config.parser.set('séction1', 'öption1', 'cönfig-valué')
        self.config.parser.set('séction1', 'öption4', 'cönfig-valué')
        self.config.parser.add_section('séction5')
        self.config.parser.set('séction5', 'öption2', 'cönfig-valué')
        self.config.parser.set('séction5', 'öption3', 'cönfig-valué')
        parent_config = Configuration(None)
        parent_config.parser.add_section('séction1')
        parent_config.parser.add_section('séction2')
        parent_config.parser.set('séction1', 'öption1', 'cönfig-valué')
        parent_config.parser.set('séction1', 'öption2', 'înherited-valué')
        parent_config.parser.set('séction2', 'öption2', 'înherited-valué')
        self.config.parents = [parent_config]
        self.default_value = 'dēfault-valué'

        class OptionClass(object):
            Option('séction1', 'öption1', self.default_value)
            Option('séction1', 'öption2', self.default_value)
            Option('séction1', 'öption3', self.default_value)
            Option('séction3', 'öption1', self.default_value)
            Option('séction5', 'öption1', self.default_value)
            Option('séction5', 'öption2', self.default_value)
            ConfigSection('séction4', 'Séction 4')

    def test_get_from_config(self):
        """Value is retrieved from the config."""
        self.assertEqual('cönfig-valué',
                         self.config.get('séction1', 'öption1'))

    def test_get_from_inherited(self):
        """Value not specified in the config is retrieved from the
        inherited config.
        """
        self.assertEqual('înherited-valué',
                         self.config.get('séction1', 'öption2'))

    def test_get_from_default(self):
        """Value not specified in the config or the inherited config
        is retrieved from the option default.
        """
        self.assertEqual(self.default_value,
                         self.config.get('séction1', 'öption3'))

    def test_get_is_cached(self):
        """Value is cached on first retrieval from the parser."""
        option1 = self.config.get('séction1', 'öption1')
        self.config.parser.set('séction1', 'öption1', 'cönfig-valué2')
        self.assertIs(self.config.get('séction1', 'öption1'), option1)

    def test_contains_from_config(self):
        """Contains returns `True` for section defined in config."""
        self.assertIn('séction1', self.config)

    def test_contains_from_inherited(self):
        """Contains returns `True` for section defined in inherited config."""
        self.assertIn('séction2', self.config)

    def test_contains_from_default(self):
        """Contains returns `True` for section defined in an option."""
        self.assertIn('séction3', self.config)

    def test_sections_with_default(self):
        """Sections including defaults."""
        sections = self.config.sections()
        self.assertIn('séction1', sections)
        self.assertIn('séction2', sections)
        self.assertIn('séction3', sections)
        self.assertNotIn('séction4', sections)

    def test_sections_without_default(self):
        """Sections without defaults."""
        sections = self.config.sections(defaults=False)
        self.assertIn('séction1', sections)
        self.assertIn('séction2', sections)
        self.assertNotIn('séction3', sections)
        self.assertNotIn('séction4', sections)

    def test_sections_with_empty(self):
        """Sections including empty."""
        sections = self.config.sections(defaults=False, empty=True)
        self.assertNotIn('séction3', sections)
        self.assertIn('séction4', sections)

    def test_remove_option_from_config(self):
        """Value is removed from configuration."""
        self.config.remove('séction1', 'öption4')
        parser = self.config.parser
        self.assertNotIn('öption4', self.config['séction1'])
        self.assertFalse(parser.has_option('séction1', 'öption4'))
        self.assertEqual('', self.config.get('séction1', 'öption4'))

    def test_remove_non_existent_option_from_config(self):
        """Removing non-existent value from config doesn't raise error."""
        parser = self.config.parser
        self.assertFalse(parser.has_option('séction1', 'öption5'))
        self.config.remove('séction1', 'öption5')
        self.assertFalse(parser.has_option('séction1', 'öption5'))
        self.assertEqual('', self.config.get('séction1', 'öption5'))

    def test_remove_option_from_section(self):
        """Value is removed from section."""
        self.config['séction1'].remove('öption4')
        parser = self.config.parser
        self.assertNotIn('öption4', self.config['séction1'])
        self.assertFalse(parser.has_option('séction1', 'öption4'))
        self.assertEqual('', self.config.get('séction1', 'öption4'))
        self.assertEqual('', self.config['séction1'].get('öption4'))

    def test_remove_non_existent_option_from_section(self):
        """Removing non-existent value from section doesn't raise error."""
        parser = self.config.parser
        self.assertFalse(parser.has_option('séction1', 'öption5'))
        self.config['séction1'].remove('öption5')
        self.assertFalse(parser.has_option('séction1', 'öption5'))
        self.assertEqual('', self.config.get('séction1', 'öption5'))

    def _assert_section_removed(self):
        parser = self.config.parser
        self.assertFalse(parser.has_option('séction5', 'öption1'))
        self.assertFalse(parser.has_option('séction5', 'öption2'))
        self.assertFalse(parser.has_option('séction5', 'öption3'))
        self.assertFalse(parser.has_section('séction5'))
        self.assertIn('séction5', self.config)
        self.assertEqual(self.default_value,
                         self.config.get('séction5', 'öption1'))
        self.assertEqual(self.default_value,
                         self.config.get('séction5', 'öption2'))
        self.assertEqual('', self.config.get('séction5', 'öption3'))

    def test_remove_section_from_config(self):
        """Section is removed from configuration."""
        self.config.remove('séction5')
        self._assert_section_removed()

    def test_remove_section_from_config_when_last_option_removed(self):
        """Section is removed from configuration when last option is
        removed from the configuration."""
        self.config.remove('séction5', 'öption1')
        self.config.remove('séction5', 'öption2')
        self.config.remove('séction5', 'öption3')
        self._assert_section_removed()

    def test_remove_non_existent_section(self):
        """Removing non-existent section doesn't raise error."""
        self.assertNotIn('séction6', self.config)
        self.config.remove('séction6')

    def test_remove_leaves_inherited_unchanged(self):
        """Value is not removed from inherited configuration."""
        self.config.remove('séction1', 'öption2')
        parser = self.config.parents[0].parser
        self.assertTrue(parser.has_option('séction1', 'öption1'))
        self.assertEqual('înherited-valué',
                         self.config.get('séction1', 'öption2'))


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
        self.assertNotEqual('file.ini', config.getpath('a', 'opt1'))
        self.assertTrue(os.path.isabs(config.getpath('a', 'opt1')))
        self.assertEqual('/somewhere/file.ini', os.path.splitdrive(
                         config.getpath('a', 'opt2'))[1].replace('\\', '/'))
        self.assertEqual('/none.ini', os.path.splitdrive(
                         config.getpath('a', 'opt3',
                                        '/none.ini'))[1].replace('\\', '/'))
        self.assertNotEqual('none.ini', config.getpath('a', 'opt3', 'none.ini'))

    def test_read_and_get(self):
        self._write(['[a]', 'option = x'])
        config = self._read()
        self.assertEqual('x', config.get('a', 'option'))
        self.assertEqual('x', config.get('a', 'option', 'y'))
        self.assertEqual('y', config.get('b', 'option2', 'y'))

    def test_read_and_get_unicode(self):
        self._write(['[ä]', 'öption = x'])
        config = self._read()
        self.assertEqual('x', config.get('ä', 'öption'))
        self.assertEqual('x', config.get('ä', 'öption', 'y'))
        self.assertEqual('y', config.get('b', 'öption2', 'y'))

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
        values = [None, False, '', 'foo', '', 'bar', 0, 0.0, 0j, 42, 43.0]
        self.assertEqual([False, 'foo', 'bar', 0, 0.0, 0j, 42, 43.0],
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
                     '[û]', 'èncoded = à'])
        config = self._read()

        class Foo(object):
            option = ChoiceOption('a', 'option', ['Item1', 2, '3'])
            other = ChoiceOption('a', 'other', [1, 2, 3])
            invalid = ChoiceOption('a', 'invalid', ['a', 'b', 'c'])
            encoded = ChoiceOption('a', 'èncoded', ['à', 'ć', 'ē'])
            case_insensitive = ChoiceOption('a', 'case-insensitive',
                                            ['A', 'B', 'C'],
                                            case_sensitive=False)

            def __init__(self):
                self.config = config

        foo = Foo()
        self.assertEqual('2', foo.option)
        self.assertEqual('1', foo.other)
        self.assertRaises(ConfigurationError, getattr, foo, 'invalid')
        self.assertEqual('à', foo.encoded)
        config.set('a', 'èncoded', 'ć')
        self.assertEqual('ć', foo.encoded)
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
        config.set('b', 'öption0', 'y')
        config.set('aä', 'öption0', 'x')
        config.set('aä', 'option2', "Voilà l'été")  # UTF-8
        config.set('aä', 'option1', "Voilà l'été")  # unicode
        section = config['b']
        section.set('option1', None)
        section = config['aä']
        section.set('öption1', 'z')
        section.set('öption2', None)
        # Note: the following would depend on the locale.getpreferredencoding()
        # config.set('a', 'option3', "Voil\xe0 l'\xe9t\xe9") # latin-1
        self.assertEqual('x', config.get('aä', 'öption0'))
        self.assertEqual("Voilà l'été", config.get('aä', 'option1'))
        self.assertEqual("Voilà l'été", config.get('aä', 'option2'))
        self.assertEqual('', config.get('b', 'option1'))
        self.assertEqual('z', config.get('aä', 'öption1'))
        self.assertEqual('', config.get('aä', 'öption2'))
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
        self.assertEqual('x', config2.get('aä', 'öption0'))
        self.assertEqual("Voilà l'été", config2.get('aä', 'option1'))
        self.assertEqual("Voilà l'été", config2.get('aä', 'option2'))
        # self.assertEqual("Voilà l'été", config2.get('a', 'option3'))

    def test_set_and_save_inherit(self):
        with self.inherited_file():
            self._write(['[a]', 'option = x'], site=True)
            config = self._read()
            config.set('a', 'option2', "Voilà l'été")  # UTF-8
            config.set('a', 'option1', "Voilà l'été")  # unicode
            self.assertEqual('x', config.get('a', 'option'))
            self.assertEqual("Voilà l'été", config.get('a', 'option1'))
            self.assertEqual("Voilà l'été", config.get('a', 'option2'))
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
            self.assertEqual("Voilà l'été", config2.get('a', 'option1'))
            self.assertEqual("Voilà l'été", config2.get('a', 'option2'))

    def test_set_and_save_inherit_remove_matching(self):
        """Options with values matching the inherited value are removed from
        the base configuration.
        """
        with self.inherited_file():
            self._write(['[a]', 'ôption = x'], site=True)
            config = self._read()
            self.assertEqual('x', config.get('a', 'ôption'))
            config.save()

            self.assertEqual(
                '# -*- coding: utf-8 -*-\n'
                '\n'
                '[inherit]\n'
                'file = trac-site.ini\n'
                '\n', read_file(self.filename))

            config.set('a', 'ôption', 'y')
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

            config.set('a', 'ôption', 'x')
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
        config.get('a', 'option')  # populates the cache
        config.set('aä', 'öption', 'öne')
        config.remove('a', 'option')
        self.assertEqual('', config.get('a', 'option'))
        config.remove('aä', 'öption')
        self.assertEqual('', config.get('aä', 'öption'))
        config.remove('a', 'option2')  # shouldn't fail
        config.remove('b', 'option2')  # shouldn't fail

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
        self._write(['[aä]', 'öption = x', '[b]', 'option = y'])
        config = self._read()
        self.assertEqual(['aä', 'b'], config.sections())

        class Foo(object):
            option_c = Option('cä', 'option', 'value')

        self.assertEqual(['aä', 'b', 'cä'], config.sections())

    def test_options(self):
        self._write(['[a]', 'option = x', '[b]', 'option = y'])
        config = self._read()
        self.assertEqual(('option', 'x'), next(iter(config.options('a'))))
        self.assertEqual(('option', 'y'), next(iter(config.options('b'))))
        self.assertRaises(StopIteration, next, iter(config.options('c')))
        self.assertEqual('option', next(iter(config['a'])))
        self.assertEqual('option', next(iter(config['b'])))
        self.assertRaises(StopIteration, next, iter(config['c']))

        class Foo(object):
            option_a = Option('a', 'b', 'c')

        self.assertEqual([('option', 'x'), ('b', 'c')],
                         list(config.options('a')))

    def test_options_unicode(self):
        self._write(['[ä]', 'öption = x', '[b]', 'option = y'])
        config = self._read()
        self.assertEqual(('öption', 'x'), next(iter(config.options('ä'))))
        self.assertEqual(('option', 'y'), next(iter(config.options('b'))))
        self.assertRaises(StopIteration, next, iter(config.options('c')))
        self.assertEqual('öption', next(iter(config['ä'])))

        class Foo(object):
            option_a = Option('ä', 'öption2', 'c')

        self.assertEqual([('öption', 'x'), ('öption2', 'c')],
                         list(config.options('ä')))

    def test_has_option(self):
        config = self._read()
        self.assertFalse(config.has_option('a', 'option'))
        self.assertNotIn('option', config['a'])
        self._write(['[a]', 'option = x'])
        config = self._read()
        self.assertTrue(config.has_option('a', 'option'))
        self.assertIn('option', config['a'])

        class Foo(object):
            option_a = Option('a', 'option2', 'x2')

        self.assertTrue(config.has_option('a', 'option2'))

    def test_has_option_unicode(self):
        config = self._read()
        self.assertFalse(config.has_option('ä', 'öption'))
        self.assertNotIn('öption', config['ä'])
        self._write(['[ä]', 'öption = x'])
        config = self._read()
        self.assertTrue(config.has_option('ä', 'öption'))
        self.assertIn('öption', config['ä'])

        class Foo(object):
            option_a = Option('ä', 'öption2', 'x2')

        self.assertTrue(config.has_option('ä', 'öption2'))

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
            config.remove('a', 'option')  # Should *not* remove option in parent
            self.assertEqual('x', config.get('a', 'option'))
            self.assertEqual([('option', 'x')], list(config.options('a')))
            self.assertIn('a', config)

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
            option_blah = Option('a', 'blah', 'Blàh!')
            option_true = BoolOption('a', 'true', True)
            option_false = BoolOption('a', 'false', False)
            option_list1 = ListOption('a', 'list', ['#cc0', 4.2, 42, 0, None,
                                                    True, False, None],
                                      sep='|', keep_empty=True)
            option_list2 = ListOption('a', 'list-seps',
                                      ['#cc0', 4.2, 42, 0, None, True, False,
                                       None],
                                      sep=(',', '|'), keep_empty=True)
            option_choice = ChoiceOption('a', 'choice', [-42, 42])

        config = self._read()
        config.set_defaults()
        config.save()
        expected = [
            '# -*- coding: utf-8 -*-\n',
            '\n',
            '[a]\n',
            'blah = Blàh!\n',
            'choice = -42\n',
            'false = disabled\n',
            'list = #cc0|4.2|42|0||enabled|disabled|\n',
            'list-seps = #cc0,4.2,42,0,,enabled,disabled,\n',
            'none = \n',
            'true = enabled\n',
            '\n',
        ]
        self.assertEqual(expected, readlines(self.filename))

    def test_unicode_option_with_raw_default(self):
        class Foo(object):
            option_none = Option('résumé', 'nöné', None)
            option_blah = Option('résumé', 'bláh', 'Blàh!')
            option_true = BoolOption('résumé', 'trüé', True)
            option_false = BoolOption('résumé', 'fálsé', False)
            option_list = ListOption('résumé', 'liśt',
                                     ['#ccö', 4.2, 42, 0, None, True,
                                      False, None],
                                     sep='|', keep_empty=True)
            option_choice = ChoiceOption('résumé', 'chöicé', [-42, 42])

        config = self._read()
        config.set_defaults()
        config.save()
        expected = [
            '# -*- coding: utf-8 -*-\n',
            '\n',
            '[résumé]\n',
            'bláh = Blàh!\n',
            'chöicé = -42\n',
            'fálsé = disabled\n',
            'liśt = #ccö|4.2|42|0||enabled|disabled|\n',
            'nöné = \n',
            'trüé = enabled\n',
            '\n',
        ]
        self.assertEqual(expected, readlines(self.filename))

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

    components = []

    @classmethod
    def setUpClass(cls):
        class CompA(Component):
            opt1 = Option('compa', 'opt1', 1)
            opt2 = Option('compa', 'opt2', 'a')

        class CompB(Component):
            opt3 = Option('compb', 'opt3', 2)
            opt4 = Option('compb', 'opt4', 'b')

        cls.components = [CompA, CompB]

    @classmethod
    def tearDownClass(cls):
        for component in cls.components:
            ComponentMeta.deregister(component)

    def test_component_module_no_match(self):
        """No defaults written if component doesn't match."""
        config = self._read()
        config.set_defaults(component='trac.tests.conf')
        config.save()
        self.assertEqual(['# -*- coding: utf-8 -*-\n', '\n'],
                         readlines(self.filename))

    def test_component_class_no_match(self):
        """No defaults written if module doesn't match."""
        config = self._read()
        config.set_defaults(component='trac.tests.conf.CompC')
        config.save()
        self.assertEqual(['# -*- coding: utf-8 -*-\n', '\n'],
                         readlines(self.filename))

    def test_component_module_match(self):
        """Defaults of components in matching module are written."""
        config = self._read()
        config.set_defaults(component='trac.tests.config')
        config.save()
        expected = [
            '# -*- coding: utf-8 -*-\n',
            '\n',
            '[compa]\n',
            'opt1 = 1\n',
            'opt2 = a\n',
            '\n',
            '[compb]\n',
            'opt3 = 2\n',
            'opt4 = b\n',
            '\n',
        ]
        self.assertEqual(expected, readlines(self.filename))

    def test_component_module_wildcard_match(self):
        """Defaults of components in matching module are written.
        Trailing dot-star are stripped in performing match.
        """
        config = self._read()
        config.set_defaults(component='trac.tests.config.*')
        config.save()
        expected = [
            '# -*- coding: utf-8 -*-\n',
            '\n',
            '[compa]\n',
            'opt1 = 1\n',
            'opt2 = a\n',
            '\n',
            '[compb]\n',
            'opt3 = 2\n',
            'opt4 = b\n',
            '\n',
        ]
        self.assertEqual(expected, readlines(self.filename))

    def test_component_class_match(self):
        """Defaults of matching component are written."""
        config = self._read()
        config.set_defaults(component='trac.tests.config.CompA')
        config.save()
        expected = [
            '# -*- coding: utf-8 -*-\n',
            '\n',
            '[compa]\n',
            'opt1 = 1\n',
            'opt2 = a\n',
            '\n',
        ]
        self.assertEqual(expected, readlines(self.filename))

    def test_component_no_overwrite(self):
        """Values in configuration are not overwritten."""
        config = self._read()
        config.set('compa', 'opt1', 3)
        config.save()
        config.set_defaults(component='trac.tests.config.CompA')
        config.save()
        expected = [
            '# -*- coding: utf-8 -*-\n',
            '\n',
            '[compa]\n',
            'opt1 = 3\n',
            'opt2 = a\n',
            '\n',
        ]
        self.assertEqual(expected, readlines(self.filename))

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

        expected = [
            '# -*- coding: utf-8 -*-\n',
            '\n',
            '[compa]\n',
            'opt1 = 3\n',
            '\n',
        ]
        self.assertEqual(expected, readlines(self.sitename))

        expected = [
            '# -*- coding: utf-8 -*-\n',
            '\n',
            '[compa]\n',
            'opt2 = a\n',
            '\n',
            '[inherit]\n',
            'file = trac-site.ini\n',
            '\n',
        ]
        self.assertEqual(expected, readlines(self.filename))


class OptionDocTestCase(BaseTestCase):

    def test_config_section(self):
        class Dummy(object):
            section_a = ConfigSection('a', 'Doc for a')
            section_b = ConfigSection(
                'b', 'Doc for [%(page)s@%(version)d b]',
                doc_args={'page': 'WikiStart', 'version': 42})
            section_c = ConfigSection('c', '')

        self.assertEqual('Doc for a', Dummy.section_a.__doc__)
        self.assertIsNone(Dummy.section_a.doc_args)
        self.assertEqual('Doc for a', Dummy.section_a.doc)
        self.assertEqual('Doc for [%(page)s@%(version)d b]',
                         Dummy.section_b.__doc__)
        self.assertEqual({'page': 'WikiStart', 'version': 42},
                         Dummy.section_b.doc_args)
        self.assertEqual('Doc for [WikiStart@42 b]', Dummy.section_b.doc)
        self.assertEqual('', Dummy.section_c.__doc__)
        self.assertIsNone(Dummy.section_c.doc_args)
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
        self.assertIsNone(Dummy.opt_nodoc.doc_args)
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


class TracAdminTestCase(TracAdminTestCaseBase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.admin = TracAdmin()
        self.admin.env_set('', self.env)

    def tearDown(self):
        self.env = None

    def test_config_get(self):
        """
        Tests the 'config get' command in trac-admin.  This particular
        test gets the project name from the config.
        """
        self.env.config.set('project', 'name', 'Test project')
        rv, output = self.execute('config get project name')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_config_set(self):
        """
        Tests the 'config set' command in trac-admin.  This particular
        test sets the project name using an option value containing a space.
        """
        rv, output = self.execute('config set project name "Test project"')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)
        self.assertEqual('Test project',
                         self.env.config.get('project', 'name'))

    def test_config_remove_option(self):
        """
        Tests the 'config remove <section> <option>' command in trac-admin.
        This particular test removes the project name from the config,
        therefore reverting the option to the default value.
        """
        self.env.config.set('project', 'name', 'Test project')
        rv, output = self.execute('config remove project name')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)
        self.assertEqual('My Project', self.env.config.get('project', 'name'))

    def test_config_remove_mising_option_raises_error(self):
        """
        Tests the 'config remove <section> <option>' command in trac-admin.
        Removing a non-existent option raises an error.
        """
        self.assertNotIn('section1', self.env.config)
        rv, output = self.execute('config remove section1 no_exists')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)
        self.assertNotIn('section1', self.env.config)

    def test_config_remove_all_options_for_section(self):
        """
        Tests the 'config remove <section> <option>' command in trac-admin.
        Remove the all options for a section and confirm the section is
        no longer present in the config.
        """
        self.env.config.set('section1', 'opt1', 'val1')
        self.env.config.set('section1', 'opt2', 'val2')
        self.assertIn('section1', self.env.config)
        rv1, output1 = self.execute('config remove section1 opt1')
        rv2, output2 = self.execute('config remove section1 opt2')
        self.assertEqual(0, rv1, output1)
        self.assertExpectedResult(output1)
        self.assertEqual(0, rv2, output2)
        self.assertExpectedResult(output2)
        self.assertNotIn('section1', self.env.config)

    def test_config_remove_section(self):
        """
        Tests the 'config remove <section>' command in trac-admin.
        Remove the section and confirm it's no longer present in the config.
        """
        self.env.config.set('section1', 'opt1', 'val1')
        self.env.config.set('section1', 'opt2', 'val2')
        self.env.config.set('section1', 'opt3', 'val3')
        self.assertIn('section1', self.env.config)
        rv, output = self.execute('config remove section1')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)
        self.assertNotIn('section1', self.env.config)

    def test_config_remove_mising_section_raises_error(self):
        """
        Tests the 'config remove <section>' command in trac-admin.
        Removing a non-existent section raises an error.
        """
        self.assertNotIn('section1', self.env.config)
        rv, output = self.execute('config remove section1')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)
        self.assertNotIn('section1', self.env.config)

    def test_config_set_complete_section(self):
        """Tab complete on a configuration section."""
        # Empty sections are included.
        output = self.complete_command('config', 'set', '')
        self.assertIn('components', output)
        self.assertIn('project', output)
        self.assertNotIn('foo-section', output)

        # Sections not defined in registry are included.
        self.env.config.set('foo-section', 'bar-option', '1')
        output = self.complete_command('config', 'set', '')
        self.assertIn('foo-section', output)

    def test_config_set_complete_option(self):
        """Tab complete on a configuration option."""
        output = self.complete_command('config', 'set', 'project', '')
        self.assertEqual(['admin', 'admin_trac_url', 'descr', 'footer', 'icon',
                          'name', 'url'], sorted(output))

        # Options not defined in registry are included.
        self.env.config.set('project', 'bar-option', '1')
        output = self.complete_command('config', 'set', 'project', '')
        self.assertIn('bar-option', output)


class TracAdminComponentTestCase(TracAdminTestCaseBase):

    components = []

    @classmethod
    def setUpClass(cls):
        class CompA(Component):
            opt1 = Option('compa', 'opt1', 1)
            opt2 = Option('compa', 'opt2', 2)

        cls.components = [CompA]

    @classmethod
    def tearDownClass(cls):
        for component in cls.components:
            ComponentMeta.deregister(component)

    def setUp(self):
        self.env = EnvironmentStub()
        self.admin = TracAdmin()
        self.admin.env_set('', self.env)

    def tearDown(self):
        self.env = None

    def test_config_component_enable(self):
        self.env.config.save()
        initial_file = copy.deepcopy(self.env.config.parser)

        rv, output = self.execute('config set components '
                                   'trac.tests.config.* enabled')

        self.assertEqual(0, rv, output)
        self.assertFalse(initial_file.has_section('compa'))
        self.assertIn('compa', self.env.config)
        self.assertIn('1', self.env.config.parser.get('compa', 'opt1'))
        self.assertIn('2', self.env.config.parser.get('compa', 'opt2'))


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
    suite.addTest(unittest.makeSuite(TracAdminTestCase))
    if __name__ == 'trac.tests.config':
        suite.addTest(unittest.makeSuite(TracAdminComponentTestCase))
    else:
        print("SKIP: trac.tests.config.TracAdminComponentTestCase "
              "(__name__ is not trac.tests.config)")
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
