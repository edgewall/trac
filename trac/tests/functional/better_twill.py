# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2020 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

"""better_twill is a small wrapper around twill to set some sane defaults and
monkey-patch some better versions of some of twill's methods.
It also handles twill's absense.
"""

import hashlib
import http.client
import http.server
import re
import os.path
import socketserver
import sys
import tempfile
import threading
from urllib.parse import urljoin
from urllib.request import HTTPBasicAuthHandler, Request, build_opener, \
                           pathname2url

from trac.test import mkdtemp, rmtree

try:
    import selenium
except ImportError:
    selenium = None

try:
    from tidylib import tidy_document
    tidy_document('<!DOCTYPE html><html><body></body></html>')
except ImportError:
    print("SKIP: validation of HTML output in functional tests"
          " (no tidylib installed)")
    tidy_document = None
except OSError as e:
    print("SKIP: validation of HTML output in functional tests"
          " (no tidy dynamic library installed: %s)" % e)
    tidy_document = None


if selenium:
    from selenium import webdriver
    from selenium.common.exceptions import (
        NoSuchElementException, WebDriverException as ConnectError)
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions
    from selenium.webdriver.support.ui import WebDriverWait

    # setup short names to reduce typing
    # This selenium browser (and the tc commands that use it) are essentially
    # global, and not tied to our test fixture.

    class Proxy(object):

        tmpdir = None
        proxy_server = None
        proxy_thread = None
        driver = None
        auth_handler = None
        keys = Keys

        def init(self, port, proxy_port):
            self.tmpdir = mkdtemp()
            self.proxy_server = self._create_proxy_server(port, proxy_port)
            self.proxy_thread = self._create_proxy_thread(self.proxy_server)
            self.driver = self._create_webdriver()
            self.driver.maximize_window()

        def _create_proxy_server(self, port, proxy_port):
            dir_ = os.path.join(self.tmpdir, 'response')
            os.mkdir(dir_)
            server = ReverseProxyServer(('127.0.0.1', port),
                                        ReverseProxyRequestHandler,
                                        proxy_port=proxy_port,
                                        response_dir=dir_)
            return server

        def _create_proxy_thread(self, server):
            def target():
                server.serve_forever()
            t = threading.Thread(target=target, daemon=True)
            t.start()
            return t

        def _create_webdriver(self):
            if os.name == 'posix':
                mime_types = os.path.join(tempfile.mkdtemp(dir=self.tmpdir),
                                          'mime.types')
                with open(mime_types, 'w', encoding='utf-8') as f:
                    f.write('multipart/related mht\n')
            else:
                mime_types = None
            profile = webdriver.FirefoxProfile()
            profile.set_preference('intl.accept_languages', 'en-us')
            profile.set_preference('network.http.phishy-userpass-length', 255)
            profile.set_preference('general.warnOnAboutConfig', False)
            if mime_types:
                profile.set_preference('helpers.private_mime_types_file',
                                       mime_types)
            options = webdriver.FirefoxOptions()
            options.profile = profile
            options.add_argument('--headless')
            options.log.level = 'debug'
            log_path = 'geckodriver.log'
            open(log_path, 'w').close()
            return webdriver.Firefox(options=options,
                                     service_log_path=log_path)

        def close(self):
            if self.tmpdir:
                rmtree(self.tmpdir)
                self.tmpdir = None
            if self.driver:
                self.driver.quit()
                self.driver = None
            if self.proxy_server:
                self.proxy_server.shutdown()
                self.proxy_server.server_close()
                self.proxy_server = None
            if self.proxy_thread:
                self.proxy_thread.join()
                self.proxy_thread = None

        def go(self, url):
            url = self._urljoin(url)
            self.driver.get(url)
            self._validate_html(self.get_source())

        def back(self):
            self.driver.back()

        def click(self, *args, **kwargs):
            self._find_by(*args, **kwargs).click()

        def reload(self):
            self.driver.refresh()
            self._validate_html(self.get_source())

        def download(self, url):
            cookie = '; '.join('%s=%s' % (c['name'], c['value'])
                               for c in self.get_cookies())
            url = self._urljoin(url)
            handlers = []
            if self.auth_handler:
                handlers.append(self.auth_handler)
            opener = build_opener(*handlers)
            req = Request(url, headers={'Cookie': cookie})
            with opener.open(req) as resp:
                return resp.getcode(), resp.read()

        _normurl_re = re.compile(r'[a-z]+://[^:/]+:?[0-9]*$')

        def url(self, url, regexp=True):
            current_url = self.get_url()
            if regexp:
                if not re.match(url, current_url):
                    raise AssertionError("URL didn't match: {!r} not matched "
                                         "in {!r}".format(url, current_url))
            else:
                if self._normurl_re.match(url):
                    url += '/'
                if url != current_url:
                    raise AssertionError("URL didn't equal: {!r} != {!r}"
                                         .format(url, current_url))

        def notfind(self, s, flags=None):
            source = self.get_source()
            match = re.search(self._to_bytes(s), source, self._re_flags(flags))
            if match:
                url = self.write_source(source)
                raise AssertionError('Regex matched: {!r} matches {!r} in {}'
                                     .format(source[match.start():match.end()],
                                             s, url))

        def find(self, s, flags=None):
            source = self.get_source()
            if not re.search(self._to_bytes(s), source, self._re_flags(flags)):
                url = self.write_source(source)
                raise AssertionError("Regex didn't match: {!r} not found in {}"
                                     .format(s, url))

        def add_auth(self, x, url, username, password):
            handler = HTTPBasicAuthHandler()
            handler.add_password(x, url, username, password)
            self.auth_handler = handler

        def follow(self, s):
            self._find_link(s).click()
            self._validate_html(self.get_source())

        def download_link(self, pattern):
            element = self._find_link(pattern)
            href = element.get_attribute('href')
            return self.download(href)

        def formvalue(self, form, field, value):
            form_element = self._find_by(id=form)
            elements = form_element.find_elements_by_css_selector(
                                    '[name="{0}"], [id="{0}"]'.format(field))
            for element in elements:
                tag = element.tag_name
                if tag == 'input':
                    type_ = element.get_attribute('type')
                    if type_  in ('text', 'password', 'file'):
                        element.clear()
                        element.send_keys(value)
                        return
                    if type_ == 'checkbox':
                        if isinstance(value, str):
                            v = value[1:] \
                                if value.startswith(('+', '-')) else value
                            if element.get_attribute('value') != v:
                                continue
                            checked = not value.startswith('-')
                        elif value in (True, False):
                            checked = value
                        else:
                            raise ValueError('Unrecognized value for '
                                             'checkbox: %s' % repr(value))
                        element.click()  # to focus
                        if element.is_selected() != checked:
                            element.click()
                        return
                    if type_ == 'radio':
                        if element.get_attribute('value') == value:
                            element.click()
                            return
                if tag == 'textarea':
                    element.clear()
                    element.send_keys(value)
                    return
                if tag == 'select':
                    for option in element.find_elements_by_tag_name('option'):
                        if value == option.get_attribute('value') or \
                                value == option.get_property('textContent'):
                            option.click()
                            element.click()  # to focus the select element
                            return
                    else:
                        url = self.write_source()
                        raise ValueError('Missing option[value=%r] in %s' %
                                         (value, url))
            else:
                url = self.write_source()
                raise ValueError('Unable to find element matched with '
                                 '`formvalue(%r, %r, %r)` in %s' %
                                 (form, field, value, url))

        fv = formvalue

        def formfile(self, formname, fieldname, filename, content_type=None,
                     fp=None):
            if fp:
                phypath = os.path.join(tempfile.mkdtemp(dir=self.tmpdir),
                                       filename)
                with open(phypath, 'wb') as f:
                    f.write(fp.read())
            else:
                phypath = os.path.abspath(filename)

            form = self._find_form(formname)
            enctype = form.get_attribute('enctype')
            if enctype != 'multipart/form-data':
                url = self.write_source()
                raise ValueError('enctype should be multipart/form-data: %r '
                                 'in %s' % (enctype, url))
            field = self._find_field(fieldname, formname)
            type_ = field.get_attribute('type')
            if type_ != 'file':
                url = self.write_source()
                raise ValueError('type should be file: %r in %s' %
                                 (type_, url))
            field.send_keys(phypath)

        def javascript_disabled(self, fn):
            def wrapper(*args, **kwargs):
                prev = self.set_prefs({'javascript.enabled': False})
                try:
                    return fn(*args, **kwargs)
                finally:
                    if prev is not None:
                        self.set_prefs(prev)
            return wrapper

        def prefs(self, values):
            def decorator(fn):
                def wrapper(*args, **kwargs):
                    prev = self.set_prefs(values)
                    try:
                        return fn(*args, **kwargs)
                    finally:
                        if prev is not None:
                            self.set_prefs(prev)
                return wrapper
            return decorator

        def set_prefs(self, values):
            driver = self.driver
            driver.get('about:config')
            prev = driver.execute_script("""\
                var prefs = Components.classes
                            ["@mozilla.org/preferences-service;1"]
                            .getService(Components.interfaces.nsIPrefBranch);
                var values = arguments[0];
                var prev = {};
                var key, value;
                for (key in values) {
                    switch (prefs.getPrefType(key)) {
                    case 32:
                        value = prefs.getCharPref(key);
                        break;
                    case 64:
                        value = prefs.getIntPref(key);
                        break;
                    case 128:
                        value = prefs.getBoolPref(key);
                        break;
                    default:
                        continue;
                    }
                    prev[key] = value;
                }
                for (key in values) {
                    value = values[key];
                    switch (typeof value) {
                    case 'string':
                        prefs.setCharPref(key, value);
                        break;
                    case 'number':
                        prefs.setIntPref(key, value);
                        break;
                    case 'boolean':
                        prefs.setBoolPref(key, value);
                        break;
                    }
                }
                return prev;
            """, values)
            return prev

        def submit(self, fieldname=None, formname=None):
            element = self._find_field(fieldname, formname)
            if element.get_attribute('type') == 'submit':
                if not element.is_enabled():
                    raise ValueError('Unable to click disabled submit element')
            else:
                if element.tag_name != 'form':
                    element = element.get_property('form')
                    if element is None:
                        url = self.write_source()
                        raise ValueError('No form property in %s' % url)
                for element in element.find_elements_by_css_selector(
                        '[type="submit"]'):
                    if element.is_enabled():
                        break
                else:
                    url = self.write_source()
                    raise ValueError('No active submit elements in %s' % url)
            element.click()
            self._validate_html(self.get_source())

        def move_to(self, *args, **kwargs):
            element = self._find_by(*args, **kwargs)
            ActionChains(self.driver).move_to_element(element).perform()

        def send_keys(self, *args):
            chains = ActionChains(self.driver)
            for arg in args:
                chains.send_keys(arg)
            chains.perform()

        def wait_for(self, condition, *args, **kwargs):
            element = self._find_by(*args, **kwargs)
            method = getattr(expected_conditions, condition)
            WebDriverWait(tc.driver, 2).until(method(element))

        def _find_form(self, id_):
            selector = 'form[id="%(name)s"]' % {'name': id_}
            return self._find_by(selector)

        def _find_field(self, field=None, form=None):
            if field is form is None:
                return self.driver.switch_to.active_element
            node = self.driver
            try:
                if form:
                    node = node.find_element_by_css_selector(
                        'form[id="{0}"], form[name="{0}"]'.format(form))
                if field:
                    node = node.find_element_by_css_selector(
                        '[id="{0}"], [name="{0}"], '
                        '[type="submit"][value="{0}"]'.format(field))
                return node
            except NoSuchElementException as e:
                url = self.write_source()
                raise AssertionError('Missing field (%r, %r) in %s' %
                                     (field, form, url)) from e

        def _find_by(self, *args, **kwargs):
            driver = self.driver
            try:
                if kwargs.get('id'):
                    return driver.find_element_by_id(kwargs['id'])
                if kwargs.get('name'):
                    return driver.find_element_by_name(kwargs['name'])
                if kwargs.get('class_'):
                    return driver.find_element_by_class_name(kwargs['class_'])
                if len(args) == 1:
                    return driver.find_element_by_css_selector(args[0])
                if len(args) == 0:
                    return driver.switch_to.active_element
            except NoSuchElementException as e:
                url = self.write_source()
                raise AssertionError('Missing element (%r, %r) in %s' %
                                     (args, kwargs, url)) from e
            raise ValueError('Invalid arguments: %r %r' % (args, kwargs))

        def _find_link(self, pattern):
            def get_href(element):
                # Retrieve raw href attribute via javascript because
                # WebElement.get_attribute('href') returns absolute URL
                script = "return arguments[0].getAttribute('href');"
                return element.parent.execute_script(script, element)
            re_pattern = re.compile(pattern)
            search = lambda text: text and re_pattern.search(text)
            for element in self.driver.find_elements_by_tag_name('a'):
                if search(element.get_property('textContent')) or \
                        search(get_href(element)):
                    return element
            else:
                url = self.write_source(self.get_source())
                raise AssertionError('Missing link %r in %s' % (pattern, url))

        _re_flag_bits = {'i': re.IGNORECASE, 'm': re.MULTILINE, 's': re.DOTALL}

        def _re_flags(self, flags):
            bit = 0
            if flags is not None:
                for flag in flags:
                    try:
                        value = self._re_flag_bits[flag]
                    except IndexError:
                        raise ValueError('Invalid flags %r' % flags)
                    else:
                        bit |= value
            return bit

        def _to_bytes(self, value):
            if isinstance(value, str):
                value = value.encode('utf-8')
            return value

        def _urljoin(self, url):
            if '://' not in url:
                url = urljoin(self.get_url(), url)
            return url

        _tidy_options = {
            'escape-scripts': 0,
            'drop-empty-elements': 0,
        }

        _doctype_re = re.compile(r'\s*<!DOCTYPE\b'.encode('ascii'))

        def _validate_html(self, source):
            if not tidy_document:
                return
            if not self._doctype_re.match(source):
                return
            corrected, errors = tidy_document(source, self._tidy_options)
            if errors:
                errors = errors.splitlines()
                url = self.write_source(source)
                raise AssertionError('tidylib found %d error(s) in %s\n\n%s' %
                                     (len(errors), url, '\n'.join(errors)))

        # When we can't find something we expected, or find something we didn't
        # expect, it helps the debugging effort to have a copy of the html to
        # analyze.
        def write_source(self, source=None):
            """Write the current html to a file. Name the file based on the
            current testcase.
            """
            import unittest

            frame = sys._getframe()
            while frame:
                if frame.f_code.co_name in ('runTest', 'setUp', 'tearDown'):
                    testcase = frame.f_locals['self']
                    testname = testcase.__class__.__name__
                    tracdir = testcase._testenv.tracdir
                    break
                elif isinstance(frame.f_locals.get('self'), unittest.TestCase):
                    testcase = frame.f_locals['self']
                    testname = '%s.%s' % (testcase.__class__.__name__,
                                          testcase._testMethodName)
                    tracdir = testcase._testenv.tracdir
                    break
                frame = frame.f_back
            else:
                # We didn't find a testcase in the stack, so we have no clue
                # what's going on.
                raise Exception("No testcase was found on the stack. This was "
                                "really not expected, and I don't know how to "
                                "handle it.")

            if source is None:
                source = self.get_source()
            filename = os.path.join(tracdir, 'log', '%s.html' % testname)
            try:
                if isinstance(source, bytes):
                    html_file = open(filename, 'wb')
                else:
                    html_file = open(filename, 'w', encoding='utf-8')
                html_file.write(source)
            finally:
                html_file.close()

            return urljoin('file:', pathname2url(filename))

        def get_cookies(self):
            return iter(self.driver.get_cookies())

        def get_url(self):
            return self.driver.current_url

        _request_re = re.compile(r'http://[^/]+(/[^#]*)(?:#.*)?\Z')

        def get_source(self):
            path = self._request_re.match(self.get_url()).group(1)
            return self.proxy_server.get_response(path)

        get_html = get_source

