#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2020 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import re
import unittest

from trac.tests.contentgen import random_page, random_sentence, \
                                  random_unique_camel
from trac.tests.functional import FunctionalTestCaseSetup, tc
from trac.util.datefmt import http_date
from trac.wiki import WikiPage


class RegressionTestRev5883(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of the timeline fix in r5883
        From Tim:
        the issue was that event.markup was never being output anywhere, so
        you actually have to render the template with a wiki modification
        and see if '(diff)' shows up as the text in a link
        also note that (diff) should _not_ show up for a wiki creation
        """
        pagename = random_unique_camel()
        self._tester.create_wiki_page(pagename)
        self._tester.go_to_timeline()
        tc.find(pagename)
        tc.notfind(pagename + '.*diff</a>\\)')
        self._tester.go_to_wiki(pagename)
        tc.submit(formname='modifypage')
        tc.find('Editing ' + pagename)
        tc.formvalue('edit', 'text', random_page())
        tc.formvalue('edit', 'comment', random_sentence())
        tc.submit('save')
        self._tester.go_to_timeline()
        tc.find(pagename + '.*diff</a>\\)')


class RegressionTestTicket12946(FunctionalTestCaseSetup):
    def runTest(self):
        """Empty <dd> element should not be created when there is
        no comment associated with an event.
        """
        pagename = random_unique_camel()
        self._tester.create_wiki_page(pagename)
        self._tester.attach_file_to_wiki(pagename, description="")
        self._tester.go_to_timeline()
        tc.find('<dt class="attachment unread">.*?</dt>', 's')
        tc.notfind('<dt class="attachment unread">.*?</dt>[ \t\n]+'
                   '<dd class="attachment">[ \t\n]*</dd>', 's')


class TestRssFormat(FunctionalTestCaseSetup):
    def runTest(self):
        """Test timeline in RSS format."""
        pagename = random_unique_camel()
        self._tester.create_wiki_page(pagename)
        page = WikiPage(self._testenv.get_trac_environment(), pagename)
        self._tester.go_to_timeline()
        code, content = tc.download_link("RSS Feed")
        self.assertEqual(200, code)
        pattern = r"""<\?xml version="1.0"\?>[\n]+
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>Functional Tests</title>
    <link>http://127.0.0.1:\d+/timeline</link>
    <description>Trac Timeline</description>
    <language>en-US</language>
    <generator>Trac [^<]+</generator>
    <image>
      <title>Functional Tests</title>
      <url>http://127.0.0.1:\d+/chrome/site/your_project_logo.png</url>
      <link>http://127.0.0.1:\d+/timeline</link>
    </image>
    <item>
      <title>%(pagename)s created</title>

      <dc:creator>admin</dc:creator>
      <pubDate>%(http_date)s</pubDate>
      <link>http://127.0.0.1:\d+/wiki/%(pagename)s\?version=1</link>
      <guid isPermaLink="false">http://127.0.0.1:\d+/wiki/%(pagename)s\?version=1/\d+</guid>
      <description>[^<]+</description>
      <category>wiki</category>
    </item>
""" % {'pagename': pagename, 'http_date': http_date(page.time)}
        if not re.match(pattern.encode('utf-8'), content,
                    re.MULTILINE | re.DOTALL):
            url = tc.write_source(content)
            raise AssertionError("Regex didn't match: {!r} not found in {}"
                                 .format(pattern, url))


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional
        suite = trac.tests.functional.functionalSuite()
    suite.addTest(RegressionTestRev5883())
    suite.addTest(RegressionTestTicket12946())
    suite.addTest(TestRssFormat())
    return suite


test_suite = functionalSuite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
