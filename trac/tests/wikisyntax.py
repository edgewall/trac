# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import tempfile
import unittest

from trac.attachment import Attachment
from trac.mimeview.api import RenderingContext
from trac.resource import Resource
from trac.search.web_ui import SearchModule
from trac.test import MockPerm
from trac.web.href import Href
from trac.wiki.tests import formatter


SEARCH_TEST_CASES = u"""
============================== search: link resolver
search:foo
search:"foo bar"
[search:bar Bar]
[search:bar]
[search:]
------------------------------
<p>
<a class="search" href="/search?q=foo">search:foo</a>
<a class="search" href="/search?q=foo+bar">search:"foo bar"</a>
<a class="search" href="/search?q=bar">Bar</a>
<a class="search" href="/search?q=bar">bar</a>
<a class="search" href="/search">search</a>
</p>
------------------------------
============================== search: link resolver with query arguments
search:foo?wiki=on
search:?q=foo&wiki=on
search:"foo bar?wiki=on"
search:"?q=foo bar&wiki=on"
[search:bar?ticket=on Bar in Tickets]
[search:?q=bar&ticket=on Bar in Tickets]
------------------------------
<p>
<a class="search" href="/search?q=foo&amp;wiki=on">search:foo?wiki=on</a>
<a class="search" href="/search?q=foo&amp;wiki=on">search:?q=foo&amp;wiki=on</a>
<a class="search" href="/search?q=foo+bar&amp;wiki=on">search:"foo bar?wiki=on"</a>
<a class="search" href="/search?q=foo+bar&amp;wiki=on">search:"?q=foo bar&amp;wiki=on"</a>
<a class="search" href="/search?q=bar&amp;ticket=on">Bar in Tickets</a>
<a class="search" href="/search?q=bar&amp;ticket=on">Bar in Tickets</a>
</p>
------------------------------
"""

ATTACHMENT_TEST_CASES = u"""
============================== attachment: link resolver (deprecated)
attachment:wiki:WikiStart:file.txt (deprecated)
attachment:ticket:123:file.txt (deprecated)
[attachment:wiki:WikiStart:file.txt file.txt] (deprecated)
[attachment:ticket:123:file.txt] (deprecated)
------------------------------
<p>
<a class="attachment" href="/attachment/wiki/WikiStart/file.txt" title="Attachment 'file.txt' in WikiStart">attachment:wiki:WikiStart:file.txt</a><a class="trac-rawlink" href="/raw-attachment/wiki/WikiStart/file.txt" title="Download"></a> (deprecated)
<a class="attachment" href="/attachment/ticket/123/file.txt" title="Attachment 'file.txt' in Ticket #123">attachment:ticket:123:file.txt</a><a class="trac-rawlink" href="/raw-attachment/ticket/123/file.txt" title="Download"></a> (deprecated)
<a class="attachment" href="/attachment/wiki/WikiStart/file.txt" title="Attachment 'file.txt' in WikiStart">file.txt</a><a class="trac-rawlink" href="/raw-attachment/wiki/WikiStart/file.txt" title="Download"></a> (deprecated)
<a class="attachment" href="/attachment/ticket/123/file.txt" title="Attachment 'file.txt' in Ticket #123">ticket:123:file.txt</a><a class="trac-rawlink" href="/raw-attachment/ticket/123/file.txt" title="Download"></a> (deprecated)
</p>
------------------------------
============================== attachment: "foreign" links
attachment:file.txt:wiki:WikiStart
attachment:file.txt:ticket:123
[attachment:file.txt:wiki:WikiStart file.txt]
[attachment:file.txt:ticket:123]
attachment:foo.txt:wiki:SomePage/SubPage
------------------------------
<p>
<a class="attachment" href="/attachment/wiki/WikiStart/file.txt" title="Attachment 'file.txt' in WikiStart">attachment:file.txt:wiki:WikiStart</a><a class="trac-rawlink" href="/raw-attachment/wiki/WikiStart/file.txt" title="Download"></a>
<a class="attachment" href="/attachment/ticket/123/file.txt" title="Attachment 'file.txt' in Ticket #123">attachment:file.txt:ticket:123</a><a class="trac-rawlink" href="/raw-attachment/ticket/123/file.txt" title="Download"></a>
<a class="attachment" href="/attachment/wiki/WikiStart/file.txt" title="Attachment 'file.txt' in WikiStart">file.txt</a><a class="trac-rawlink" href="/raw-attachment/wiki/WikiStart/file.txt" title="Download"></a>
<a class="attachment" href="/attachment/ticket/123/file.txt" title="Attachment 'file.txt' in Ticket #123">file.txt:ticket:123</a><a class="trac-rawlink" href="/raw-attachment/ticket/123/file.txt" title="Download"></a>
<a class="attachment" href="/attachment/wiki/SomePage/SubPage/foo.txt" title="Attachment 'foo.txt' in SomePage/SubPage">attachment:foo.txt:wiki:SomePage/SubPage</a><a class="trac-rawlink" href="/raw-attachment/wiki/SomePage/SubPage/foo.txt" title="Download"></a>
</p>
------------------------------
============================== attachment: "local" links
attachment:file.txt
[attachment:file.txt that file]
------------------------------
<p>
<a class="attachment" href="/attachment/wiki/WikiStart/file.txt" title="Attachment 'file.txt' in WikiStart">attachment:file.txt</a><a class="trac-rawlink" href="/raw-attachment/wiki/WikiStart/file.txt" title="Download"></a>
<a class="attachment" href="/attachment/wiki/WikiStart/file.txt" title="Attachment 'file.txt' in WikiStart">that file</a><a class="trac-rawlink" href="/raw-attachment/wiki/WikiStart/file.txt" title="Download"></a>
</p>
------------------------------
============================== attachment: "missing" links
attachment:foo.txt
[attachment:foo.txt other file]
------------------------------
<p>
<a class="missing attachment">attachment:foo.txt</a>
<a class="missing attachment">other file</a>
</p>
------------------------------
============================== attachment: "raw" links
raw-attachment:file.txt
[raw-attachment:file.txt that file]
------------------------------
<p>
<a class="attachment" href="/raw-attachment/wiki/WikiStart/file.txt" title="Attachment 'file.txt' in WikiStart">raw-attachment:file.txt</a>
<a class="attachment" href="/raw-attachment/wiki/WikiStart/file.txt" title="Attachment 'file.txt' in WikiStart">that file</a>
</p>
------------------------------
============================== attachment: raw format as explicit argument
attachment:file.txt?format=raw
[attachment:file.txt?format=raw that file]
------------------------------
<p>
<a class="attachment" href="/attachment/wiki/WikiStart/file.txt?format=raw" title="Attachment 'file.txt' in WikiStart">attachment:file.txt?format=raw</a><a class="trac-rawlink" href="/raw-attachment/wiki/WikiStart/file.txt?format=raw" title="Download"></a>
<a class="attachment" href="/attachment/wiki/WikiStart/file.txt?format=raw" title="Attachment 'file.txt' in WikiStart">that file</a><a class="trac-rawlink" href="/raw-attachment/wiki/WikiStart/file.txt?format=raw" title="Download"></a>
</p>
------------------------------
""" # "

