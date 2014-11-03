# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

from pkg_resources import resource_listdir

from trac.config import ListOption, Option
from trac.core import Component, implements
from trac.web.api import IRequestFilter

NOTICE_TEMPLATE = """\
{{{#!box note
This page documents the %(release)s (%(desc)s) release.
See [[%(alt_page)s]] if you need the %(alt_desc)s version.
}}}
"""


class HelpGuideVersionNotice(Component):
    """Adds a version notice to pages in the Help/Guide with a link to
    the previous or current version of the page in the guide. The
    WikiExtraPlugin needs to be installed for pretty rendering of the
    notice using the `box` WikiProcessor.
    """

    implements(IRequestFilter)

    lts_release = Option('teo', 'lts_release', '0.12',
        doc="Version of the LTS release of Trac.")

    stable_release = Option('teo', 'stable_release', '1.0',
        doc="Version of the stable release of Trac.")

    dev_release = Option('teo', 'dev_release', '1.1',
        doc="Version of the dev release of Trac.")

    ignored_pages = ListOption('teo', 'ignored_pages',
                               'WikiStart, TitleIndex',
        doc="List of pages to ignore.")

    def __init__(self):
        self.default_pages = resource_listdir('trac.wiki', 'default-pages')
        for page in self.ignored_pages:
            self.default_pages.remove(page)

    def pre_process_request(self, req, handler):
        return handler

    def post_process_request(self, req, template, data, content_type):
        if data and 'page' in data and 'text' in data:
            name = data['page'].name
            notice = ""
            if name in self.default_pages:
                alt_page = self.lts_release + '/' + name
                notice = NOTICE_TEMPLATE % {'release': self.stable_release,
                                            'desc': 'latest stable',
                                            'alt_page': alt_page,
                                            'alt_desc': 'previous'}
            elif name.startswith(self.lts_release) and \
                    name[len(self.lts_release)+1:] in self.default_pages:
                alt_page = '../../' + name[len(self.lts_release)+1:]
                notice = NOTICE_TEMPLATE % {'release': self.lts_release,
                                            'desc': 'maintenance',
                                            'alt_page': alt_page,
                                            'alt_desc': 'latest stable'}
            elif name.startswith(self.dev_release) and \
                    name[len(self.dev_release)+1:] in self.default_pages:
                alt_page = '../../' + name[len(self.dev_release)+1:]
                notice = NOTICE_TEMPLATE % {'release': self.dev_release,
                                            'desc': 'development',
                                            'alt_page': alt_page,
                                            'alt_desc': 'latest stable'}
            data['text'] = notice + data['text']

        return template, data, content_type
