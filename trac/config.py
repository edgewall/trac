# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
#
# Trac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Trac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
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
            return None
        try:
            return self.parser.items(section)
        except AttributeError:
            options = []
            for option in self.parser.options(section):
                options.append((option, self.parser.get(section, option)))
            return options

    def __contains__(self, name):
        return self.parser.has_section(name)

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
            self.parser.read(self.filename)
            self.__lastmtime = modtime