def attachment_setup(tc):
    import trac.ticket.api
    import trac.wiki.api
    tc.env.path = tempfile.mkdtemp(prefix='trac-tempenv-')
    with tc.env.db_transaction as db:
        db("INSERT INTO wiki (name,version) VALUES ('SomePage/SubPage',1)")
        db("INSERT INTO ticket (id) VALUES (123)")
    attachment = Attachment(tc.env, 'ticket', 123)
    attachment.insert('file.txt', tempfile.TemporaryFile(), 0)
    attachment = Attachment(tc.env, 'wiki', 'WikiStart')
    attachment.insert('file.txt', tempfile.TemporaryFile(), 0)
    attachment = Attachment(tc.env, 'wiki', 'SomePage/SubPage')
    attachment.insert('foo.txt', tempfile.TemporaryFile(), 0)

def attachment_teardown(tc):
    tc.env.reset_db_and_disk()


EMAIL_TEST_CASE_DEFAULT = u"""
============================== mailto: obfuscated by default, like plain email
user@example.org vs. mailto:user@example.org
and [mailto:user@example.org Joe User]
------------------------------
<p>
user@\u2026 vs. mailto:user@\u2026
and Joe User
</p>
------------------------------
"""

def email_default_context():
    class NoEmailViewPerm(MockPerm):
        def has_permission(self, action, realm_or_resource=None, id=False,
                           version=False):
            return action != 'EMAIL_VIEW'
        __contains__ = has_permission

    context = RenderingContext(Resource('wiki', 'WikiStart'), href=Href('/'),
                               perm=NoEmailViewPerm())
    context.req = None # 1.0 FIXME .req shouldn't be required by formatter
    return context


EMAIL_TEST_CASE_NEVER_OBFUSCATE = u"""
============================== mailto: not obfuscated, unlike plain email
user@example.org vs. mailto:user@example.org
and [mailto:user@example.org Joe User]
------------------------------
<p>
user@\u2026 vs. <a class="mail-link" href="mailto:user@example.org"><span class="icon"></span>mailto:user@example.org</a>
and <a class="mail-link" href="mailto:user@example.org"><span class="icon"></span>Joe User</a>
</p>
------------------------------
"""

def email_never_obfuscate_setup(tc):
    tc.env.config.set('trac', 'never_obfuscate_mailto', True)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(formatter.test_suite(SEARCH_TEST_CASES, file=__file__))
    suite.addTest(formatter.test_suite(ATTACHMENT_TEST_CASES, file=__file__,
                                       context=('wiki', 'WikiStart'),
                                       setup=attachment_setup,
                                       teardown=attachment_teardown))
    suite.addTest(formatter.test_suite(EMAIL_TEST_CASE_DEFAULT, file=__file__,
                                       context=email_default_context()))
    suite.addTest(formatter.test_suite(EMAIL_TEST_CASE_NEVER_OBFUSCATE,
                                       file=__file__,
                                       context=email_default_context(),
                                       setup=email_never_obfuscate_setup))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
