# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2018 Edgewall Software
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

import copy
import os.path
import re
from ConfigParser import ConfigParser, ParsingError

from genshi.builder import tag

from trac.admin import AdminCommandError, IAdminCommandProvider
from trac.core import Component, ExtensionPoint, TracError, implements
from trac.util import AtomicFile, as_bool
from trac.util.compat import OrderedDict, wait_for_file_mtime_change
from trac.util.text import cleandoc, printout, to_unicode, to_utf8
from trac.util.translation import N_, _, dgettext, tag_

__all__ = ['Configuration', 'ConfigSection', 'Option', 'BoolOption',
           'IntOption', 'FloatOption', 'ListOption', 'ChoiceOption',
           'PathOption', 'ExtensionOption', 'OrderedExtensionsOption',
           'ConfigurationError']

_use_default = object()


def _getint(value):
    return int(value or 0)


def _getfloat(value):
    return float(value or 0.0)


def _getlist(value, sep, keep_empty):
    if not value:
        return []
    if isinstance(value, basestring):
        if isinstance(sep, (list, tuple)):
            splitted = re.split('|'.join(map(re.escape, sep)), value)
        else:
            splitted = value.split(sep)
        items = [item.strip() for item in splitted]
    else:
        items = list(value)
    if not keep_empty:
        items = [item for item in items if item not in (None, '')]
    return items


def _getdoc(option_or_section):
    doc = to_unicode(option_or_section.__doc__)
    if doc:
        doc = dgettext(option_or_section.doc_domain, doc,
                       **(option_or_section.doc_args or {}))
    return doc


class ConfigurationError(TracError):
    """Exception raised when a value in the configuration file is not valid."""
    title = N_("Configuration Error")

    def __init__(self, message=None, title=None, show_traceback=False):
        if message is None:
            message = _("Look in the Trac log for more information.")
        super(ConfigurationError, self).__init__(message, title,
                                                 show_traceback)


class UnicodeConfigParser(ConfigParser):
    """A Unicode-aware version of ConfigParser. Arguments are encoded to
    UTF-8 and return values are decoded from UTF-8.
    """

    # All of the methods of ConfigParser are overridden except
    # `getboolean`, `getint`, `getfloat`, `defaults`, `read`, `readfp`,
    # `optionxform` and `write`. `getboolean`, `getint` and `getfloat`
    # call `get`, so it isn't necessary to reimplement them.
    # The base class `RawConfigParser` doesn't inherit from `object`
    # so we can't use `super`.

    def __init__(self, ignorecase_option=True, **kwargs):
        self._ignorecase_option = ignorecase_option
        dict_type = kwargs.pop('dict_type', None) or OrderedDict
        ConfigParser.__init__(self, dict_type=dict_type, **kwargs)

    def optionxform(self, option):
        if self._ignorecase_option:
            option = option.lower()
        return option

    def sections(self):
        return map(to_unicode, ConfigParser.sections(self))

    def add_section(self, section):
        section_str = to_utf8(section)
        ConfigParser.add_section(self, section_str)

    def has_section(self, section):
        section_str = to_utf8(section)
        return ConfigParser.has_section(self, section_str)

    def options(self, section):
        section_str = to_utf8(section)
        return map(to_unicode, ConfigParser.options(self, section_str))

    def get(self, section, option, raw=False, vars=None):
        section_str = to_utf8(section)
        option_str = to_utf8(option)
        return to_unicode(ConfigParser.get(self, section_str,
                                           option_str, raw, vars))

    def items(self, section, raw=False, vars=None):
        section_str = to_utf8(section)
        return [(to_unicode(k), to_unicode(v))
                for k, v in ConfigParser.items(self, section_str, raw, vars)]

    def has_option(self, section, option):
        section_str = to_utf8(section)
        option_str = to_utf8(option)
        return ConfigParser.has_option(self, section_str, option_str)

    def set(self, section, option, value=None):
        section_str = to_utf8(section)
        option_str = to_utf8(option)
        value_str = to_utf8(value) if value is not None else ''
        ConfigParser.set(self, section_str, option_str, value_str)

    def remove_option(self, section, option):
        section_str = to_utf8(section)
        option_str = to_utf8(option)
        ConfigParser.remove_option(self, section_str, option_str)

    def remove_section(self, section):
        section_str = to_utf8(section)
        ConfigParser.remove_section(self, section_str)

    def __copy__(self):
        parser = self.__class__()
        parser._sections = copy.copy(self._sections)
        return parser

    def __deepcopy__(self, memo):
        parser = self.__class__()
        parser._sections = copy.deepcopy(self._sections)
        return parser


