# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2016 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import difflib
import os
import re
import unittest
import StringIO

# Python 2.7 `assertMultiLineEqual` calls `safe_repr(..., short=True)`
# which breaks our custom failure display in WikiTestCase.

try:
    from unittest.util import safe_repr
except ImportError:
    pass
else:
    unittest.case.safe_repr = lambda obj, short=False: safe_repr(obj, False)

from trac.test import EnvironmentStub, MockRequest
from trac.util.datefmt import datetime_now, to_utimestamp, utc
from trac.util.text import strip_line_ws, to_unicode
from trac.web.chrome import web_context
from trac.wiki.formatter import (HtmlFormatter, InlineHtmlFormatter,
                                 OutlineFormatter)


class WikiTestCase(unittest.TestCase):

    generate_opts = {}

    def __init__(self, title, input, correct, file, line, setup=None,
                 teardown=None, context=None, default_data=False,
                 enable_components=None, disable_components=None,
                 env_path='', destroying=False):
        unittest.TestCase.__init__(self, 'test')
        self.title = title
        self.input = input
        self.correct = correct
        self.file = file
        self.line = line
        self._setup = setup
        self._teardown = teardown
        self._context = context
        self.context = None
        self._env_kwargs = {'default_data': default_data,
                            'enable': enable_components,
                            'disable': disable_components,
                            'path': env_path, 'destroying': destroying}

    def _create_env(self):
        env = EnvironmentStub(**self._env_kwargs)
        # -- intertrac support
        env.config.set('intertrac', 'trac.title', "Trac's Trac")
        env.config.set('intertrac', 'trac.url', "http://trac.edgewall.org")
        env.config.set('intertrac', 't', 'trac')
        env.config.set('intertrac', 'th.title', "Trac Hacks")
        env.config.set('intertrac', 'th.url', "http://trac-hacks.org")
        # -- safe schemes
        env.config.set('wiki', 'safe_schemes',
                       'data,file,ftp,http,https,svn,svn+ssh,'
                       'rfc-2396.compatible,rfc-2396+under_score')
        return env

    def setUp(self):
        self.env = self._create_env()
        self.req = MockRequest(self.env, script_name='/')
        context = self._context
        if context:
            if isinstance(self._context, tuple):
                context = web_context(self.req, *self._context)
        else:
            context = web_context(self.req, 'wiki', 'WikiStart')
        self.context = context
        # Remove the following lines in order to discover
        # all the places were we should use the req.href
        # instead of env.href
        self.env.href = self.req.href
        self.env.abs_href = self.req.abs_href
        self.env.db_transaction(
            "INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            ('WikiStart', 1, to_utimestamp(datetime_now(utc)), 'joe',
             '::1', '--', 'Entry page', 0))
        if self._setup:
            self._setup(self)

    def tearDown(self):
        self.env.reset_db()
        if self._teardown:
            self._teardown(self)

    def test(self):
        """Testing WikiFormatter"""
        formatter = self.formatter()
        v = unicode(formatter.generate(**self.generate_opts))
        v = v.replace('\r', '').replace(u'\u200b', '')  # FIXME: keep ZWSP
        v = strip_line_ws(v, leading=False)
        try:
            self.assertEqual(self.correct, v)
        except AssertionError as e:
            msg = to_unicode(e)
            match = re.match(r"u?'(.*)' != u?'(.*)'", msg)
            if match:
                g1 = ["%s\n" % x for x in match.group(1).split(r'\n')]
                g2 = ["%s\n" % x for x in match.group(2).split(r'\n')]
                expected = ''.join(g1)
                actual = ''.join(g2)
                wiki = repr(self.input).replace(r'\n', '\n')
                diff = ''.join(list(difflib.unified_diff(g1, g2, 'expected',
                                                         'actual')))
                # Tip: sometimes, 'expected' and 'actual' differ only by
                #      whitespace, so it can be useful to visualize them, e.g.
                # expected = expected.replace(' ', '.')
                # actual = actual.replace(' ', '.')
                def info(*args):
                    return '\n========== %s: ==========\n%s' % args
                msg = info('expected', expected)
                msg += info('actual', actual)
                msg += info('wiki', ''.join(wiki))
                msg += info('diff', diff)
            raise AssertionError( # See below for details
                '%s\n\n%s:%s: "%s" (%s flavor)' \
                % (msg, self.file, self.line, self.title, formatter.flavor))

    def formatter(self):
        return HtmlFormatter(self.env, self.context, self.input)

    def shortDescription(self):
        return 'Test ' + self.title


class OneLinerTestCase(WikiTestCase):
    def formatter(self):
        return InlineHtmlFormatter(self.env, self.context, self.input)


class EscapeNewLinesTestCase(WikiTestCase):
    generate_opts = {'escape_newlines': True}

    def formatter(self):
        return HtmlFormatter(self.env, self.context, self.input)


class OutlineTestCase(WikiTestCase):
    def formatter(self):
        class Outliner(object):
            flavor = 'outliner'
            def __init__(self, env, context, input):
                self.outliner = OutlineFormatter(env, context)
                self.input = input
            def generate(self):
                out = StringIO.StringIO()
                self.outliner.format(self.input, out)
                return out.getvalue()
        return Outliner(self.env, self.context, self.input)


def wikisyntax_test_suite(data=None, setup=None, file=None, teardown=None,
                          context=None, default_data=False,
                          enable_components=None, disable_components=None,
                          env_path=None, destroying=False):
    suite = unittest.TestSuite()

    def add_test_cases(data, filename):
        tests = re.compile('^(%s.*)$' % ('=' * 30), re.MULTILINE).split(data)
        next_line = 1
        line = 0
        for title, test in zip(tests[1::2], tests[2::2]):
            title = title.lstrip('=').strip()
            if line != next_line:
                line = next_line
            if not test or test == '\n':
                continue
            next_line += len(test.split('\n')) - 1
            if 'SKIP' in title or 'WONTFIX' in title:
                continue
            blocks = test.split('-' * 30 + '\n')
            if len(blocks) < 5:
                blocks.extend([None] * (5 - len(blocks)))
            input, page, oneliner, page_escape_nl, outline = blocks[:5]
            for cls, correct in [
                    (WikiTestCase, page),
                    (OneLinerTestCase, oneliner and oneliner[:-1]),
                    (EscapeNewLinesTestCase, page_escape_nl),
                    (OutlineTestCase, outline)]:
                if correct:
                    tc = cls(title, input, correct, filename, line, setup,
                             teardown, context, default_data,
                             enable_components, disable_components, env_path,
                             destroying)
                    suite.addTest(tc)

    if data:
        add_test_cases(data, file)
    else:
        if os.path.exists(file):
            with open(file, 'r') as fobj:
                data = fobj.read().decode('utf-8')
            add_test_cases(data, file)
        else:
            print('no ' + file)

    return suite
