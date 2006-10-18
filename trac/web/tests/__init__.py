import unittest

from trac.web.tests import api, auth, cgi_frontend, chrome, \
                           href, paginate, session, wikisyntax

try:
    import neo_cgi
    from trac.web.tests import clearsilver
except ImportError:
    clearsilver = None

def suite():
    suite = unittest.TestSuite()
    suite.addTest(api.suite())
    suite.addTest(auth.suite())
    suite.addTest(cgi_frontend.suite())
    suite.addTest(chrome.suite())
    if clearsilver:
        suite.addTest(clearsilver.suite())
    suite.addTest(href.suite())
    suite.addTest(paginate.suite())
    suite.addTest(session.suite())
    suite.addTest(wikisyntax.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
