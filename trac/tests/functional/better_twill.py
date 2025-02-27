# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2023 Edgewall Software
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
It also handles twill's absence.
"""

import contextlib
import hashlib
import http.client
import http.server
import inspect
import locale
import re
import os.path
import socketserver
import sys
import tempfile
import time
import threading
from urllib.parse import urljoin
from urllib.request import HTTPBasicAuthHandler, Request, build_opener, \
                           pathname2url

from trac.test import mkdtemp, rmtree

try:
    import selenium
except ImportError:
    selenium = None


_tidy_options = {
    'escape-scripts': 0,
    'drop-empty-elements': 0,
}
_curr = locale.setlocale(locale.LC_ALL, None)
try:
    import tidylib
    tidylib.tidy_document('<!DOCTYPE html><html><body></body></html>',
                          _tidy_options)
except ImportError:
    print("SKIP: validation of HTML output in functional tests"
          " (no tidylib installed)")
    tidy_document = None
except OSError as e:
    print("SKIP: validation of HTML output in functional tests"
          " (no tidy dynamic library installed: %s)" % e)
    tidy_document = None
except ValueError as e:
    print("SKIP: validation of HTML output in functional tests (%r)" % e)
    tidy_document = None
else:
    if _curr == locale.setlocale(locale.LC_ALL, None):
        tidy_document = tidylib.tidy_document
    else:
        def tidy_document(*args, **kwargs):
            curr = locale.setlocale(locale.LC_ALL, None)
            try:
                return tidylib.tidy_document(*args, **kwargs)
            finally:
                # Restore the locale because tidy-html5 library changes the
                # locale each call of tidy_document if 5.6.0 or early.
                locale.setlocale(locale.LC_ALL, curr)
finally:
    if _curr != locale.setlocale(locale.LC_ALL, None):
        locale.setlocale(locale.LC_ALL, _curr)
    del _curr


def _has_arg(f, name):
    return name in inspect.signature(f).parameters


if selenium:
    from selenium import webdriver
    from selenium.common.exceptions import (NoSuchElementException,
                                            TimeoutException,
                                            WebDriverException as ConnectError)
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.by import By
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
        _javascript_enabled = True

        def init(self, port, proxy_port):
            self.tmpdir = mkdtemp()
            self.proxy_server = self._create_proxy_server(port, proxy_port)
            self.proxy_thread = self._create_proxy_thread(self.proxy_server)
            self.driver = self._create_webdriver()

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
            options = webdriver.FirefoxOptions()
            options.set_preference('intl.accept_languages', 'en-us')
            options.set_preference('network.http.phishy-userpass-length', 255)
            options.set_preference('general.warnOnAboutConfig', False)
            if mime_types:
                options.set_preference('helpers.private_mime_types_file',
                                       mime_types)
            options.add_argument('-headless')
            options.add_argument('--width=1280')
            options.add_argument('--height=2048')
            options.log.level = 'info'
            log_path = 'geckodriver.log'
            open(log_path, 'wb').close()

            if _has_arg(webdriver.Firefox, 'service'):
                if hasattr(webdriver, 'FirefoxService'):
                    FirefoxService = webdriver.FirefoxService
                else:
                    FirefoxService = webdriver.firefox.service.Service
                if _has_arg(FirefoxService, 'log_output'):
                    service = FirefoxService(log_output=log_path)
                else:
                    service = FirefoxService(log_path=log_path)
                def launch():
                    return webdriver.Firefox(options=options, service=service)
            else:
                service = None
                def launch():
                    return webdriver.Firefox(options=options,
                                             service_log_path=log_path)

            n = 1
            while True:
                try:
                    return launch()
                except TimeoutException:
                    if n >= 20:
                        raise
                    n += 1
                    time.sleep(3)

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
            with self._wait_for_page_load():
                self.driver.get(url)
            self._validate_html(self.get_source())

        def back(self):
            self.driver.back()

        def click(self, *args, **kwargs):
            self._find_by(*args, **kwargs).click()

        def reload(self):
            with self._wait_for_page_load():
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
            with self._wait_for_page_load():
                self._find_link(s).click()
            self._validate_html(self.get_source())

        def download_link(self, pattern):
            element = self._find_link(pattern)
            href = element.get_attribute('href')
            return self.download(href)

        def formvalue(self, form, field, value):
            form_element = self._find_by(id=form)
            selector = '[name="{0}"], [id="{0}"]'.format(field)
            elements = form_element.find_elements(by=By.CSS_SELECTOR,
                                                  value=selector)
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
                    for option in element.find_elements(by=By.CSS_SELECTOR,
                                                        value='option'):
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

        def toggle_foldable(self, *args, **kwargs):
            foldable = self._find_by(*args, **kwargs)
            method = lambda: foldable.find_element(by=By.CSS_SELECTOR,
                                                   value='a')
            anchor = self.wait_for(method, timeout=2)
            anchor.click()

        def javascript_disabled(self, fn):
            def wrapper(*args, **kwargs):
                prev_js = self._javascript_enabled
                prev_prefs = self.set_prefs({'javascript.enabled': False})
                self._javascript_enabled = False
                try:
                    return fn(*args, **kwargs)
                finally:
                    self._javascript_enabled = prev_js
                    if prev_prefs is not None:
                        self.set_prefs(prev_prefs)
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
                for element in element.find_elements(by=By.CSS_SELECTOR,
                                                     value='[type="submit"]'):
                    if element.is_enabled():
                        break
                else:
                    url = self.write_source()
                    raise ValueError('No active submit elements in %s' % url)
            with self._wait_for_page_load():
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

        def wait_for(self, condition, *args, timeout=2, **kwargs):
            if isinstance(condition, str):
                locator = self._get_locator(*args, **kwargs)
                method = getattr(expected_conditions, condition)(locator)
            else:
                method = lambda driver: condition(*args, **kwargs)
            wait = WebDriverWait(self.driver, timeout)
            try:
                return wait.until(method)
            except TimeoutException as e:
                raise AssertionError('Timed out in %s' %
                                     self.write_source()) from e

        def _find_form(self, id_):
            selector = 'form[id="%(name)s"]' % {'name': id_}
            return self._find_by(selector)

        def _find_field(self, field=None, form=None):
            if field is form is None:
                return self.driver.switch_to.active_element
            node = self.driver
            try:
                if form:
                    selector = 'form[id="{0}"], form[name="{0}"]'.format(form)
                    node = node.find_element(by=By.CSS_SELECTOR,
                                             value=selector)
                if field:
                    selector = ('[id="{0}"], [name="{0}"], '
                                '[type="submit"][value="{0}"]').format(field)
                    node = node.find_element(by=By.CSS_SELECTOR,
                                             value=selector)
                return node
            except NoSuchElementException as e:
                url = self.write_source()
                raise AssertionError('Missing field (%r, %r) in %s' %
                                     (field, form, url)) from e

        def _get_locator(self, *args, **kwargs):
            if kwargs.get('id'):
                return By.ID, kwargs['id']
            if kwargs.get('name'):
                return By.NAME, kwargs['name']
            if kwargs.get('class_'):
                return By.CLASS_NAME, kwargs['class_']
            if kwargs.get('css'):
                return By.CSS_SELECTOR, kwargs['css']
            if not kwargs:
                if len(args) == 1:
                    return By.CSS_SELECTOR, args[0]
                if len(args) == 2:
                    return args

        def _find_by(self, *args, **kwargs):
            try:
                if not args and not kwargs:
                    return self.driver.switch_to.active_element
                locator = self._get_locator(*args, **kwargs)
                if locator:
                    return self.driver.find_element(*locator)
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
            for element in self.driver.find_elements(by=By.CSS_SELECTOR,
                                                     value='a'):
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

        if hasattr(webdriver.Firefox, 'save_full_page_screenshot'):
            def _save_screenshot(self, filename):
                self.driver.save_full_page_screenshot(filename)
        else:
            def _save_screenshot(self, filename):
                self.driver.save_screenshot(filename)

        def _to_bytes(self, value):
            if isinstance(value, str):
                value = value.encode('utf-8')
            return value

        def _urljoin(self, url):
            if '://' not in url:
                url = urljoin(self.get_url(), url)
            return url

        _doctype_re = re.compile(r'\s*<!DOCTYPE\b'.encode('ascii'))

        def _validate_html(self, source):
            if not tidy_document:
                return
            if not self._doctype_re.match(source):
                return
            corrected, errors = tidy_document(source, _tidy_options)
            if errors:
                errors = errors.splitlines()
                url = self.write_source(source)
                raise AssertionError('tidylib found %d error(s) in %s\n\n%s' %
                                     (len(errors), url, '\n'.join(errors)))

        @contextlib.contextmanager
        def _wait_for_page_load(self, seconds=5):

            def wait_for(expr):
                script = 'return (%s)' % expr
                condition = lambda: execute_script(script)
                try:
                    self.wait_for(condition, timeout=5)
                except TimeoutException:
                    return False
                else:
                    return True

            execute_script = self.driver.execute_script

            if self.get_url().startswith('http://'):
                execute_script('window._trac_page_not_loaded = 42')
            yield
            if not wait_for('window._trac_page_not_loaded === undefined'):
                raise AssertionError('Timed out for page load in %s' %
                                     self.write_source())

            expr = 'window.jQuery !== undefined && jQuery.isReady'
            if self._javascript_enabled and not wait_for(expr):
                raise AssertionError('Timed out for jQuery.ready() in %s' %
                                     self.write_source())

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
            self._save_screenshot(filename[:-4] + 'png')

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
        super().__init__(*args, **kwargs)

    def get_connection(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.proxy_port)
        conn.connect()
        return conn

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
        self.server.save_response(self.path, b'')
        conn = self.server.get_connection()
        try:
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
        except ConnectionError:
            self.close_connection = True
        finally:
            conn.close()

    do_HEAD = do_GET = do_POST = _do

    def log_message(self, format, *args):
        pass
