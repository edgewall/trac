# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2018 Edgewall Software
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
import os.path
import pkg_resources
from pkg_resources import working_set, DistributionNotFound, \
                          VersionConflict, UnknownExtra
import sys

from trac.util import get_doc, get_module_path, get_sources, get_pkginfo
from trac.util.text import exception_to_unicode, to_unicode

__all__ = ['load_components']


def _enable_plugin(env, module):
    """Enable the given plugin module if it wasn't disabled explicitly."""
    if env.is_component_enabled(module) is None:
        env.enable_component(module)


def load_eggs(entry_point_name):
    """Loader that loads any eggs on the search path and `sys.path`."""
    def _load_eggs(env, search_path, auto_enable=None):
        # Note that the following doesn't seem to support unicode search_path
        distributions, errors = working_set.find_plugins(
            pkg_resources.Environment(search_path)
        )
        for dist in distributions:
            if dist not in working_set:
                env.log.debug('Adding plugin "%s" from "%s"',
                              dist, dist.location)
                working_set.add(dist)

        def _log_error(item, e):
            ue = exception_to_unicode(e)
            if isinstance(e, DistributionNotFound):
                env.log.debug('Skipping "%s": %s', item, ue)
            elif isinstance(e, (ImportError, UnknownExtra, VersionConflict)):
                env.log.error('Skipping "%s": %s', item, ue)
            else:
                env.log.error('Skipping "%s": %s', item,
                              exception_to_unicode(e, traceback=True))

        for dist, e in errors.iteritems():
            _log_error(dist, e)

        def deregister_components(entry_point):
            """Remove components for `entry_point` from the registry."""
            from trac.core import ComponentMeta
            for name in entry_point.attrs:
                for c in ComponentMeta._components:
                    if c.__module__ == entry_point.module_name and \
                            c.__name__ == name:
                        ComponentMeta.deregister(c)

        for entry in sorted(working_set.iter_entry_points(entry_point_name),
                            key=lambda entry: entry.name):
            env.log.debug('Loading plugin "%s" from "%s"',
                          entry.name, entry.dist.location)
            try:
                entry.load(require=True)
            except Exception as e:
                _log_error(entry, e)
                deregister_components(entry)
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
                plugin_name = os.path.basename(plugin_file[:-3])
                env.log.debug("Loading file plugin %s from %s",
                              plugin_name, plugin_file)
                try:
                    if plugin_name not in sys.modules:
                        imp.load_source(plugin_name, plugin_file)
                except (ImportError, VersionConflict) as e:
                    env.log.error('Skipping "%s": %s', plugin_name,
                                  exception_to_unicode(e))
                except (Exception, SystemExit) as e:
                    env.log.error(
                        "Failed to load plugin from %s: %s", plugin_file,
                        exception_to_unicode(e, traceback=True))
                else:
                    if path == auto_enable:
                        _enable_plugin(env, plugin_name)

    return _load_py_files


def get_plugins_dir(env):
    """Return the path to the `plugins` directory of the environment.

    :since 1.0.11: Deprecated and will be removed in 1.3.1. Use the
                   Environment.plugins_dir property instead."""
    return env.plugins_dir


def load_components(env, extra_path=None, loaders=(load_eggs('trac.plugins'),
                                                   load_py_files())):
    """Load all plugin components found on the given search path."""
    plugins_dir = env.plugins_dir
    search_path = [plugins_dir]
    if extra_path:
        search_path += list(extra_path)

    for loadfunc in loaders:
        loadfunc(env, search_path, auto_enable=plugins_dir)


