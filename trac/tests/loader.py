# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

import glob
import os
import pkg_resources
import shutil
import subprocess
import sys
import tempfile
import unittest

from trac import loader
from trac.core import ComponentMeta
from trac.test import EnvironmentStub
from trac.util import create_file
from trac.util.compat import close_fds


_setup_py = """\
from setuptools import setup, find_packages

setup(
    name = '%(name)s',
    version = '1.0',
    description = '',
    license = '',
    install_requires = ['Trac'],
    packages = find_packages(exclude=['*.tests*']),
    extras_require = {'dependency': 'Dependency'},
    entry_points = {'trac.plugins': [
        'ComponentA = %(name)s:ComponentA',
        'ComponentB = %(name)s:ComponentB[dependency]'
        ]
    })
"""


_plugin_py = """\
import os.path
from trac.core import Component, implements
from trac.env import IEnvironmentSetupParticipant
from trac.util import create_file

class ComponentA(Component):

    implements(IEnvironmentSetupParticipant)

    def __init__(self):
        self._created_file = os.path.join(self.env.path, 'log', 'created_a')
        self._upgraded_file = os.path.join(self.env.path, 'log', 'upgraded_a')

    def environment_created(self):
        self.upgrade_environment()

    def environment_needs_upgrade(self):
        return not os.path.exists(self._upgraded_file)

    def upgrade_environment(self):
        create_file(self._upgraded_file)


class ComponentB(Component):

    implements(IEnvironmentSetupParticipant)

    def __init__(self):
        self._created_file = os.path.join(self.env.path, 'log', 'created_b')
        self._upgraded_file = os.path.join(self.env.path, 'log', 'upgraded_b')

    def environment_created(self):
        self.upgrade_environment()

    def environment_needs_upgrade(self):
        return not os.path.exists(self._upgraded_file)

    def upgrade_environment(self):
        create_file(self._upgraded_file)
"""


class LoadComponentsTestCase(unittest.TestCase):

    def setUp(self):
        tempdir = tempfile.mkdtemp(prefix='trac-tempenv-')
        self.env = EnvironmentStub(path=tempdir)
        self.components = []

    def tearDown(self):
        self._cleanup_working_set()
        self.env.reset_db_and_disk()
        for c in self.components:
            ComponentMeta.deregister(c)

    def _cleanup_working_set(self):
        for plugin_name in os.listdir(self.env.plugins_dir):
            plugin_path = os.path.join(self.env.plugins_dir, plugin_name)
            pkg_resources.working_set.entries.remove(plugin_path)
            del pkg_resources.working_set.entry_keys[plugin_path]

    def _build_egg_file(self, module_name):
        plugin_src = os.path.join(self.env.path, 'plugin_src')
        os.mkdir(plugin_src)
        os.mkdir(os.path.join(plugin_src, module_name))
        create_file(os.path.join(plugin_src, 'setup.py'),
                    _setup_py % {'name': module_name})
        create_file(os.path.join(plugin_src, module_name, '__init__.py'),
                    _plugin_py)
        proc = subprocess.Popen((sys.executable, 'setup.py', 'bdist_egg'),
                                cwd=plugin_src, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                close_fds=close_fds)
        proc.communicate(input='')
        for f in (proc.stdin, proc.stdout, proc.stderr):
            f.close()
        for filename in glob.glob(os.path.join(plugin_src, 'dist', '*-*.egg')):
            return filename

    def test_entry_point_with_extras(self):
        """Load entry points with extras

        Entry points with absent dependencies should not be found in
        the component registry.
        """
        egg_file_src = self._build_egg_file('plugin1')
        egg_file_dst = os.path.join(self.env.plugins_dir,
                                    os.path.basename(egg_file_src))
        os.mkdir(self.env.plugins_dir)
        shutil.copyfile(egg_file_src, egg_file_dst)

        loader.load_components(self.env)
        from plugin1 import ComponentA, ComponentB
        self.components.append(ComponentA)
        self.components.append(ComponentB)

        from trac.env import IEnvironmentSetupParticipant
        registry = ComponentMeta._registry
        self.assertIn(ComponentA, ComponentMeta._components)
        self.assertIn(ComponentA, registry.get(IEnvironmentSetupParticipant))
        self.assertNotIn(ComponentB, ComponentMeta._components)
        self.assertNotIn(ComponentB, registry.get(IEnvironmentSetupParticipant))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(LoadComponentsTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
