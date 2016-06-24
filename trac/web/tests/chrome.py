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
import tempfile
import unittest

import trac.tests.compat
from trac.config import ConfigurationError
from trac.core import Component, TracError, implements
from trac.perm import PermissionSystem
from trac.test import EnvironmentStub, MockPerm, MockRequest, locale_en
from trac.tests.contentgen import random_sentence
from trac.resource import Resource
from trac.util import create_file
from trac.util.datefmt import pytz, timezone, utc
from trac.util.html import Markup, tag
from trac.web.chrome import (
    Chrome, INavigationContributor, add_link, add_meta, add_notice, add_script,
    add_script_data, add_stylesheet, add_warning, web_context)
from trac.web.href import Href


class Request(object):
    locale = None
    perm = MockPerm()
    args = {}
    def __init__(self, **kwargs):
        self.chrome = {}
        for k, v in kwargs.items():
            setattr(self, k, v)


class ChromeTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.env.clear_component_registry()

    def tearDown(self):
        self.env.restore_component_registry()

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

    def _test_add_message_escapes_markup(self, msgtype, add_fn):
        req = Request(chrome={msgtype: []})
        add_fn(req, 'Message with an "&"')
        add_fn(req, Exception("Exception message with an &"))
        add_fn(req, tag("Message with text ", tag.b("& markup")))
        add_fn(req, Markup("Markup <strong>message</strong>."))
        messages = req.chrome[msgtype]
        self.assertIn('Message with an "&amp;"', messages)
        self.assertIn("Exception message with an &amp;", messages)
        self.assertIn("Message with text <b>&amp; markup</b>", messages)
        self.assertIn("Markup <strong>message</strong>.", messages)

    def test_add_warning_escapes_markup(self):
        """Message text is escaped. Regression test for
        http://trac.edgewall.org/ticket/12285
        """
        self._test_add_message_escapes_markup('warnings', add_warning)

    def test_add_notice_escapes_markup(self):
        """Message text is escaped. Regression test for
        http://trac.edgewall.org/ticket/12285
        """
        self._test_add_message_escapes_markup('notices', add_notice)

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
        self.assertNotIn('shortcut icon', links)

        # URL relative to the server root for icon config option
        self.env.config.set('project', 'icon', '/favicon.ico')
        links = chrome.prepare_request(req)['links']
        self.assertEqual('/favicon.ico', links['icon'][0]['href'])
        self.assertNotIn('shortcut icon', links)

        # Absolute URL for icon config option
        self.env.config.set('project', 'icon',
                            'http://example.com/favicon.ico')
        links = chrome.prepare_request(req)['links']
        self.assertEqual('http://example.com/favicon.ico',
                         links['icon'][0]['href'])
        self.assertNotIn('shortcut icon', links)

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

    def _get_jquery_ui_script_data(self, lc_time):
        req = Request(href=Href('/trac.cgi'), tz=utc, lc_time=lc_time)
        Chrome(self.env).add_jquery_ui(req)
        return req.chrome['script_data']['jquery_ui']

    def test_add_jquery_ui_is_iso8601(self):
        data = self._get_jquery_ui_script_data('iso8601')
        self.assertIn({'value': -60, 'label': '-01:00'}, data['timezone_list'])
        self.assertIn({'value': 0, 'label': '+00:00'}, data['timezone_list'])
        self.assertIn({'value': 60, 'label': '+01:00'}, data['timezone_list'])

    def test_add_jquery_ui_default_format(self):
        data = self._get_jquery_ui_script_data(locale_en)
        self.assertIsNone(data['timezone_list'])

    def test_invalid_default_dateinfo_format_raises_exception(self):
        self.env.config.set('trac', 'default_dateinfo_format', u'ābšolute')

        self.assertEqual(u'ābšolute',
                         self.env.config.get('trac', 'default_dateinfo_format'))
        self.assertRaises(ConfigurationError, getattr, Chrome(self.env),
                          'default_dateinfo_format')

    def test_add_jquery_ui_first_week_day(self):
        def first_week_day(locale, lc_time, languages):
            chrome = Chrome(self.env)
            req = Request(href=Href('/trac.cgi'), locale=locale,
                          lc_time=lc_time, tz=utc, languages=languages)
            chrome.add_jquery_ui(req)
            return req.chrome['script_data']['jquery_ui']['first_week_day']

        # Babel is unavailable
        self.assertEqual(0, first_week_day(None, None, None))
        self.assertEqual(1, first_week_day(None, 'iso8601', None))
        if locale_en:
            # We expect the following aliases
            from babel.core import LOCALE_ALIASES, Locale
            self.assertEqual('ja_JP', LOCALE_ALIASES['ja'])
            self.assertEqual('de_DE', LOCALE_ALIASES['de'])
            self.assertEqual('fr_FR', LOCALE_ALIASES['fr'])

            self.assertEqual(0, first_week_day(locale_en, locale_en, []))
            self.assertEqual(1, first_week_day(locale_en, 'iso8601', []))
            ja = Locale.parse('ja')
            self.assertEqual(0, first_week_day(ja, ja, []))
            self.assertEqual(0, first_week_day(ja, ja, ['ja', 'ja-jp']))
            de = Locale.parse('de')
            self.assertEqual(1, first_week_day(de, de, []))
            self.assertEqual(1, first_week_day(de, de, ['de', 'de-de']))
            fr = Locale.parse('fr')
            self.assertEqual(1, first_week_day(fr, fr, []))
            self.assertEqual(1, first_week_day(fr, fr, ['fr', 'fr-fr']))
            self.assertEqual(0, first_week_day(fr, fr, ['fr', 'fr-ca']))
            # invalid locale identifier (#12408)
            self.assertEqual(1, first_week_day(fr, fr, ['fr', 'fr-']))
            self.assertEqual(0, first_week_day(fr, fr, ['fr', 'fr-', 'fr-ca']))

    def test_add_jquery_ui_timezone_list_has_default_timezone(self):
        chrome = Chrome(self.env)
        href = Href('/trac.cgi')
        gmt07b = timezone('GMT -7:00')
        gmt04a = timezone('GMT +4:00')

        def verify_tzprops(lc_time, tz, tz_default, tz_label):
            req = Request(href=href, locale=locale_en, lc_time=lc_time, tz=tz)
            chrome.add_jquery_ui(req)
            data = req.chrome['script_data']['jquery_ui']
            self.assertEqual(tz_default, data['default_timezone'])
            if tz_default is None:
                self.assertIsNone(data['timezone_list'])
            else:
                self.assertIn({'value': tz_default, 'label': tz_label},
                              data['timezone_list'])

        verify_tzprops('iso8601', utc, 0, '+00:00')
        verify_tzprops(locale_en, utc, None, None)
        verify_tzprops('iso8601', gmt07b, -420, '-07:00')
        verify_tzprops(locale_en, gmt07b, None, None)
        verify_tzprops('iso8601', gmt04a, 240, '+04:00')
        verify_tzprops(locale_en, gmt04a, None, None)
        if pytz:
            # must use timezones which does not use DST
            guam = timezone('Pacific/Guam')
            monrovia = timezone('Africa/Monrovia')
            panama = timezone('America/Panama')
            verify_tzprops('iso8601', guam, 600, '+10:00')
            verify_tzprops(locale_en, guam, None, None)
            verify_tzprops('iso8601', monrovia, 0, '+00:00')
            verify_tzprops(locale_en, monrovia, None, None)
            verify_tzprops('iso8601', panama, -300, '-05:00')
            verify_tzprops(locale_en, panama, None, None)

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

    def test_cc_list(self):
        """Split delimited string to a list of email addresses."""
        chrome = Chrome(self.env)
        cc_field1 = 'user1@abc.com,user2@abc.com, user3@abc.com'
        cc_field2 = 'user1@abc.com;user2@abc.com; user3@abc.com'
        expected = ['user1@abc.com', 'user2@abc.com', 'user3@abc.com']
        self.assertEqual(expected, chrome.cc_list(cc_field1))
        self.assertEqual(expected, chrome.cc_list(cc_field2))

    def test_cc_list_is_empty(self):
        """Empty list is returned when input is `None` or empty."""
        chrome = Chrome(self.env)
        self.assertEqual([], chrome.cc_list(None))
        self.assertEqual([], chrome.cc_list(''))
        self.assertEqual([], chrome.cc_list([]))


