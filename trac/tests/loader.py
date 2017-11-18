# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import os
import unittest

from trac.loader import load_components
from trac.test import EnvironmentStub, mkdtemp
from trac.util import create_file


class LoadComponentsTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(path=mkdtemp())
        os.makedirs(os.path.join(self.env.path, 'plugins'))

    def tearDown(self):
        self.env.reset_db_and_disk()

    def test_component_loaded_once(self):
        from trac.core import ComponentMeta

        create_file(os.path.join(self.env.plugins_dir,
                                 'RegressionTestRev6017.py'), """\
from trac.wiki.macros import WikiMacroBase

class RegressionTestRev6017Macro(WikiMacroBase):
    def expand_macro(self, formatter, name, content, args):
        return "Hello World"

""")

        load_components(self.env)
        load_components(self.env)

        loaded_components = [c for c in ComponentMeta._components
                               if 'RegressionTestRev6017' in c.__name__]

        self.assertEqual(1, len(loaded_components),
                         "Plugin loaded more than once.")


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(LoadComponentsTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
