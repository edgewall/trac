import unittest

from trac.web.tests import api, auth, cgi_frontend, chrome, clearsilver, \
                           href, session, wikisyntax

def suite():

    suite = unittest.TestSuite()
    suite.addTest(api.suite())
    suite.addTest(auth.suite())
    suite.addTest(cgi_frontend.suite())
    suite.addTest(chrome.suite())
    suite.addTest(clearsilver.suite())
    suite.addTest(href.suite())
    suite.addTest(session.suite())
    suite.addTest(wikisyntax.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
