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
from copy import deepcopy
import os.path

from trac.core import ExtensionPoint, TracError
from trac.util import AtomicFile
from trac.util.compat import set, sorted
from trac.util.text import to_unicode, CRLF
from trac.util.translation import _

__all__ = ['Configuration', 'Option', 'BoolOption', 'IntOption', 'ListOption',
           'PathOption', 'ExtensionOption', 'OrderedExtensionsOption',
           'ConfigurationError']

_TRUE_VALUES = ('yes', 'true', 'enabled', 'on', 'aye', '1', 1, True)

_use_default = object()

def _to_utf8(basestr):
    return to_unicode(basestr).encode('utf-8')


class ConfigurationError(TracError):
    """Exception raised when a value in the configuration file is not valid."""
    title = 'Configuration Error'


class Configuration(object):
    """Thin layer over `ConfigParser` from the Python standard library.

    In addition to providing some convenience methods, the class remembers
    the last modification time of the configuration file, and reparses it
    when the file has changed.
    """
    def __init__(self, filename):
        self.filename = filename
        self.parser = ConfigParser()
        self._old_sections = {}
        self.parent = None
        self._base_filename = None
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

    def get(self, section, key, default=''):
        """Return the value of the specified option.
        
        Valid default input is a string. Returns a string.
        """
        return self[section].get(key, default)

    def getbool(self, section, key, default=''):
        """Return the specified option as boolean value.
        
        If the value of the option is one of "yes", "true", "enabled", "on",
        or "1", this method wll return `True`, otherwise `False`.
        
        Valid default input is a string or a bool. Returns a bool.
        
        (since Trac 0.9.3, "enabled" added in 0.11)
        """
        return self[section].getbool(key, default)

    def getint(self, section, key, default=''):
        """Return the value of the specified option as integer.
        
        If the specified option can not be converted to an integer, a
        `ConfigurationError` exception is raised.
        
        Valid default input is a string or an int. Returns an int.
        
        (since Trac 0.10)
        """
        return self[section].getint(key, default)

    def getlist(self, section, key, default='', sep=',', keep_empty=False):
        """Return a list of values that have been specified as a single
        comma-separated option.
        
        A different separator can be specified using the `sep` parameter. If
        the `keep_empty` parameter is set to `True`, empty elements are
        included in the list.
        
        Valid default input is a string or a list. Returns a string.
        
        (since Trac 0.10)
        """
        return self[section].getlist(key, default, sep, keep_empty)

    def getpath(self, section, key, default=''):
        """Return a configuration value as an absolute path.
        
        Relative paths are made absolute relative to the location of the file
        the option is read from. A value read from defaults use location of
        first configuration file as base.

        Valid default input is a string. Returns a string as correct path.
        
        (enabled since Trac 0.11.5)
        """
        return self[section].getpath(key, default)

    def set(self, section, key, value):
        """Change a configuration value.
        
        These changes are not persistent unless saved with `save()`.
        """
        self[section].set(key, value)

    def defaults(self):
        """Returns a dictionary of the default configuration values.
        
        (since Trac 0.10)
        """
        defaults = {}
        for (section, key), option in Option.registry.items():
            defaults.setdefault(section, {})[key] = option.default
        return defaults

    def options(self, section):
        """Return a list of `(name, value)` tuples for every option in the
        specified section.
        
        This includes options that have default values that haven't been
        overridden.
        """
        return self[section].options()

    def remove(self, section, key):
        """Remove the specified option."""
        section_str = _to_utf8(section)
        key_str = _to_utf8(key)
        if self.parser.has_section(section_str):
            self.parser.remove_option(section_str, key_str)

    def sections(self):
        """Return a list of section names."""
        sections = set([to_unicode(s) for s in self.parser.sections()])
        if self.parent:
            sections.update(self.parent.sections())
        else:
            sections.update(self.defaults().keys())
        return sorted(sections)

    def has_option(self, section, option):
        """Returns True if option exists in section in either project or
        parent trac.ini, or available through the Option registry.
        
        (since Trac 0.11)
        """
        section_str = _to_utf8(section)
        if self.parser.has_section(section_str):
            if _to_utf8(option) in self.parser.options(section_str):
                return True
        if self.parent:
            return self.parent.has_option(section, option)
        else:
            return (section, option) in Option.registry

    def save(self):
        """Write the configuration options to the primary file."""
        if not self.filename:
            return

        # Only save options that differ from the defaults
        sections = []
        for section in self.sections():
            section_str = _to_utf8(section)
            options = []
            for option in self[section]:
                default_str = None
                if self.parent:
                    default_str = _to_utf8(self.parent.get(section, option))
                option_str = _to_utf8(option)
                current_str = False
                if self.parser.has_option(section_str, option_str):
                    current_str = self.parser.get(section_str, option_str)
                if current_str is not False and current_str != default_str:
                    options.append((option_str, current_str))
            if options:
                sections.append((section_str, sorted(options)))

        # At this point, all the strings in `sections` are UTF-8 encoded `str`
        try:
            fileobj = AtomicFile(self.filename, 'w')
            try:
                fileobj.write('# -*- coding: utf-8 -*-\n\n')
                for section, options in sections:
                    fileobj.write('[%s]\n' % section)
                    for key_str, val_str in options:
                        if to_unicode(key_str) in self[section].overridden:
                            fileobj.write('# %s = <inherited>\n' % key_str)
                        else:
                            val_str = val_str.replace(CRLF, '\n') \
                                             .replace('\n', '\n ')
                            fileobj.write('%s = %s\n' % (key_str, val_str))
                    fileobj.write('\n')
            finally:
                fileobj.close()
            self._old_sections = deepcopy(self.parser._sections)
        except Exception:
            # Revert all changes to avoid inconsistencies
            self.parser._sections = deepcopy(self._old_sections)
            raise

    def parse_if_needed(self):
        if not self.filename or not os.path.isfile(self.filename):
            return False

        changed = False
        modtime = os.path.getmtime(self.filename)
        if modtime > self._lastmtime:
            self._sections = {}
            self.parser._sections = {}
            self.parser.read(self.filename)
            self._lastmtime = modtime
            self._old_sections = deepcopy(self.parser._sections)
            changed = True

        if self.parser.has_option('inherit', 'file'):
            filename = to_unicode(self.parser.get('inherit', 'file'))
            if not os.path.isabs(filename):
                filename = os.path.join(os.path.dirname(self.filename),
                                        filename)
            if not self.parent or self.parent.filename != filename:
                self.parent = Configuration(filename)
                self.parent._base_filename = self._base_filename \
                                                or self.filename
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
    __slots__ = ['config', 'name', 'overridden', '_cache']

    def __init__(self, config, name):
        self.config = config
        self.name = name
        self.overridden = {}
        self._cache = {}

    def __contains__(self, key):
        if self.config.parser.has_option(_to_utf8(self.name), _to_utf8(key)):
            return True
        if self.config.parent:
            return key in self.config.parent[self.name]
        return Option.registry.has_key((self.name, key))

    def __iter__(self):
        options = set()
        name_str = _to_utf8(self.name)
        if self.config.parser.has_section(name_str):
            for option_str in self.config.parser.options(name_str):
                option = to_unicode(option_str)
                options.add(option.lower())
                yield option
        if self.config.parent:
            for option in self.config.parent[self.name]:
                if option.lower() not in options:
                    yield option
        else:
            for section, option in Option.registry.keys():
                if section == self.name and option.lower() not in options:
                    yield option

    def __repr__(self):
        return '<Section [%s]>' % (self.name)

    def get(self, key, default=''):
        """Return the value of the specified option.
        
        Valid default input is a string. Returns a string.
        """
        cached = self._cache.get(key, _use_default)
        if cached is not _use_default:
            return cached
        name_str = _to_utf8(self.name)
        key_str = _to_utf8(key)
        if self.config.parser.has_option(name_str, key_str):
            value = self.config.parser.get(name_str, key_str)
        elif self.config.parent:
            value = self.config.parent[self.name].get(key, default)
        else:
            option = Option.registry.get((self.name, key))
            if option:
                value = option.default or _use_default
            else:
                value = _use_default
        if value is _use_default:
            return default
        if not value:
            value = u''
        elif isinstance(value, basestring):
            value = to_unicode(value)
        self._cache[key] = value
        return value

    def getbool(self, key, default=''):
        """Return the value of the specified option as boolean.
        
        This method returns `True` if the option value is one of "yes", "true",
        "enabled", "on", or "1", ignoring case. Otherwise `False` is returned.

        Valid default input is a string or a bool. Returns a bool.
        """
        value = self.get(key, default)
        if isinstance(value, basestring):
            value = value.lower() in _TRUE_VALUES
        return bool(value)

    def getint(self, key, default=''):
        """Return the value of the specified option as integer.
        
        If the specified option can not be converted to an integer, a
        `ConfigurationError` exception is raised.
        
        Valid default input is a string or an int. Returns an int.
        """
        value = self.get(key, default)
        if not value:
            return 0
        try:
            return int(value)
        except ValueError:
            raise ConfigurationError(
                    _('[%(section)s] %(entry)s: expected integer, got %(value)s',
                      section=self.name, entry=key, value=repr(value)))

    def getlist(self, key, default='', sep=',', keep_empty=True):
        """Return a list of values that have been specified as a single
        comma-separated option.
        
        A different separator can be specified using the `sep` parameter. If
        the `keep_empty` parameter is set to `False`, empty elements are omitted
        from the list.
        
        Valid default input is a string or a list. Returns a list.
        """
        value = self.get(key, default)
        if not value:
            return []
        if isinstance(value, basestring):
            items = [item.strip() for item in value.split(sep)]
        else:
            items = list(value)
        if not keep_empty:
            items = filter(None, items)
        return items

    def getpath(self, key, default=''):
        """Return the value of the specified option as a path name, relative to
        the location of the configuration file the option is defined in.

        Valid default input is a string. Returns a string with normalised path.
        """
        name_str = _to_utf8(self.name)
        key_str = _to_utf8(key)
        if self.config.parser.has_option(name_str, key_str):
            path = to_unicode(self.config.parser.get(name_str, key_str))
            if not path:
                return default
            if not os.path.isabs(path):
                path = os.path.join(os.path.dirname(self.config.filename),
                                    path)
            return os.path.normcase(os.path.realpath(path))
        elif self.config.parent:
            return self.config.parent[self.name].getpath(key, default)
        else:
            base = self.config._base_filename or self.config.filename
            path_opt = Option.registry.get((self.name, key), None)
            path = path_opt and path_opt.default or default
            if path and not os.path.isabs(path):
                path = os.path.join(os.path.dirname(base), path)
            return path

    def options(self):
        """Return `(key, value)` tuples for every option in the section."""
        for key in self:
            yield key, self.get(key)

    def set(self, key, value):
        """Change a configuration value.
        
        These changes are not persistent unless saved with `save()`.
        """
        self._cache.pop(key, None)
        name_str = _to_utf8(self.name)
        key_str = _to_utf8(key)
        if not self.config.parser.has_section(name_str):
            self.config.parser.add_section(name_str)
        if value is None:
            self.overridden[key] = True
            value_str = ''
        else:
            value_str = _to_utf8(value)
        return self.config.parser.set(name_str, key_str, value_str)


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
