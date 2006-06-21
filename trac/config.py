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
try:
    set
except NameError:
    from sets import Set as set
import sys

from trac.core import ExtensionPoint, TracError
from trac.util import sorted, to_unicode

__all__ = ['Configuration', 'Option', 'BoolOption', 'IntOption', 'ListOption',
           'ExtensionOption', 'OrderedExtensionsOption', 'ConfigurationError',
           'default_dir']

_TRUE_VALUES = ('yes', 'true', 'on', 'aye', '1', 1, True)


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

    def getlist(self, section, name, default=None, sep=',', keep_empty=False):
        """Return a list of values that have been specified as a single
        comma-separated option.
        
        A different separator can be specified using the `sep` parameter. If
        the `keep_empty` parameter is set to `True`, empty elements are
        included in the list.
        
        (since Trac 0.10)
        """
        return self[section].getlist(name, default, sep, keep_empty)

    def set(self, section, name, value):
        """Change a configuration value.
        
        These changes are not persistent unless saved with `save()`.
        """
        self[section].set(name, value)

    def defaults(self):
        """Returns a dictionary of the default configuration values.
        
        (since Trac 0.10)
        """
        defaults = {}
        for (section, name), option in Option.registry.items():
            defaults.setdefault(section, {})[name] = option.default
        return defaults

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
        return sorted(set(self.site_parser.sections() + self.parser.sections()))

    def save(self):
        """Write the configuration options to the primary file."""
        if not self.filename:
            return

        # Only save options that differ from the defaults
        config = ConfigParser()
        for section in self.sections():
            for option in self[section]:
                default = self.site_parser.has_option(section, option) and \
                          self.site_parser.get(section, option)
                current = self.parser.has_option(section, option) and \
                          self.parser.get(section, option)
                if current is not False and current != default:
                    if not config.has_section(section):
                        config.add_section(section)
                    config.set(section, option, current or '')

        fileobj = file(self.filename, 'w')
        try:
            config.write(fileobj)
        finally:
            fileobj.close()

    def parse_if_needed(self):
        # Load global configuration
        if os.path.isfile(self.site_filename):
            modtime = os.path.getmtime(self.site_filename)
            if modtime > self._lastsitemtime:
                self.site_parser.read(self.site_filename)
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
        return self.config.parser.has_option(self.name, name) or \
               self.config.site_parser.has_option(self.name, name) 

    def __iter__(self):
        options = []
        if self.config.parser.has_section(self.name):
            for option in self.config.parser.options(self.name):
                options.append(option.lower())
                yield option
        if self.config.site_parser.has_section(self.name):
            for option in self.config.site_parser.options(self.name):
                if option.lower() not in options:
                    yield option

    def __repr__(self):
        return '<Section [%s]>' % (self.name)

    def get(self, name, default=None):
        """Return the value of the specified option."""
        if self.config.parser.has_option(self.name, name):
            value = self.config.parser.get(self.name, name)
        elif self.config.site_parser.has_option(self.name, name):
            value = self.config.site_parser.get(self.name, name)
        else:
            option = Option.registry.get((self.name, name))
            if option:
                value = option.default or default
            else:
                value = default
        if value is None:
            return ''
        return to_unicode(value)

    def getbool(self, name, default=None):
        """Return the value of the specified option as boolean.
        
        This method returns `True` if the option value is one of "yes", "true",
        "on", or "1", ignoring case. Otherwise `False` is returned.
        """
        value = self.get(name, default)
        if isinstance(value, basestring):
            value = value.lower() in _TRUE_VALUES
        return bool(value)

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
        if isinstance(value, basestring):
            items = [item.strip() for item in value.split(sep)]
        else:
            items = list(value)
        if not keep_empty:
            items = filter(None, items)
        return items

    def options(self):
        """Return `(name, value)` tuples for every option in the section."""
        for name in self:
            yield name, self.get(name)

    def set(self, name, value):
        """Change a configuration value.
        
        These changes are not persistent unless saved with `save()`.
        """
        if not self.config.parser.has_section(self.name):
            self.config.parser.add_section(self.name)
        return self.config.parser.set(self.name, name,
                                      to_unicode(value).encode('utf-8'))


class Option(object):
    """Descriptor for configuration options on `Configurable` subclasses."""

    registry = {}
    accessor = Section.get

    def __init__(self, section, name, default=None, doc=''):
        """Create the extension point.
        
        @param section: the name of the configuration section this option
            belongs to
        @param name: the name of the option
        @param default: the default value for the option
        @param doc: documentation of the option
        """
        self.section = section
        self.name = name
        self.default = default
        self.registry[(self.section, self.name)] = self
        self.__doc__ = doc

    def __get__(self, instance, owner):
        if instance is None:
            return self
        config = getattr(instance, 'config', None)
        if config and isinstance(config, Configuration):
            section = config[self.section]
            value = self.accessor(section, self.name, self.default)
            return value
        return None

    def __set__(self, instance, value):
        raise AttributeError, 'can\'t set attribute'

    def __repr__(self):
        return '<%s [%s] "%s">' % (self.__class__.__name__, self.section,
                                   self.name)


class BoolOption(Option):
    """Descriptor for boolean configuration options."""
    accessor = Section.getbool


class IntOption(Option):
    """Descriptor for integer configuration options."""
    accessor = Section.getint


class ListOption(Option):
    """Descriptor for configuration options that contain multiple values
    separated by a specific character."""

    def __init__(self, section, name, default=None, sep=',', keep_empty=False,
                 doc=''):
        Option.__init__(self, section, name, default, doc)
        self.sep = sep
        self.keep_empty = keep_empty

    def accessor(self, section, name, default):
        return section.getlist(name, default, self.sep, self.keep_empty)


class ExtensionOption(Option):

    def __init__(self, section, name, interface, default=None, doc=''):
        Option.__init__(self, section, name, default, doc)
        self.xtnpt = ExtensionPoint(interface)

    def __get__(self, instance, owner):
        if instance is None:
            return self
        value = Option.__get__(self, instance, owner)
        for impl in self.xtnpt.extensions(instance):
            if impl.__class__.__name__ == value:
                return impl
        raise AttributeError('Cannot find an implementation of the "%s" '
                             'interface named "%s".  Please update the option '
                             '%s.%s in trac.ini.'
                             % (self.xtnpt.interface.__name__, value,
                                self.section, self.name))


class OrderedExtensionsOption(ListOption):
    """A comma separated, ordered, list of components implementing `interface`.
    Can be empty.

    If `include_missing` is true (the default) all components implementing the
    interface are returned, with those specified by the option ordered first."""

    def __init__(self, section, name, interface, default=None,
                 include_missing=True, doc=''):
        ListOption.__init__(self, section, name, default, doc=doc)
        self.xtnpt = ExtensionPoint(interface)
        self.include_missing = include_missing

    def __get__(self, instance, owner):
        if instance is None:
            return self
        order = ListOption.__get__(self, instance, owner)
        components = []
        for impl in self.xtnpt.extensions(instance):
            if self.include_missing or impl.__class__.__name__ in order:
                components.append(impl)

        def compare(x, y):
            x, y = x.__class__.__name__, y.__class__.__name__
            if x not in order:
                return int(y in order)
            if y not in order:
                return -int(x in order)
            return cmp(order.index(x), order.index(y))
        components.sort(compare)
        return components


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
