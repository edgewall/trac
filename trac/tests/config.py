# -*- coding: utf-8 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

from trac.config import *

import os
from StringIO import StringIO
import tempfile
import time
import unittest


class ConfigurationTestCase(unittest.TestCase):

    def setUp(self):
        self.filename = os.path.join(tempfile.gettempdir(), 'trac-test.ini')
        self._write([])
        self._orig_registry = Option.registry
        Option.registry = {}

    def tearDown(self):
        Option.registry = self._orig_registry
        os.remove(self.filename)

    def _write(self, lines):
        fileobj = open(self.filename, 'w')
        try:
            fileobj.write('\n'.join(lines + ['']))
        finally:
            fileobj.close()

    def test_default(self):
        config = Configuration(self.filename)
        self.assertEquals('', config.get('a', 'option'))
        self.assertEquals('value', config.get('a', 'option', 'value'))

        class Foo(object):
            option_a = Option('a', 'option', 'value')

        self.assertEquals('value', config.get('a', 'option'))

    def test_default_bool(self):
        config = Configuration(self.filename)
        self.assertEquals(False, config.getbool('a', 'option'))
        self.assertEquals(True, config.getbool('a', 'option', 'yes'))
        self.assertEquals(True, config.getbool('a', 'option', 1))

        class Foo(object):
            option_a = Option('a', 'option', 'true')

        self.assertEquals(True, config.getbool('a', 'option'))

    def test_default_int(self):
        config = Configuration(self.filename)
        self.assertRaises(ConfigurationError, config.getint, 'a', 'option')
        self.assertEquals(1, config.getint('a', 'option', '1'))
        self.assertEquals(1, config.getint('a', 'option', 1))

        class Foo(object):
            option_a = Option('a', 'option', '2')

        self.assertEquals(2, config.getint('a', 'option'))

    def test_read_and_get(self):
        self._write(['[a]', 'option = x'])
        config = Configuration(self.filename)
        self.assertEquals('x', config.get('a', 'option'))
        self.assertEquals('x', config.get('a', 'option', 'y'))

    def test_read_and_getbool(self):
        self._write(['[a]', 'option = yes'])
        config = Configuration(self.filename)
        self.assertEquals(True, config.getbool('a', 'option'))
        self.assertEquals(True, config.getbool('a', 'option', False))

    def test_read_and_getint(self):
        self._write(['[a]', 'option = 42'])
        config = Configuration(self.filename)
        self.assertEquals(42, config.getint('a', 'option'))
        self.assertEquals(42, config.getint('a', 'option', 25))

    def test_read_and_getlist(self):
        self._write(['[a]', 'option = foo, bar, baz'])
        config = Configuration(self.filename)
        self.assertEquals(['foo', 'bar', 'baz'],
                          config.getlist('a', 'option'))

    def test_read_and_getlist_sep(self):
        self._write(['[a]', 'option = foo | bar | baz'])
        config = Configuration(self.filename)
        self.assertEquals(['foo', 'bar', 'baz'],
                          config.getlist('a', 'option', sep='|'))

    def test_read_and_getlist_keep_empty(self):
        self._write(['[a]', 'option = ,bar,baz'])
        config = Configuration(self.filename)
        self.assertEquals(['bar', 'baz'], config.getlist('a', 'option'))
        self.assertEquals(['', 'bar', 'baz'],
                          config.getlist('a', 'option', keep_empty=True))

    def test_set_and_save(self):
        config = Configuration(self.filename)
        config.set('a', 'option', 'x')
        self.assertEquals('x', config.get('a', 'option'))
        config.save()

        configfile = open(self.filename, 'r')
        self.assertEquals(['[a]\n', 'option = x\n', '\n'],
                          configfile.readlines())
        configfile.close()

    def test_sections(self):
        self._write(['[a]', 'option = x', '[b]', 'option = y'])
        config = Configuration(self.filename)
        self.assertEquals(['a', 'b'], config.sections())

    def test_options(self):
        self._write(['[a]', 'option = x', '[b]', 'option = y'])
        config = Configuration(self.filename)
        self.assertEquals(('option', 'x'), iter(config.options('a')).next())
        self.assertEquals(('option', 'y'), iter(config.options('b')).next())
        self.assertRaises(StopIteration, iter(config.options('c')).next)

    def test_reparse(self):
        self._write(['[a]', 'option = x'])
        config = Configuration(self.filename)
        self.assertEquals('x', config.get('a', 'option'))
        time.sleep(1) # needed because of low mtime granularity

        self._write(['[a]', 'option = y'])
        config.parse_if_needed()
        self.assertEquals('y', config.get('a', 'option'))


def suite():
    return unittest.makeSuite(ConfigurationTestCase, 'test')

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
