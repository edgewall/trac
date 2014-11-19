# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
# Copyright (C) 2005-2006 Christian Boos <cboos@edgewall.org>
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
# Author: Christian Boos <cboos@edgewall.org>

import re

from genshi.builder import Element, Fragment, tag

from trac.config import ConfigSection
from trac.core import *
from trac.util.html import find_element
from trac.util.translation import N_, _, tag_
from trac.web.api import IRequestHandler
from trac.wiki.api import IWikiMacroProvider
from trac.wiki.formatter import extract_link


class InterTracDispatcher(Component):
    """InterTrac dispatcher."""

    implements(IRequestHandler, IWikiMacroProvider)

    is_valid_default_handler = False

    intertrac_section = ConfigSection('intertrac',
        """This section configures InterTrac prefixes. Options in this section
        whose name contain a `.` define aspects of the InterTrac prefix
        corresponding to the option name up to the `.`. Options whose name
        don't contain a `.` define an alias.

        The `.url` is mandatory and is used for locating the other Trac.
        This can be a relative URL in case that Trac environment is located
        on the same server.

        The `.title` information is used for providing a useful tooltip when
        moving the cursor over an InterTrac link.

        Example configuration:
        {{{
        [intertrac]
        # -- Example of setting up an alias:
        t = trac

        # -- Link to an external Trac:
        trac.title = Edgewall's Trac for Trac
        trac.url = http://trac.edgewall.org
        }}}
        """)

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
            if target[:1] + target[-1:] not in ('""', "''"):
                link = '%s:"%s"' % (resolver, target)
        from trac.web.chrome import web_context
        link_frag = extract_link(self.env, web_context(req), link)
        if isinstance(link_frag, (Element, Fragment)):
            elt = find_element(link_frag, 'href')
            if elt is None:
                raise TracError(
                    _("Can't view %(link)s. Resource doesn't exist or "
                      "you don't have the required permission.", link=link))
            href = elt.attrib.get('href')
        else:
            href = req.href(link.rstrip(':'))
        req.redirect(href)

    # IWikiMacroProvider methods

    def get_macros(self):
        yield 'InterTrac'

    def get_macro_description(self, name):
        return 'messages', N_("Provide a list of known InterTrac prefixes.")

    def expand_macro(self, formatter, name, content):
        intertracs = {}
        for key, value in self.intertrac_section.options():
            idx = key.rfind('.')
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
                yield tag.tr(tag.td(tag.strong(prefix)),
                             tag.td(tag_("Alias for %(name)s",
                                         name=tag.strong(intertrac))))
            else:
                url = intertrac.get('url', '')
                if url:
                    title = intertrac.get('title', url)
                    yield tag.tr(tag.td(tag.a(tag.strong(prefix),
                                              href=url + '/timeline')),
                                 tag.td(tag.a(title, href=url)))

        return tag.table(class_="wiki intertrac")(
            tag.tr(tag.th(tag.em(_("Prefix"))),
                   tag.th(tag.em(_("Trac Site")))),
            [generate_prefix(p) for p in sorted(intertracs.keys())])
