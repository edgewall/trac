#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2020 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import codecs
import os.path
import re
import sys

from pkg_resources import resource_listdir, resource_string

from trac.loader import load_components
from trac.test import EnvironmentStub, Mock, MockPerm
from trac.util.text import printerr, printout
from trac.web.chrome import web_context
from trac.web.href import Href
from trac.wiki.formatter import format_to_html
from trac.wiki.model import WikiPage

try:
    import pypandoc
except ImportError:
    printerr("The pypandoc package must be installed.")
    sys.exit(1)


def wiki2rest(env, context, wiki):
    # Convert CRLF to LF and remove macros.
    text = re.sub('\r?\n', '\n', wiki.text)
    text = re.sub(r'\[\[TracGuideToc\]\]\r?\n?', '', text)
    text = re.sub(r'\[\[PageOutline\([^\)]*\)\]\]\r?\n?', '', text)

    html = str(format_to_html(env, context, text))
    html = html.replace('<span class="icon">\u200b</span>', '')
    html = re.sub(r'<em>\s*([^<]*?)\s*</em>', r'<em>\1</em>', html)
    # Convert intra-document links from absolute to relative URLs.
    html = re.sub(r'(<a [^>]*href=")%s(#\w+")' % context.href.wiki(wiki.name),
                  r'\1\2', html)

    html = '<html><body>%s</body></html>' % html
    rst = pypandoc.convert_text(html, 'rst', 'html')

    # Remove "wiki" class from code directive - not recognized by Pygments.
    rst = re.sub(r'^(\.\. code::) wiki$', r'\1', rst, flags=re.M)
    rst = lower_reference_names(rst)
    rst = lower_intradocument_links(rst)
    rst = re.sub(r'\n{4,}', '\n\n\n', rst)
    if any(ord(c) > 0x7f for c in rst):
        # Trac detects utf-8 using BOM
        rst = '%s.. charset=utf-8\n\n%s' % (codecs.BOM_UTF8, rst)
    return rst + '\n'


def lower_reference_names(rst):
    """Lowercase reference names

    Reference names are converted to lowercase when HTML is rendered
    from reST. Here they are lowercased for consistency in the rst
    document.

    .. _Target-No.1: -> .. _target-no.1:
    """
    rst = re.sub(r'^\.\. _[^:]+:$', lambda m: m.group(0).lower(),
                 rst, flags=re.M)
    return rst


def lower_intradocument_links(rst):
    """Lowercase intra-document links

    Reference names are converted to lowercase when HTML is rendered
    from reST (https://bit.ly/2yXRPzL). Intra-document links must be
    lowercased in order to preserve linkage.

    `The Link <#Target-No.1>`__ -> `The Link <#target-no.1>`__
    """
    pattern = r'`%s <#%s>`__'
    rst = re.sub(pattern % (r'([^<]+)', r'([^>]+)'),
                 lambda m: pattern % (m.group(1), m.group(2).lower()),
                 rst)
    return rst


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

    req = Mock(href=Href('/'), abs_href=Href('https://trac.edgewall.org/'),
               perm=MockPerm(), chrome={})
    for name in sys.argv[1:]:
        name = os.path.basename(name)
        wiki = WikiPage(env, name)
        if not wiki.exists:
            continue
        context = web_context(req, wiki.resource, absurls=True)
        rst = wiki2rest(env, context, wiki)
        sys.stdout.write(rst)


if __name__ == '__main__':
    main()
