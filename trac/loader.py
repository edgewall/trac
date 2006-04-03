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

import os
import sys
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
    plugins_dir = os.path.normcase(os.path.realpath(os.path.join(env.path,
                                                                 'plugins')))

    # Load components from the environment plugins directory
    loaded_components = []
    if pkg_resources is not None: # But only if setuptools is installed!
        ws = pkg_resources.working_set
        pkg_env = pkg_resources.Environment([plugins_dir] + sys.path)
        ws.add_entry(plugins_dir)

        memo = set()
        def flatten(dists):
             for dist in dists:
                 if dist in memo:
                     continue
                 memo.add(dist)
                 predecessors = ws.resolve([dist.as_requirement()])
                 for predecessor in flatten(predecessors):
                     yield predecessor
                 yield dist

        for egg in flatten([pkg_env[name][0] for name in pkg_env]):
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
                if os.path.dirname(egg.location) == plugins_dir:
                    for module in modules:
                        env.config.setdefault('components', module + '.*',
                                              'enabled')

    elif os.path.exists(plugins_dir) and os.listdir(plugins_dir):
        env.log.warning('setuptools is required for plugin deployment')

    # Load default components
    from trac.db_default import default_components
    for module in default_components:
        if not module in loaded_components:
            __import__(module)
