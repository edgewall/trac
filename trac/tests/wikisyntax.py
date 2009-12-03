import os
import shutil
import tempfile
import unittest

from trac.attachment import Attachment
from trac.mimeview.api import Context
from trac.resource import Resource
from trac.search.web_ui import SearchModule
from trac.test import MockPerm
from trac.web.href import Href
from trac.wiki.tests import formatter

SEARCH_TEST_CASES = """
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
<a class="search" href="/search?q=">search</a>
</p>
------------------------------
============================== search: link resolver with query arguments
search:?q=foo&wiki=on
search:"?q=foo bar&wiki=on"
[search:?q=bar&ticket=on Bar in Tickets]
------------------------------
<p>
<a class="search" href="/search?q=foo&amp;wiki=on">search:?q=foo&amp;wiki=on</a>
<a class="search" href="/search?q=foo+bar&amp;wiki=on">search:"?q=foo bar&amp;wiki=on"</a>
<a class="search" href="/search?q=bar&amp;ticket=on">Bar in Tickets</a>
</p>
------------------------------
"""

ATTACHMENT_TEST_CASES = """
============================== attachment: link resolver (deprecated)
attachment:wiki:WikiStart:file.txt (deprecated)
attachment:ticket:123:file.txt (deprecated)
[attachment:wiki:WikiStart:file.txt file.txt] (deprecated)
[attachment:ticket:123:file.txt] (deprecated)
------------------------------
<p>
<a class="attachment" href="/attachment/wiki/WikiStart/file.txt" title="Attachment 'file.txt' in WikiStart">attachment:wiki:WikiStart:file.txt</a><span class="noprint"> <a class="trac-rawlink" href="/raw-attachment/wiki/WikiStart/file.txt" title="Download"><img src="/chrome/common/download.png" alt="Download"/></a></span> (deprecated)
<a class="attachment" href="/attachment/ticket/123/file.txt" title="Attachment 'file.txt' in Ticket #123">attachment:ticket:123:file.txt</a><span class="noprint"> <a class="trac-rawlink" href="/raw-attachment/ticket/123/file.txt" title="Download"><img src="/chrome/common/download.png" alt="Download"/></a></span> (deprecated)
<a class="attachment" href="/attachment/wiki/WikiStart/file.txt" title="Attachment 'file.txt' in WikiStart">file.txt</a><span class="noprint"> <a class="trac-rawlink" href="/raw-attachment/wiki/WikiStart/file.txt" title="Download"><img src="/chrome/common/download.png" alt="Download"/></a></span> (deprecated)
<a class="attachment" href="/attachment/ticket/123/file.txt" title="Attachment 'file.txt' in Ticket #123">ticket:123:file.txt</a><span class="noprint"> <a class="trac-rawlink" href="/raw-attachment/ticket/123/file.txt" title="Download"><img src="/chrome/common/download.png" alt="Download"/></a></span> (deprecated)
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
<a class="attachment" href="/attachment/wiki/WikiStart/file.txt" title="Attachment 'file.txt' in WikiStart">attachment:file.txt:wiki:WikiStart</a><span class="noprint"> <a class="trac-rawlink" href="/raw-attachment/wiki/WikiStart/file.txt" title="Download"><img src="/chrome/common/download.png" alt="Download"/></a></span>
<a class="attachment" href="/attachment/ticket/123/file.txt" title="Attachment 'file.txt' in Ticket #123">attachment:file.txt:ticket:123</a><span class="noprint"> <a class="trac-rawlink" href="/raw-attachment/ticket/123/file.txt" title="Download"><img src="/chrome/common/download.png" alt="Download"/></a></span>
<a class="attachment" href="/attachment/wiki/WikiStart/file.txt" title="Attachment 'file.txt' in WikiStart">file.txt</a><span class="noprint"> <a class="trac-rawlink" href="/raw-attachment/wiki/WikiStart/file.txt" title="Download"><img src="/chrome/common/download.png" alt="Download"/></a></span>
<a class="attachment" href="/attachment/ticket/123/file.txt" title="Attachment 'file.txt' in Ticket #123">file.txt:ticket:123</a><span class="noprint"> <a class="trac-rawlink" href="/raw-attachment/ticket/123/file.txt" title="Download"><img src="/chrome/common/download.png" alt="Download"/></a></span>
<a class="attachment" href="/attachment/wiki/SomePage/SubPage/foo.txt" title="Attachment 'foo.txt' in SomePage/SubPage">attachment:foo.txt:wiki:SomePage/SubPage</a><span class="noprint"> <a class="trac-rawlink" href="/raw-attachment/wiki/SomePage/SubPage/foo.txt" title="Download"><img src="/chrome/common/download.png" alt="Download"/></a></span>
</p>
------------------------------
============================== attachment: "local" links
attachment:file.txt
[attachment:file.txt that file]
------------------------------
<p>
<a class="attachment" href="/attachment/wiki/WikiStart/file.txt" title="Attachment 'file.txt' in WikiStart">attachment:file.txt</a><span class="noprint"> <a class="trac-rawlink" href="/raw-attachment/wiki/WikiStart/file.txt" title="Download"><img src="/chrome/common/download.png" alt="Download"/></a></span>
<a class="attachment" href="/attachment/wiki/WikiStart/file.txt" title="Attachment 'file.txt' in WikiStart">that file</a><span class="noprint"> <a class="trac-rawlink" href="/raw-attachment/wiki/WikiStart/file.txt" title="Download"><img src="/chrome/common/download.png" alt="Download"/></a></span>
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
<a class="attachment" href="/attachment/wiki/WikiStart/file.txt?format=raw" title="Attachment 'file.txt' in WikiStart">attachment:file.txt?format=raw</a><span class="noprint"> <a class="trac-rawlink" href="/raw-attachment/wiki/WikiStart/file.txt?format=raw" title="Download"><img src="/chrome/common/download.png" alt="Download"/></a></span>
<a class="attachment" href="/attachment/wiki/WikiStart/file.txt?format=raw" title="Attachment 'file.txt' in WikiStart">that file</a><span class="noprint"> <a class="trac-rawlink" href="/raw-attachment/wiki/WikiStart/file.txt?format=raw" title="Download"><img src="/chrome/common/download.png" alt="Download"/></a></span>
</p>
------------------------------
""" # "

