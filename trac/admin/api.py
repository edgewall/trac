# -*- coding: utf-8 -*-
# 
# Copyright (C) 2006 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os.path
import sys
import traceback

from trac.core import *
from trac.util import common_length
from trac.util.translation import _


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
    
    def get_admin_commands(self):
        """Return a list of available admin commands.
        
        The items returned by this function must be tuples of the form
        `(command, params, help, complete, execute)`, where `command` is the
        command and sub-command name, `params` is a string describing the
        command parameters and `help` is the help text.
        
        `complete` is called to auto-complete the command arguments, and
        `execute` is called for executing the command. The latter is called
        with positional arguments consisting of the command parameters.
        """


class AdminCommandManager(Component):
    """Component registering the supported admin commands.
    """
    
    providers = ExtensionPoint(IAdminCommandProvider)
    
    def get_commands(self):
        """Return the names of the top-level commands."""
        for provider in self.providers:
            for cmd in provider.get_admin_commands():
                yield cmd[0].split(None, 1)[0]
    
    def get_command_help(self, command=None):
        """Return help information for a command, or all commands if None."""
        commands = []
        for provider in self.providers:
            for cmd in provider.get_admin_commands():
                if command is None or cmd[0].startswith(command):
                    commands.append((cmd[0] + ' ' + cmd[1], cmd[2]))
        commands.sort()
        return commands
        
    def complete_command(self, args):
        """Perform auto-completion on the given arguments."""
        comp = []
        for provider in self.providers:
            for cmd in provider.get_admin_commands():
                parts = cmd[0].split()
                common_len = common_length(args, parts)
                if common_len == 0:                 # No match
                    continue
                elif common_len < len(parts):       # Command name
                    comp.append(parts[common_len])
                elif len(args) == len(parts):       # Command name (end)
                    comp.append(parts[common_len - 1])
                else:                               # Arguments
                    if cmd[3] is None:
                        return []
                    return cmd[3](args[len(parts):]) or []
        return comp
        
    def execute_command(self, *args):
        """Execute a command given by a list of arguments."""
        args = list(args)
        for provider in self.providers:
            for cmd in provider.get_admin_commands():
                parts = cmd[0].split()
                if args[:len(parts)] == parts:
                    f = cmd[4]
                    fargs = args[len(parts):]
                    try:
                        return f(*fargs)
                    except AdminCommandError, e:
                        e.cmd = ' '.join(parts)
                        raise
                    except TypeError, e:
                        tb = traceback.extract_tb(sys.exc_info()[2])
                        if len(tb) == 1:
                            raise AdminCommandError(_("Invalid arguments"),
                                                    show_usage=True,
                                                    cmd=' '.join(parts))
                        raise
        raise AdminCommandError(_("Command not found"), show_usage=True)


class PathList(list):
    """A list of paths for command auto-completion."""


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
        path = os.path.join(dname, entry)
        try:
            if os.path.isdir(path):
                result.append(os.path.join(path, ''))
            elif not dirs_only:
                result.append(path)
        except OSError:
            pass
    return result
