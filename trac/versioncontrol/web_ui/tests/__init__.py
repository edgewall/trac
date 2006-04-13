import unittest

from trac.versioncontrol.web_ui.tests import wikisyntax

def suite():
    suite = unittest.TestSuite()
    suite.addTest(wikisyntax.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
