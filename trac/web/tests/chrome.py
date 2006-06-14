from trac.config import Configuration
from trac.core import Component, ComponentManager, implements
from trac.perm import PermissionCache
from trac.test import EnvironmentStub, Mock
from trac.web.clearsilver import HDFWrapper
from trac.web.chrome import add_link, add_stylesheet, Chrome, \
                            INavigationContributor
from trac.web.href import Href

import unittest


class ChromeTestCase(unittest.TestCase):

    def test_add_link_simple(self):
        req = Mock(hdf=HDFWrapper(), href=Href('/trac.cgi'))
        add_link(req, 'start', '/trac/wiki')
        self.assertEqual('/trac/wiki', req.hdf['chrome.links.start.0.href'])

    def test_add_link_advanced(self):
        req = Mock(hdf=HDFWrapper(), href=Href('/trac.cgi'))
        add_link(req, 'start', '/trac/wiki', 'Start page', 'text/html', 'home')
        self.assertEqual('/trac/wiki', req.hdf['chrome.links.start.0.href'])
        self.assertEqual('Start page', req.hdf['chrome.links.start.0.title'])
        self.assertEqual('text/html', req.hdf['chrome.links.start.0.type'])
        self.assertEqual('home', req.hdf['chrome.links.start.0.class'])

    def test_add_stylesheet(self):
        req = Mock(base_path='/trac.cgi', hdf=HDFWrapper(), href=Href('/trac.cgi'))
        add_stylesheet(req, 'common/css/trac.css')
        self.assertEqual('text/css', req.hdf['chrome.links.stylesheet.0.type'])
        self.assertEqual('/trac.cgi/chrome/common/css/trac.css',
                         req.hdf['chrome.links.stylesheet.0.href'])

    def test_htdocs_location(self):
        env = EnvironmentStub(enable=[])
        req = Mock(hdf=HDFWrapper(), href=Href('/trac.cgi'),
                   base_path='/trac.cgi', path_info='')
        Chrome(env).populate_hdf(req, None)
        self.assertEqual('/trac.cgi/chrome/common/', req.hdf['htdocs_location'])

    def test_logo(self):
        env = EnvironmentStub(enable=[])
        req = Mock(hdf=HDFWrapper(), href=Href('/trac.cgi'),
                   base_path='/trac.cgi', path_info='')

        # Verify that no logo data is put in the HDF if no logo is configured
        env.config.set('header_logo', 'src', '')
        Chrome(env).populate_hdf(req, None)
        assert 'chrome.logo.src' not in req.hdf

        # Test with a relative path to the logo image
        req.hdf = HDFWrapper()
        env.config.set('header_logo', 'src', 'foo.png')
        Chrome(env).populate_hdf(req, None)
        self.assertEqual('/trac.cgi/chrome/common/foo.png',
                         req.hdf['chrome.logo.src'])

        # Test with a server-relative path to the logo image
        req.hdf = HDFWrapper()
        env.config.set('header_logo', 'src', '/img/foo.png')
        Chrome(env).populate_hdf(req, None)
        self.assertEqual('/img/foo.png', req.hdf['chrome.logo.src'])

        # Test with an absolute path to the logo image
        req.hdf = HDFWrapper()
        env.config.set('header_logo', 'src', 'http://www.example.org/foo.png')
        Chrome(env).populate_hdf(req, None)
        self.assertEqual('http://www.example.org/foo.png',
                         req.hdf['chrome.logo.src'])

    def test_default_links(self):
        env = EnvironmentStub(enable=[])
        req = Mock(hdf=HDFWrapper(), href=Href('/trac.cgi'),
                   base_path='/trac.cgi', path_info='')
        Chrome(env).populate_hdf(req, None)
        self.assertEqual('/trac.cgi/wiki',
                         req.hdf['chrome.links.start.0.href'])
        self.assertEqual('/trac.cgi/search',
                         req.hdf['chrome.links.search.0.href'])
        self.assertEqual('/trac.cgi/wiki/TracGuide',
                         req.hdf['chrome.links.help.0.href'])
        self.assertEqual('/trac.cgi/chrome/common/css/trac.css',
                         req.hdf['chrome.links.stylesheet.0.href'])

    def test_icon_links(self):
        env = EnvironmentStub(enable=[])
        req = Mock(hdf=HDFWrapper(), href=Href('/trac.cgi'),
                   base_path='/trac.cgi', path_info='')

        # No icon set in config, so no icon links
        env.config.set('project', 'icon', '')
        Chrome(env).populate_hdf(req, None)
        assert 'chrome.links.icon' not in req.hdf
        assert 'chrome.links.shortcut icon' not in req.hdf

        # Relative URL for icon config option
        env.config.set('project', 'icon', 'trac.ico')
        Chrome(env).populate_hdf(req, None)
        self.assertEqual('/trac.cgi/chrome/common/trac.ico',
                         req.hdf['chrome.links.icon.0.href'])
        self.assertEqual('/trac.cgi/chrome/common/trac.ico',
                         req.hdf['chrome.links.shortcut icon.0.href'])

        # URL relative to the server root for icon config option
        req.hdf = HDFWrapper()
        env.config.set('project', 'icon', '/favicon.ico')
        Chrome(env).populate_hdf(req, None)
        self.assertEqual('/favicon.ico',
                         req.hdf['chrome.links.icon.0.href'])
        self.assertEqual('/favicon.ico',
                         req.hdf['chrome.links.shortcut icon.0.href'])

        # Absolute URL for icon config option
        req.hdf = HDFWrapper()
        env.config.set('project', 'icon', 'http://example.com/favicon.ico')
        Chrome(env).populate_hdf(req, None)
        self.assertEqual('http://example.com/favicon.ico',
                         req.hdf['chrome.links.icon.0.href'])
        self.assertEqual('http://example.com/favicon.ico',
                         req.hdf['chrome.links.shortcut icon.0.href'])

    def test_nav_contributor(self):
        class TestNavigationContributor(Component):
            implements(INavigationContributor)
            def get_active_navigation_item(self, req):
                return None
            def get_navigation_items(self, req):
                yield 'metanav', 'test', 'Test'
        env = EnvironmentStub(enable=[TestNavigationContributor])
        req = Mock(hdf=HDFWrapper(), href=Href('/trac.cgi'),
                   path_info='/', base_path='/trac.cgi')
        chrome = Chrome(env)
        chrome.populate_hdf(req, None)
        self.assertEqual('Test', req.hdf['chrome.nav.metanav.test'])
        self.assertRaises(KeyError, req.hdf.__getitem__,
                          'chrome.nav.metanav.test.active')

    def test_nav_contributor_active(self):
        class TestNavigationContributor(Component):
            implements(INavigationContributor)
            def get_active_navigation_item(self, req):
                return 'test'
            def get_navigation_items(self, req):
                yield 'metanav', 'test', 'Test'
        env = EnvironmentStub(enable=[TestNavigationContributor])
        req = Mock(hdf=HDFWrapper(), href=Href('/trac.cgi'),
                   path_info='/', base_path='/trac.cgi')
        chrome = Chrome(env)
        chrome.populate_hdf(req, TestNavigationContributor(env))
        self.assertEqual('Test', req.hdf['chrome.nav.metanav.test'])
        self.assertEqual('1', req.hdf['chrome.nav.metanav.test.active'])

    def test_nav_contributor_order(self):
        class TestNavigationContributor1(Component):
            implements(INavigationContributor)
            def get_active_navigation_item(self, req):
                return None
            def get_navigation_items(self, req):
                yield 'metanav', 'test1', 'Test 1'
        class TestNavigationContributor2(Component):
            implements(INavigationContributor)
            def get_active_navigation_item(self, req):
                return None
            def get_navigation_items(self, req):
                yield 'metanav', 'test2', 'Test 2'
        env = EnvironmentStub(enable=[TestNavigationContributor1,
                                      TestNavigationContributor2])
        req = Mock(hdf=HDFWrapper(), href=Href('/trac.cgi'),
                   path_info='/', base_path='/trac.cgi')
        chrome = Chrome(env)

        # Test with both items set in the order option
        env.config.set('trac', 'metanav', 'test2, test1')
        chrome.populate_hdf(req, None)
        node = req.hdf.getObj('chrome.nav.metanav').child()
        self.assertEqual('test2', node.name())
        self.assertEqual('test1', node.next().name())

        # Test with only test1 in the order options
        req.hdf = HDFWrapper()
        env.config.set('trac', 'metanav', 'test1')
        chrome.populate_hdf(req, None)
        node = req.hdf.getObj('chrome.nav.metanav').child()
        self.assertEqual('test1', node.name())
        self.assertEqual('test2', node.next().name())

        # Test with only test2 in the order options
        req.hdf = HDFWrapper()
        env.config.set('trac', 'metanav', 'test2')
        chrome.populate_hdf(req, None)
        node = req.hdf.getObj('chrome.nav.metanav').child()
        self.assertEqual('test2', node.name())
        self.assertEqual('test1', node.next().name())

        # Test with none in the order options (order corresponds to
        # registration order)
        req.hdf = HDFWrapper()
        env.config.set('trac', 'metanav', 'foo, bar')
        chrome.populate_hdf(req, None)
        node = req.hdf.getObj('chrome.nav.metanav').child()
        self.assertEqual('test1', node.name())
        self.assertEqual('test2', node.next().name())


def suite():
    return unittest.makeSuite(ChromeTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
