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

try:
    import pkg_resources
except ImportError:
    pkg_resources = None

TRAC_META = 'trac_plugin.txt'

__all__ = ['load_components']

def load_components(env):
    loaded_components = []

    # Load components from the environment plugins directory
    plugins_dir = os.path.join(env.path, 'plugins')
    if pkg_resources is not None: # But only if setuptools is installed!
        distributions = pkg_resources.AvailableDistributions()
        distributions.scan([plugins_dir])
        for name in distributions:
            egg = distributions[name][0]
            if egg.metadata.has_metadata(TRAC_META):
                env.log.debug('Loading component egg %s from %s', egg.name,
                              egg.path)
                egg.install_on() # Put the egg on sys.path
                for module in egg.metadata.get_metadata_lines(TRAC_META):
                    if module not in loaded_components:
                        try:
                            __import__(module)
                            loaded_components.append(module)
                        except ImportError, e:
                            env.log.error('Component module %s not found',
                                          module, exc_info=True)
    elif os.path.exists(plugins_dir) and os.listdir(plugins_dir):
        env.log.warning('setuptools is required for plugin deployment')

    # Load default components
    from trac.db_default import default_components
    for module in default_components:
        if not module in loaded_components:
            __import__(module)
