# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
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
from pkg_resources import working_set, DistributionNotFound, VersionConflict, \
                          UnknownExtra
import os
import sys

from trac.util.compat import set
from trac.util.text import exception_to_unicode

__all__ = ['load_components']

def _enable_plugin(env, module):
    """Enable the given plugin module by adding an entry to the configuration.
    """
    if module + '.*' not in env.config['components']:
        env.config['components'].set(module + '.*', 'enabled')

def load_eggs(entry_point_name):
    """Loader that loads any eggs on the search path and `sys.path`."""
    def _load_eggs(env, search_path, auto_enable=None):
        # Note that the following doesn't seem to support unicode search_path
        distributions, errors = working_set.find_plugins(
            pkg_resources.Environment(search_path)
        )
        for dist in distributions:
            env.log.debug('Adding plugin %s from %s', dist, dist.location)
            working_set.add(dist)

        def _log_error(item, e):
            ue = exception_to_unicode(e)
            if isinstance(e, DistributionNotFound):
                env.log.debug('Skipping "%s": ("%s" not found)', item, ue)
            elif isinstance(e, VersionConflict):
                env.log.error('Skipping "%s": (version conflict "%s")',
                              item, ue)
            elif isinstance(e, UnknownExtra):
                env.log.error('Skipping "%s": (unknown extra "%s")', item, ue)
            elif isinstance(e, ImportError):
                env.log.error('Skipping "%s": (can\'t import "%s")', item, ue)
            else:
                env.log.error('Skipping "%s": (error "%s")', item, ue)

        for dist, e in errors.iteritems():
            _log_error(dist, e)

        for entry in working_set.iter_entry_points(entry_point_name):
            env.log.debug('Loading %s from %s', entry.name,
                          entry.dist.location)
            try:
                entry.load(require=True)
            except (ImportError, DistributionNotFound, VersionConflict,
                    UnknownExtra), e:
                _log_error(entry, e)
            else:
                if os.path.dirname(entry.dist.location) == auto_enable:
                    _enable_plugin(env, entry.module_name)
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
                    if plugin_name not in sys.modules:
                        module = imp.load_source(plugin_name, plugin_file)
                    if path == auto_enable:
                        _enable_plugin(env, plugin_name)
                except Exception, e:
                    env.log.error('Failed to load plugin from %s', plugin_file,
                                  exception_to_unicode(e, traceback=True))

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
