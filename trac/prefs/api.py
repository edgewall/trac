# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2014 Edgewall Software
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


class IPreferencePanelProvider(Interface):
    """Provides panels for managing user preferences."""

    def get_preference_panels(req):
        """Return a list of available preference panels.

        The items returned by this function must be tuple of the form
        `(panel, label)`, or `(panel, label, parent_panel)` for child panels.
        """

    def render_preference_panel(req, panel):
        """Process a request for a preference panel.

        This function should return a tuple of the form `(template, data)`,
        where `template` is the name of the template to use and `data` is the
        data to be passed to the template.
        """
