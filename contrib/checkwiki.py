#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

import re
import os
import sys
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
            if not isinstance(rv, basestring):
                text = unicode(rv)
            else:
                text = rv
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


def parse_args():
    from optparse import OptionParser
    parser = OptionParser(usage='Usage: %prog [options] [PAGES...]')
    parser.add_option('-d', '--download', dest='download', default=False,
                      action='store_true',
                      help='Download default pages from trac.edgewall.org '
                           'before checking')
    parser.add_option('-p', '--prefix', dest='prefix', default='',
                      help='Prepend "prefix/" to the page when downloading')
    return parser.parse_args()


re_box_processor = re.compile(r'{{{#!box[^\}]+}}}\s*\r?\n?')


def download_default_pages(names, prefix):
    from httplib import HTTPSConnection
    host = 'trac.edgewall.org'
    if prefix and not prefix.endswith('/'):
        prefix += '/'
    conn = HTTPSConnection(host)
    for name in names:
        if name in ('SandBox', 'TitleIndex', 'WikiStart'):
            continue
        sys.stdout.write('Downloading %s%s' % (prefix, name))
        conn.request('GET', '/wiki/%s%s?format=txt' % (prefix, name))
        response = conn.getresponse()
        content = response.read()
        if prefix and (response.status != 200 or not content):
            sys.stdout.write(' %s' % name)
            conn.request('GET', '/wiki/%s?format=txt' % name)
            response = conn.getresponse()
            content = response.read()
        if response.status == 200 and content:
            with open('trac/wiki/default-pages/' + name, 'w') as f:
                content = re_box_processor.sub('', content)
                lines = content.replace('\r\n', '\n').splitlines(True)
                f.write(''.join(line for line in lines
                                     if line.strip() != '[[TranslatedPages]]'))
            sys.stdout.write('\tdone.\n')
        else:
            sys.stdout.write('\tmissing or empty.\n')
    conn.close()


def main():
    options, args = parse_args()
    names = sorted(name for name in resource_listdir('trac.wiki',
                                                     'default-pages')
                        if not name.startswith('.'))
    if args:
        args = sorted(set(names) & set(map(os.path.basename, args)))
    else:
        args = names

    if options.download:
        download_default_pages(args, options.prefix)

    env = EnvironmentStub(disable=['trac.mimeview.pygments.*'])
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

    req = Mock(href=Href('/'), abs_href=Href('http://localhost/'),
               perm=MockPerm())
    for name in args:
        wiki = WikiPage(env, name)
        if not wiki.exists:
            continue
        context = web_context(req, wiki.resource)
        out = DummyIO()
        DefaultWikiChecker(env, context, name).format(wiki.text, out)


if __name__ == '__main__':
    main()