else:
    class ConnectError(Exception): pass

    class Proxy(object):

        def javascript_disabled(self, fn):
            def wrapper(*args, **kwargs):
                return fn(*args, **kwargs)
            return wrapper

        def prefs(self, values):
            def decorator(fn):
                def wrapper(*args, **kwargs):
                    return fn(*args, **kwargs)
                return wrapper
            return decorator


b = tc = Proxy()


# The server saves raw response body. It unable to use `Firefox.page_source`
# attribute in `find()` and `notfind()` because the attribute returns html
# generated from DOM structure in Firefox. E.g. "<input ... />".
class ReverseProxyServer(socketserver.ThreadingMixIn, http.server.HTTPServer):

    proxy_port = None
    response_dir = None

    def __init__(self, *args, **kwargs):
        self.proxy_port = kwargs.pop('proxy_port')
        self.response_dir = kwargs.pop('response_dir')
        super(ReverseProxyServer, self).__init__(*args, **kwargs)

    def get_response(self, path):
        filename = self._response_path(path)
        with open(filename, 'rb') as f:
            return f.read()

    def save_response(self, path, body):
        filename = self._response_path(path)
        if isinstance(body, bytes):
            body = [body]
        with open(filename, 'wb') as f:
            for chunk in body:
                f.write(chunk)

    def _response_path(self, path):
        key = hashlib.sha1(path.encode('utf-8')).hexdigest()
        return os.path.join(self.response_dir, key)


class ReverseProxyRequestHandler(http.server.BaseHTTPRequestHandler):

    def _do(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.proxy_port)
        try:
            conn.connect()
            conn.putrequest(self.command, self.path, skip_host=True,
                            skip_accept_encoding=True)
            for name, value in self.headers.raw_items():
                conn.putheader(name, value)
            length = int(self.headers.get('content-length') or 0)
            conn.endheaders(self.rfile.read(length) if length > 0 else b'')
            resp = conn.getresponse()
            resp_body = []
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                resp_body.append(chunk)
            self.server.save_response(self.path, resp_body)
            self.send_response(resp.status, resp.reason)
            for name, value in resp.getheaders():
                self.send_header(name, value)
            self.end_headers()
            if resp.chunked:
                for chunk in resp_body:
                    self.wfile.write(b'%x\r\n%s\r\n' % (len(chunk), chunk))
                self.wfile.write(b'0\r\n\r\n')
            else:
                for chunk in resp_body:
                    self.wfile.write(chunk)
        except OSError:
            self.server.save_response(self.path, b'')
        finally:
            conn.close()

    do_HEAD = do_GET = do_POST = _do

    def log_message(self, format, *args):
        pass
