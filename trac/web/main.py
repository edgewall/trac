# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
#
# Trac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Trac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

import mimetypes
import os
import os.path

from trac.core import *
from trac.perm import PermissionCache, PermissionError
from trac.util import escape, http_date, TRUE
from trac.web.href import Href
from trac.web.session import Session


class RequestDone(Exception):
    """
    Marker exception that indicates whether request processing has completed
    and a response was sent.
    """


class Request(object):
    """
    This class is used to abstract the interface between different frontends.

    Trac modules must use this interface. It is not allowed to have
    frontend (cgi, tracd, mod_python) specific code in the modules.
    """

    method = None
    scheme = None
    server_name = None
    server_port = None
    remote_addr = None
    remote_user = None

    args = None
    hdf = None
    authname = None
    perm = None
    session = None
    _headers = None # additional headers to send

    def __init__(self):
        import Cookie
        self.incookie = Cookie.SimpleCookie()
        self.outcookie = Cookie.SimpleCookie()
        self._headers = []

    def get_header(self, name):
        """
        Return the value of the specified HTTP header, or `None` if there's no
        such header in the request.
        """
        raise NotImplementedError

    def send_response(self, code):
        """
        Set the status code of the response.
        """
        raise NotImplementedError

    def send_header(self, name, value):
        """
        Send the response header with the specified name and value.
        """
        raise NotImplementedError

    def end_headers(self):
        """
        Must be called after all headers have been sent and before the actual
        content is written.
        """
        raise NotImplementedError

    def check_modified(self, timesecs, extra=''):
        """
        Check the request "If-None-Match" header against an entity tag generated
        from the specified last modified time in seconds (`timesecs`),
        optionally appending an `extra` string to indicate variants of the
        requested resource.

        If the generated tag matches the "If-None-Match" header of the request,
        this method sends a "304 Not Modified" response to the client.
        Otherwise, it adds the entity tag as as "ETag" header to the response so
        that consequetive requests can be cached.
        """
        etag = 'W"%s/%d/%s"' % (self.authname, timesecs, extra)
        inm = self.get_header('If-None-Match')
        if (not inm or inm != etag):
            self._headers.append(('ETag', etag))
        else:
            self.send_response(304)
            self.end_headers()
            raise RequestDone()

    def redirect(self, url):
        """
        Send a redirect to the client, forwarding to the specified URL. The
        `url` may be relative or absolute, relative URLs will be translated
        appropriately.
        """
        self.send_response(302)
        if not url.startswith('http://') and not url.startswith('https://'):
            # Make sure the URL is absolute
            url = absolute_url(self, url)
        self.send_header('Location', url)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Cache-control', 'no-cache')
        self.send_header('Expires', 'Fri, 01 Jan 1999 00:00:00 GMT')
        cookies = self.outcookie.output(header='')
        for cookie in cookies.splitlines():
            self.send_header('Set-Cookie', cookie.strip())
        self.end_headers()
        self.write('Redirecting...')
        raise RequestDone()

    def display(self, template, content_type='text/html', response=200):
        """
        Render the response using the ClearSilver template given by the
        `template` parameter, which can be either the name of the template file,
        or an already parsed `neo_cs.CS` object.
        """
        assert self.hdf, 'HDF dataset not available'
        if self.args.has_key('hdfdump'):
            # FIXME: the administrator should probably be able to disable HDF
            #        dumps
            content_type = 'text/plain'
            data = str(self.hdf)
        else:
            data = self.hdf.render(template)

        self.send_response(response)
        self.send_header('Cache-control', 'must-revalidate')
        self.send_header('Expires', 'Fri, 01 Jan 1999 00:00:00 GMT')
        self.send_header('Content-Type', content_type + ';charset=utf-8')
        self.send_header('Content-Length', len(data))
        for name, value in self._headers:
            self.send_header(name, value)
        cookies = self.outcookie.output(header='')
        for cookie in cookies.splitlines():
            self.send_header('Set-Cookie', cookie.strip())
        self.end_headers()

        if self.method != 'HEAD':
            self.write(data)

        raise RequestDone

    def send_file(self, path, mimetype=None):
        """
        Send a local file to the browser. This method includes the
        "Last-Modified", "Content-Type" and "Content-Length" headers in the
        response, corresponding to the file attributes. It also checks the last
        modification time of the local file against the "If-Modified-Since"
        provided by the user agent, and sends a "304 Not Modified" response if
        it matches.
        """
        if not os.path.isfile(path):
            raise TracError, "File %s not found" % path

        stat = os.stat(path)
        last_modified = http_date(stat.st_mtime)

        if last_modified == self.get_header('If-Modified-Since'):
            self.send_response(304)
            return

        self.send_response(200)
        if not mimetype:
            mimetype = mimetypes.guess_type(path)[0]
        self.send_header('Content-Type', mimetype)
        self.send_header('Content-Length', stat.st_size)
        self.send_header('Last-Modified', last_modified)
        self.end_headers()

        try:
            fd = open(path, 'rb')
            if self.method != 'HEAD':
                while True:
                    data = fd.read(4096)
                    if not data:
                        break
                    self.write(data)
        finally:
            fd.close()
        raise RequestDone

    def read(self, size):
        """
        Read the specified number of bytes from the request body.
        """
        raise NotImplementedError

    def write(self, data):
        """
        Write the given data to the response body.
        """
        raise NotImplementedError


