from trac.Href import Href

import unittest


class HrefTestCase(unittest.TestCase):

    def setUp(self):
        self.href = Href('/')
    
    def test_log(self):
        """Testing Href.log"""
        self.assertEqual('/log/foo/bar', self.href.log('/foo/bar'))
        self.assertEqual('/log/foo/bar?rev=42', self.href.log('/foo/bar', 42))

    def test_file(self):
        """Testing Href.file"""
        self.assertEqual('/file/foo/bar', self.href.file('/foo/bar'))
        self.assertEqual('/file/foo/bar?rev=42', self.href.file('/foo/bar',42))
        self.assertEqual('/file/foo/bar?format=foo',
                         self.href.file('/foo/bar',format='foo'))
        self.assertEqual('/file/foo/bar?rev=42&format=foo',
                         self.href.file('/foo/bar',42, 'foo'))

    def test_browser(self):
        """Testing Href.browser"""
        self.assertEqual('/browser/foo/bar', self.href.browser('/foo/bar'))
        self.assertEqual('/browser/foo/bar?rev=42',
                         self.href.browser('/foo/bar', 42))
        
    def test_login(self):
        """Testing Href.login"""
        self.assertEqual('/login', self.href.login())
        
    def test_logout(self):
        """Testing Href.logout"""
        self.assertEqual('/logout', self.href.logout())

    def test_timeline(self):
        """Testing Href.timeline"""
        self.assertEqual('/timeline', self.href.timeline())

    def test_changeset(self):
        """Testing Href.changeset"""
        self.assertEqual('/changeset/42', self.href.changeset(42))

    def test_ticket(self):
        """Testing Href.ticket"""
        self.assertEqual('/ticket/42', self.href.ticket(42))

    def test_newticket(self):
        """Testing Href.newticket"""
        self.assertEqual('/newticket', self.href.newticket())

    def test_search(self):
        """Testing Href.search"""
        self.assertEqual('/search', self.href.search())
        self.assertEqual('/search?q=foo', self.href.search('foo'))
        self.assertEqual('/search?q=foo%20bar', self.href.search('foo bar'))
        self.assertEqual('/search?q=foo%20bar%3F', self.href.search('foo bar?'))

    def test_about(self):
        """Testing Href.about"""
        self.assertEqual('/about_trac', self.href.about())
        self.assertEqual('/about_trac/config', self.href.about('config'))
        self.assertEqual('/about_trac/config', self.href.about('/config'))

    def test_wiki(self):
        """Testing Href.wiki"""
        self.assertEqual('/wiki', self.href.wiki())
        self.assertEqual('/wiki/FooBar', self.href.wiki('FooBar'))
        self.assertEqual('/wiki/FooBar?version=42',
                         self.href.wiki('FooBar', 42))
        self.assertEqual('/wiki/FooBar?action=diff&version=42',
                         self.href.wiki('FooBar', 42, action='diff'))
        self.assertEqual('/wiki/FooBar?action=history&version=42',
                         self.href.wiki('FooBar', 42, action='history'))

    def test_report(self):
        """Testing Href.wiki"""
        self.assertEqual('/report', self.href.report())
        self.assertEqual('/report/42', self.href.report(42))
        self.assertEqual('/report/42?action=edit', self.href.report(42, 'edit'))

    def test_attachment(self):
        """Testing Href.attachment"""
        self.assertEqual('/attachment/wiki/FooBar/foo.txt',
                         self.href.attachment('wiki', 'FooBar', 'foo.txt'))
        self.assertEqual('/attachment/wiki/FooBar/foo.txt?format=raw',
                         self.href.attachment('wiki', 'FooBar', 'foo.txt',
                                              'raw'))
        self.assertEqual('/attachment/ticket/42/foo.txt',
                         self.href.attachment('ticket', '42', 'foo.txt'))
        self.assertEqual('/attachment/ticket/42/foo.txt?format=raw',
                         self.href.attachment('ticket', '42', 'foo.txt', 'raw'))

def suite():
    return unittest.makeSuite(HrefTestCase,'test')

if __name__ == '__main__':
    unittest.main()
