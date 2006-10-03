from trac.core import Component, ComponentManager, implements
from trac.perm import PermissionCache
from trac.test import EnvironmentStub, Mock
from trac.web.chrome import add_link, add_stylesheet, Chrome, \
                            INavigationContributor
from trac.web.href import Href

import unittest


class ChromeTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        from trac.core import ComponentMeta
        self._old_registry = ComponentMeta._registry
        ComponentMeta._registry = {}

    def tearDown(self):
        from trac.core import ComponentMeta
        ComponentMeta._registry = self._old_registry

    def test_add_link_simple(self):
        req = Mock(environ={}, href=Href('/trac.cgi'))
        add_link(req, 'start', '/trac/wiki')
        self.assertEqual('/trac/wiki',
                         req.environ['trac.chrome.links']['start'][0]['href'])

    def test_add_link_advanced(self):
        req = Mock(environ={}, href=Href('/trac.cgi'))
        add_link(req, 'start', '/trac/wiki', 'Start page', 'text/html', 'home')
        link = req.environ['trac.chrome.links']['start'][0]
        self.assertEqual('/trac/wiki', link['href'])
        self.assertEqual('Start page', link['title'])
        self.assertEqual('text/html', link['type'])
        self.assertEqual('home', link['class'])

    def test_add_stylesheet(self):
        req = Mock(base_path='/trac.cgi', environ={}, href=Href('/trac.cgi'))
        add_stylesheet(req, 'common/css/trac.css')
        link = req.environ['trac.chrome.links']['stylesheet'][0]
        self.assertEqual('text/css', link['type'])
        self.assertEqual('/trac.cgi/chrome/common/css/trac.css', link['href'])

    def test_htdocs_location(self):
        req = Mock(environ={}, href=Href('/trac.cgi'), base_path='/trac.cgi',
                   path_info='')
        Chrome(self.env).prepare_request(req)
        self.assertEqual('/trac.cgi/chrome/common/',
                         req.environ['trac.htdocs_location'])

    def test_logo(self):
        req = Mock(environ={}, href=Href('/trac.cgi'), base_path='/trac.cgi',
                   path_info='')

        # Verify that no logo data is put in the HDF if no logo is configured
        self.env.config.set('header_logo', 'src', '')
        Chrome(self.env).prepare_request(req)
        assert 'src' not in req.environ['trac.chrome.logo']

        # Test with a relative path to the logo image
        self.env.config.set('header_logo', 'src', 'foo.png')
        Chrome(self.env).prepare_request(req)
        self.assertEqual('/trac.cgi/chrome/common/foo.png',
                         req.environ['trac.chrome.logo']['src'])

        # Test with a server-relative path to the logo image
        self.env.config.set('header_logo', 'src', '/img/foo.png')
        Chrome(self.env).prepare_request(req)
        self.assertEqual('/img/foo.png', req.environ['trac.chrome.logo']['src'])

        # Test with an absolute path to the logo image
        self.env.config.set('header_logo', 'src',
                            'http://www.example.org/foo.png')
        Chrome(self.env).prepare_request(req)
        self.assertEqual('http://www.example.org/foo.png',
                         req.environ['trac.chrome.logo']['src'])

    def test_default_links(self):
        req = Mock(environ={}, href=Href('/trac.cgi'), base_path='/trac.cgi',
                   path_info='')
        Chrome(self.env).prepare_request(req)
        links = req.environ['trac.chrome.links']
        self.assertEqual('/trac.cgi/wiki', links['start'][0]['href'])
        self.assertEqual('/trac.cgi/search', links['search'][0]['href'])
        self.assertEqual('/trac.cgi/wiki/TracGuide', links['help'][0]['href'])
        self.assertEqual('/trac.cgi/chrome/common/css/trac.css',
                         links['stylesheet'][0]['href'])

    def test_icon_links(self):
        req = Mock(environ={}, href=Href('/trac.cgi'), base_path='/trac.cgi',
                   path_info='')

        # No icon set in config, so no icon links
        self.env.config.set('project', 'icon', '')
        Chrome(self.env).prepare_request(req)
        links = req.environ['trac.chrome.links']
        assert 'icon' not in links
        assert 'shortcut icon' not in links

        # Relative URL for icon config option
        self.env.config.set('project', 'icon', 'foo.ico')
        Chrome(self.env).prepare_request(req)
        links = req.environ['trac.chrome.links']
        self.assertEqual('/trac.cgi/chrome/common/foo.ico',
                         links['icon'][0]['href'])
        self.assertEqual('/trac.cgi/chrome/common/foo.ico',
                         links['shortcut icon'][0]['href'])

        # URL relative to the server root for icon config option
        self.env.config.set('project', 'icon', '/favicon.ico')
        Chrome(self.env).prepare_request(req)
        links = req.environ['trac.chrome.links']
        self.assertEqual('/favicon.ico', links['icon'][0]['href'])
        self.assertEqual('/favicon.ico', links['shortcut icon'][0]['href'])

        # Absolute URL for icon config option
        self.env.config.set('project', 'icon', 'http://example.com/favicon.ico')
        Chrome(self.env).prepare_request(req)
        links = req.environ['trac.chrome.links']
        self.assertEqual('http://example.com/favicon.ico',
                         links['icon'][0]['href'])
        self.assertEqual('http://example.com/favicon.ico',
                         links['shortcut icon'][0]['href'])

    def test_nav_contributor(self):
        class TestNavigationContributor(Component):
            implements(INavigationContributor)
            def get_active_navigation_item(self, req):
                return None
            def get_navigation_items(self, req):
                yield 'metanav', 'test', 'Test'
        req = Mock(environ={}, href=Href('/trac.cgi'), path_info='/',
                   base_path='/trac.cgi')
        Chrome(self.env).prepare_request(req)
        nav = req.environ['trac.chrome.nav']
        self.assertEqual({'name': 'test', 'label': 'Test'}, nav['metanav'][0])

    def test_nav_contributor_active(self):
        class TestNavigationContributor(Component):
            implements(INavigationContributor)
            def get_active_navigation_item(self, req):
                return 'test'
            def get_navigation_items(self, req):
                yield 'metanav', 'test', 'Test'
        req = Mock(environ={}, href=Href('/trac.cgi'), path_info='/',
                   base_path='/trac.cgi')
        handler = TestNavigationContributor(self.env)
        Chrome(self.env).prepare_request(req, handler)
        nav = req.environ['trac.chrome.nav']
        self.assertEqual({'name': 'test', 'label': 'Test', 'active': True},
                         nav['metanav'][0])

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
        req = Mock(environ={}, href=Href('/trac.cgi'), base_path='/trac.cgi',
                   path_info='/')
        chrome = Chrome(self.env)

        # Test with both items set in the order option
        self.env.config.set('trac', 'metanav', 'test2, test1')
        chrome.prepare_request(req)
        items = req.environ['trac.chrome.nav']['metanav']
        self.assertEqual('test2', items[0]['name'])
        self.assertEqual('test1', items[1]['name'])

        # Test with only test1 in the order options
        self.env.config.set('trac', 'metanav', 'test1')
        chrome.prepare_request(req)
        items = req.environ['trac.chrome.nav']['metanav']
        self.assertEqual('test1', items[0]['name'])
        self.assertEqual('test2', items[1]['name'])

        # Test with only test2 in the order options
        self.env.config.set('trac', 'metanav', 'test2')
        chrome.prepare_request(req)
        items = req.environ['trac.chrome.nav']['metanav']
        self.assertEqual('test2', items[0]['name'])
        self.assertEqual('test1', items[1]['name'])

        # Test with none in the order options (order corresponds to
        # registration order)
        self.env.config.set('trac', 'metanav', 'foo, bar')
        chrome.prepare_request(req)
        items = req.environ['trac.chrome.nav']['metanav']
        self.assertEqual('test1', items[0]['name'])
        self.assertEqual('test2', items[1]['name'])


def suite():
    return unittest.makeSuite(ChromeTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
