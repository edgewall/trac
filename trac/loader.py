# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2006 Edgewall Software
# Copyright (C) 2005-2006 Christopher Lenz <cmlenz@gmx.de>
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

from glob import glob
import imp
import pkg_resources
import os
import sys

from trac.util.compat import set

__all__ = ['load_components']

def _enable_plugin(env, module):
    """Enable the given plugin module by adding an entry to the configuration.
    """
    if module + '.*' not in env.config['components']:
        env.config['components'].set(module + '.*', 'enabled')

def load_eggs(entry_point_name):
    """Loader that loads any eggs on the search path and `sys.path`."""
    def _load_eggs(env, search_path, auto_enable=None):
        working_set = pkg_resources.working_set
        for path in search_path:
            working_set.add_entry(path)

        memo = set()
        def flatten(dists):
             for dist in dists:
                 if dist in memo:
                     continue
                 memo.add(dist)
                 try:
                     predecessors = working_set.resolve([dist.as_requirement()])
                     for predecessor in flatten(predecessors):
                         yield predecessor
                     yield dist
                 except pkg_resources.DistributionNotFound, e:
                     env.log.error('Skipping "%s" ("%s" not found)', dist, e)
                 except pkg_resources.VersionConflict, e:
                     env.log.error('Skipping "%s" (version conflict: "%s")',
                                   dist, e)

        pkg_env = pkg_resources.Environment(search_path + sys.path)
        for egg in flatten([pkg_env[name][0] for name in pkg_env]):
            modules = []

            for name in egg.get_entry_map(entry_point_name):
                # Load plugins declared via a specific entry point.
                env.log.debug('Loading egg plugin %s from %s', name,
                              egg.location)
                egg.activate()
                try:
                    entry_point = egg.get_entry_info('trac.plugins', name)
                    try:
                        entry_point.load()
                    except pkg_resources.DistributionNotFound, e:
                        env.log.warning('Cannot load plugin %s because it '
                                        'requires "%s"', name, e)
                        modules.append(entry_point.module_name)
                except ImportError, e:
                    env.log.error('Failed to load plugin %s from %s', name,
                                  egg.location, exc_info=True)

            if modules:
                # Automatically enable any components provided by plugins
                # loaded from the environment plugins directory.
                if os.path.dirname(egg.location) == auto_enable:
                    for module in modules:
                        _enable_plugin(env, module)

    return _load_eggs

def load_py_files():
    """Loader that look for Python source files in the plugins directories,
    which simply get imported, thereby registering them with the component
    manager if they define any components.
    """
    def _load_py_files(env, search_path, auto_enable=None):
        for path in search_path:
            plugin_files = glob(os.path.join(path, '*.py'))
            for plugin_file in plugin_files:
                try:
                    plugin_name = os.path.basename(plugin_file[:-3])
                    env.log.debug('Loading file plugin %s from %s' % \
                                  (plugin_name, plugin_file))
                    module = imp.load_source(plugin_name, plugin_file)
                    if path == auto_enable:
                        _enable_plugin(env, plugin_name)
                except Exception, e:
                    env.log.error('Failed to load plugin from %s', plugin_file,
                                  exc_info=True)

    return _load_py_files

def load_components(env, extra_path=None, loaders=(load_eggs('trac.plugins'),
                                                   load_py_files())):
    """Load all plugin components found on the given search path."""
    plugins_dir = os.path.normcase(os.path.realpath(
        os.path.join(env.path, 'plugins')
    ))
    search_path = [plugins_dir]
    if extra_path:
        search_path += list(extra_path)

    for loadfunc in loaders:
        loadfunc(env, search_path, auto_enable=plugins_dir)
