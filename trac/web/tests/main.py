from trac.test import Mock
from trac.web.main import absolute_url, Request, RequestDone

from Cookie import SimpleCookie as Cookie
from StringIO import StringIO
import unittest


class WebMainTestCase(unittest.TestCase):

    def test_absolute_url(self):
        req = Mock(scheme='http', server_name='example.org', server_port=None,
                   get_header=lambda x: None)
        url = absolute_url(req, '/trac')
        self.assertEqual('http://example.org/trac', url)

    def test_absolute_url_host(self):
        headers = {'Host': 'example.org'}
        req = Mock(scheme='http', server_name='localhost', server_port=8080,
                   get_header=lambda x: headers.get(x))
        url = absolute_url(req, '/trac')
        self.assertEqual('http://example.org/trac', url)

    def test_absolute_url_nondefaultport(self):
        req = Mock(scheme='http', server_name='example.org', server_port=8080,
                   get_header=lambda x: None)
        url = absolute_url(req, '/trac')
        self.assertEqual('http://example.org:8080/trac', url)

    def test_absolute_url_https(self):
        req = Mock(scheme='https', server_name='example.org', server_port=None,
                   get_header=lambda x: None)
        url = absolute_url(req, '/trac')
        self.assertEqual('https://example.org/trac', url)

    def test_absolute_url_https_host(self):
        headers = {'Host': 'example.org'}
        req = Mock(scheme='https', server_name='localhost', server_port=8443,
                   get_header=lambda x: headers.get(x))
        url = absolute_url(req, '/trac')
        self.assertEqual('https://example.org/trac', url)

    def test_absolute_url_https_nondefaultport(self):
        req = Mock(scheme='https', server_name='example.org', server_port=8443,
                   get_header=lambda x: None)
        url = absolute_url(req, '/trac')
        self.assertEqual('https://example.org:8443/trac', url)

    def test_absolute_url_proxy(self):
        headers = {'X-Forwarded-Host': 'example.org'}
        req = Mock(scheme='http', server_name='some.proxy', server_port=None,
                   get_header=lambda x: headers.get(x))
        url = absolute_url(req, '/trac')
        self.assertEqual('http://example.org/trac', url)

    def test_redirect(self):
        status = []
        headers = {}
        body = StringIO()
        req = Mock(Request, scheme='http', server_name='example.org',
                   server_port=None, outcookie=Cookie(),
                   get_header=lambda x: None,
                   end_headers=lambda: None,
                   send_header=lambda x,y: headers.setdefault(x, y),
                   write=lambda x: body.write(x),
                   send_response=lambda x: status.append(x))
        self.assertRaises(RequestDone, req.redirect, '/trac/test')
        self.assertEqual(302, status[0])
        self.assertEqual('http://example.org/trac/test', headers['Location'])

    def test_redirect_absolute(self):
        status = []
        headers = {}
        body = StringIO()
        req = Mock(Request, scheme='http', server_name='example.org',
                   server_port=None, outcookie=Cookie(),
                   get_header=lambda x: None,
                   end_headers=lambda: None,
                   send_header=lambda x,y: headers.setdefault(x, y),
                   write=lambda x: body.write(x),
                   send_response=lambda x: status.append(x))
        self.assertRaises(RequestDone, req.redirect,
                          'http://example.org/trac/test')
        self.assertEqual(302, status[0])
        self.assertEqual('http://example.org/trac/test', headers['Location'])


def suite():
    return unittest.makeSuite(WebMainTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
