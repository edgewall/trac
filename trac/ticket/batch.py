# -*- coding: utf-8 -*-
#
# Copyright (C) 2010 Brian Meeker
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Brian Meeker <meeker.brian@gmail.com>

from trac.core import *
from trac.config import Option, ListOption
from trac.perm import IPermissionRequestor
from trac.ticket import TicketSystem, Ticket
from trac.web import IRequestHandler
import re

class BatchModifyModule(Component):
    
    implements(IRequestHandler, IPermissionRequestor)
    
    fields_as_list = ListOption("batchmod", "fields_as_list", 
                default="keywords", 
                doc="field names modified as a value list(separated by ',')")
    list_separator_regex = Option("batchmod", "list_separator_regex",
                default='[,\s]+',
                doc="separator regex used for 'list' fields")
    list_connector_string = Option("batchmod", "list_connector_string",
                default=',',
                doc="connecter string for 'list' fields")

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return 'TICKET_BATCH_MODIFY'
    
    # IRequestHandler methods

    def match_request(self, req):
        return req.path_info == '/batchmodify'

    def process_request(self, req):
        req.perm.assert_permission('TICKET_BATCH_MODIFY')

        tickets = req.session['query_tickets'].split(' ')
        comment = req.args.get('batchmod_value_comment', '')
        
        values = self._get_new_ticket_values(req) 
        self._check_for_resolution(values)
        self._remove_resolution_if_not_closed(values)

        selectedTickets = req.args.get('selectedTickets')
        selectedTickets = isinstance(selectedTickets, list) and \
                            selectedTickets or selectedTickets.split(',')
        if not selectedTickets:
            raise TracError('No tickets selected')
        
        for id in selectedTickets:
            if id in tickets:
                t = Ticket(env, int(id))
                
                _values = values.copy()
                for field in [f for f in values.keys() \
                              if f in self._fields_as_list]:
                    _values[field] = self._merge_keywords(t.values[field], 
                                                          values[field])
                
                t.populate(_values)
                t.save_changes(req.authname, comment)

    def _get_new_ticket_values(self, req):
        """Pull all of the new values out of the post data."""
        values = {}
        for field in TicketSystem(self.env).get_ticket_fields():
            name = field['name']
            if name not in ('summary', 'reporter', 'description'):
                value = req.args.get('batchmod_value_' + name)
                if value is not None:
                    values[name] = value
        return values
    
    def _check_for_resolution(self, values):
        """If a resolution has been set the status is automatically
        set to closed."""
        if values.has_key('resolution'):
            values['status'] = 'closed'
    
    def _remove_resolution_if_not_closed(self, values):
        """If the status is set to something other than closed the
        resolution should be removed."""
        if values.has_key('status') and values['status'] is not 'closed':
            values['resolution'] = ''

    def _merge_keywords(self, original_keywords, new_keywords):
        """
        Prevent duplicate keywords by merging the two lists.
        Any keywords prefixed with '-' will be removed.
        """
        
        regexp = re.compile(self._list_separator_regex)
        
        new_keywords = [k.strip() for k in regexp.split(new_keywords) if k]
        combined_keywords = [k.strip() for k 
                             in regexp.split(original_keywords) if k]
        
        for keyword in new_keywords:
            if keyword.startswith('-'):
                keyword = keyword[1:]
                while keyword in combined_keywords:
                    combined_keywords.remove(keyword)
            else:
                if keyword not in combined_keywords:
                    combined_keywords.append(keyword)
        
        return self._list_connector_string.join(combined_keywords)