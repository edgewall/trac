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

from ConfigParser import ConfigParser
import os
import sys

from trac.core import *
from trac.util import doctrim

__all__ = ['IConfigurable', 'ConfigSection', 'ConfigOption', 'Configuration',
           'ConfigurationError', 'default_dir']

_TRUE_VALUES = ('yes', 'true', 'on', 'aye', '1', 1, True)


class IConfigurable(Interface):
    def get_config_sections():
        """Generate `ConfigSection` objects"""
         

class ConfigSection(object):
    def __init__(self, name, options, header=None, footer=None):
        """
        `name` is the section name.
        `options` is a list of `ConfigOption` objects.
        `header` is some documentation for the section that should appear
        before the list of options, as opposed to the `footer` documentation.
        """
        self.name = name
        self.options = options
        self.header = header and doctrim(header) or ''
        self.footer = footer and doctrim(footer) or ''
        
class ConfigOption(object):
    def __init__(self, name, default, doc):
        self.name = name
        self.default = default or ''
        self.doc = doc and doctrim(doc) or ''


class ConfigurationError(TracError):
    """Exception raised when a value in the configuration file is not valid."""


class Configuration(object):
    """Thin layer over `ConfigParser` from the Python standard library.

    In addition to providing some convenience methods, the class remembers
    the last modification time of the configuration file, and reparses it
    when the file has changed.
    """
    def __init__(self, filename):
        self._sections = {}
        self._defaults = {}
        self.filename = filename
        self.parser = ConfigParser()
        self._lastmtime = 0
        self.site_filename = os.path.join(default_dir('conf'), 'trac.ini')
        self.site_parser = ConfigParser()
        self._lastsitemtime = 0
        self.parse_if_needed()

    def __contains__(self, name):
        """Return whether the configuration contains a section of the given
        name.
        """
        return self.parser.has_section(name)

    def __getitem__(self, name):
        """Return the configuration section with the specified name."""
        if name not in self._sections:
            self._sections[name] = Section(self, name)
        return self._sections[name]

    def get(self, section, name, default=None):
        """Return the value of the specified option."""
        return self[section].get(name, default)

    def getbool(self, section, name, default=None):
        """Return the specified option as boolean value.
        
        If the value of the option is one of "yes", "true",  "on", or "1", this
        method wll return `True`, otherwise `False`.
        
        (since Trac 0.9.3)
        """
        return self[section].getbool(name, default)

    def getint(self, section, name, default=None):
        """Return the value of the specified option as integer.
        
        If the specified option can not be converted to an integer, a
        `ConfigurationError` exception is raised.
        
        (since Trac 0.10)
        """
        return self[section].getint(name, default)

    def getlist(self, section, name, default=None, sep=',', keep_empty=True):
        """Return a list of values that have been specified as a single
        comma-separated option.
        
        A different separator can be specified using the `sep` parameter. If
        the `keep_empty` parameter is set to `False`, empty elements are
        omitted from the list.
        
        (since Trac 0.10)
        """
        return self[section].getlist(name, default, sep, keep_empty)

    def setdefault(self, section, name, value):
        """Set the default value of a specific option."""
        return self[section].setdefault(name, value)

    def set(self, section, name, value):
        """Change a configuration value.
        
        These changes are not persistent unless saved with `save()`.
        """
        self[section].set(name, value)

    def options(self, section):
        """Return a list of `(name, value)` tuples for every option in the
        specified section.
        
        This includes options that have default values that haven't been
        overridden.
        """
        return self[section].options()

    def remove(self, section, name):
        """Remove the specified option."""
        if self.parser.has_section(section):
            self.parser.remove_option(section, name)

    def sections(self):
        """Return a list of section names."""
        return self.parser.sections()

    def save(self):
        """Write the configuration options to the primary file."""
        if not self.filename:
            return
        fileobj = file(self.filename, 'w')
        try:
            self.parser.write(fileobj)
        finally:
            fileobj.close()

    def parse_if_needed(self):
        # Merge global configuration option into _defaults
        if os.path.isfile(self.site_filename):
            modtime = os.path.getmtime(self.site_filename)
            if modtime > self._lastsitemtime:
                self.site_parser.read(self.site_filename)
                for section in self.site_parser.sections():
                    for option in self.site_parser.options(section):
                        value = self.site_parser.get(section, option)
                        self._defaults[(section, option)] = value
                self._lastsitemtime = modtime

        if not self.filename or not os.path.isfile(self.filename):
            return
        modtime = os.path.getmtime(self.filename)
        if modtime > self._lastmtime:
            self.parser.read(self.filename)
            self._lastmtime = modtime


