#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os.path
import sys

from cStringIO import StringIO
from html2rest import html2rest
from pkg_resources import resource_listdir, resource_string

from trac.loader import load_components
from trac.test import EnvironmentStub, Mock, MockPerm
from trac.util.text import printout
from trac.web.chrome import web_context
from trac.web.href import Href
from trac.wiki.formatter import format_to_html
from trac.wiki.model import WikiPage


def main():
    names = sorted(name for name in resource_listdir('trac.wiki',
                                                     'default-pages')
                        if not name.startswith('.'))

    env = EnvironmentStub()
    load_components(env)
    with env.db_transaction:
        for name in names:
            wiki = WikiPage(env, name)
            wiki.text = resource_string('trac.wiki', 'default-pages/' +
                                        name).decode('utf-8')
            if wiki.text:
                wiki.save('trac', '')
            else:
                printout('%s: Skipped empty page' % name)

    req = Mock(href=Href('/'), abs_href=Href('http://trac.edgewall.org/'),
               perm=MockPerm())
    for name in sys.argv[1:]:
        name = os.path.basename(name)
        wiki = WikiPage(env, name)
        if not wiki.exists:
            continue
        context = web_context(req, wiki.resource, absurls=True)
        html = '<html><body>%s</body></html>' % \
               format_to_html(env, context, wiki.text).encode('utf-8')
        out = StringIO()
        html2rest(html, writer=out)
        out = out.getvalue().replace(': http://trac.edgewall.org/wiki/',
                                     ': trac/wiki/default-pages/')
        sys.stdout.write(out)


if __name__ == '__main__':
    main()
