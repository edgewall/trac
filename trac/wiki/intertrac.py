# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2006 Edgewall Software
# Copyright (C) 2005-2006 Christian Boos <cboos@neuf.fr>
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
# Author: Christian Boos <cboos@neuf.fr>

import re

from trac.core import *
from trac.util import sorted
from trac.util.html import Element, html
from trac.web import IRequestHandler
from trac.wiki.api import IWikiMacroProvider
from trac.wiki.formatter import wiki_to_link


class InterTracDispatcher(Component):
    """Implements support for InterTrac dispatching."""

    implements(IRequestHandler, IWikiMacroProvider)

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
            href = link_elt.attrib.get('href')
            if href:
                req.redirect(href)
        raise TracError('"%s" is not a TracLinks' % link)


    # IWikiMacroProvider methods

    def get_macros(self):
        yield 'InterTrac'

    def get_macro_description(self, name): 
        return "Provide a list of known InterTrac prefixes."

    def render_macro(self, req, name, content):
        intertracs = {}
        for key, value in self.config.options('intertrac'):
            idx = key.rfind('.') # rsplit only in 2.4
            if idx > 0: # 0 itself doesn't help much: .xxx = ...
                prefix, attribute = key[:idx], key[idx+1:]
                intertrac = intertracs.setdefault(prefix, {})
                intertrac[attribute] = value
            else:
                intertracs[key] = value # alias

        def generate_prefix(prefix):
            intertrac = intertracs[prefix]
            if isinstance(intertrac, basestring):
                yield html.TR(html.TD(html.B(prefix)),
                              html.TD('Alias for ', html.B(intertrac)))
            else:
                url = intertrac.get('url', '')
                if url:
                    title = intertrac.get('title', url)
                    yield html.TR(html.TD(html.A(html.B(prefix),
                                                 href=url + '/timeline')),
                                  html.TD(html.A(title, href=url)))

        return html.TABLE(class_="wiki intertrac")(
            html.TR(html.TH(html.EM('Prefix')), html.TH(html.EM('Trac Site'))),
            [generate_prefix(p) for p in sorted(intertracs.keys())])
