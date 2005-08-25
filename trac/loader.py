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
import imp
import sys

try:
    import pkg_resources
except ImportError:
    pkg_resources = None

TRAC_META = 'trac_plugin.txt'

__all__ = ['load_components']

def load_components(env):
    loaded_components = []

    # Load configured modules
    for section in env.config.sections():
        for name, value in env.config.options(section):
            if name == 'module':
                loaded_components.append(value)
                path = env.config.get(section, 'path') or None
                env.log.debug('Loading component module %s from %s', value,
                              path or 'default path')
                if path:
                    path = [path]
                try:
                    load_component(value, path)
                except ImportError, e:
                    env.log.error('Component module %s not found', value,
                                  exc_info=True)

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
            load_component(module)

def load_component(name, path=None):
    if path and os.path.isfile(path[0]):
        try:
            from zipimport import zipimporter
            zip = zipimporter(path[0])
            return zip.load_module(name)
        except ImportError:
            pass

    if '.' in name:
        i = name.find('.')
        head, tail = name[:i], name[i + 1:]
    else:
        head, tail = name, ''

    module = _load_module(head, head, None, path)
    if not module:
        raise ImportError, 'No module named ' + head

    while tail:
        i = tail.find('.')
        if i < 0:
            i = len(tail)
        head, tail = tail[:i], tail[i + 1:]
        module_name = '%s.%s' % (module.__name__, head)
        module = _load_module(head, module_name, module, path)
        if not module:
            raise ImportError, 'No module named ' + module_name

def _load_module(part, name, parent, path=None):
    try:
        return sys.modules[name]
    except KeyError:
        try:
            fd, path, desc = imp.find_module(part,
                                             parent and parent.__path__ or path)
        except ImportError:
            return None
        try:
            module = imp.load_module(name, fd, path, desc)
        finally:
            if fd:
                fd.close()
        return module
