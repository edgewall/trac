import unittest

from trac.web.tests import auth, cgi_frontend, clearsilver, href, main, session

def suite():

    suite = unittest.TestSuite()
    suite.addTest(auth.suite())
    suite.addTest(cgi_frontend.suite())
    suite.addTest(clearsilver.suite())
    suite.addTest(href.suite())
    suite.addTest(main.suite())
    suite.addTest(session.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
