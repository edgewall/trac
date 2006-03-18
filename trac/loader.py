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

import os
import sys

try:
    import pkg_resources
except ImportError:
    pkg_resources = None

TRAC_META = 'trac_plugin.txt'

__all__ = ['load_components']

def normalize_path(s):
  return os.path.normcase(os.path.abspath(s))

def paths_equal(path1, path2):
  return normalize_path(path1) == normalize_path(path2)

def load_components(env):

    loaded_components = []

    def load_module(name):
         if name not in loaded_components:
             try:
                 module = __import__(name)
                 loaded_components.append(name)
                 return module
             except ImportError, e:
                 env.log.error('Component module %s not found',
                               name, exc_info=True)

    plugins_dir = os.path.join(env.path, 'plugins')

    def enable_modules(egg_path, modules):
        """Automatically enable any components provided by plugins loaded from
        the environment plugins directory."""
        if paths_equal(os.path.dirname(egg_path), os.path.realpath(plugins_dir)):
            for module in modules:
                env.config.setdefault('components', module + '.*', 'enabled')

    # Load components from the environment plugins directory
    if pkg_resources is not None: # But only if setuptools is installed!
        if hasattr(pkg_resources, 'Environment'):
            # setuptools >= 0.6
            pkg_env = pkg_resources.Environment([plugins_dir] + sys.path)
            for name in pkg_env:
                egg = pkg_env[name][0]
                modules = []

                for name in egg.get_entry_map('trac.plugins'):
                    # Load plugins declared via the `trac.plugins` entry point.
                    # This is the only supported option going forward, the
                    # others will be dropped at some point in the future.
                    env.log.debug('Loading plugin %s from %s', name,
                                  egg.location)
                    egg.activate()
                    try:
                        entry_point = egg.get_entry_info('trac.plugins', name)
                        if entry_point.module_name not in loaded_components:
                            entry_point.load()
                            modules.append(entry_point.module_name)
                            loaded_components.append(entry_point.module_name)
                    except ImportError, e:
                        env.log.error('Failed to load plugin %s from %s', name,
                                      egg.location, exc_info=True)

                else:
                    # Support for pre-entry-point plugins
                    if egg.has_metadata('trac_plugin.txt'):
                        env.log.debug('Loading plugin %s from %s', name,
                                      egg.location)
                        egg.activate()
                        for module in egg.get_metadata_lines('trac_plugin.txt'):
                            if load_module(module):
                                modules.append(module)

                if modules:
                    enable_modules(egg.location, modules)

        else:
            # setuptools < 0.6
            distributions = pkg_resources.AvailableDistributions([plugins_dir] \
                                                                 + sys.path)
            for name in distributions:
                egg = distributions[name][0]
                modules = []
                if egg.metadata.has_metadata(TRAC_META):
                    egg.install_on()
                    for module in egg.metadata.get_metadata_lines(TRAC_META):
                        if load_module(module):
                            modules.append(module)

                if modules:
                    enable_modules(egg.path, modules)

    elif os.path.exists(plugins_dir) and os.listdir(plugins_dir):
        env.log.warning('setuptools is required for plugin deployment')

    # Load default components
    from trac.db_default import default_components
    for module in default_components:
        if not module in loaded_components:
            __import__(module)
