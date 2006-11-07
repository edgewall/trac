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

from trac.core import *


class AdminCommand(object):

    def __init__(self, env, name=None, description=None):
        if name is None:
            name = self.__class__.__name__.lower()
            if name.endswith('command'):
                name = name[:-7]
        if description is None:
            description = inspect.getdoc(self.__class__)
        self.env = env
        self.config = env.config
        self.log = env.log
        self.name = name
        self.description = description

    def complete(self, args):
        return []

    def execute(self, optparser, args):
        raise NotImplementedError


class IAdminCommandProvider(Interface):
    """Extension point interface for adding commands to the admin
    command-line.
    """

    def get_admin_commands():
        """Return an `AdminCommand` instance for every supported
        command.
        """


class IAdminPanelProvider(Interface):
    """Extension point interface for adding panels to the web-based
    administration interface.
    """

    def get_admin_panels(req):
        """Return a list of available admin pages.
        
        The pages returned by this function must be a tuple of the form
        `(category, category_label, page, page_label)`.
        """

    def render_admin_paneel(req, category, page, path_info):
        """Process a request for an admin panel.
        
        This function should return a tuple of the form `(template, data)`,
        where `template` is the name of the template to use and `data` is the
        data to be passed to the template.
        """
