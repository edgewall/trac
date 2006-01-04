# -*- coding: iso-8859-1 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
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
# Author: Jonas Borgström <jonas@edgewall.com>

from trac import util
from trac.core import *
from trac.perm import IPermissionRequestor
from trac.wiki import IWikiSyntaxProvider
from trac.Search import ISearchSource, query_to_sql, shorten_result


class TicketSystem(Component):
    implements(IPermissionRequestor, IWikiSyntaxProvider, ISearchSource)

    # Public API

    def get_available_actions(self, ticket, perm_):
        """Returns the actions that can be performed on the ticket."""
        actions = {
            'new':      ['leave', 'resolve', 'reassign', 'accept'],
            'assigned': ['leave', 'resolve', 'reassign'          ],
            'reopened': ['leave', 'resolve', 'reassign'          ],
            'closed':   ['leave',                        'reopen']
        }
        perms = {'resolve': 'TICKET_MODIFY', 'reassign': 'TICKET_CHGPROP',
                 'accept': 'TICKET_CHGPROP', 'reopen': 'TICKET_CREATE'}
        return [action for action in actions.get(ticket['status'], ['leave'])
                if action not in perms or perm_.has_permission(perms[action])]

    def get_ticket_fields(self):
        """Returns the list of fields available for tickets."""
        from trac.ticket import model

        db = self.env.get_db_cnx()
        fields = []

        # Basic text fields
        for name in ('summary', 'reporter'):
            field = {'name': name, 'type': 'text', 'label': name.title()}
            fields.append(field)

        # Owner field, can be text or drop-down depending on configuration
        field = {'name': 'owner', 'label': 'Owner'}
        if self.config.getbool('ticket', 'restrict_owner'):
            field['type'] = 'select'
            users = []
            for username, name, email in self.env.get_known_users(db):
                users.append(username)
            field['options'] = users
            field['optional'] = True
        else:
            field['type'] = 'text'
        fields.append(field)

        # Description
        fields.append({'name': 'description', 'type': 'textarea',
                       'label': 'Description'})

        # Default select and radio fields
        selects = [('type', model.Type), ('status', model.Status),
                   ('priority', model.Priority), ('milestone', model.Milestone),
                   ('component', model.Component), ('version', model.Version),
                   ('severity', model.Severity), ('resolution', model.Resolution)]
        for name, cls in selects:
            options = [val.name for val in cls.select(self.env, db=db)]
            if not options:
                # Fields without possible values are treated as if they didn't
                # exist
                continue
            field = {'name': name, 'type': 'select', 'label': name.title(),
                     'value': self.config.get('ticket', 'default_' + name),
                     'options': options}
            if name in ('status', 'resolution'):
                field['type'] = 'radio'
            elif name in ('milestone', 'version'):
                field['optional'] = True
            fields.append(field)

        # Advanced text fields
        for name in ('keywords', 'cc', ):
            field = {'name': name, 'type': 'text', 'label': name.title()}
            fields.append(field)

        custom_fields = self.get_custom_fields()
        for field in custom_fields:
            field['custom'] = True

        return fields + custom_fields

    def get_custom_fields(self):
        fields = []
        for name in [option for option, value
                     in self.config.options('ticket-custom')
                     if '.' not in option]:
            field = {
                'name': name,
                'type': self.config.get('ticket-custom', name),
                'order': int(self.config.get('ticket-custom', name + '.order', '0')),
                'label': self.config.get('ticket-custom', name + '.label', ''),
                'value': self.config.get('ticket-custom', name + '.value', '')
            }
            if field['type'] == 'select' or field['type'] == 'radio':
                options = self.config.get('ticket-custom', name + '.options')
                field['options'] = [value.strip() for value in options.split('|')]
            elif field['type'] == 'textarea':
                field['width'] = self.config.get('ticket-custom', name + '.cols')
                field['height'] = self.config.get('ticket-custom', name + '.rows')
            fields.append(field)

        fields.sort(lambda x, y: cmp(x['order'], y['order']))
        return fields

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['TICKET_APPEND', 'TICKET_CREATE', 'TICKET_CHGPROP',
                'TICKET_VIEW',  
                ('TICKET_MODIFY', ['TICKET_APPEND', 'TICKET_CHGPROP']),  
                ('TICKET_ADMIN', ['TICKET_CREATE', 'TICKET_MODIFY',  
                                  'TICKET_VIEW'])]

    # IWikiSyntaxProvider methods

    def get_link_resolvers(self):
        return [('bug', self._format_link),
                ('ticket', self._format_link)]

    def get_wiki_syntax(self):
        yield (r"(?:\A|[^&])#\d+", # #123 but not &#123; (HTML entity)
               lambda x, y, z: self._format_link(x, 'ticket', y[1:], y))

    def _format_link(self, formatter, ns, target, label):
        cursor = formatter.db.cursor()
        cursor.execute("SELECT summary,status FROM ticket WHERE id=%s",
                       (target,))
        row = cursor.fetchone()
        if row:
            summary = util.escape(util.shorten_line(row[0]))
            return '<a class="%s ticket" href="%s" title="%s (%s)">%s</a>' \
                   % (row[1], formatter.href.ticket(target), summary, row[1],
                      label)
        else:
            return '<a class="missing ticket" href="%s" rel="nofollow">%s</a>' \
                   % (formatter.href.ticket(target), label)

    
    # ISearchProvider methods

    def get_search_filters(self, req):
        if req.perm.has_permission('TICKET_VIEW'):
            yield ('ticket', 'Tickets')

    def get_search_results(self, req, query, filters):
        if not 'ticket' in filters:
            return
        db = self.env.get_db_cnx()
        sql, args = query_to_sql(db, query, 'b.newvalue')
        sql2, args2 = query_to_sql(db, query, 'summary||keywords||description||reporter||cc')
        cursor = db.cursor()
        cursor.execute("SELECT DISTINCT a.summary,a.description,a.reporter, "
                       "a.keywords,a.id,a.time FROM ticket a "
                       "LEFT JOIN ticket_change b ON a.id = b.ticket "
                       "WHERE (b.field='comment' AND %s ) OR %s" % (sql, sql2),
                       args + args2)
        for summary,desc,author,keywords,tid,date in cursor:
            yield (self.env.href.ticket(tid),
                   '#%d: %s' % (tid, util.shorten_line(summary)),
                   date, author,
                   shorten_result(desc, query.split()))
            
