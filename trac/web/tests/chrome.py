# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os
import shutil
import tempfile
import unittest

from genshi.builder import tag
import trac.tests.compat
from trac.core import Component, TracError, implements
from trac.test import EnvironmentStub, locale_en
from trac.tests.contentgen import random_sentence
from trac.util import create_file
from trac.web.chrome import (
    Chrome, INavigationContributor, add_link, add_meta, add_notice, add_script,
    add_script_data, add_stylesheet, add_warning)
from trac.web.href import Href


class Request(object):
    locale = None
    args = {}
    def __init__(self, **kwargs):
        self.chrome = {}
        for k, v in kwargs.items():
            setattr(self, k, v)


class ChromeTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        from trac.core import ComponentMeta
        self._old_registry = ComponentMeta._registry
        ComponentMeta._registry = {}

    def tearDown(self):
        from trac.core import ComponentMeta
        ComponentMeta._registry = self._old_registry

    def _get_navigation_item(self, items, name):
        for item in items:
            if item['name'] == name:
                return item
        return {}

    def test_add_meta(self):
        req = Request(href=Href('/trac.cgi'))
        add_meta(req, 'Jim Smith', name='Author', scheme='test', lang='en-us')
        add_meta(req, 'Tue, 20 Aug 1996 14:25:27 GMT', http_equiv='Expires')
        metas = req.chrome['metas']
        self.assertEqual(2, len(metas))
        meta = metas[0]
        self.assertEqual('Jim Smith', meta['content'])
        self.assertEqual('Author', meta['name'])
        self.assertEqual('test', meta['scheme'])
        self.assertEqual('en-us', meta['lang'])
        self.assertEqual('en-us', meta['xml:lang'])
        meta = metas[1]
        self.assertEqual('Tue, 20 Aug 1996 14:25:27 GMT', meta['content'])
        self.assertEqual('Expires', meta['http-equiv'])

    def test_add_link_simple(self):
        req = Request(href=Href('/trac.cgi'))
        add_link(req, 'start', '/trac/wiki')
        self.assertEqual('/trac/wiki',
                         req.chrome['links']['start'][0]['href'])

    def test_add_link_advanced(self):
        req = Request(href=Href('/trac.cgi'))
        add_link(req, 'start', '/trac/wiki', 'Start page', 'text/html', 'home')
        link = req.chrome['links']['start'][0]
        self.assertEqual('/trac/wiki', link['href'])
        self.assertEqual('Start page', link['title'])
        self.assertEqual('text/html', link['type'])
        self.assertEqual('home', link['class'])

    def test_add_script(self):
        req = Request(base_path='/trac.cgi', href=Href('/trac.cgi'))
        add_script(req, 'common/js/trac.js')
        add_script(req, 'common/js/trac.js')
        add_script(req, 'http://example.com/trac.js')
        add_script(req, '//example.com/trac.js')
        add_script(req, '/dynamic.js')
        add_script(req, 'plugin/js/plugin.js')
        scripts = req.chrome['scripts']
        self.assertEqual(5, len(scripts))
        self.assertEqual('text/javascript', scripts[0]['type'])
        self.assertEqual('/trac.cgi/chrome/common/js/trac.js',
                         scripts[0]['href'])
        self.assertEqual('text/javascript', scripts[1]['type'])
        self.assertEqual('http://example.com/trac.js',
                         scripts[1]['href'])
        self.assertEqual('text/javascript', scripts[2]['type'])
        self.assertEqual('//example.com/trac.js',
                         scripts[2]['href'])
        self.assertEqual('/trac.cgi/dynamic.js',
                         scripts[3]['href'])
        self.assertEqual('/trac.cgi/chrome/plugin/js/plugin.js',
                         scripts[4]['href'])

    def test_add_script_data(self):
        req = Request(href=Href('/trac.cgi'))
        add_script_data(req, {'var1': 1, 'var2': 'Testing'})
        add_script_data(req, var2='More testing', var3=3)
        self.assertEqual({'var1': 1, 'var2': 'More testing', 'var3': 3},
                         req.chrome['script_data'])

    def test_add_stylesheet(self):
        req = Request(base_path='/trac.cgi', href=Href('/trac.cgi'))
        add_stylesheet(req, 'common/css/trac.css')
        add_stylesheet(req, 'common/css/trac.css')
        add_stylesheet(req, 'https://example.com/trac.css')
        add_stylesheet(req, '//example.com/trac.css')
        add_stylesheet(req, '/dynamic.css')
        add_stylesheet(req, 'plugin/css/plugin.css')
        links = req.chrome['links']['stylesheet']
        self.assertEqual(5, len(links))
        self.assertEqual('text/css', links[0]['type'])
        self.assertEqual('/trac.cgi/chrome/common/css/trac.css',
                         links[0]['href'])
        self.assertEqual('text/css', links[1]['type'])
        self.assertEqual('https://example.com/trac.css',
                         links[1]['href'])
        self.assertEqual('text/css', links[2]['type'])
        self.assertEqual('//example.com/trac.css',
                         links[2]['href'])
        self.assertEqual('/trac.cgi/dynamic.css',
                         links[3]['href'])
        self.assertEqual('/trac.cgi/chrome/plugin/css/plugin.css',
                         links[4]['href'])

    def test_add_stylesheet_media(self):
        req = Request(base_path='/trac.cgi', href=Href('/trac.cgi'))
        add_stylesheet(req, 'foo.css', media='print')
        links = req.chrome['links']['stylesheet']
        self.assertEqual(1, len(links))
        self.assertEqual('print', links[0]['media'])

    def test_add_warning_is_unique(self):
        req = Request(abs_href=Href('http://example.org/trac.cgi'),
                      href=Href('/trac.cgi'), base_path='/trac.cgi',
                      path_info='',
                      add_redirect_listener=lambda listener: None)
        Chrome(self.env).prepare_request(req)
        message = random_sentence(5)
        add_warning(req, message)
        add_warning(req, message)
        self.assertEqual(1, len(req.chrome['warnings']))

    def test_add_notice_is_unique(self):
        req = Request(abs_href=Href('http://example.org/trac.cgi'),
                      href=Href('/trac.cgi'), base_path='/trac.cgi',
                      path_info='',
                      add_redirect_listener=lambda listener: None)
        Chrome(self.env).prepare_request(req)
        message = random_sentence(5)
        add_notice(req, message)
        add_notice(req, message)
        self.assertEqual(1, len(req.chrome['notices']))

    def test_htdocs_location(self):
        req = Request(abs_href=Href('http://example.org/trac.cgi'),
                      href=Href('/trac.cgi'), base_path='/trac.cgi',
                      path_info='',
                      add_redirect_listener=lambda listener: None)
        info = Chrome(self.env).prepare_request(req)
        self.assertEqual('/trac.cgi/chrome/common/', info['htdocs_location'])

    def test_logo(self):
        req = Request(abs_href=Href('http://example.org/trac.cgi'),
                      href=Href('/trac.cgi'), base_path='/trac.cgi',
                      path_info='',
                      add_redirect_listener=lambda listener: None)

        # Verify that no logo data is put in the HDF if no logo is configured
        self.env.config.set('header_logo', 'src', '')
        info = Chrome(self.env).prepare_request(req)
        self.assertNotIn('src', info['logo'])
        self.assertNotIn('src_abs', info['logo'])

        # Test with a relative path to the logo image
        self.env.config.set('header_logo', 'src', 'foo.png')
        info = Chrome(self.env).prepare_request(req)
        self.assertEqual('/trac.cgi/chrome/common/foo.png',
                         info['logo']['src'])
        self.assertEqual('http://example.org/trac.cgi/chrome/common/foo.png',
                         info['logo']['src_abs'])

        # Test with a location in project htdocs
        self.env.config.set('header_logo', 'src', 'site/foo.png')
        info = Chrome(self.env).prepare_request(req)
        self.assertEqual('/trac.cgi/chrome/site/foo.png',
                         info['logo']['src'])
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
        self.assertEqual('http://www.example.org/foo.png',
                         info['logo']['src'])
        self.assertEqual('http://www.example.org/foo.png',
                         info['logo']['src_abs'])

    def test_default_links(self):
        req = Request(abs_href=Href('http://example.org/trac.cgi'),
                      href=Href('/trac.cgi'), base_path='/trac.cgi',
                      path_info='',
                      add_redirect_listener=lambda listener: None)
        links = Chrome(self.env).prepare_request(req)['links']
        self.assertEqual('/trac.cgi/wiki', links['start'][0]['href'])
        self.assertEqual('/trac.cgi/search', links['search'][0]['href'])
        self.assertEqual('/trac.cgi/wiki/TracGuide', links['help'][0]['href'])
        self.assertEqual('/trac.cgi/chrome/common/css/trac.css',
                         links['stylesheet'][0]['href'])

    def test_icon_links(self):
        req = Request(abs_href=Href('http://example.org/trac.cgi'),
                      href=Href('/trac.cgi'), base_path='/trac.cgi',
                      path_info='',
                      add_redirect_listener=lambda listener: None)
        chrome = Chrome(self.env)

        # No icon set in config, so no icon links
        self.env.config.set('project', 'icon', '')
        links = chrome.prepare_request(req)['links']
        self.assertNotIn('icon', links)
        self.assertNotIn('shortcut icon', links)

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
        self.env.config.set('project', 'icon',
                            'http://example.com/favicon.ico')
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
        req = Request(abs_href=Href('http://example.org/trac.cgi'),
                      href=Href('/trac.cgi'), path_info='/',
                      base_path='/trac.cgi',
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
        req = Request(abs_href=Href('http://example.org/trac.cgi'),
                      href=Href('/trac.cgi'), path_info='/',
                      base_path='/trac.cgi',
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
        req = Request(abs_href=Href('http://example.org/trac.cgi'),
                      href=Href('/trac.cgi'), base_path='/trac.cgi',
                      path_info='/',
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

    def test_add_jquery_ui_timezone_list_has_z(self):
        chrome = Chrome(self.env)

        req = Request(href=Href('/trac.cgi'), lc_time='iso8601')
        chrome.add_jquery_ui(req)
        self.assertIn({'value': 'Z', 'label': '+00:00'},
                      req.chrome['script_data']['jquery_ui']['timezone_list'])

        req = Request(href=Href('/trac.cgi'), lc_time=locale_en)
        chrome.add_jquery_ui(req)
        self.assertIn({'value': 'Z', 'label': '+00:00'},
                      req.chrome['script_data']['jquery_ui']['timezone_list'])

    def test_navigation_item_customization(self):
        class TestNavigationContributor1(Component):
            implements(INavigationContributor)
            def get_active_navigation_item(self, req):
                return None
            def get_navigation_items(self, req):
                yield 'mainnav', 'test1', 'Test 1'
        class TestNavigationContributor2(Component):
            implements(INavigationContributor)
            def get_active_navigation_item(self, req):
                return None
            def get_navigation_items(self, req):
                yield 'mainnav', 'test2', 'Test 2'
        class TestNavigationContributor3(Component):
            implements(INavigationContributor)
            def get_active_navigation_item(self, req):
                return None
            def get_navigation_items(self, req):
                yield 'mainnav', 'test3', 'Test 3'
        req = Request(abs_href=Href('http://example.org/trac.cgi'),
                      href=Href('/trac.cgi'), base_path='/trac.cgi',
                      path_info='/',
                      add_redirect_listener=lambda listener: None)
        self.env.config.set('mainnav', 'test2.href', 'testtwo')
        self.env.config.set('mainnav', 'test3.label', 'Test Three')
        self.env.config.set('mainnav', 'test3.href', 'testthree')

        chrome = Chrome(self.env)
        items = chrome.prepare_request(req)['nav']['mainnav']

        item = self._get_navigation_item(items, 'test1')
        self.assertEqual('Test 1', item['label'])
        item = self._get_navigation_item(items, 'test2')
        self.assertEqual(str(tag.a('Test 2', href='testtwo')),
                         str(item['label']))
        item = self._get_navigation_item(items, 'test3')
        self.assertEqual(str(tag.a('Test Three', href='testthree')),
                         str(item['label']))

    def test_attributes_preserved_in_navigation_item(self):
        class TestNavigationContributor1(Component):
            implements(INavigationContributor)
            def get_active_navigation_item(self, req):
                return None
            def get_navigation_items(self, req):
                yield 'mainnav', 'test1', \
                      tag.a('Test 1', href='test1', target='blank')
        class TestNavigationContributor2(Component):
            implements(INavigationContributor)
            def get_active_navigation_item(self, req):
                return None
            def get_navigation_items(self, req):
                yield 'mainnav', 'test2', \
                      tag.a('Test 2', href='test2', target='blank')
        req = Request(abs_href=Href('http://example.org/trac.cgi'),
                      href=Href('/trac.cgi'), base_path='/trac.cgi',
                      path_info='/',
                      add_redirect_listener=lambda listener: None)
        self.env.config.set('mainnav', 'test1.label', 'Test One')
        self.env.config.set('mainnav', 'test2.label', 'Test Two')
        self.env.config.set('mainnav', 'test2.href', 'testtwo')

        chrome = Chrome(self.env)
        items = chrome.prepare_request(req)['nav']['mainnav']

        item = self._get_navigation_item(items, 'test1')
        self.assertEqual(str(tag.a('Test One', href='test1', target='blank')),
                         str(item['label']))
        item = self._get_navigation_item(items, 'test2')
        self.assertEqual(str(tag.a('Test Two', href='testtwo',
                                   target='blank')),
                         str(item['label']))


class ChromeTestCase2(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(path=tempfile.mkdtemp())
        self.chrome = Chrome(self.env)

    def tearDown(self):
        shutil.rmtree(self.env.path)

    def test_malicious_filename_raises(self):
        req = Request(path_info='/chrome/site/../conf/trac.ini')
        self.assertTrue(self.chrome.match_request(req))
        self.assertRaises(TracError, self.chrome.process_request, req)

    def test_empty_shared_htdocs_dir_raises_file_not_found(self):
        req = Request(path_info='/chrome/shared/trac_logo.png')
        self.assertEqual('', self.chrome.shared_htdocs_dir)
        self.assertTrue(self.chrome.match_request(req))
        from trac.web.api import HTTPNotFound
        self.assertRaises(HTTPNotFound, self.chrome.process_request, req)

    def test_shared_htdocs_dir_file_is_found(self):
        from trac.web.api import RequestDone
        def send_file(path, mimetype):
            raise RequestDone
        req = Request(path_info='/chrome/shared/trac_logo.png',
                      send_file=send_file)
        shared_htdocs_dir = os.path.join(self.env.path, 'chrome', 'shared')
        os.makedirs(shared_htdocs_dir)
        create_file(os.path.join(shared_htdocs_dir, 'trac_logo.png'))
        self.env.config.set('inherit', 'htdocs_dir', shared_htdocs_dir)
        self.assertTrue(self.chrome.match_request(req))
        self.assertRaises(RequestDone, self.chrome.process_request, req)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ChromeTestCase))
    suite.addTest(unittest.makeSuite(ChromeTestCase2))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