class IRequestHandler(Interface):
    """
    Extension point interface for request handlers.
    """

    def match_request(req):
        """
        Return whether the handler wants to process the given request.
        """

    def process_request(req):
        """
        Process the request. Should return a (template_name, content_type)
        tuple, where `template` is the ClearSilver template to use (either
        a `neo_cs.CS` object, or the file name of the template), and
        `content_type` is the MIME type of the content. If `content_type` is
        `None`, "text/html" is assumed.

        Note that if template processing should not occur, this method can
        simply send the response itself and not return anything.
        """


class RequestDispatcher(Component):
    """
    Component responsible for dispatching requests to registered handlers.
    """

    handlers = ExtensionPoint(IRequestHandler)

    def dispatch(self, req):
        """
        Find a registered handler that matches the request and let it process
        it. In addition, this method initializes the HDF data set and adds the
        web site chrome.
        """
        from trac.web.clearsilver import HDFWrapper
        req.hdf = HDFWrapper(loadpaths=[self.env.get_templates_dir(),
                                        self.config.get('trac',
                                                        'templates_dir')])
        populate_hdf(req.hdf, self.env, req)

        # Select the component that should handle the request
        chosen_handler = None
        default_handler = None
        if not req.path_info or req.path_info == '/':
            default_handler = self.config.get('trac', 'default_handler')
        for handler in self.handlers:
            if handler.match_request(req) or \
               handler.__class__.__name__ == default_handler:
                chosen_handler = handler
                break

        from trac.web.chrome import Chrome
        chrome = Chrome(self.env)
        chrome.populate_hdf(req, chosen_handler)

        if not chosen_handler:
            # FIXME: Should return '404 Not Found' to the client
            raise TracError, 'No handler matched request to %s' % req.path_info


        resp = chosen_handler.process_request(req)
        if resp:
            template, content_type = resp
            if not content_type:
                content_type = 'text/html'

            req.display(template, content_type or 'text/html')


def populate_hdf(hdf, env, req=None):
    """
    Populate the HDF data set with various information, such as common URLs,
    project information and request-related information.
    """
    from trac import __version__
    from time import gmtime, localtime, strftime
    hdf['trac'] = {
        'version': __version__,
        'time': strftime('%c', localtime()),
        'time.gmt': strftime('%a, %d %b %Y %H:%M:%S GMT', gmtime())
    }
    hdf['trac.href'] = {
        'wiki': env.href.wiki(),
        'browser': env.href.browser('/'),
        'timeline': env.href.timeline(),
        'roadmap': env.href.roadmap(),
        'milestone': env.href.milestone(None),
        'report': env.href.report(),
        'query': env.href.query(),
        'newticket': env.href.newticket(),
        'search': env.href.search(),
        'about': env.href.about(),
        'about_config': env.href.about('config'),
        'login': env.href.login(),
        'logout': env.href.logout(),
        'settings': env.href.settings(),
        'homepage': 'http://trac.edgewall.com/'
    }

    hdf['project'] = {
        'name': env.config.get('project', 'name'),
        'name.encoded': escape(env.config.get('project', 'name')),
        'descr': env.config.get('project', 'descr'),
        'footer': env.config.get('project', 'footer',
                 'Visit the Trac open source project at<br />'
                 '<a href="http://trac.edgewall.com/">'
                 'http://trac.edgewall.com/</a>'),
        'url': env.config.get('project', 'url')
    }

    if req:
        hdf['base_url'] = req.base_url
        hdf['base_host'] = req.base_url[:req.base_url.rfind(req.cgi_location)]
        hdf['cgi_location'] = req.cgi_location
        hdf['trac.authname'] = escape(req.authname)
        for action in req.perm.permissions():
            req.hdf['trac.acl.' + action] = 1
        for arg in [k for k in req.args.keys() if k]:
            if isinstance(req.args[arg], (list, tuple)):
                hdf['args.%s' % arg] = [v.value for v in req.args[arg]]
            else:
                hdf['args.%s' % arg] = req.args[arg].value

