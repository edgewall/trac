from trac.web.cgi_frontend import CGIRequest
from trac.web.main import _reconstruct_base_url

import unittest


class CGIRequestTestCase(unittest.TestCase):

    def test_cgi_attrs(self):
        environ = {'SCRIPT_NAME': '/trac', 'REMOTE_ADDR': '127.0.0.1'}
        req = CGIRequest(environ)
        self.assertEqual('/trac', req.cgi_location)
        self.assertEqual('127.0.0.1', req.remote_addr)
        self.assertEqual(None, req.remote_user)

    def test_authname(self):
        environ = {'SCRIPT_NAME': '/trac', 'REMOTE_USER': 'john'}
        req = CGIRequest(environ)
        self.assertEqual('john', req.remote_user)

    def test_base_url(self):
        environ = {'SCRIPT_NAME': '/trac', 'SERVER_NAME': 'example.org'}
        req = CGIRequest(environ)
        req.base_url = _reconstruct_base_url(req)
        self.assertEqual('http://example.org/trac', req.base_url)

    def test_base_url_host(self):
        environ = {'SCRIPT_NAME': '/trac', 'SERVER_NAME': 'localhost',
                   'SERVER_PORT': '8080', 'HTTP_HOST': 'example.org'}
        req = CGIRequest(environ)
        req.base_url = _reconstruct_base_url(req)
        self.assertEqual('http://example.org/trac', req.base_url)

    def test_base_url_nondefaultport(self):
        environ = {'SCRIPT_NAME': '/trac', 'SERVER_NAME': 'example.org',
                   'SERVER_PORT': '8080'}
        req = CGIRequest(environ)
        req.base_url = _reconstruct_base_url(req)
        self.assertEqual('http://example.org:8080/trac', req.base_url)

    def test_base_url_https(self):
        environ = {'SCRIPT_NAME': '/trac', 'SERVER_NAME': 'example.org',
                   'HTTPS': 'on'}
        req = CGIRequest(environ)
        req.base_url = _reconstruct_base_url(req)
        self.assertEqual('https://example.org/trac', req.base_url)

    def test_base_url_https_host(self):
        environ = {'SCRIPT_NAME': '/trac', 'SERVER_NAME': 'localhost',
                   'SERVER_PORT': '8443', 'HTTPS': 'on',
                   'HTTP_HOST': 'example.org'}
        req = CGIRequest(environ)
        req.base_url = _reconstruct_base_url(req)
        self.assertEqual('https://example.org/trac', req.base_url)

    def test_base_url_https_nondefaultport(self):
        environ = {'SCRIPT_NAME': '/trac', 'SERVER_NAME': 'example.org',
                   'SERVER_PORT': '8443', 'HTTPS': 'on'}
        req = CGIRequest(environ)
        req.base_url = _reconstruct_base_url(req)
        self.assertEqual('https://example.org:8443/trac', req.base_url)

    def test_base_url_proxy(self):
        environ = {'SCRIPT_NAME': '/trac', 'SERVER_NAME': 'some_proxy.org',
                   'HTTP_X_FORWARDED_FOR': 'example.org'}
        req = CGIRequest(environ)
        req.base_url = _reconstruct_base_url(req)
        self.assertEqual('http://example.org/trac', req.base_url)


def suite():
    return unittest.makeSuite(CGIRequestTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
