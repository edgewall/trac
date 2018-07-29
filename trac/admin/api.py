# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os
import os.path
import sys
import traceback

from trac.core import *
from trac.util.text import levenshtein_distance
from trac.util.translation import _, get_negotiated_locale, has_babel


LANG = os.environ.get('LANG')

console_date_format = '%Y-%m-%d'
console_datetime_format = '%Y-%m-%d %H:%M:%S'
console_date_format_hint = 'YYYY-MM-DD'


class IAdminPanelProvider(Interface):
    """Extension point interface for adding panels to the web-based
    administration interface.
    """

    def get_admin_panels(req):
        """Return a list of available admin panels.

        The items returned by this function must be tuples of the form
        `(category, category_label, page, page_label)`.
        """

    def render_admin_panel(req, category, page, path_info):
        """Process a request for an admin panel.

        This function should return a tuple of the form `(template, data)`,
        where `template` is the name of the template to use and `data` is the
        data to be passed to the template.
        """


class AdminCommandError(TracError):
    """Exception raised when an admin command cannot be executed."""
    def __init__(self, msg, show_usage=False, cmd=None):
        TracError.__init__(self, msg)
        self.show_usage = show_usage
        self.cmd = cmd


class IAdminCommandProvider(Interface):
    """Extension point interface for adding commands to the console
    administration interface `trac-admin`.
    """

    def get_admin_commands():
        """Return a list of available admin commands.

        The items returned by this function must be tuples of the form
        `(command, args, help, complete, execute)`, where `command` contains
        the space-separated command and sub-command names, `args` is a string
        describing the command arguments and `help` is the help text. The
        first paragraph of the help text is taken as a short help, shown in the
        list of commands.

        `complete` is called to auto-complete the command arguments, with the
        current list of arguments as its only argument. It should return a list
        of relevant values for the last argument in the list.

        `execute` is called to execute the command, with the command arguments
        passed as positional arguments.
        """


class AdminCommandManager(Component):
    """trac-admin command manager."""

    providers = ExtensionPoint(IAdminCommandProvider)

    def get_command_help(self, args=[]):
        """Return help information for a set of commands."""
        commands = []
        for provider in self.providers:
            for cmd in provider.get_admin_commands() or []:
                parts = cmd[0].split()
                if parts[:len(args)] == args:
                    commands.append(cmd[:3])
        commands.sort()
        return commands

    def complete_command(self, args, cmd_only=False):
        """Perform auto-completion on the given arguments."""
        comp = []
        for provider in self.providers:
            for cmd in provider.get_admin_commands() or []:
                parts = cmd[0].split()
                plen = min(len(parts), len(args) - 1)
                if args[:plen] != parts[:plen]:         # Prefix doesn't match
                    continue
                elif len(args) <= len(parts):           # Command name
                    comp.append(parts[len(args) - 1])
                elif not cmd_only:                      # Arguments
                    if cmd[3] is None:
                        return []
                    return cmd[3](args[len(parts):]) or []
        return comp

    def execute_command(self, *args):
        """Execute a command given by a list of arguments."""
        args = list(args)
        for provider in self.providers:
            for cmd in provider.get_admin_commands() or []:
                parts = cmd[0].split()
                if args[:len(parts)] == parts:
                    f = cmd[4]
                    fargs = args[len(parts):]
                    try:
                        return f(*fargs)
                    except AdminCommandError as e:
                        e.cmd = ' '.join(parts)
                        raise
                    except TypeError as e:
                        tb = traceback.extract_tb(sys.exc_info()[2])
                        if len(tb) == 1:
                            raise AdminCommandError(_("Invalid arguments"),
                                                    show_usage=True,
                                                    cmd=' '.join(parts))
                        raise
        raise AdminCommandError(_("Command not found"), show_usage=True)

    def get_similar_commands(self, arg, n=5):
        if not arg:
            return []

        cmds = set()
        for provider in self.providers:
            for cmd in provider.get_admin_commands() or []:
                cmds.add(cmd[0].split()[0]) # use only first token

        def score(cmd, arg):
            if cmd.startswith(arg):
                return 0
            return levenshtein_distance(cmd, arg) / float(len(cmd) + len(arg))
        similars = sorted((score(cmd, arg), cmd) for cmd in cmds)
        similars = [cmd for val, cmd in similars if val <= 0.5]
        return similars[:n]


class PrefixList(list):
    """A list of prefixes for command argument auto-completion."""
    def complete(self, text):
        return list(set(a for a in self if a.startswith(text)))


def path_startswith(path, prefix):
    return os.path.normcase(path).startswith(os.path.normcase(prefix))


class PathList(list):
    """A list of paths for command argument auto-completion."""
    def complete(self, text):
        """Return the items in the list matching text."""
        matches = list(set(a for a in self if path_startswith(a, text)))
        if len(matches) == 1 and not os.path.isdir(matches[0]):
            matches[0] += ' '
        return matches


def get_dir_list(path, dirs_only=False):
    """Return a list of paths to filesystem entries in the same directory
    as the given path."""
    dname = os.path.dirname(path)
    d = os.path.join(os.getcwd(), dname)
    result = PathList()
    try:
        dlist = os.listdir(d)
    except OSError:
        return result
    for entry in dlist:
        path = os.path.normpath(os.path.join(dname, entry))
        try:
            if os.path.isdir(path):
                result.append(os.path.join(path, ''))
            elif not dirs_only:
                result.append(path)
        except OSError:
            pass
    return result


def get_console_locale(env=None, lang=None,
                       categories=('LANGUAGE', 'LC_ALL', 'LC_MESSAGES',
                                   'LANG')):
    """Return negotiated locale for console by locale environments and
    [trac] default_language."""
    if has_babel:
        from babel.core import UnknownLocaleError, parse_locale
        def normalize(value):
            if not value:
                return None
            try:
                return '_'.join(filter(None, parse_locale(value)))
            except:
                return None
        locales = [lang]
        for category in categories:
            value = os.environ.get(category)
            if not value:
                continue
            if category == 'LANGUAGE' and ':' in value:
                value = value.split(':')[0]
            locales.append(value)
        if env:
            locales.append(env.config.get('trac', 'default_language'))
        locales = filter(None, map(normalize, locales))
        try:
            return get_negotiated_locale(locales)
        except UnknownLocaleError:
            pass
    return None
