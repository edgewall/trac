from trac.core import CGIRequest

import unittest


class CGIRequestTestCase(unittest.TestCase):

    def test_cgi_attrs(self):
        environ = {'SCRIPT_NAME': '/trac', 'REMOTE_ADDR': '127.0.0.1'}
        req = CGIRequest(environ)
        req.init_request()
        self.assertEqual('/trac', req.cgi_location)
        self.assertEqual('127.0.0.1', req.remote_addr)
        self.assertEqual(None, req.remote_user)

    def test_authname(self):
        environ = {'SCRIPT_NAME': '/trac', 'REMOTE_USER': 'john'}
        req = CGIRequest(environ)
        req.init_request()
        self.assertEqual('john', req.remote_user)

    def test_base_url(self):
        environ = {'SCRIPT_NAME': '/trac', 'SERVER_NAME': 'example.org'}
        req = CGIRequest(environ)
        req.init_request()
        self.assertEqual('http://example.org/trac', req.base_url)

    def test_base_url_nondefaultport(self):
        environ = {'SCRIPT_NAME': '/trac', 'SERVER_NAME': 'example.org',
                   'SERVER_PORT': '8080'}
        req = CGIRequest(environ)
        req.init_request()
        self.assertEqual('http://example.org:8080/trac', req.base_url)

    def test_base_url_https(self):
        environ = {'SCRIPT_NAME': '/trac', 'SERVER_NAME': 'example.org',
                   'HTTPS': 'on'}
        req = CGIRequest(environ)
        req.init_request()
        self.assertEqual('https://example.org/trac', req.base_url)

    def test_base_url_https_nondefaultport(self):
        environ = {'SCRIPT_NAME': '/trac', 'SERVER_NAME': 'example.org',
                   'SERVER_PORT': '8443', 'HTTPS': 'on'}
        req = CGIRequest(environ)
        req.init_request()
        self.assertEqual('https://example.org:8443/trac', req.base_url)

    def test_base_url_proxy(self):
        environ = {'SCRIPT_NAME': '/trac', 'SERVER_NAME': 'some_proxy.org',
                   'HTTP_X_FORWARDED_HOST': 'example.org'}
        req = CGIRequest(environ)
        req.init_request()
        self.assertEqual('http://example.org/trac', req.base_url)


def suite():
    return unittest.makeSuite(CGIRequestTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
