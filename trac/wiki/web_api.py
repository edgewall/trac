# -*- coding: utf-8 -*-
#
# Copyright (C) 2009 Edgewall Software
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
from trac.mimeview.api import Context
from trac.resource import Resource
from trac.web.api import IRequestHandler
from trac.wiki.formatter import format_to
 

class WikiRenderer(Component):
    """Wiki text renderer."""

    implements(IRequestHandler)

    # IRequestHandler methods

    def match_request(self, req):
        return req.path_info == '/wiki_render'

    def process_request(self, req):
        # Allow all POST requests (with a valid __FORM_TOKEN, ensuring that
        # the client has at least some permission). Additionally, allow GET
        # requests from TRAC_ADMIN for testing purposes.
        if req.method != 'POST':
            req.perm.require('TRAC_ADMIN')
        realm = req.args.get('realm', 'wiki')
        id = req.args.get('id')
        version = req.args.get('version')
        if version is not None:
            try:
                version = int(version)
            except ValueError:
                version = None
        text = req.args.get('text', '')
        flavor = req.args.get('flavor')
        options = {}
        if 'escape_newlines' in req.args:
            options['escape_newlines'] = bool(int(req.args['escape_newlines']
                                                  or 0))
        if 'shorten' in req.args:
            options['shorten'] = bool(int(req.args['shorten'] or 0))
        
        resource = Resource(realm, id=id, version=version)
        context = Context.from_request(req, resource)
        rendered = format_to(self.env, flavor, context, text, **options)
        req.send(rendered.encode('utf-8'))
