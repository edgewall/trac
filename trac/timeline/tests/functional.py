#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import unittest

from trac.tests.contentgen import random_page, random_sentence, \
                                  random_unique_camel
from trac.tests.functional import FunctionalTwillTestCaseSetup, tc
from trac.util.datefmt import http_date
from trac.wiki import WikiPage


class RegressionTestRev5883(FunctionalTwillTestCaseSetup):
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
        tc.formvalue('modifypage', 'action', 'edit')
        tc.submit()
        tc.find('Editing ' + pagename)
        tc.formvalue('edit', 'text', random_page())
        tc.formvalue('edit', 'comment', random_sentence())
        tc.submit('save')
        self._tester.go_to_timeline()
        tc.find(pagename + '.*diff</a>\\)')


class TestRssFormat(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test timeline in RSS format."""
        pagename = random_unique_camel()
        self._tester.create_wiki_page(pagename)
        page = WikiPage(self._testenv.get_trac_environment(), pagename)
        self._tester.go_to_timeline()
        tc.follow("RSS Feed")
        tc.find(r"""<\?xml version="1.0"\?>
<rss xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">
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
\s+
        <dc:creator>admin</dc:creator>

      <pubDate>%(http_date)s</pubDate>
      <link>http://127.0.0.1:\d+/wiki/%(pagename)s\?version=1</link>
      <guid isPermaLink="false">http://127.0.0.1:\d+/wiki/%(pagename)s\?version=1/\d+</guid>
      <description>[^<]+</description>
      <category>wiki</category>
    </item><item>
""" % {'pagename': pagename, 'http_date': http_date(page.time)}, 'ms')


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional
        suite = trac.tests.functional.functionalSuite()
    suite.addTest(RegressionTestRev5883())
    suite.addTest(TestRssFormat())
    return suite


test_suite = functionalSuite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
