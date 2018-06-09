# -*- coding: utf-8 -*-
#
# Copyright (C) 2010-2017 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from trac.attachment import Attachment
from trac.core import Component, TracError, implements
from trac.ticket.model import Ticket
from trac.ticket.web_ui import TicketModule
from trac.util import get_reporter_id
from trac.util.datefmt import from_utimestamp
from trac.util.translation import _
from trac.web.api import IRequestFilter, IRequestHandler
from trac.web.chrome import (ITemplateProvider, add_notice, add_script,
                             add_script_data, add_stylesheet)


class TicketDeleter(Component):
    """Ticket and ticket comment deleter.

    This component allows deleting ticket comments and complete tickets. For
    users having `TICKET_ADMIN` permission, it adds a "Delete" button next to
    each "Reply" button on the page. The button in the ticket description
    requests deletion of the complete ticket, and the buttons in the change
    history request deletion of a single comment.

    '''Comment and ticket deletion are irreversible (and therefore
    ''dangerous'') operations.''' For that reason, a confirmation step is
    requested. The confirmation page shows the ticket box (in the case of a
    ticket deletion) or the ticket change (in the case of a comment deletion).
    """

    implements(ITemplateProvider, IRequestFilter, IRequestHandler)

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        from pkg_resources import resource_filename
        yield 'ticketopt', resource_filename(__name__, 'htdocs')

    def get_templates_dirs(self):
        from pkg_resources import resource_filename
        return [resource_filename(__name__, 'templates')]

    # IRequestFilter methods

    def pre_process_request(self, req, handler):
        if handler is not TicketModule(self.env):
            return handler
        action = req.args.get('action')
        if action in ('delete', 'delete-comment'):
            return self
        else:
            return handler

    def post_process_request(self, req, template, data, metadata):
        if template in ('ticket.html', 'ticket_preview.html'):
            ticket = data.get('ticket')
            if (ticket and ticket.exists and
                    'TICKET_ADMIN' in req.perm(ticket.resource)):
                add_script(req, 'ticketopt/ticketdeleter.js')
                add_script_data(req, ui={'use_symbols':
                                         req.session.get('ui.use_symbols')})
        return template, data, metadata

    # IRequestHandler methods

    def match_request(self, req):
        return False

    def process_request(self, req):
        id = req.args.getint('id')
        req.perm('ticket', id).require('TICKET_ADMIN')
        ticket = Ticket(self.env, id)
        action = req.args['action']
        cnum = req.args.get('cnum')
        if req.method == 'POST':
            if 'cancel' in req.args:
                href = req.href.ticket(id)
                if action == 'delete-comment':
                    href += '#comment:%s' % cnum
                req.redirect(href)

            if action == 'delete':
                ticket.delete()
                add_notice(req, _("Ticket #%(num)s and all associated data "
                                  "removed.", num=ticket.id))
                redirect_to = req.href.query()
                if 'query_tickets' in req.session:
                    tickets = req.session['query_tickets'].split()
                    if str(ticket.id) in tickets:
                        redirect_to = req.session['query_href']
                req.redirect(redirect_to)

            elif action == 'delete-comment':
                cdate = from_utimestamp(int(req.args.get('cdate')))
                ticket.delete_change(cdate=cdate)
                add_notice(req, _("The ticket comment %(num)s on ticket "
                                  "#%(id)s has been deleted.",
                                  num=cnum, id=ticket.id))
                req.redirect(req.href.ticket(id))

        tm = TicketModule(self.env)
        data = tm._prepare_data(req, ticket)
        tm._insert_ticket_data(req, ticket, data,
                               get_reporter_id(req, 'author'), {})
        data.update(action=action, cdate=None)

        if action == 'delete-comment':
            data['cdate'] = req.args.get('cdate')
            cdate = from_utimestamp(int(data['cdate']))
            for change in data['changes']:
                if change.get('date') == cdate:
                    data['change'] = change
                    data['cnum'] = change.get('cnum')
                    break
            else:
                raise TracError(_("Comment %(num)s not found", num=cnum))
        elif action == 'delete':
            attachments = Attachment.select(self.env, ticket.realm, ticket.id)
            data.update(attachments=list(attachments))

        add_stylesheet(req, 'common/css/ticket.css')
        return 'ticket_delete.html', data
