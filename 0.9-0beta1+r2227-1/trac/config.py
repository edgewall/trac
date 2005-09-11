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

from __future__ import generators

from ConfigParser import ConfigParser
import os.path


class Configuration:
    """
    Thin layer over ConfigParser from the Python standard library.
    In addition to providing some convenience methods, the class remembers
    the last modification time of the configuration file, and reparses it
    when the file has changed.
    """

    def __init__(self, filename):
        self.filename = filename
        self.parser = ConfigParser()
        self.__defaults = {}
        self.__lastmtime = 0
        self.parse_if_needed()

    def get(self, section, name, default=None):
        if not self.parser.has_option(section, name):
            if default is None:
                return self.__defaults.get((section, name), '')
            return default
        return self.parser.get(section, name)

    def setdefault(self, section, name, value):
        self.__defaults[(section, name)] = value

    def set(self, section, name, value):
        """
        Changes a config value, these changes are _not_ persistent unless saved
        with `save()`.
        """
        if not self.parser.has_section(section):
            self.parser.add_section(section)
        return self.parser.set(section, name, value)

    def options(self, section):
        if not self.parser.has_section(section):
            return []
        try:
            return self.parser.items(section)
        except AttributeError:
            options = []
            for option in self.parser.options(section):
                options.append((option, self.parser.get(section, option)))
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
        self.parser.write(open(self.filename, 'w'))

    def parse_if_needed(self):
        if not self.filename:
            return
        modtime = os.path.getmtime(self.filename)
        if modtime > self.__lastmtime:
            self.parser.readfp(open(self.filename))
            self.__lastmtime = modtime


def default_dir(name):
    try:
        from trac import siteconfig
        return getattr(siteconfig, '__default_%s_dir__' % name)
    except ImportError:
        # This is not a regular install with a generated siteconfig.py file,
        # so try to figure out the directory based on common setups
        import os.path, sys
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