class Section(object):
    """Proxy for a specific configuration section.
    
    Objects of this class should not be instantiated directly.
    """
    __slots__ = ['config', 'name']

    def __init__(self, config, name):
        self.config = config
        self.name = name

    def __contains__(self, name):
        return self.config.parser.has_option(self.name, name)

    def __iter__(self):
        options = []
        if self.config.parser.has_section(self.name):
            for option in self.config.parser.options(self.name):
                options.append(option)
                yield option
        for section, option in self.config._defaults:
            if section == self.name and option not in options:
                yield option

    def get(self, name, default=None):
        """Return the value of the specified option."""
        if not name in self:
            if default is None:
                return self.config._defaults.get((self.name, name), '')
            return default
        return self.config.parser.get(self.name, name)

    def getbool(self, name, default=None):
        """Return the value of the specified option as boolean.
        
        This method returns `True` if the option value is one of "yes", "true",
        "on", or "1", ignoring case. Otherwise `False` is returned.
        """
        if isinstance(default, basestring):
            default = default.lower()
        return self.get(name, default) in _TRUE_VALUES

    def getint(self, name, default=None):
        """Return the value of the specified option as integer.
        
        If the specified option can not be converted to an integer, a
        `ConfigurationError` exception is raised.
        """
        value = self.get(name, default)
        try:
            return int(value)
        except ValueError:
            raise ConfigurationError('expected integer, got %s' % repr(value))

    def getlist(self, name, default=None, sep=',', keep_empty=True):
        """Return a list of values that have been specified as a single
        comma-separated option.
        
        A different separator can be specified using the `sep` parameter. If
        the `skip_empty` parameter is set to `True`, empty elements are omitted
        from the list.
        """
        value = self.get(name, default)
        if value is None:
            return []
        items = [item.strip() for item in value.split(sep)]
        if not keep_empty:
            items = filter(None, items)
        return items

    def options(self):
        """Return `(name, value)` tuples for every option in the section."""
        for name in self:
            yield name, self.get(name)

    def setdefault(self, name, value):
        """Set the default value of a specific option."""
        if (self.name, name) not in self.config._defaults:
            self.config._defaults[(self.name, name)] = value

    def set(self, name, value):
        """Change a configuration value.
        
        These changes are not persistent unless saved with `save()`.
        """
        if not self.config.parser.has_section(self.name):
            self.config.parser.add_section(self.name)
        return self.config.parser.set(self.name, name, value)


def default_dir(name):
    try:
        from trac import siteconfig
        return getattr(siteconfig, '__default_%s_dir__' % name)
    except ImportError:
        # This is not a regular install with a generated siteconfig.py file,
        # so try to figure out the directory based on common setups
        special_dirs = {'wiki': 'wiki-default', 'macros': 'wiki-macros'}
        dirname = special_dirs.get(name, name)

        # First assume we're being executing directly form the source directory
        import trac
        path = os.path.join(os.path.split(os.path.dirname(trac.__file__))[0],
                            dirname)
        if not os.path.isdir(path):
            # Not being executed from the source directory, so assume the
            # default installation prefix
            path = os.path.join(sys.prefix, 'share', 'trac', dirname)

        return path
