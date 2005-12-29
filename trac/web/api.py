# -*- coding: iso-8859-1 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

from Cookie import SimpleCookie as Cookie
import mimetypes
import os
import urlparse

from trac.core import Interface
from trac.util import http_date


class RequestDone(Exception):
    """Marker exception that indicates whether request processing has completed
    and a response was sent.
    """


class Request(object):
    """This class is used to abstract the interface between different frontends.

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
        self.incookie = Cookie()
        self.outcookie = Cookie()
        self._headers = []

    def get_header(self, name):
        """Return the value of the specified HTTP header, or `None` if there's
        no such header in the request.
        """
        raise NotImplementedError

    def send_response(self, code):
        """Set the status code of the response."""
        raise NotImplementedError

    def send_header(self, name, value):
        """Send the response header with the specified name and value."""
        raise NotImplementedError

    def end_headers(self):
        """Must be called after all headers have been sent and before the actual
        content is written.
        """
        raise NotImplementedError

    def _send_cookie_headers(self):
        # Cookie values can not contain " ,;" characters, so escape them
        for name in self.outcookie.keys():
            path = self.outcookie[name].get('path')
            if path:
                path = path.replace(' ', '%20') \
                           .replace(';', '%3B') \
                           .replace(',', '%3C')
            self.outcookie[name]['path'] = path

        cookies = self.outcookie.output(header='')
        for cookie in cookies.splitlines():
            self.send_header('Set-Cookie', cookie.strip())

    def check_modified(self, timesecs, extra=''):
        """Check the request "If-None-Match" header against an entity tag
        generated from the specified last modified time in seconds (`timesecs`),
        optionally appending an `extra` string to indicate variants of the
        requested resource. That `extra` parameter can also be a list,
        in which case the MD5 sum of the list content will be used.

        If the generated tag matches the "If-None-Match" header of the request,
        this method sends a "304 Not Modified" response to the client.
        Otherwise, it adds the entity tag as as "ETag" header to the response so
        that consequetive requests can be cached.
        """
        if isinstance(extra, list):
            import md5
            m = md5.new()
            for elt in extra:
                m.update(str(elt))
            extra = m.hexdigest()
        etag = 'W"%s/%d/%s"' % (self.authname, timesecs, extra)
        inm = self.get_header('If-None-Match')
        if (not inm or inm != etag):
            self._headers.append(('ETag', etag))
        else:
            self.send_response(304)
            self.end_headers()
            raise RequestDone()

    def redirect(self, url):
        """Send a redirect to the client, forwarding to the specified URL. The
        `url` may be relative or absolute, relative URLs will be translated
        appropriately.
        """
        if self.session:
            self.session.save() # has to be done before the redirect is sent
        self.send_response(302)
        if not url.startswith('http://') and not url.startswith('https://'):
            # Make sure the URL is absolute
            url = absolute_url(self, url)
        self.send_header('Location', url)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Cache-control', 'no-cache')
        self.send_header('Expires', 'Fri, 01 Jan 1999 00:00:00 GMT')
        self._send_cookie_headers()
        self.end_headers()

        if self.method != 'HEAD':
            self.write('Redirecting...')

        raise RequestDone

    def display(self, template, content_type='text/html', response=200):
        """Render the response using the ClearSilver template given by the
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
        self._send_cookie_headers()
        self.end_headers()

        if self.method != 'HEAD':
            self.write(data)

        raise RequestDone

    def send_file(self, path, mimetype=None):
        """Send a local file to the browser.
        
        This method includes the "Last-Modified", "Content-Type" and
        "Content-Length" headers in the response, corresponding to the file
        attributes. It also checks the last modification time of the local file
        against the "If-Modified-Since" provided by the user agent, and sends a
        "304 Not Modified" response if it matches.
        """
        if not os.path.isfile(path):
            raise TracError, "File %s not found" % path

        stat = os.stat(path)
        last_modified = http_date(stat.st_mtime)
        if last_modified == self.get_header('If-Modified-Since'):
            self.send_response(304)
            self.end_headers()
            raise RequestDone

        self.send_response(200)
        if not mimetype:
            mimetype = mimetypes.guess_type(path)[0]
        self.send_header('Content-Type', mimetype)
        self.send_header('Content-Length', stat.st_size)
        self.send_header('Last-Modified', last_modified)
        for name, value in self._headers:
            self.send_header(name, value)
        self._send_cookie_headers()
        self.end_headers()

        if self.method != 'HEAD':
            try:
                fd = open(path, 'rb')
                while True:
                    data = fd.read(4096)
                    if not data:
                        break
                    self.write(data)
            finally:
                fd.close()

        raise RequestDone

    def read(self, size):
        """Read the specified number of bytes from the request body."""
        raise NotImplementedError

    def write(self, data):
        """Write the given data to the response body."""
        raise NotImplementedError


class IAuthenticator(Interface):
    """Extension point interface for components that can provide the name
    of the remote user."""

    def authenticate(req):
        """Return the name of the remote user, or `None` if the identity of the
        user is unknown."""


class IRequestHandler(Interface):
    """Extension point interface for request handlers."""

    def match_request(req):
        """Return whether the handler wants to process the given request."""

    def process_request(req):
        """Process the request. Should return a (template_name, content_type)
        tuple, where `template` is the ClearSilver template to use (either
        a `neo_cs.CS` object, or the file name of the template), and
        `content_type` is the MIME type of the content. If `content_type` is
        `None`, "text/html" is assumed.

        Note that if template processing should not occur, this method can
        simply send the response itself and not return anything.
        """


def absolute_url(req, path=None):
    """Reconstruct the absolute URL of the given request.
    
    If the `path` parameter is specified, the path is appended to the URL.
    Otherwise, only a URL with the components scheme, host and port is returned.
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
    return urlparse.urlunparse((req.scheme, host, path, None, None, None))