class Configuration(object):
    """Thin layer over `ConfigParser` from the Python standard library.

    In addition to providing some convenience methods, the class remembers
    the last modification time of the configuration file, and reparses it
    when the file has changed.
    """
    def __init__(self, filename, params={}):
        self.filename = filename
        self.parser = UnicodeConfigParser()
        self._pristine_parser = None
        self.parents = []
        self._lastmtime = 0
        self._sections = {}
        self.parse_if_needed(force=True)

    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, self.filename)

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

    @property
    def exists(self):
        """Return boolean indicating configuration file existence.

        :since: 1.0.11
        """
        return os.path.isfile(self.filename)

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
        """
        return self[section].getbool(key, default)

    def getint(self, section, key, default=''):
        """Return the value of the specified option as integer.

        If the specified option can not be converted to an integer, a
        `ConfigurationError` exception is raised.

        Valid default input is a string or an int. Returns an int.
        """
        return self[section].getint(key, default)

    def getfloat(self, section, key, default=''):
        """Return the value of the specified option as float.

        If the specified option can not be converted to a float, a
        `ConfigurationError` exception is raised.

        Valid default input is a string, float or int. Returns a float.
        """
        return self[section].getfloat(key, default)

    def getlist(self, section, key, default='', sep=',', keep_empty=False):
        """Return a list of values that have been specified as a single
        comma-separated option.

        A different separator can be specified using the `sep` parameter. The
        `sep` parameter can specify multiple values using a list or a tuple.
        If the `keep_empty` parameter is set to `True`, empty elements are
        included in the list.

        Valid default input is a string or a list. Returns a string.
        """
        return self[section].getlist(key, default, sep, keep_empty)

    def getpath(self, section, key, default=''):
        """Return a configuration value as an absolute path.

        Relative paths are resolved relative to the location of this
        configuration file.

        Valid default input is a string. Returns a normalized path.
        """
        return self[section].getpath(key, default)

    def set(self, section, key, value):
        """Change a configuration value.

        These changes are not persistent unless saved with `save()`.
        """
        self[section].set(key, value)

    def defaults(self, compmgr=None):
        """Returns a dictionary of the default configuration values.

        If `compmgr` is specified, return only options declared in components
        that are enabled in the given `ComponentManager`.
        """
        defaults = {}
        for (section, key), option in \
                Option.get_registry(compmgr).iteritems():
            defaults.setdefault(section, {})[key] = \
                option.dumps(option.default)
        return defaults

    def options(self, section, compmgr=None):
        """Return a list of `(name, value)` tuples for every option in the
        specified section.

        This includes options that have default values that haven't been
        overridden. If `compmgr` is specified, only return default option
        values for components that are enabled in the given
        `ComponentManager`.
        """
        return self[section].options(compmgr)

    def remove(self, section, key):
        """Remove the specified option."""
        self[section].remove(key)

    def sections(self, compmgr=None, defaults=True, empty=False):
        """Return a list of section names.

        If `compmgr` is specified, only the section names corresponding to
        options declared in components that are enabled in the given
        `ComponentManager` are returned.

        :param empty: If `True`, include sections from the registry that
            contain no options.
        """
        sections = set(self.parser.sections())
        for parent in self.parents:
            sections.update(parent.sections(compmgr, defaults=False))
        if defaults:
            sections.update(self.defaults(compmgr))
        if empty:
            sections.update(ConfigSection.get_registry(compmgr))
        return sorted(sections)

    def has_option(self, section, option, defaults=True):
        """Returns True if option exists in section in either the project
        trac.ini or one of the parents, or is available through the Option
        registry.
        """
        return self[section].contains(option, defaults)

    def save(self):
        """Write the configuration options to the primary file."""

        all_options = {}
        for (section, name), option in Option.get_registry().iteritems():
            all_options.setdefault(section, {})[name] = option

        def normalize(section, name, value):
            option = all_options.get(section, {}).get(name)
            return option.normalize(value) if option else value

        sections = []
        for section in self.sections():
            options = []
            for option in self[section]:
                default = None
                for parent in self.parents:
                    if parent.has_option(section, option, defaults=False):
                        default = normalize(section, option,
                                            parent.get(section, option))
                        break
                if self.parser.has_option(section, option):
                    current = normalize(section, option,
                                        self.parser.get(section, option))
                    if current != default:
                        options.append((option, current))
            if options:
                sections.append((section, sorted(options)))

        # Prepare new file contents to write to disk.
        parser = UnicodeConfigParser()
        for section, options in sections:
            parser.add_section(section)
            for key, val in options:
                parser.set(section, key, val)

        try:
            self._write(parser)
        except Exception:
            # Revert all changes to avoid inconsistencies
            self.parser = copy.deepcopy(self._pristine_parser)
            raise
        else:
            self._pristine_parser = copy.deepcopy(self.parser)

    def parse_if_needed(self, force=False):
        if not self.filename or not self.exists:
            return False

        changed = False
        modtime = os.path.getmtime(self.filename)
        if force or modtime != self._lastmtime:
            self.parser = UnicodeConfigParser()
            try:
                if not self.parser.read(self.filename):
                    raise TracError(_("Error reading '%(file)s', make sure "
                                      "it is readable.", file=self.filename))
            except ParsingError as e:
                raise TracError(e)
            self._lastmtime = modtime
            self._pristine_parser = copy.deepcopy(self.parser)
            changed = True

        if changed:
            self.parents = self._get_parents()
        else:
            for parent in self.parents:
                changed |= parent.parse_if_needed(force=force)

        if changed:
            self._sections = {}
        return changed

    def touch(self):
        if self.filename and self.exists \
                and os.access(self.filename, os.W_OK):
            wait_for_file_mtime_change(self.filename)

    def set_defaults(self, compmgr=None, component=None):
        """Retrieve all default values and store them explicitly in the
        configuration, so that they can be saved to file.

        Values already set in the configuration are not overwritten.
        """
        def set_option_default(option):
            section = option.section
            name = option.name
            if not self.has_option(section, name, defaults=False):
                value = option.dumps(option.default)
                self.set(section, name, value)

        if component:
            if component.endswith('.*'):
                component = component[:-2]
            component = component.lower().split('.')
            from trac.core import ComponentMeta
            for cls in ComponentMeta._components:
                clsname = (cls.__module__ + '.' + cls.__name__).lower() \
                                                               .split('.')
                if clsname[:len(component)] == component:
                    for option in cls.__dict__.itervalues():
                        if isinstance(option, Option):
                            set_option_default(option)
        else:
            for option in Option.get_registry(compmgr).itervalues():
                set_option_default(option)

    def _get_parents(self):
        _parents = []
        if self.parser.has_option('inherit', 'file'):
            for filename in self.parser.get('inherit', 'file').split(','):
                filename = filename.strip()
                if not os.path.isabs(filename):
                    filename = os.path.join(os.path.dirname(self.filename),
                                            filename)
                _parents.append(Configuration(filename))
        return _parents

    def _write(self, parser):
        if not self.filename:
            return
        wait_for_file_mtime_change(self.filename)
        with AtomicFile(self.filename, 'w') as fd:
            fd.writelines(['# -*- coding: utf-8 -*-\n', '\n'])
            parser.write(fd)


class Section(object):
    """Proxy for a specific configuration section.

    Objects of this class should not be instantiated directly.
    """
    __slots__ = ['config', 'name', '_cache']

    def __init__(self, config, name):
        self.config = config
        self.name = name
        self._cache = {}

    def __repr__(self):
        return '<%s [%s]>' % (self.__class__.__name__, self.name)

    def contains(self, key, defaults=True):
        if self.config.parser.has_option(self.name, key):
            return True
        for parent in self.config.parents:
            if parent[self.name].contains(key, defaults=False):
                return True
        return defaults and (self.name, key) in Option.registry

    __contains__ = contains

    def iterate(self, compmgr=None, defaults=True):
        """Iterate over the options in this section.

        If `compmgr` is specified, only return default option values for
        components that are enabled in the given `ComponentManager`.
        """
        options = set()
        if self.config.parser.has_section(self.name):
            for option in self.config.parser.options(self.name):
                options.add(option.lower())
                yield option
        for parent in self.config.parents:
            for option in parent[self.name].iterate(defaults=False):
                loption = option.lower()
                if loption not in options:
                    options.add(loption)
                    yield option
        if defaults:
            for section, option in Option.get_registry(compmgr).iterkeys():
                if section == self.name and option.lower() not in options:
                    yield option

    __iter__ = iterate

    def get(self, key, default=''):
        """Return the value of the specified option.

        Valid default input is a string. Returns a string.
        """
        cached = self._cache.get(key, _use_default)
        if cached is not _use_default:
            return cached
        if self.config.parser.has_option(self.name, key):
            value = self.config.parser.get(self.name, key)
        else:
            for parent in self.config.parents:
                value = parent[self.name].get(key, _use_default)
                if value is not _use_default:
                    break
            else:
                if default is not _use_default:
                    option = Option.registry.get((self.name, key))
                    value = option.dumps(option.default) if option \
                                                         else _use_default
                else:
                    value = _use_default
        if value is _use_default:
            return default
        self._cache[key] = value
        return value

    def getbool(self, key, default=''):
        """Return the value of the specified option as boolean.

        This method returns `True` if the option value is one of "yes",
        "true", "enabled", "on", or non-zero numbers, ignoring case.
        Otherwise `False` is returned.

        Valid default input is a string or a bool. Returns a bool.
        """
        return as_bool(self.get(key, default))

    def getint(self, key, default=''):
        """Return the value of the specified option as integer.

        If the specified option can not be converted to an integer, a
        `ConfigurationError` exception is raised.

        Valid default input is a string or an int. Returns an int.
        """
        value = self.get(key, default)
        try:
            return _getint(value)
        except ValueError:
            raise ConfigurationError(
                    _('[%(section)s] %(entry)s: expected integer,'
                      ' got %(value)s', section=self.name, entry=key,
                      value=repr(value)))

    def getfloat(self, key, default=''):
        """Return the value of the specified option as float.

        If the specified option can not be converted to a float, a
        `ConfigurationError` exception is raised.

        Valid default input is a string, float or int. Returns a float.
        """
        value = self.get(key, default)
        try:
            return _getfloat(value)
        except ValueError:
            raise ConfigurationError(
                    _('[%(section)s] %(entry)s: expected float,'
                      ' got %(value)s', section=self.name, entry=key,
                      value=repr(value)))

    def getlist(self, key, default='', sep=',', keep_empty=True):
        """Return a list of values that have been specified as a single
        comma-separated option.

        A different separator can be specified using the `sep` parameter. The
        `sep` parameter can specify multiple values using a list or a tuple.
        If the `keep_empty` parameter is set to `True`, empty elements are
        included in the list.

        Valid default input is a string or a list. Returns a list.
        """
        return _getlist(self.get(key, default), sep, keep_empty)

    def getpath(self, key, default=''):
        """Return the value of the specified option as a path, relative to
        the location of this configuration file.

        Valid default input is a string. Returns a normalized path.
        """
        path = self.get(key, default)
        if not path:
            return default
        if not os.path.isabs(path):
            path = os.path.join(os.path.dirname(self.config.filename), path)
        return os.path.normcase(os.path.realpath(path))

    def options(self, compmgr=None):
        """Return `(key, value)` tuples for every option in the section.

        This includes options that have default values that haven't been
        overridden. If `compmgr` is specified, only return default option
        values for components that are enabled in the given `ComponentManager`.
        """
        for key in self.iterate(compmgr):
            yield key, self.get(key)

    def set(self, key, value):
        """Change a configuration value.

        These changes are not persistent unless saved with `save()`.
        """
        self._cache.pop(key, None)
        if not self.config.parser.has_section(self.name):
            self.config.parser.add_section(self.name)
        return self.config.parser.set(self.name, key, value)

    def remove(self, key):
        """Delete a key from this section.

        Like for `set()`, the changes won't persist until `save()` gets
        called.
        """
        if self.config.parser.has_section(self.name):
            self._cache.pop(key, None)
            self.config.parser.remove_option(self.name, key)


def _get_registry(cls, compmgr=None):
    """Return the descriptor registry.

    If `compmgr` is specified, only return descriptors for components that
    are enabled in the given `ComponentManager`.
    """
    if compmgr is None:
        return cls.registry

    from trac.core import ComponentMeta
    components = {}
    for comp in ComponentMeta._components:
        for attr in comp.__dict__.itervalues():
            if isinstance(attr, cls):
                components[attr] = comp

    return dict(each for each in cls.registry.iteritems()
                if each[1] not in components
                   or compmgr.is_enabled(components[each[1]]))


class ConfigSection(object):
    """Descriptor for configuration sections."""

    registry = {}

    @staticmethod
    def get_registry(compmgr=None):
        """Return the section registry, as a `dict` mapping section names to
        `ConfigSection` objects.

        If `compmgr` is specified, only return sections for components that
        are enabled in the given `ComponentManager`.
        """
        return _get_registry(ConfigSection, compmgr)

    def __init__(self, name, doc, doc_domain='tracini', doc_args=None):
        """Create the configuration section."""
        self.name = name
        self.registry[self.name] = self
        self.__doc__ = cleandoc(doc)
        self.doc_domain = doc_domain
        self.doc_args = doc_args

    def __get__(self, instance, owner):
        if instance is None:
            return self
        config = getattr(instance, 'config', None)
        if config and isinstance(config, Configuration):
            return config[self.name]

    def __repr__(self):
        return '<%s [%s]>' % (self.__class__.__name__, self.name)

    @property
    def doc(self):
        """Return localized document of the section"""
        return _getdoc(self)


class Option(object):
    """Descriptor for configuration options."""

    registry = {}

    def accessor(self, section, name, default):
        return section.get(name, default)

    @staticmethod
    def get_registry(compmgr=None):
        """Return the option registry, as a `dict` mapping `(section, key)`
        tuples to `Option` objects.

        If `compmgr` is specified, only return options for components that are
        enabled in the given `ComponentManager`.
        """
        return _get_registry(Option, compmgr)

    def __init__(self, section, name, default=None, doc='',
                 doc_domain='tracini', doc_args=None):
        """Create the configuration option.

        :param section: the name of the configuration section this option
                        belongs to
        :param name: the name of the option
        :param default: the default value for the option
        :param doc: documentation of the option
        """
        self.section = section
        self.name = name
        self.default = self.normalize(default)
        self.registry[(self.section, self.name)] = self
        self.__doc__ = cleandoc(doc)
        self.doc_domain = doc_domain
        self.doc_args = doc_args

    def __get__(self, instance, owner):
        if instance is None:
            return self
        config = getattr(instance, 'config', None)
        if config and isinstance(config, Configuration):
            section = config[self.section]
            value = self.accessor(section, self.name, self.default)
            return value

    def __set__(self, instance, value):
        raise AttributeError(_("Setting attribute is not allowed."))

    def __repr__(self):
        return '<%s [%s] %r>' % (self.__class__.__name__, self.section,
                                 self.name)

    @property
    def doc(self):
        """Return localized document of the option"""
        return _getdoc(self)

    def dumps(self, value):
        """Return the value as a string to write to a trac.ini file"""
        if value is None:
            return ''
        if value is True:
            return 'enabled'
        if value is False:
            return 'disabled'
        if isinstance(value, unicode):
            return value
        return to_unicode(value)

    def normalize(self, value):
        """Normalize the given value to write to a trac.ini file"""
        return self.dumps(value)


class BoolOption(Option):
    """Descriptor for boolean configuration options."""

    def accessor(self, section, name, default):
        return section.getbool(name, default)

    def normalize(self, value):
        if value not in (True, False):
            value = as_bool(value)
        return self.dumps(value)


class IntOption(Option):
    """Descriptor for integer configuration options."""

    def accessor(self, section, name, default):
        return section.getint(name, default)

    def normalize(self, value):
        try:
            value = _getint(value)
        except ValueError:
            pass
        return self.dumps(value)


class FloatOption(Option):
    """Descriptor for float configuration options."""

    def accessor(self, section, name, default):
        return section.getfloat(name, default)

    def normalize(self, value):
        try:
            value = _getfloat(value)
        except ValueError:
            pass
        return self.dumps(value)


class ListOption(Option):
    """Descriptor for configuration options that contain multiple values
    separated by a specific character.
    """

    def __init__(self, section, name, default=None, sep=',', keep_empty=False,
                 doc='', doc_domain='tracini', doc_args=None):
        self.sep = sep
        self.keep_empty = keep_empty
        Option.__init__(self, section, name, default, doc, doc_domain,
                        doc_args)

    def accessor(self, section, name, default):
        return section.getlist(name, default, self.sep, self.keep_empty)

    def dumps(self, value):
        if isinstance(value, (list, tuple)):
            sep = self.sep
            if isinstance(sep, (list, tuple)):
                sep = sep[0]
            return sep.join(Option.dumps(self, v) or '' for v in value)
        return Option.dumps(self, value)

    def normalize(self, value):
        return self.dumps(_getlist(value, self.sep, self.keep_empty))


class ChoiceOption(Option):
    """Descriptor for configuration options providing a choice among a list
    of items.

    The default value is the first choice in the list.
    """

    def __init__(self, section, name, choices, doc='', doc_domain='tracini',
                 doc_args=None, case_sensitive=True):
        Option.__init__(self, section, name, to_unicode(choices[0]), doc,
                        doc_domain, doc_args)
        self.choices = list(set(to_unicode(c).strip() for c in choices))
        self.case_sensitive = case_sensitive

    def accessor(self, section, name, default):
        value = section.get(name, default)
        choices = self.choices[:]
        if not self.case_sensitive:
            choices = map(unicode.lower, choices)
            value = value.lower()
        try:
            idx = choices.index(value)
        except ValueError:
            raise ConfigurationError(
                    _('[%(section)s] %(entry)s: expected one of '
                      '(%(choices)s), got %(value)s',
                      section=section.name, entry=name, value=repr(value),
                      choices=', '.join('"%s"' % c
                                        for c in sorted(self.choices))))
        return self.choices[idx]


class PathOption(Option):
    """Descriptor for file system path configuration options.

    Relative paths are resolved to absolute paths using the directory
    containing the configuration file as the reference.
    """

    def accessor(self, section, name, default):
        return section.getpath(name, default)


class ExtensionOption(Option):
    """Name of a component implementing `interface`. Raises a
    `ConfigurationError` if the component cannot be found in the list of
    active components implementing the interface."""

    def __init__(self, section, name, interface, default=None, doc='',
                 doc_domain='tracini', doc_args=None):
        Option.__init__(self, section, name, default, doc, doc_domain,
                        doc_args)
        self.xtnpt = ExtensionPoint(interface)

    def __get__(self, instance, owner):
        if instance is None:
            return self
        value = Option.__get__(self, instance, owner)
        for impl in self.xtnpt.extensions(instance):
            if impl.__class__.__name__ == value:
                return impl
        raise ConfigurationError(
            tag_("Cannot find an implementation of the %(interface)s "
                 "interface named %(implementation)s. Please check "
                 "that the Component is enabled or update the option "
                 "%(option)s in trac.ini.",
                 interface=tag.code(self.xtnpt.interface.__name__),
                 implementation=tag.code(value),
                 option=tag.code("[%s] %s" % (self.section, self.name))))


class OrderedExtensionsOption(ListOption):
    """A comma separated, ordered, list of components implementing
    `interface`. Can be empty.

    If `include_missing` is true (the default) all components implementing the
    interface are returned, with those specified by the option ordered first.
    """

    def __init__(self, section, name, interface, default=None,
                 include_missing=True, doc='', doc_domain='tracini',
                 doc_args=None):
        ListOption.__init__(self, section, name, default, doc=doc,
                            doc_domain=doc_domain, doc_args=doc_args)
        self.xtnpt = ExtensionPoint(interface)
        self.include_missing = include_missing

    def __get__(self, instance, owner):
        if instance is None:
            return self
        order = ListOption.__get__(self, instance, owner)
        components = []
        implementing_classes = []
        for impl in self.xtnpt.extensions(instance):
            implementing_classes.append(impl.__class__.__name__)
            if self.include_missing or impl.__class__.__name__ in order:
                components.append(impl)
        not_found = sorted(set(order) - set(implementing_classes))
        if not_found:
            raise ConfigurationError(
                tag_("Cannot find implementation(s) of the %(interface)s "
                     "interface named %(implementation)s. Please check "
                     "that the Component is enabled or update the option "
                     "%(option)s in trac.ini.",
                     interface=tag.code(self.xtnpt.interface.__name__),
                     implementation=tag(
                         (', ' if idx != 0 else None, tag.code(impl))
                         for idx, impl in enumerate(not_found)),
                     option=tag.code("[%s] %s" % (self.section, self.name))))

        def compare(x, y):
            x, y = x.__class__.__name__, y.__class__.__name__
            if x not in order:
                return int(y in order)
            if y not in order:
                return -int(x in order)
            return cmp(order.index(x), order.index(y))
        components.sort(compare)
        return components


class ConfigurationAdmin(Component):
    """trac-admin command provider for trac.ini administration."""

    implements(IAdminCommandProvider)

    # IAdminCommandProvider methods

    def get_admin_commands(self):
        yield ('config get', '<section> <option>',
               'Get the value of the given option in "trac.ini"',
               self._complete_config, self._do_get)
        yield ('config remove', '<section> <option>',
               'Remove the specified option from "trac.ini"',
               self._complete_config, self._do_remove)
        yield ('config set', '<section> <option> <value>',
               'Set the value for the given option in "trac.ini"',
               self._complete_config, self._do_set)

    def _complete_config(self, args):
        if len(args) == 1:
            return self.config.sections(empty=True)
        elif len(args) == 2:
            return [name for (name, value) in self.config[args[0]].options()]

    def _do_get(self, section, option):
        if not self.config.has_option(section, option):
            raise AdminCommandError(
                _("Option '%(option)s' doesn't exist in section"
                  " '%(section)s'", option=option, section=section))
        printout(self.config.get(section, option))

    def _do_set(self, section, option, value):
        self.config.set(section, option, value)
        if section == 'components' and as_bool(value):
            self.config.set_defaults(component=option)
        self.config.save()
        if section == 'inherit' and option == 'file':
            self.config.parse_if_needed(force=True)  # Full reload

    def _do_remove(self, section, option):
        if not self.config.has_option(section, option):
            raise AdminCommandError(
                _("Option '%(option)s' doesn't exist in section"
                  " '%(section)s'", option=option, section=section))
        self.config.remove(section, option)
        self.config.save()
        if section == 'inherit' and option == 'file':
            self.config.parse_if_needed(force=True)  # Full reload


def get_configinfo(env):
    """Returns a list of dictionaries containing the `name` and `options`
    of each configuration section. The value of `options` is a list of
    dictionaries containing the `name`, `value` and `modified` state of
    each configuration option. The `modified` value is True if the value
    differs from its default.

    :since: version 1.1.2
    """
    all_options = {}
    for (section, name), option in \
            Option.get_registry(env.compmgr).iteritems():
        all_options.setdefault(section, {})[name] = option
    sections = []
    for section in env.config.sections(env.compmgr):
        options = []
        for name, value in env.config.options(section, env.compmgr):
            registered = all_options.get(section, {}).get(name)
            if registered:
                default = registered.default
                normalized = registered.normalize(value)
            else:
                default = u''
                normalized = unicode(value)
            options.append({'name': name, 'value': value,
                            'modified': normalized != default})
        options.sort(key=lambda o: o['name'])
        sections.append({'name': section, 'options': options})
    sections.sort(key=lambda s: s['name'])
    return sections
