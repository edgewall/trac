from trac.core import Component, ComponentManager, implements
from trac.test import EnvironmentStub, Mock
from trac.web.chrome import add_link, add_script, add_stylesheet, Chrome, \
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
        req = Mock(chrome={}, href=Href('/trac.cgi'))
        add_link(req, 'start', '/trac/wiki')
        self.assertEqual('/trac/wiki',
                         req.chrome['links']['start'][0]['href'])

    def test_add_link_advanced(self):
        req = Mock(chrome={}, href=Href('/trac.cgi'))
        add_link(req, 'start', '/trac/wiki', 'Start page', 'text/html', 'home')
        link = req.chrome['links']['start'][0]
        self.assertEqual('/trac/wiki', link['href'])
        self.assertEqual('Start page', link['title'])
        self.assertEqual('text/html', link['type'])
        self.assertEqual('home', link['class'])

    def test_add_script(self):
        req = Mock(base_path='/trac.cgi', chrome={}, href=Href('/trac.cgi'))
        add_script(req, 'common/js/trac.js')
        add_script(req, 'common/js/trac.js')
        scripts = req.chrome['scripts']
        self.assertEqual(1, len(scripts))
        self.assertEqual('text/javascript', scripts[0]['type'])
        self.assertEqual('/trac.cgi/chrome/common/js/trac.js',
                         scripts[0]['href'])

    def test_add_stylesheet(self):
        req = Mock(base_path='/trac.cgi', chrome={}, href=Href('/trac.cgi'))
        add_stylesheet(req, 'common/css/trac.css')
        add_stylesheet(req, 'common/css/trac.css')
        links = req.chrome['links']['stylesheet']
        self.assertEqual(1, len(links))
        self.assertEqual('text/css', links[0]['type'])
        self.assertEqual('/trac.cgi/chrome/common/css/trac.css',
                         links[0]['href'])

    def test_htdocs_location(self):
        req = Mock(chrome={}, abs_href=Href('http://example.org/trac.cgi'),
                   href=Href('/trac.cgi'), base_path='/trac.cgi', path_info='',
                   add_redirect_listener=lambda listener: None)
        info = Chrome(self.env).prepare_request(req)
        self.assertEqual('/trac.cgi/chrome/common/', info['htdocs_location'])

    def test_logo(self):
        req = Mock(chrome={}, abs_href=Href('http://example.org/trac.cgi'),
                   href=Href('/trac.cgi'), base_path='/trac.cgi', path_info='',
                   add_redirect_listener=lambda listener: None)

        # Verify that no logo data is put in the HDF if no logo is configured
        self.env.config.set('header_logo', 'src', '')
        info = Chrome(self.env).prepare_request(req)
        assert 'src' not in info['logo']
        assert 'src_abs' not in info['logo']

        # Test with a relative path to the logo image
        self.env.config.set('header_logo', 'src', 'foo.png')
        info = Chrome(self.env).prepare_request(req)
        self.assertEqual('/trac.cgi/chrome/common/foo.png', info['logo']['src'])
        self.assertEqual('http://example.org/trac.cgi/chrome/common/foo.png', 
                    info['logo']['src_abs'])

        # Test with a location in project htdocs
        self.env.config.set('header_logo', 'src', 'site/foo.png')
        info = Chrome(self.env).prepare_request(req)
        self.assertEqual('/trac.cgi/chrome/site/foo.png', info['logo']['src'])
        self.assertEqual('http://example.org/trac.cgi/chrome/site/foo.png', 
                    info['logo']['src_abs'])

        # Test with a server-relative path to the logo image
        self.env.config.set('header_logo', 'src', '/img/foo.png')
        info = Chrome(self.env).prepare_request(req)
        self.assertEqual('/img/foo.png', info['logo']['src'])
        self.assertEqual('/img/foo.png', info['logo']['src_abs'])

        # Test with an absolute path to the logo image
        self.env.config.set('header_logo', 'src',
                            'http://www.example.org/foo.png')
        info = Chrome(self.env).prepare_request(req)
        self.assertEqual('http://www.example.org/foo.png', info['logo']['src'])
        self.assertEqual('http://www.example.org/foo.png', info['logo']['src_abs'])

    def test_default_links(self):
        req = Mock(chrome={}, abs_href=Href('http://example.org/trac.cgi'),
                   href=Href('/trac.cgi'), base_path='/trac.cgi', path_info='',
                   add_redirect_listener=lambda listener: None)
        links = Chrome(self.env).prepare_request(req)['links']
        self.assertEqual('/trac.cgi/wiki', links['start'][0]['href'])
        self.assertEqual('/trac.cgi/search', links['search'][0]['href'])
        self.assertEqual('/trac.cgi/wiki/TracGuide', links['help'][0]['href'])
        self.assertEqual('/trac.cgi/chrome/common/css/trac.css',
                         links['stylesheet'][0]['href'])

    def test_icon_links(self):
        req = Mock(chrome={}, abs_href=Href('http://example.org/trac.cgi'),
                   href=Href('/trac.cgi'), base_path='/trac.cgi', path_info='',
                   add_redirect_listener=lambda listener: None)
        chrome = Chrome(self.env)

        # No icon set in config, so no icon links
        self.env.config.set('project', 'icon', '')
        links = chrome.prepare_request(req)['links']
        assert 'icon' not in links
        assert 'shortcut icon' not in links

        # Relative URL for icon config option
        self.env.config.set('project', 'icon', 'foo.ico')
        links = chrome.prepare_request(req)['links']
        self.assertEqual('/trac.cgi/chrome/common/foo.ico',
                         links['icon'][0]['href'])
        self.assertEqual('/trac.cgi/chrome/common/foo.ico',
                         links['shortcut icon'][0]['href'])

        # URL relative to the server root for icon config option
        self.env.config.set('project', 'icon', '/favicon.ico')
        links = chrome.prepare_request(req)['links']
        self.assertEqual('/favicon.ico', links['icon'][0]['href'])
        self.assertEqual('/favicon.ico', links['shortcut icon'][0]['href'])

        # Absolute URL for icon config option
        self.env.config.set('project', 'icon', 'http://example.com/favicon.ico')
        links = chrome.prepare_request(req)['links']
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
        req = Mock(chrome={}, abs_href=Href('http://example.org/trac.cgi'),
                   href=Href('/trac.cgi'), path_info='/', base_path='/trac.cgi',
                   add_redirect_listener=lambda listener: None)
        nav = Chrome(self.env).prepare_request(req)['nav']
        self.assertEqual({'name': 'test', 'label': 'Test', 'active': False},
                         nav['metanav'][0])

    def test_nav_contributor_active(self):
        class TestNavigationContributor(Component):
            implements(INavigationContributor)
            def get_active_navigation_item(self, req):
                return 'test'
            def get_navigation_items(self, req):
                yield 'metanav', 'test', 'Test'
        req = Mock(chrome={}, abs_href=Href('http://example.org/trac.cgi'),
                   href=Href('/trac.cgi'), path_info='/', base_path='/trac.cgi',
                   add_redirect_listener=lambda listener: None)
        handler = TestNavigationContributor(self.env)
        nav = Chrome(self.env).prepare_request(req, handler)['nav']
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
        req = Mock(chrome={}, abs_href=Href('http://example.org/trac.cgi'),
                   href=Href('/trac.cgi'), base_path='/trac.cgi', path_info='/',
                   add_redirect_listener=lambda listener: None)
        chrome = Chrome(self.env)

        # Test with both items set in the order option
        self.env.config.set('trac', 'metanav', 'test2, test1')
        items = chrome.prepare_request(req)['nav']['metanav']
        self.assertEqual('test2', items[0]['name'])
        self.assertEqual('test1', items[1]['name'])

        # Test with only test1 in the order options
        self.env.config.set('trac', 'metanav', 'test1')
        items = chrome.prepare_request(req)['nav']['metanav']
        self.assertEqual('test1', items[0]['name'])
        self.assertEqual('test2', items[1]['name'])

        # Test with only test2 in the order options
        self.env.config.set('trac', 'metanav', 'test2')
        items = chrome.prepare_request(req)['nav']['metanav']
        self.assertEqual('test2', items[0]['name'])
        self.assertEqual('test1', items[1]['name'])

        # Test with none in the order options (order corresponds to
        # registration order)
        self.env.config.set('trac', 'metanav', 'foo, bar')
        items = chrome.prepare_request(req)['nav']['metanav']
        self.assertEqual('test1', items[0]['name'])
        self.assertEqual('test2', items[1]['name'])


def suite():
    return unittest.makeSuite(ChromeTestCase, 'test')

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
