# -*- coding: iso8859-1 -*-
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

def load_components(env):

    loaded_components = []
    def load_module(module):
         if module not in loaded_components:
             try:
                 __import__(module)
                 loaded_components.append(module)
             except ImportError, e:
                 env.log.error('Component module %s not found',
                               module, exc_info=True)

    # Load components from the environment plugins directory
    plugins_dir = os.path.join(env.path, 'plugins')
    if pkg_resources is not None: # But only if setuptools is installed!
        if hasattr(pkg_resources, 'Environment'):
            # setuptools >= 0.6
            pkg_env = pkg_resources.Environment([plugins_dir] + sys.path)
            for name in pkg_env:
                egg = pkg_env[name][0]
                for name in egg.get_entry_map('trac.plugins'):
                    env.log.debug('Loading plugin %s from %s', name,
                                  egg.location)
                    egg.activate()
                    try:
                        egg.load_entry_point('trac.plugins', name)
                    except ImportError, e:
                        env.log.error('Failied to load plugin %s from %s', name,
                                      egg.location, exc_info=True)
                else:
                    if egg.has_metadata('trac_plugin.txt'):
                        env.log.debug('Loading plugin %s from %s', name,
                                      egg.location)
                        # Support for pre-entry-point plugins
                        egg.activate()
                        for module in egg.get_metadata_lines('trac_plugin.txt'):
                            load_module(module)
        else:
            # setuptools < 0.6
            distributions = pkg_resources.AvailableDistributions([plugins_dir] \
                                                                 + sys.path)
            for name in distributions:
                egg = distributions[name][0]
                if egg.metadata.has_metadata(TRAC_META):
                    egg.install_on()
                    for module in egg.metadata.get_metadata_lines(TRAC_META):
                        load_module(module)

    elif os.path.exists(plugins_dir) and os.listdir(plugins_dir):
        env.log.warning('setuptools is required for plugin deployment')

    # Load default components
    from trac.db_default import default_components
    for module in default_components:
        if not module in loaded_components:
            __import__(module)
