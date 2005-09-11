from trac.web.cgi_frontend import CGIRequest

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


def suite():
    return unittest.makeSuite(CGIRequestTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
