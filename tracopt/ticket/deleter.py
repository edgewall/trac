# -*- coding: utf-8 -*-
#
# Copyright (C) 2010 Edgewall Software
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
from genshi.filters.transform import StreamBuffer

from trac.core import Component, TracError, implements
from trac.ticket.model import Ticket
from trac.ticket.web_ui import TicketModule
from trac.util import get_reporter_id
from trac.util.translation import _
from trac.web.api import IRequestFilter, IRequestHandler, ITemplateStreamFilter
from trac.web.chrome import ITemplateProvider, add_notice, add_stylesheet


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

    implements(ITemplateProvider, ITemplateStreamFilter, IRequestFilter,
               IRequestHandler)

    # ITemplateProvider methods
    
    def get_htdocs_dirs(self):
        return []

    def get_templates_dirs(self):
        from pkg_resources import resource_filename
        return [resource_filename(__name__, 'templates')]

    # ITemplateStreamFilter methods
    
    def filter_stream(self, req, method, filename, stream, data):
        if filename != 'ticket.html':
            return stream
        ticket = data.get('ticket')
        if not (ticket and ticket.exists
                and 'TICKET_ADMIN' in req.perm(ticket.resource)):
            return stream
        
        # Insert "Delete" buttons for ticket description and each comment
        def delete_ticket():
            return tag.form(
                tag.div(
                    tag.input(type='hidden', name='action', value='delete'),
                    tag.input(type='submit', value=_('Delete'),
                              title=_('Delete ticket')),
                    class_='inlinebuttons'),
                action='#', method='get')
        
        def delete_comment():
            for event in buffer:
                cnum = event[1][1].get('id')[12:]
                return tag.form(
                    tag.div(
                        tag.input(type='hidden', name='action',
                                  value='delete-comment'),
                        tag.input(type='hidden', name='cnum', value=cnum),
                        tag.input(type='submit', value=_('Delete'),
                                  title=_('Delete comment %(num)s',
                                          num=cnum)),
                        class_='inlinebuttons'),
                    action='#', method='get')
            
        buffer = StreamBuffer()
        return stream | Transformer('//div[@class="description"]'
                                    '/h3[@id="comment:description"]') \
            .after(delete_ticket).end() \
            .select('//div[@class="change"]/@id') \
            .copy(buffer).end() \
            .select('//div[@class="change" and @id]/h3[@class="change"]') \
            .after(delete_comment)

    # IRequestFilter methods
    
    def pre_process_request(self, req, handler):
        if handler is not TicketModule(self.env):
            return handler
        action = req.args.get('action')
        if action in ('delete', 'delete-comment'):
            return self
        else:
            return handler

    def post_process_request(self, req, template, data, content_type):
        return template, data, content_type

    # IRequestHandler methods

    def match_request(self, req):
        return False

    def process_request(self, req):
        id = int(req.args.get('id'))
        req.perm('ticket', id).require('TICKET_ADMIN')
        ticket = Ticket(self.env, id)
        action = req.args['action']
        if req.method == 'POST':
            if 'cancel' in req.args:
                href = req.href.ticket(id)
                if action == 'delete-comment':
                    href += '#comment:%s' % req.args.get('cnum')
                req.redirect(href)
            
            if action == 'delete':
                ticket.delete()
                add_notice(req, _('The ticket #%(id)s has been deleted.',
                                  id=ticket.id))
                req.redirect(req.href())
            
            elif action == 'delete-comment':
                cnum = int(req.args.get('cnum'))
                ticket.delete_change(cnum)
                add_notice(req, _('The ticket comment %(num)s on ticket '
                                  '#%(id)s has been deleted.',
                                  num=cnum, id=ticket.id))
                req.redirect(req.href.ticket(id))
            
        tm = TicketModule(self.env)
        data = tm._prepare_data(req, ticket)
        tm._insert_ticket_data(req, ticket, data,
                               get_reporter_id(req, 'author'), {})
        data.update(action=action, del_cnum=None)
        
        if action == 'delete-comment':
            cnum = int(req.args.get('cnum'))
            data['del_cnum'] = cnum
            for change in data['changes']:
                if change.get('cnum') == cnum:
                    data['change'] = change
                    break
            else:
                raise TracError(_('Comment %(num)s not found', num=cnum))
        
        add_stylesheet(req, 'common/css/ticket.css')
        return 'ticket_delete.html', data, None