class ChromeTestCase2(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(path=tempfile.mkdtemp())
        self.chrome = Chrome(self.env)

    def tearDown(self):
        self.env.reset_db_and_disk()

    def test_permission_requestor(self):
        self.assertIn('EMAIL_VIEW', PermissionSystem(self.env).get_actions())

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


class NavigationOrderTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.env.clear_component_registry()
        self.req = Request(abs_href=Href('http://example.org/trac.cgi'),
                           href=Href('/trac.cgi'), base_path='/trac.cgi',
                           path_info='/',
                           add_redirect_listener=lambda listener: None)
        self.chrome = Chrome(self.env)

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

    def tearDown(self):
        self.env.restore_component_registry()

    def test_explicit_ordering(self):
        """Ordering is explicitly specified."""
        self.env.config.set('metanav', 'test1.order', 2)
        self.env.config.set('metanav', 'test2.order', 1)
        items = self.chrome.prepare_request(self.req)['nav']['metanav']
        self.assertEqual('test2', items[0]['name'])
        self.assertEqual('test1', items[1]['name'])

    def test_partial_explicit_ordering_1(self):
        """Ordering for one item is explicitly specified."""
        self.env.config.set('metanav', 'test1.order', 1)
        items = self.chrome.prepare_request(self.req)['nav']['metanav']
        self.assertEqual('test1', items[0]['name'])
        self.assertEqual('test2', items[1]['name'])

    def test_partial_explicit_ordering_2(self):
        """Ordering for one item is explicitly specified."""
        self.env.config.set('metanav', 'test2.order', 1)
        items = self.chrome.prepare_request(self.req)['nav']['metanav']
        self.assertEqual('test2', items[0]['name'])
        self.assertEqual('test1', items[1]['name'])

    def test_implicit_ordering(self):
        """When not specified, ordering is alphabetical."""
        self.env.config.set('metanav', 'foo.order', 1)
        self.env.config.set('metanav', 'bar.order', 2)

        items = self.chrome.prepare_request(self.req)['nav']['metanav']
        self.assertEqual('test1', items[0]['name'])
        self.assertEqual('test2', items[1]['name'])


class FormatAuthorTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=['trac.web.chrome.*',
                                           'trac.perm.*',
                                           'tracopt.perm.authz_policy'])
        self.env.config.set('trac', 'permission_policies',
                            'AuthzPolicy, DefaultPermissionPolicy')
        fd, self.authz_file = tempfile.mkstemp()
        with os.fdopen(fd, 'w') as f:
            f.write("""\
[wiki:WikiStart]
user2 = EMAIL_VIEW
[wiki:TracGuide]
user2 =
""")
        PermissionSystem(self.env).grant_permission('user1', 'EMAIL_VIEW')
        self.env.config.set('authz_policy', 'authz_file', self.authz_file)

    def tearDown(self):
        os.remove(self.authz_file)

    def test_subject_is_anonymous(self):
        format_author = Chrome(self.env).format_author
        self.assertEqual('anonymous', format_author(None, 'anonymous'))

    def test_subject_is_none(self):
        format_author = Chrome(self.env).format_author
        self.assertEqual('(none)', format_author(None, None))

    def test_actor_has_email_view(self):
        req = MockRequest(self.env, authname='user1')
        author = Chrome(self.env).format_author(req, 'user@domain.com')
        self.assertEqual('user@domain.com', author)

    def test_actor_no_email_view(self):
        req = MockRequest(self.env, authname='user2')
        author = Chrome(self.env).format_author(req, 'user@domain.com')
        self.assertEqual(u'user@\u2026', author)

    def test_actor_no_email_view_show_email_addresses(self):
        self.env.config.set('trac', 'show_email_addresses', True)
        req = MockRequest(self.env, authname='user2')
        author = Chrome(self.env).format_author(req, 'user@domain.com')
        self.assertEqual('user@domain.com', author)

    def test_actor_no_email_view_no_req(self):
        author = Chrome(self.env).format_author(None, 'user@domain.com')
        self.assertEqual(u'user@\u2026', author)

    def test_actor_has_email_view_for_resource(self):
        format_author = Chrome(self.env).format_author
        req = MockRequest(self.env, authname='user2')
        resource = Resource('wiki', 'WikiStart')
        author = format_author(req, 'user@domain.com', resource)
        self.assertEqual('user@domain.com', author)

    def test_actor_has_email_view_for_resource_negative(self):
        format_author = Chrome(self.env).format_author
        req = MockRequest(self.env, authname='user2')
        resource = Resource('wiki', 'TracGuide')
        author = format_author(req, 'user@domain.com', resource)
        self.assertEqual(u'user@\u2026', author)

    def test_show_full_names_true(self):
        format_author = Chrome(self.env).format_author
        self.env.config.set('trac', 'show_full_names', True)
        self.env.insert_users([
            ('user1', 'User One', 'user1@example.org'),
            ('user2', None, None)
        ])

        self.assertEqual('User One', format_author(None, 'user1'))
        self.assertEqual('user2', format_author(None, 'user2'))

    def test_show_full_names_false(self):
        format_author = Chrome(self.env).format_author
        self.env.config.set('trac', 'show_full_names', False)

        self.assertEqual('user1', format_author(None, 'user1'))
        self.assertEqual('user2', format_author(None, 'user2'))

    def test_show_email_true(self):
        format_author = Chrome(self.env).format_author
        req = MockRequest(self.env, authname='user2')

        author = format_author(None, 'user@domain.com', show_email=True)
        self.assertEqual('user@domain.com', author)
        author = format_author(req, 'user@domain.com', show_email=True)
        self.assertEqual('user@domain.com', author)

    def test_show_email_false(self):
        format_author = Chrome(self.env).format_author
        req = MockRequest(self.env, authname='user1')

        author = format_author(None, 'user@domain.com', show_email=False)
        self.assertEqual(u'user@\u2026', author)
        author = format_author(req, 'user@domain.com', show_email=False)
        self.assertEqual(u'user@\u2026', author)

    def test_show_full_names_true_actor_has_email_view(self):
        format_author = Chrome(self.env).format_author
        self.env.config.set('trac', 'show_full_names', True)
        self.env.insert_users([
            ('user1', 'User One', 'user1@example.org'),
            ('user2', None, None)
        ])

        self.assertEqual('User One', format_author(None, 'user1'))
        self.assertEqual('user2', format_author(None, 'user2'))

    def test_show_full_names_false_actor_has_email_view(self):
        req = MockRequest(self.env, authname='user1')
        format_author = Chrome(self.env).format_author
        self.env.config.set('trac', 'show_full_names', False)

        self.assertEqual('user1', format_author(req, 'user1'))
        self.assertEqual('user2', format_author(req, 'user2'))

    def test_show_email_addresses_true(self):
        format_author = Chrome(self.env).format_author
        self.env.config.set('trac', 'show_email_addresses', True)

        self.assertEqual('user3@example.org',
                         format_author(None, 'user3@example.org'))
        self.assertEqual('user3@example.org',
                         format_author(Request(), 'user3@example.org'))

    def test_show_email_addresses_false(self):
        format_author = Chrome(self.env).format_author
        self.env.config.set('trac', 'show_email_addresses', False)

        self.assertEqual(u'user3@\u2026',
                         format_author(None, 'user3@example.org'))
        self.assertEqual('user3@example.org',
                         format_author(Request(), 'user3@example.org'))

    def test_format_emails(self):
        format_emails = Chrome(self.env).format_emails
        to_format = 'user1@example.org, user2; user3@example.org'

        self.assertEqual(u'user1@\u2026, user2, user3@\u2026',
                         format_emails(None, to_format))

    def test_format_emails_actor_has_email_view(self):
        req = MockRequest(self.env, authname='user1')
        context = web_context(req)
        format_emails = Chrome(self.env).format_emails
        to_format = 'user1@example.org, user2; user3@example.org'

        self.assertEqual('user1@example.org, user2, user3@example.org',
                         format_emails(context, to_format))

    def test_format_emails_actor_no_email_view(self):
        req = MockRequest(self.env, authname='user2')
        context = web_context(req)
        format_emails = Chrome(self.env).format_emails
        to_format = 'user1@example.org, user2; user3@example.org'

        self.assertEqual(u'user1@\u2026, user2, user3@\u2026',
                         format_emails(context, to_format))


class AuthorInfoTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=['trac.web.chrome.*',
                                           'trac.perm.*',
                                           'tracopt.perm.authz_policy'])
        self.env.config.set('trac', 'permission_policies',
                            'AuthzPolicy, DefaultPermissionPolicy')
        fd, self.authz_file = tempfile.mkstemp()
        with os.fdopen(fd, 'w') as f:
            f.write("""\
[wiki:WikiStart]
user2 = EMAIL_VIEW
[wiki:TracGuide]
user2 =
""")
        PermissionSystem(self.env).grant_permission('user1', 'EMAIL_VIEW')
        self.env.config.set('authz_policy', 'authz_file', self.authz_file)

    def tearDown(self):
        os.remove(self.authz_file)

    def test_subject_is_anonymous(self):
        chrome = Chrome(self.env)
        req = Request()
        self.assertEqual('<span class="trac-author-anonymous">anonymous</span>',
                         str(chrome.authorinfo(req, 'anonymous')))
        self.assertEqual('<span class="trac-author-anonymous">anonymous</span>',
                         str(chrome.authorinfo_short('anonymous')))

    def test_subject_is_none(self):
        chrome = Chrome(self.env)
        req = Request(authname=None)
        self.assertEqual('<span class="trac-author">(none)</span>',
                         str(chrome.authorinfo(req, '(none)')))
        self.assertEqual('<span class="trac-author-none">(none)</span>',
                         str(chrome.authorinfo(req, None)))
        self.assertEqual('<span class="trac-author-none">(none)</span>',
                         str(chrome.authorinfo(req, '')))
        self.assertEqual('<span class="trac-author">(none)</span>',
                         str(chrome.authorinfo_short('(none)')))
        self.assertEqual('<span class="trac-author-none">(none)</span>',
                         str(chrome.authorinfo_short(None)))
        self.assertEqual('<span class="trac-author-none">(none)</span>',
                         str(chrome.authorinfo_short('')))

    def test_actor_has_email_view(self):
        chrome = Chrome(self.env)
        req = MockRequest(self.env, authname='user1')
        self.assertEqual('<span class="trac-author">user@domain.com</span>',
                         unicode(chrome.authorinfo(req, 'user@domain.com')))
        self.assertEqual('<span class="trac-author">User One &lt;user@example.org&gt;</span>',
                         unicode(chrome.authorinfo(req, 'User One <user@example.org>')))
        self.assertEqual('<span class="trac-author">user</span>',
                         str(chrome.authorinfo_short('User One <user@example.org>')))
        self.assertEqual('<span class="trac-author">user</span>',
                         str(chrome.authorinfo_short('user@example.org')))

    def test_actor_no_email_view(self):
        req = MockRequest(self.env, authname='user2')
        authorinfo = Chrome(self.env).authorinfo
        self.assertEqual(u'<span class="trac-author">user@\u2026</span>',
                         unicode(authorinfo(req, 'user@domain.com')))
        self.assertEqual(u'<span class="trac-author">User One &lt;user@\u2026&gt;</span>',
                         unicode(authorinfo(req, 'User One <user@domain.com>')))

    def test_actor_no_email_view_show_email_addresses(self):
        self.env.config.set('trac', 'show_email_addresses', True)
        req = MockRequest(self.env, authname='user2')
        authorinfo = Chrome(self.env).authorinfo
        self.assertEqual('<span class="trac-author">user@domain.com</span>',
                         unicode(authorinfo(req, 'user@domain.com')))
        self.assertEqual('<span class="trac-author">User One &lt;user@domain.com&gt;</span>',
                         unicode(authorinfo(req, 'User One <user@domain.com>')))

    def test_actor_no_email_view_no_req(self):
        authorinfo = Chrome(self.env).authorinfo
        self.assertEqual(u'<span class="trac-author">user@\u2026</span>',
                         unicode(authorinfo(None, 'user@domain.com')))
        self.assertEqual(u'<span class="trac-author">User One &lt;user@\u2026&gt;</span>',
                         unicode(authorinfo(None, 'User One <user@domain.com>')))

    def test_actor_has_email_view_for_resource(self):
        authorinfo = Chrome(self.env).authorinfo
        authorinfo_short = Chrome(self.env).authorinfo_short
        req = MockRequest(self.env, authname='user2')
        resource = Resource('wiki', 'WikiStart')
        authorinfo = authorinfo(req, 'user@domain.com', resource=resource)
        author_short = authorinfo_short('user@domain.com')
        self.assertEqual(u'<span class="trac-author">user@domain.com</span>',
                         unicode(authorinfo))
        self.assertEqual(u'<span class="trac-author">user</span>',
                         unicode(author_short))

    def test_actor_has_email_view_for_resource_negative(self):
        authorinfo = Chrome(self.env).authorinfo
        authorinfo_short = Chrome(self.env).authorinfo_short
        req = MockRequest(self.env, authname='user2')
        resource = Resource('wiki', 'TracGuide')
        author = authorinfo(req,  'user@domain.com', resource=resource)
        author_short = authorinfo_short('user@domain.com')
        self.assertEqual(u'<span class="trac-author">user@\u2026</span>',
                         unicode(author))
        self.assertEqual(u'<span class="trac-author">user</span>',
                         unicode(author_short))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ChromeTestCase))
    suite.addTest(unittest.makeSuite(ChromeTestCase2))
    suite.addTest(unittest.makeSuite(NavigationOrderTestCase))
    suite.addTest(unittest.makeSuite(FormatAuthorTestCase))
    suite.addTest(unittest.makeSuite(AuthorInfoTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
