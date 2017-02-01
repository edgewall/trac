# -*- coding: utf-8 -*-
#
# Copyright (C) 2011 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from trac.core import Component, implements
from trac.util.html import tag
from trac.util.presentation import captioned_button
from trac.util.translation import _
from trac.web.api import IRequestFilter
from trac.web.chrome import ITemplateProvider, add_script, add_script_data


class TicketCloneButton(Component):
    """Add a ''Clone'' button in the ticket box and in ticket comments.

    This button is located next to the 'Reply' to description button,
    and pressing it will send a request for creating a new ticket
    which will be based on the cloned one.
    """

    implements(IRequestFilter, ITemplateProvider)

    # IRequestFilter methods

    def pre_process_request(self, req, handler):
        return handler

    def post_process_request(self, req, template, data, content_type):
        if template == 'ticket.html':
            add_script(req, 'ticketopt/ticketclone.js')
            add_script_data(req, baseurl=req.href(), ui={
                    'use_symbols': req.session.get('ui.use_symbols')})
        return template, data, content_type

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        from pkg_resources import resource_filename
        yield 'ticketopt', resource_filename(__name__, 'htdocs')

    def get_templates_dirs(self):
        return []
