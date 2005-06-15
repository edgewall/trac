import os
import StringIO
import unittest

from Href import Href

class HrefTestCase(unittest.TestCase):
    def setUp(self):
        self.href = Href('/')
    
    def test_log(self):
        """Testing Href.log"""
        assert self.href.log('/foo/bar') == '/log/foo/bar'
        assert self.href.log('/foo/bar', 42) == '/log/foo/bar?rev=42'

    def test_file(self):
        """Testing Href.file"""
        assert self.href.file('/foo/bar') == '/file/foo/bar'
        assert self.href.file('/foo/bar',42) == '/file/foo/bar?rev=42'
        assert self.href.file('/foo/bar',format='foo') == '/file/foo/bar?format=foo'
        assert self.href.file('/foo/bar',42, 'foo') == '/file/foo/bar?rev=42&format=foo'

    def test_browser(self):
        """Testing Href.browser"""
        assert self.href.browser('/foo/bar') == '/browser/foo/bar'
        assert self.href.browser('/foo/bar', 42) == '/browser/foo/bar?rev=42'
        
    def test_login(self):
        """Testing Href.login"""
        assert self.href.login() == '/login'
        
    def test_logout(self):
        """Testing Href.logout"""
        assert self.href.logout() == '/logout'

    def test_timeline(self):
        """Testing Href.timeline"""
        assert self.href.timeline() == '/timeline'

    def test_changeset(self):
        """Testing Href.changeset"""
        assert self.href.changeset(42) == '/changeset/42'

    def test_ticket(self):
        """Testing Href.ticket"""
        assert self.href.ticket(42) == '/ticket/42'

    def test_newticket(self):
        """Testing Href.newticket"""
        assert self.href.newticket() == '/newticket'

    def test_search(self):
        """Testing Href.search"""
        assert self.href.search() == '/search'
        assert self.href.search('foo') == '/search?q=foo'
        assert self.href.search('foo bar') == '/search?q=foo%20bar'
        assert self.href.search('foo bar?') == '/search?q=foo%20bar%3F'

    def test_about(self):
        """Testing Href.about"""
        assert self.href.about() == '/about_trac'
        assert self.href.about('config') == '/about_trac/config'
        assert self.href.about('/config') == '/about_trac/config'

    def test_wiki(self):
        """Testing Href.wiki"""
        assert self.href.wiki() == '/wiki'
        assert self.href.wiki('FooBar') == '/wiki/FooBar'
        assert self.href.wiki('FooBar',42) == '/wiki/FooBar?version=42'
        assert self.href.wiki('FooBar',42, 1) == '/wiki/FooBar?version=42&diff=yes'
        assert self.href.wiki('FooBar',42, diff=1) == '/wiki/FooBar?version=42&diff=yes'

    def test_report(self):
        """Testing Href.wiki"""
        assert self.href.report() == '/report'
        assert self.href.report(42) == '/report/42'
        assert self.href.report(42, 'edit') == '/report/42?action=edit'

    def test_attachment(self):
        """Testing Href.attachment"""
        assert self.href.attachment('wiki', 'FooBar', 'foo.txt') == \
               '/attachment/wiki/FooBar/foo.txt'
        assert self.href.attachment('wiki', 'FooBar', 'foo.txt', 'raw') == \
               '/attachment/wiki/FooBar/foo.txt?format=raw'
        assert self.href.attachment('ticket', '42', 'foo.txt') == \
               '/attachment/ticket/42/foo.txt'
        assert self.href.attachment('ticket', '42', 'foo.txt', 'raw') == \
               '/attachment/ticket/42/foo.txt?format=raw'

def suite():
    return unittest.makeSuite(HrefTestCase,'test')
