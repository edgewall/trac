from trac.web import clearsilver

import unittest


def suite():
    try:
        from doctest import DocTestSuite
        return DocTestSuite(clearsilver)
    except ImportError:
        import sys
        print >> sys.stderr, "WARNING: DocTestSuite required to run these " \
                             "tests"
    return unittest.TestSuite()

if __name__ == '__main__':
    runner = unittest.TextTestRunner()
    runner.run(suite())
