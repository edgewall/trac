#from trac.web.cgi_frontend import CGIRequest

import unittest


class CGIRequestTestCase(unittest.TestCase):
    pass


def suite():
    return unittest.makeSuite(CGIRequestTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
