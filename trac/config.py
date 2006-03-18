# -*- coding: utf-8 -*-
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

from ConfigParser import ConfigParser
import os
import sys

_TRUE_VALUES = ('yes', 'true',  'on', 'aye', '1', 1, True)


class Configuration:
    """Thin layer over `ConfigParser` from the Python standard library.

    In addition to providing some convenience methods, the class remembers
    the last modification time of the configuration file, and reparses it
    when the file has changed.
    """

    def __init__(self, filename):
        self._defaults = {}
        self.filename = filename
        self.parser = ConfigParser()
        self._lastmtime = 0
        self.site_filename = os.path.join(default_dir('conf'), 'trac.ini')
        self.site_parser = ConfigParser()
        self._lastsitemtime = 0
        self.parse_if_needed()

    def get(self, section, name, default=None):
        if not self.parser.has_option(section, name):
            return self._defaults.get((section, name)) or default or ''
        return self.parser.get(section, name)

    def getbool(self, section, name, default=None):
        """Return the specified option as boolean value.
        
        If the value of the option is one of "yes", "true",  "on", or "1", this
        method wll return `True`, otherwise `False`.
        
        (since Trac 0.9.3)
        """
        if isinstance(default, basestring):
            default = default.lower()
        return self.get(section, name, default) in _TRUE_VALUES

    def setdefault(self, section, name, value):
        if (section, name) not in self._defaults:
            self._defaults[(section, name)] = value

    def set(self, section, name, value):
        """Change a configuration value.
        
        These changes are not persistent unless saved with `save()`.
        """
        if not self.parser.has_section(section):
            self.parser.add_section(section)
        return self.parser.set(section, name, value)

    def options(self, section):
        options = []
        if self.parser.has_section(section):
            for option in self.parser.options(section):
                options.append((option, self.parser.get(section, option)))
        for option, value in self._defaults.iteritems():
            if option[0] == section:
                if not [exists for exists in options if exists[0] == option[1]]:
                    options.append((option[1], value))
        return options

    def __contains__(self, name):
        return self.parser.has_section(name)

    def remove(self, section, name):
        if self.parser.has_section(section):
            self.parser.remove_option(section, name)

    def sections(self):
        return self.parser.sections()

    def save(self):
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
