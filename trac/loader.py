# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2006 Edgewall Software
# Copyright (C) 2005-2006 Christopher Lenz <cmlenz@gmx.de>
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

from glob import glob
import imp
import os
import sys
from trac.config import default_dir
try:
    set
except NameError:
    from sets import Set as set

try:
    import pkg_resources
except ImportError:
    pkg_resources = None

__all__ = ['load_components']

def load_components(env):
    loaded_components = []
    plugins_dirs = [os.path.normcase(os.path.realpath(os.path.join(env.path,
                                                                  'plugins'))),
                    default_dir('plugins')]

    # First look for Python source files in the plugins directories, which
    # simply get imported, thereby registering them with the component manager
    # if they define any components.
    for plugins_dir in plugins_dirs:
        auto_enable = plugins_dir != default_dir('plugins')
        plugin_files = glob(os.path.join(plugins_dir, '*.py'))
        for plugin_file in plugin_files:
            try:
                plugin_name = os.path.basename(plugin_file[:-3])
                if plugin_name not in loaded_components:
                    env.log.debug('Loading file plugin %s from %s' % (plugin_name,
                                                                 plugin_file))
                    module = imp.load_source(plugin_name, plugin_file)
                    loaded_components.append(plugin_name)
                    if auto_enable and plugin_name + '.*' \
                            not in env.config['components']:
                        env.config['components'].set(plugin_name + '.*', 'enabled')
            except Exception, e:
                env.log.error('Failed to load plugin from %s', plugin_file,
                              exc_info=True)

    # If setuptools is installed try to load any eggs from the plugins
    # directory, and also plugins available on sys.path
    if pkg_resources is not None:
        ws = pkg_resources.working_set
        for plugins_dir in plugins_dirs:
            ws.add_entry(plugins_dir)
        pkg_env = pkg_resources.Environment(plugins_dirs + sys.path)

        memo = set()
        def flatten(dists):
             for dist in dists:
                 if dist in memo:
                     continue
                 memo.add(dist)
                 try:
                     predecessors = ws.resolve([dist.as_requirement()])
                     for predecessor in flatten(predecessors):
                         yield predecessor
                     yield dist
                 except pkg_resources.DistributionNotFound, e:
                     env.log.error('Skipping "%s" ("%s" not found)', dist, e)
                 except pkg_resources.VersionConflict, e:
                     env.log.error('Skipping "%s" (version conflict: "%s")',
                                   dist, e)

        for egg in flatten([pkg_env[name][0] for name in pkg_env]):
            modules = []

            for name in egg.get_entry_map('trac.plugins'):
                # Load plugins declared via the `trac.plugins` entry point.
                # This is the only supported option going forward, the
                # others will be dropped at some point in the future.
                env.log.debug('Loading egg plugin %s from %s', name,
                              egg.location)
                egg.activate()
                try:
                    entry_point = egg.get_entry_info('trac.plugins', name)
                    if entry_point.module_name not in loaded_components:
                        try:
                            entry_point.load()
                        except pkg_resources.DistributionNotFound, e:
                            env.log.warning('Cannot load plugin %s because it '
                                            'requires "%s"', name, e)
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
                    for modname in egg.get_metadata_lines('trac_plugin.txt'):
                        module = None
                        if modname not in loaded_components:
                            try:
                                module = __import__(modname)
                                loaded_components.append(modname)
                                modules.append(modname)
                            except ImportError, e:
                                env.log.error('Component module %s not found',
                                              modname, exc_info=True)

            if modules:
                # Automatically enable any components provided by plugins
                # loaded from the environment plugins directory.
                if os.path.dirname(egg.location) == plugins_dirs[0]:
                    for module in modules:
                        if module + '.*' not in env.config['components']:
                            env.config['components'].set(module + '.*',
                                                         'enabled')

    # Load default components
    from trac.db_default import default_components
    for module in default_components:
        if not module in loaded_components:
            __import__(module)