def get_plugin_info(env, include_core=False):
    """Return package information about Trac core and installed plugins."""
    path_sources = {}

    def find_distribution(module):
        name = module.__name__
        path = get_module_path(module)
        sources = path_sources.get(path)
        if sources is None:
            sources = path_sources[path] = get_sources(path)
        dist = sources.get(name.replace('.', '/') + '.py')
        if dist is None:
            dist = sources.get(name.replace('.', '/') + '/__init__.py')
        if dist is None:
            # This is a plain Python source file, not an egg
            dist = pkg_resources.Distribution(project_name=name,
                                              version='',
                                              location=module.__file__)
        return dist

    plugins_dir = env.plugins_dir
    plugins = {}
    from trac.core import ComponentMeta
    for component in ComponentMeta._components:
        module = sys.modules[component.__module__]

        dist = find_distribution(module)
        plugin_filename = None
        if os.path.realpath(os.path.dirname(dist.location)) == plugins_dir:
            plugin_filename = os.path.basename(dist.location)

        if dist.project_name not in plugins:
            readonly = True
            if plugin_filename and os.access(dist.location,
                                             os.F_OK + os.W_OK):
                readonly = False
            # retrieve plugin metadata
            info = get_pkginfo(dist)
            if not info:
                info = {}
                for k in ('author', 'author_email', 'home_page', 'url',
                          'license', 'summary', 'trac'):
                    v = getattr(module, k, '')
                    if v and isinstance(v, basestring):
                        if k in ('home_page', 'url'):
                            k = 'home_page'
                            v = v.replace('$', '').replace('URL: ', '')
                        else:
                            v = to_unicode(v)
                        info[k] = v
            else:
                # Info found; set all those fields to "None" that have the
                # value "UNKNOWN" as this is the value for fields that
                # aren't specified in "setup.py"
                for k in info:
                    if info[k] == 'UNKNOWN':
                        info[k] = ''
                    else:
                        # Must be encoded as unicode as otherwise Genshi
                        # may raise a "UnicodeDecodeError".
                        info[k] = to_unicode(info[k])

            # retrieve plugin version info
            version = dist.version
            if not version:
                version = (getattr(module, 'version', '') or
                           getattr(module, 'revision', ''))
                # special handling for "$Rev$" strings
                if version != '$Rev$':
                    version = version.replace('$', '').replace('Rev: ', 'r')
                else:  # keyword hasn't been expanded
                    version = ''
            plugins[dist.project_name] = {
                'name': dist.project_name, 'version': version,
                'path': dist.location, 'plugin_filename': plugin_filename,
                'readonly': readonly, 'info': info, 'modules': {},
            }
        modules = plugins[dist.project_name]['modules']
        if module.__name__ not in modules:
            summary, description = get_doc(module)
            plugins[dist.project_name]['modules'][module.__name__] = {
                'summary': summary, 'description': description,
                'components': {},
            }
        full_name = module.__name__ + '.' + component.__name__
        summary, description = get_doc(component)
        c = component
        if c in env and not issubclass(c, env.__class__):
            c = component(env)
        modules[module.__name__]['components'][component.__name__] = {
            'full_name': full_name,
            'summary': summary, 'description': description,
            'enabled': env.is_component_enabled(component),
            'required': getattr(c, 'required', False),
        }
    if not include_core:
        for name in plugins.keys():
            if name.lower() == 'trac':
                plugins.pop(name)
    return sorted(plugins.itervalues(),
                  key=lambda p: (p['name'].lower() != 'trac',
                                 p['name'].lower()))


def match_plugins_to_frames(plugins, frames):
    """Add a `frame_idx` element to plugin information as returned by
    `get_plugin_info()`, containing the index of the highest frame in the
    list that was located in the plugin.
    """
    egg_frames = [(i, f) for i, f in enumerate(frames)
                  if f['filename'].startswith('build/')]

    def find_egg_frame_index(plugin):
        for dist in pkg_resources.find_distributions(plugin['path'],
                                                     only=True):
            try:
                sources = dist.get_metadata('SOURCES.txt')
                for src in sources.splitlines():
                    if src.endswith('.py'):
                        nsrc = src.replace('\\', '/')
                        for i, f in egg_frames:
                            if f['filename'].endswith(nsrc):
                                plugin['frame_idx'] = i
                                return
            except KeyError:
                pass    # Metadata not found

    for plugin in plugins:
        base, ext = os.path.splitext(plugin['path'].replace('\\', '/'))
        if ext == '.egg' and egg_frames:
            find_egg_frame_index(plugin)
        else:
            for i, f in enumerate(frames):
                if f['filename'].startswith(base):
                    plugin['frame_idx'] = i
                    break