def absolute_url(req, path=None):
    """
    Reconstruct the absolute URL of the given request. If the `path` parameter
    is specified, the path is appended to the URL. Otherwise, only a URL with
    the components scheme, host and port is returned.
    """
    host = req.get_header('Host')
    if req.get_header('X-Forwarded-Host'):
        host = req.get_header('X-Forwarded-Host')
    if not host:
        # Missing host header, so reconstruct the host from the
        # server name and port
        default_port = {'http': 80, 'https': 443}
        if req.server_port and req.server_port != default_port[req.scheme]:
            host = '%s:%d' % (req.server_name, req.server_port)
        else:
            host = req.server_name
    if not path:
        path = req.cgi_location
    from urlparse import urlunparse
    return urlunparse((req.scheme, host, path, None, None, None))

def dispatch_request(path_info, req, env):
    """
    Main entry point for the Trac web interface.
    """

    # Re-parse the configuration file if it changed since the last the time it
    # was parsed
    env.config.parse_if_needed()

    base_url = env.config.get('trac', 'base_url')
    if not base_url:
        base_url = absolute_url(req)
    req.base_url = base_url
    req.path_info = path_info

    env.href = Href(req.cgi_location)
    env.abs_href = Href(req.base_url)

    db = env.get_db_cnx()

    try:
        try:
            from trac.web.auth import Authenticator
            check_ip = env.config.get('trac', 'check_auth_ip')
            check_ip = check_ip.strip().lower() in TRUE
            authenticator = Authenticator(db, req, check_ip)
            if path_info == '/logout':
                authenticator.logout()
                referer = req.get_header('Referer')
                if referer and not referer.startswith(req.base_url):
                    # only redirect to referer if the latter is from the same
                    # instance
                    referer = None
                req.redirect(referer or env.href.wiki())
            elif req.remote_user:
                authenticator.login(req)
                if path_info == '/login':
                    referer = req.get_header('Referer')
                    if referer and not referer.startswith(req.base_url):
                        # only redirect to referer if the latter is from the
                        # same instance
                        referer = None
                    req.redirect(referer or env.href.wiki())
            req.authname = authenticator.authname
            req.perm = PermissionCache(db, req.authname)

            newsession = req.args.has_key('newsession')
            req.session = Session(env, db, req, newsession)

            try:
                dispatcher = RequestDispatcher(env)
                dispatcher.dispatch(req)
            finally:
                # Give the session a chance to persist changes
                req.session.save()

        except RequestDone:
            pass

    finally:
        db.close()

def send_pretty_error(e, env, req=None):
    """
    Send a "pretty" HTML error page to the client.
    """
    import traceback
    import StringIO
    tb = StringIO.StringIO()
    traceback.print_exc(file=tb)
    if not req:
        from trac.web.cgi_frontend import CGIRequest
        req = CGIRequest()
        req.authname = ''
    try:
        if not env:
            from trac.env import open_environment
            env = open_environment()
            env.href = Href(req.cgi_location)
        populate_hdf(req.hdf, env, req)
        if env and env.log:
            env.log.error(str(e))
            env.log.error(tb.getvalue())

        if isinstance(e, TracError):
            req.hdf['title'] = e.title or 'Error'
            req.hdf['error.title'] = e.title or 'Error'
            req.hdf['error.type'] = 'TracError'
            req.hdf['error.message'] = e.message
            if e.show_traceback:
                req.hdf['error.traceback'] = escape(tb.getvalue())
            req.display('error.cs', response=500)

        elif isinstance(e, PermissionError):
            req.hdf['title'] = 'Permission Denied'
            req.hdf['error.type'] = 'permission'
            req.hdf['error.action'] = e.action
            req.hdf['error.message'] = e
            req.display('error.cs', response=403)

        else:
            req.hdf['title'] = 'Oops'
            req.hdf['error.type'] = 'internal'
            req.hdf['error.message'] = escape(str(e))
            req.hdf['error.traceback'] = escape(tb.getvalue())
            req.display('error.cs', response=500)

    except RequestDone:
        pass
    except Exception, e2:
        if env and env.log:
            env.log.error('Failed to render pretty error page: %s' % e2)
        req.send_response(500)
        req.send_header('Content-Type', 'text/plain')
        req.end_headers()
        req.write('Oops...\n\nTrac detected an internal error:\n\n')
        req.write(str(e))
        req.write('\n')
        req.write(tb.getvalue())
