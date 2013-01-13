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

from genshi.builder import tag
from genshi.filters import Transformer

from trac.core import Component, implements
from trac.web.api import ITemplateStreamFilter
from trac.util.presentation import captioned_button
from trac.util.translation import _


class TicketCloneButton(Component):
    """Add a 'Clone' button to the ticket box.

    This button is located next to the 'Reply' to description button,
    and pressing it will send a request for creating a new ticket
    which will be based on the cloned one.
    """

    implements(ITemplateStreamFilter)

    # ITemplateStreamFilter methods

    def filter_stream(self, req, method, filename, stream, data):
        if filename == 'ticket.html':
            ticket = data.get('ticket')
            if ticket and ticket.exists and \
                    'TICKET_ADMIN' in req.perm(ticket.resource):
                filter = Transformer('//h3[@id="comment:description"]')
                stream |= filter.after(self._clone_form(req, ticket, data))
        return stream

    def _clone_form(self, req, ticket, data):
        fields = {}
        for f in data.get('fields', []):
            name = f['name']
            if name == 'summary':
                fields['summary'] = _("%(summary)s (cloned)",
                                      summary=ticket['summary'])
            elif name == 'description':
                fields['description'] = \
                    _("Cloned from #%(id)s:\n----\n%(description)s",
                      id=ticket.id, description=ticket['description'])
            else:
                fields[name] = ticket[name]
        return tag.form(
            tag.div(
                tag.input(type="submit", name="clone",
                          value=captioned_button(req, '+#', _("Clone")),
                          title=_("Create a copy of this ticket")),
                [tag.input(type="hidden", name='field_' + n, value=v)
                 for n, v in fields.iteritems()],
                tag.input(type="hidden", name='preview', value=''),
                class_="inlinebuttons"),
            method="post", action=req.href.newticket())
