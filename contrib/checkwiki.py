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
# history and logs, available at https://trac.edgewall.org/.

import argparse
import re
import sys
from contextlib import closing
from pkg_resources import resource_listdir, resource_string

from trac.loader import load_components
from trac.test import EnvironmentStub, Mock, MockPerm
from trac.util.text import printout
from trac.web.chrome import web_context
from trac.web.href import Href
from trac.wiki.formatter import Formatter
from trac.wiki.model import WikiPage


TURN_ON = '\033[30m\033[41m'
TURN_OFF = '\033[m'


class DefaultWikiChecker(Formatter):

    def __init__(self, env, context, name):
        Formatter.__init__(self, env, context)
        self.__name = name
        self.__marks = []
        self.__super = super(DefaultWikiChecker, self)

    def handle_match(self, fullmatch):
        rv = self.__super.handle_match(fullmatch)
        if rv:
            text = str(rv) if not isinstance(rv, str) else rv
            if text.startswith('<a ') and text.endswith('</a>') and \
                    'class="missing ' in text:
                self.__marks.append((fullmatch.start(0), fullmatch.end(0)))
        return rv

    def handle_code_block(self, line, startmatch=None):
        prev_processor = getattr(self, 'code_processor', None)
        try:
            return self.__super.handle_code_block(line, startmatch)
        finally:
            processor = self.code_processor
            if startmatch and processor and processor != prev_processor and \
                    processor.error:
                self.__marks.append((startmatch.start(0), startmatch.end(0)))

    def format(self, text, out=None):
        return self.__super.format(SourceWrapper(self, text), out)

    def next_callback(self, line, idx):
        marks = self.__marks
        if marks:
            buf = []
            prev = 0
            for start, end in self.__marks:
                buf.append(line[prev:start])
                buf.append(TURN_ON)
                buf.append(line[start:end])
                buf.append(TURN_OFF)
                prev = end
            buf.append(line[prev:])
            printout('%s:%d:%s' % (self.__name, idx + 1, ''.join(buf)))
            self.__marks[:] = ()


class SourceWrapper(object):

    def __init__(self, formatter, text):
        self.formatter = formatter
        self.text = text

    def __iter__(self):
        return LinesIterator(self.formatter, self.text.splitlines())


class LinesIterator(object):

    def __init__(self, formatter, lines):
        self.formatter = formatter
        self.lines = lines
        self.idx = 0
        self.current = None

    def next(self):
        idx = self.idx
        if self.current is not None:
            self.formatter.next_callback(self.current, idx)
        if idx >= len(self.lines):
            self.current = None
            raise StopIteration
        self.idx = idx + 1
        self.current = self.lines[idx]
        return self.current


class DummyIO(object):

    def write(self, data):
        pass


def parse_args(all_pages):
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--download', action='store_true',
                        help="download default pages from trac.edgewall.org "
                             "before checking")
    parser.add_argument('-p', '--prefix', default='',
                        help="prepend PREFIX/ to the page name when "
                             "downloading")
    parser.add_argument('-s', '--strict', action='store_true',
                        help="only download pages below PREFIX/ if -p given")
    parser.add_argument('pages', metavar='page', nargs='*',
                        help="the wiki page(s) to download and/or check")

    args = parser.parse_args()
    if args.pages:
        for page in args.pages:
            if page not in all_pages:
                parser.error("%s is not one of the default pages." % page)

    return args


re_box_processor = re.compile(r'{{{#!box[^\}]+}}}\s*\r?\n?')


def download_default_pages(names, prefix, strict):
    from httplib import HTTPSConnection
    host = 'trac.edgewall.org'
    if prefix and not prefix.endswith('/'):
        prefix += '/'
    with closing(HTTPSConnection(host)) as conn:
        for name in names:
            if name in ('SandBox', 'TitleIndex', 'WikiStart'):
                continue
            sys.stdout.write('Downloading %s%s' % (prefix, name))
            conn.request('GET', '/wiki/%s%s?format=txt' % (prefix, name))
            response = conn.getresponse()
            content = response.read()
            if prefix and (response.status != 200 or not content) \
                    and not strict:
                sys.stdout.write(' %s' % name)
                conn.request('GET', '/wiki/%s?format=txt' % name)
                response = conn.getresponse()
                content = response.read()
            if response.status == 200 and content:
                with open('trac/wiki/default-pages/' + name, 'w',
                          encoding='utf-8') as f:
                    if not strict:
                        content = re_box_processor.sub('', content)
                    lines = content.replace('\r\n', '\n').splitlines(True)
                    f.write(''.join(line for line in lines
                                         if strict or line.strip() !=
                                            '[[TranslatedPages]]'))
                sys.stdout.write('\tdone.\n')
            else:
                sys.stdout.write('\tmissing or empty.\n')


def main():
    all_pages = sorted(name for name
                            in resource_listdir('trac.wiki', 'default-pages')
                            if not name.startswith('.'))
    args = parse_args(all_pages)
    if args.pages:
        pages = sorted(args.pages)
    else:
        pages = all_pages

    if args.download:
        download_default_pages(pages, args.prefix, args.strict)

    env = EnvironmentStub(disable=['trac.mimeview.pygments.*'])
    load_components(env)
    with env.db_transaction:
        for name in all_pages:
            wiki = WikiPage(env, name)
            wiki.text = resource_string('trac.wiki', 'default-pages/' +
                                        name).decode('utf-8')
            if wiki.text:
                wiki.save('trac', '')
            else:
                printout('%s: Skipped empty page' % name)

    req = Mock(href=Href('/'), abs_href=Href('http://localhost/'),
               perm=MockPerm())
    for name in pages:
        wiki = WikiPage(env, name)
        if not wiki.exists:
            continue
        context = web_context(req, wiki.resource)
        out = DummyIO()
        DefaultWikiChecker(env, context, name).format(wiki.text, out)


if __name__ == '__main__':
    main()
