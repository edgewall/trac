from trac.test import Mock
from trac.web.clearsilver import HDFWrapper
from trac.web.chrome import add_link

import unittest


class ChromeTestCase(unittest.TestCase):

    def test_add_link_simple(self):
        hdf = HDFWrapper()
        req = Mock(hdf=hdf)
        add_link(req, 'start', '/trac/wiki')
        self.assertEqual('/trac/wiki', hdf['links.start.0.href'])

    def test_add_link_advanced(self):
        hdf = HDFWrapper()
        req = Mock(hdf=hdf)
        add_link(req, 'start', '/trac/wiki', 'Start page', 'text/html', 'home')
        self.assertEqual('/trac/wiki', hdf['links.start.0.href'])
        self.assertEqual('Start page', hdf['links.start.0.title'])
        self.assertEqual('text/html', hdf['links.start.0.type'])
        self.assertEqual('home', hdf['links.start.0.class'])


def suite():
    return unittest.makeSuite(ChromeTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