def attachment_setup(tc):
    import trac.ticket.api
    import trac.wiki.api
    tc.env.path = os.path.join(tempfile.gettempdir(), 'trac-tempenv')
    os.mkdir(tc.env.path)
    attachment = Attachment(tc.env, 'wiki', 'WikiStart')
    attachment.insert('file.txt', tempfile.TemporaryFile(), 0)
    attachment = Attachment(tc.env, 'ticket', 123)
    attachment.insert('file.txt', tempfile.TemporaryFile(), 0)
    attachment = Attachment(tc.env, 'wiki', 'SomePage/SubPage')
    attachment.insert('foo.txt', tempfile.TemporaryFile(), 0)

def attachment_teardown(tc):
    shutil.rmtree(tc.env.path)
    tc.env.reset_db()


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

    context = Context(Resource('wiki', 'WikiStart'), href=Href('/'), 
                      perm=NoEmailViewPerm())
    context.req = None # 0.12 FIXME .req shouldn't be required by formatter
    return context


EMAIL_TEST_CASE_NEVER_OBFUSCATE = u"""
============================== mailto: not obfuscated, unlike plain email
user@example.org vs. mailto:user@example.org
and [mailto:user@example.org Joe User]
------------------------------
<p>
user@\u2026 vs. <a class="mail-link" href="mailto:user@example.org"><span class="icon">\xa0</span>mailto:user@example.org</a>
and <a class="mail-link" href="mailto:user@example.org"><span class="icon">\xa0</span>Joe User</a>
</p>
------------------------------
"""

def email_never_obfuscate_setup(tc):
    tc.env.config.set('trac', 'never_obfuscate_mailto', True)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(formatter.suite(SEARCH_TEST_CASES, file=__file__))
    suite.addTest(formatter.suite(ATTACHMENT_TEST_CASES, file=__file__,
                                  context=('wiki', 'WikiStart'),
                                  setup=attachment_setup,
                                  teardown=attachment_teardown))
    suite.addTest(formatter.suite(EMAIL_TEST_CASE_DEFAULT, file=__file__, 
                                  context=email_default_context()))
    suite.addTest(formatter.suite(EMAIL_TEST_CASE_NEVER_OBFUSCATE, 
                                  file=__file__,
                                  context=email_default_context(),
                                  setup=email_never_obfuscate_setup))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')

