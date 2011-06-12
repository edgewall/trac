# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
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

from genshi.builder import Element, Fragment, tag

from trac.core import *
from trac.mimeview import Context
from trac.perm import PermissionError
from trac.util.html import find_element
from trac.util.translation import _
from trac.web import IRequestHandler
from trac.wiki.api import IWikiMacroProvider
from trac.wiki.formatter import extract_link


class InterTracDispatcher(Component):
    """InterTrac dispatcher."""

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
        parts = link.split(':', 1)
        if len(parts) > 1:
            resolver, target = parts
            if target and (target[0] not in '\'"' or target[0] != target[-1]):
                link = '%s:"%s"' % (resolver, target)
        link_frag = extract_link(self.env, Context.from_request(req), link)
        if isinstance(link_frag, (Element, Fragment)):
            elt = find_element(link_frag, 'href')
            if elt is None: # most probably no permissions to view
                raise PermissionError(_("Can't view %(link)s:", link=link))
            href = elt.attrib.get('href')
        else:
            href = req.href(link.rstrip(':'))
        req.redirect(href)

    # IWikiMacroProvider methods

    def get_macros(self):
        yield 'InterTrac'

    def get_macro_description(self, name): 
        return "Provide a list of known InterTrac prefixes."

    def expand_macro(self, formatter, name, content):
        intertracs = {}
        for key, value in self.config.options('intertrac'):
            idx = key.rfind('.') # rsplit only in 2.4
            if idx > 0: # 0 itself doesn't help much: .xxx = ...
                prefix, attribute = key[:idx], key[idx+1:]
                intertrac = intertracs.setdefault(prefix, {})
                intertrac[attribute] = value
            else:
                intertracs[key] = value # alias
        if 'trac' not in intertracs:
            intertracs['trac'] = {'title': _('The Trac Project'),
                                  'url': 'http://trac.edgewall.org'}

        def generate_prefix(prefix):
            intertrac = intertracs[prefix]
            if isinstance(intertrac, basestring):
                yield tag.tr(tag.td(tag.b(prefix)),
                             tag.td('Alias for ', tag.b(intertrac)))
            else:
                url = intertrac.get('url', '')
                if url:
                    title = intertrac.get('title', url)
                    yield tag.tr(tag.td(tag.a(tag.b(prefix),
                                              href=url + '/timeline')),
                                 tag.td(tag.a(title, href=url)))

        return tag.table(class_="wiki intertrac")(
            tag.tr(tag.th(tag.em('Prefix')), tag.th(tag.em('Trac Site'))),
            [generate_prefix(p) for p in sorted(intertracs.keys())])
