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
from trac.resource import Resource
from trac.util import as_bool, as_int
from trac.web.api import IRequestHandler
from trac.web.chrome import chrome_info_script, web_context
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
        version = as_int(req.args.get('version'), None)
        text = req.args.get('text', '')
        flavor = req.args.get('flavor')
        options = {}
        if 'escape_newlines' in req.args:
            options['escape_newlines'] = \
                as_bool(req.args.get('escape_newlines', 0))
        if 'shorten' in req.args:
            options['shorten'] = as_bool(req.args.get('shorten', 0))

        resource = Resource(realm, id=id, version=version)
        context = web_context(req, resource)
        rendered = format_to(self.env, flavor, context, text, **options) + \
                   chrome_info_script(req)
        req.send(rendered.encode('utf-8'))
