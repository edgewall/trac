# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2006 Edgewall Software
# Copyright (C) 2005-2006 Christian Boos <cboos@neuf.fr>
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
# Author: Christian Boos <cboos@neuf.fr>

import re

from trac.core import *
from trac.util.markup import Element
from trac.web import IRequestHandler
from trac.wiki.formatter import wiki_to_link


class InterTracDispatcher(Component):
    """Implements support for InterTrac dispatching."""

    implements(IRequestHandler)

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'^/intertrac/(.*)', req.path_info)
        if match:
            if match.group(1):
                req.args['link'] = match.group(1)
            return True

    def process_request(self, req):
        link = req.args.get('link', '')
        if not link:
            raise TracError('No TracLinks given')
        link_elt = wiki_to_link(link, self.env, req)
        if isinstance(link_elt, Element):
            href = link_elt.attr['href']
            if href:
                req.redirect(href)
        raise TracError('"%s" is not a TracLinks' % link)

