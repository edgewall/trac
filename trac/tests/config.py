# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
#
# Trac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Trac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

from trac.config import Configuration

import os
import tempfile
import time
import unittest


class ConfigurationTestCase(unittest.TestCase):

    def setUp(self):
        self.filename = os.path.join(tempfile.gettempdir(), 'trac-test.ini')
        configfile = open(self.filename, 'w')
        configfile.close()

    def tearDown(self):
        os.remove(self.filename)

    def test_default(self):
        config = Configuration(self.filename)
        self.assertEquals('', config.get('a', 'option'))
        self.assertEquals('value', config.get('a', 'option', 'value'))

        config.setdefault('a', 'option', 'value')
        self.assertEquals('value', config.get('a', 'option'))

    def test_read_and_get(self):
        configfile = open(self.filename, 'w')
        configfile.writelines(['[a]\n', 'option = x\n', '\n'])
        configfile.close()

        config = Configuration(self.filename)
        self.assertEquals('x', config.get('a', 'option'))
        self.assertEquals('x', config.get('a', 'option', 'y'))

    def test_set_and_save(self):
        configfile = open(self.filename, 'w')
        configfile.close()

        config = Configuration(self.filename)
        config.set('a', 'option', 'x')
        self.assertEquals('x', config.get('a', 'option'))
        config.save()

        configfile = open(self.filename, 'r')
        self.assertEquals(['[a]\n', 'option = x\n', '\n'],
                          configfile.readlines())
        configfile.close()

    def test_sections(self):
        configfile = open(self.filename, 'w')
        configfile.writelines(['[a]\n', 'option = x\n',
                               '[b]\n', 'option = y\n'])
        configfile.close()

        config = Configuration(self.filename)
        self.assertEquals(['a', 'b'], config.sections())

    def test_options(self):
        configfile = open(self.filename, 'w')
        configfile.writelines(['[a]\n', 'option = x\n',
                               '[b]\n', 'option = y\n'])
        configfile.close()

        config = Configuration(self.filename)
        self.assertEquals(('option', 'x'), config.options('a').next())
        self.assertEquals(('option', 'y'), config.options('b').next())

    def test_reparse(self):
        configfile = open(self.filename, 'w')
        configfile.writelines(['[a]\n', 'option = x\n', '\n'])
        configfile.close()

        config = Configuration(self.filename)
        self.assertEquals('x', config.get('a', 'option'))
        time.sleep(1) # needed because of low mtime granularity

        configfile = open(self.filename, 'w')
        configfile.write('[a]\noption = y')
        configfile.close()
        config.parse_if_needed()
        self.assertEquals('y', config.get('a', 'option'))


def suite():
    return unittest.makeSuite(ConfigurationTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
