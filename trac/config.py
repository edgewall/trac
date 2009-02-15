# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
# Copyright (C) 2005-2007 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from ConfigParser import ConfigParser
import os

from trac.core import ExtensionPoint, TracError
from trac.util.compat import set, sorted
from trac.util.text import to_unicode, CRLF

__all__ = ['Configuration', 'Option', 'BoolOption', 'IntOption', 'ListOption',
           'PathOption', 'ExtensionOption', 'OrderedExtensionsOption',
           'ConfigurationError']

_TRUE_VALUES = ('yes', 'true', 'enabled', 'on', 'aye', '1', 1, True)


class ConfigurationError(TracError):
    """Exception raised when a value in the configuration file is not valid."""


class Configuration(object):
    """Thin layer over `ConfigParser` from the Python standard library.

    In addition to providing some convenience methods, the class remembers
    the last modification time of the configuration file, and reparses it
    when the file has changed.
    """
    def __init__(self, filename):
        self.filename = filename
        self.parser = ConfigParser()
        self.parent = None
        self._lastmtime = 0
        self._sections = {}
        self.parse_if_needed()

    def __contains__(self, name):
        """Return whether the configuration contains a section of the given
        name.
        """
        return name in self.sections()

    def __getitem__(self, name):
        """Return the configuration section with the specified name."""
        if name not in self._sections:
            self._sections[name] = Section(self, name)
        return self._sections[name]

    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, self.filename)

    def get(self, section, name, default=''):
        """Return the value of the specified option.
        
        Valid default input is a string. Returns a string.
        """
        return self[section].get(name, default)

    def getbool(self, section, name, default=''):
        """Return the specified option as boolean value.
        
        If the value of the option is one of "yes", "true", "enabled", "on",
        or "1", this method wll return `True`, otherwise `False`.
        
        Valid default input is a string or a bool. Returns a bool.
        
        (since Trac 0.9.3, "enabled" added in 0.11)
        """
        return self[section].getbool(name, default)

    def getint(self, section, name, default=''):
        """Return the value of the specified option as integer.
        
        If the specified option can not be converted to an integer, a
        `ConfigurationError` exception is raised.
        
        Valid default input is a string or an int. Returns an int.
        
        (since Trac 0.10)
        """
        return self[section].getint(name, default)

    def getlist(self, section, name, default='', sep=',', keep_empty=False):
        """Return a list of values that have been specified as a single
        comma-separated option.
        
        A different separator can be specified using the `sep` parameter. If
        the `keep_empty` parameter is set to `True`, empty elements are
        included in the list.
        
        Valid default input is a string or a list. Returns a string.
        
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
        sections = set(self.parser.sections())
        parent = self.parent
        while parent:
            sections |= set(parent.parser.sections())
            parent = parent.parent
        return sorted(sections)

    def has_option(self, section, option):
        """Returns True if option exists in section in either project or
        parent trac.ini, or available through the Option registry.
        
        (since Trac 0.11)
        """
        # Check project trac.ini
        for file_option, val in self.options(section):
            if file_option == option:
                return True
        # Check parent trac.ini
        if self.parent:
            for parent_option, val in self.parent.options(section):
                if parent_option == option:
                    return True
        # Check the registry
        if (section, option) in Option.registry:
            return True
        # Not found
        return False

    def save(self):
        """Write the configuration options to the primary file."""
        if not self.filename:
            return

        # Only save options that differ from the defaults
        sections = []
        for section in self.sections():
            options = []
            for option in self[section]:
                default = None
                if self.parent:
                    default = self.parent.get(section, option)
                current = self.parser.has_option(section, option) and \
                          to_unicode(self.parser.get(section, option))
                if current is not False and current != default:
                    options.append((option, current))
            if options:
                sections.append((section, sorted(options)))

        fileobj = open(self.filename, 'w')
        try:
            fileobj.write('# -*- coding: utf-8 -*-\n\n')
            for section, options in sections:
                fileobj.write('[%s]\n' % section)
                for key, val in options:
                    if key in self[section].overridden:
                        fileobj.write('# %s = <inherited>\n' % key)
                    else:
                        val = val.replace(CRLF, '\n').replace('\n', '\n ')
                        fileobj.write('%s = %s\n' % (key, val.encode('utf-8')))
                fileobj.write('\n')
        finally:
            fileobj.close()

    def parse_if_needed(self):
        if not self.filename or not os.path.isfile(self.filename):
            return False

        changed = False
        modtime = os.path.getmtime(self.filename)
        if modtime > self._lastmtime:
            self.parser._sections = {}
            self.parser.read(self.filename)
            self._lastmtime = modtime
            changed = True

        if self.parser.has_option('inherit', 'file'):
            filename = self.parser.get('inherit', 'file')
            if not os.path.isabs(filename):
                filename = os.path.join(os.path.dirname(self.filename),
                                        filename)
            if not self.parent or self.parent.filename != filename:
                self.parent = Configuration(filename)
                changed = True
            else:
                changed |= self.parent.parse_if_needed()
        elif self.parent:
            changed = True
            self.parent = None

        return changed

    def touch(self):
        if self.filename and os.path.isfile(self.filename) \
           and os.access(self.filename, os.W_OK):
            os.utime(self.filename, None)


class Section(object):
    """Proxy for a specific configuration section.
    
    Objects of this class should not be instantiated directly.
    """
    __slots__ = ['config', 'name', 'overridden']

    def __init__(self, config, name):
        self.config = config
        self.name = name
        self.overridden = {}

    def __contains__(self, name):
        if self.config.parser.has_option(self.name, name):
            return True
        if self.config.parent:
            return name in self.config.parent[self.name]
        return False

    def __iter__(self):
        options = set()
        if self.config.parser.has_section(self.name):
            for option in self.config.parser.options(self.name):
                options.add(option.lower())
                yield option
        if self.config.parent:
            for option in self.config.parent[self.name]:
                if option.lower() not in options:
                    yield option

    def __repr__(self):
        return '<Section [%s]>' % (self.name)

    def get(self, name, default=''):
        """Return the value of the specified option.
        
        Valid default input is a string. Returns a string.
        """
        if self.config.parser.has_option(self.name, name):
            value = self.config.parser.get(self.name, name)
        elif self.config.parent:
            value = self.config.parent[self.name].get(name, default)
        else:
            option = Option.registry.get((self.name, name))
            if option:
                value = option.default or default
            else:
                value = default
        if not value:
            return u''
        elif isinstance(value, basestring):
            return to_unicode(value)
        else:
            return value

    def getbool(self, name, default=''):
        """Return the value of the specified option as boolean.
        
        This method returns `True` if the option value is one of "yes", "true",
        "enabled", "on", or "1", ignoring case. Otherwise `False` is returned.

        Valid default input is a string or a bool. Returns a bool.
        """
        value = self.get(name, default)
        if isinstance(value, basestring):
            value = value.lower() in _TRUE_VALUES
        return bool(value)

    def getint(self, name, default=''):
        """Return the value of the specified option as integer.
        
        If the specified option can not be converted to an integer, a
        `ConfigurationError` exception is raised.
        
        Valid default input is a string or an int. Returns an int.
        """
        value = self.get(name, default)
        if not value:
            return 0
        try:
            return int(value)
        except ValueError:
            raise ConfigurationError('expected integer, got %s' % repr(value))

    def getlist(self, name, default='', sep=',', keep_empty=True):
        """Return a list of values that have been specified as a single
        comma-separated option.
        
        A different separator can be specified using the `sep` parameter. If
        the `keep_empty` parameter is set to `False`, empty elements are omitted
        from the list.
        
        Valid default input is a string or a list. Returns a list.
        """
        value = self.get(name, default)
        if not value:
            return []
        if isinstance(value, basestring):
            items = [item.strip() for item in value.split(sep)]
        else:
            items = list(value)
        if not keep_empty:
            items = filter(None, items)
        return items

    def getpath(self, name, default=''):
        """Return the value of the specified option as a path name, relative to
        the location of the configuration file the option is defined in.

        Valid default input is a string. Returns a string with normalised path.
        """
        if self.config.parser.has_option(self.name, name):
            path = self.config.parser.get(self.name, name)
            if not path:
                return default
            if not os.path.isabs(path):
                path = os.path.join(os.path.dirname(self.config.filename),
                                    path)
            return os.path.normcase(os.path.realpath(path))
        elif self.config.parent:
            return self.config.parent[self.name].getpath(name, default)
        else:
            return default

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
        if value is None:
            self.overridden[name] = True
            value = ''
        else:
            value = to_unicode(value).encode('utf-8')
        return self.config.parser.set(self.name, name, value)


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

class PathOption(Option):
    """Descriptor for file system path configuration options."""
    accessor = Section.getpath


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
