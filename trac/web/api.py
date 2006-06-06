# -*- coding: utf-8 -*-
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

from BaseHTTPServer import BaseHTTPRequestHandler
from Cookie import SimpleCookie as Cookie
import cgi
import mimetypes
import os
from StringIO import StringIO
import sys
import urlparse

from trac.core import Interface
from trac.util import get_last_traceback
from trac.util.datefmt import http_date
from trac.web.href import Href

HTTP_STATUS = dict([(code, reason.title()) for code, (reason, description)
                    in BaseHTTPRequestHandler.responses.items()])


class HTTPException(Exception):
    """Exception representing a HTTP status code."""

    def __init__(self, code):
        self.code = code
        self.reason = HTTP_STATUS.get(self.code, 'Unknown')
        self.__doc__ = 'Exception for HTTP %d %s' % (self.code, self.reason)

    def __call__(self, message, *args):
        self.message = message
        if args:
            self.message = self.message % args
        Exception.__init__(self, '%s %s (%s)' % (self.code, self.reason,
                                                 message))
        return self

    def __str__(self):
        return '%s %s (%s)' % (self.code, self.reason, self.message)


for code in [code for code in HTTP_STATUS if code >= 400]:
    exc_name = HTTP_STATUS[code].replace(' ', '')
    if exc_name.lower().startswith('http'):
        exc_name = exc_name[4:]
    setattr(sys.modules[__name__], 'HTTP' + exc_name, HTTPException(code))
del code, exc_name


class _RequestArgs(dict):
    """Dictionary subclass that provides convenient access to request
    parameters that may contain multiple values."""

    def getfirst(self, name, default=None):
        """Return the first value for the specified parameter, or `default` if
        the parameter was not provided.
        """
        if name not in self:
            return default
        val = self[name]
        if isinstance(val, list):
            val = val[0]
        return val

    def getlist(self, name):
        """Return a list of values for the specified parameter, even if only
        one value was provided.
        """
        if name not in self:
            return []
        val = self[name]
        if not isinstance(val, list):
            val = [val]
        return val


class RequestDone(Exception):
    """Marker exception that indicates whether request processing has completed
    and a response was sent.
    """


class Request(object):
    """Represents a HTTP request/response pair.
    
    This class provides a convenience API over WSGI.
    """
    args = None
    hdf = None
    authname = None
    perm = None
    session = None

    def __init__(self, environ, start_response):
        """Create the request wrapper.
        
        @param environ: The WSGI environment dict
        @param start_response: The WSGI callback for starting the response
        """
        self.environ = environ
        self._start_response = start_response
        self._write = None
        self._status = '200 OK'
        self._response = None

        self._inheaders = [(name[5:].replace('_', '-').lower(), value)
                           for name, value in environ.items()
                           if name.startswith('HTTP_')]
        if 'CONTENT_LENGTH' in environ:
            self._inheaders.append(('content-length',
                                    environ['CONTENT_LENGTH']))
        if 'CONTENT_TYPE' in environ:
            self._inheaders.append(('content-type', environ['CONTENT_TYPE']))
        self._outheaders = []
        self._outcharset = None

        self.incookie = Cookie()
        cookie = self.get_header('Cookie')
        if cookie:
            self.incookie.load(cookie)
        self.outcookie = Cookie()

        self.base_url = self.environ.get('trac.base_url')
        if not self.base_url:
            self.base_url = self._reconstruct_url()
        self.href = Href(self.base_path)
        self.abs_href = Href(self.base_url)

        self.args = self._parse_args()

    def _parse_args(self):
        """Parse the supplied request parameters into a dictionary."""
        args = _RequestArgs()

        fp = self.environ['wsgi.input']
        ctype = self.get_header('Content-Type')
        if ctype:
            # Avoid letting cgi.FieldStorage consume the input stream when the
            # request does not contain form data
            ctype, options = cgi.parse_header(ctype)
            if ctype not in ('application/x-www-form-urlencoded',
                             'multipart/form-data'):
                fp = StringIO('')

        fs = cgi.FieldStorage(fp, environ=self.environ, keep_blank_values=True)
        if fs.list:
            for name in fs.keys():
                values = fs[name]
                if not isinstance(values, list):
                    values = [values]
                for value in values:
                    if not value.filename:
                        value = unicode(value.value, 'utf-8')
                    if name in args:
                        if isinstance(args[name], list):
                            args[name].append(value)
                        else:
                            args[name] = [args[name], value]
                    else:
                        args[name] = value

        return args

    def _reconstruct_url(self):
        """Reconstruct the absolute base URL of the application."""
        host = self.get_header('Host')
        if not host:
            # Missing host header, so reconstruct the host from the
            # server name and port
            default_port = {'http': 80, 'https': 443}
            if self.server_port and self.server_port != default_port[self.scheme]:
                host = '%s:%d' % (self.server_name, self.server_port)
            else:
                host = self.server_name
        return urlparse.urlunparse((self.scheme, host, self.base_path, None,
                                    None, None))

    method = property(fget=lambda self: self.environ['REQUEST_METHOD'],
                      doc='The HTTP method of the request')
    path_info = property(fget=lambda self: self.environ.get('PATH_INFO', '').decode('utf-8'),
                         doc='Path inside the application')
    remote_addr = property(fget=lambda self: self.environ.get('REMOTE_ADDR'),
                           doc='IP address of the remote user')
    remote_user = property(fget=lambda self: self.environ.get('REMOTE_USER'),
                           doc='Name of the remote user, `None` if the user'
                               'has not logged in using HTTP authentication')
    scheme = property(fget=lambda self: self.environ['wsgi.url_scheme'],
                      doc='The scheme of the request URL')
    base_path = property(fget=lambda self: self.environ.get('SCRIPT_NAME', ''),
                         doc='The root path of the application')
    server_name = property(fget=lambda self: self.environ['SERVER_NAME'],
                           doc='Name of the server')
    server_port = property(fget=lambda self: int(self.environ['SERVER_PORT']),
                           doc='Port number the server is bound to')

    def get_header(self, name):
        """Return the value of the specified HTTP header, or `None` if there's
        no such header in the request.
        """
        name = name.lower()
        for key, value in self._inheaders:
            if key == name:
                return value
        return None

    def send_response(self, code=200):
        """Set the status code of the response."""
        self._status = '%s %s' % (code, HTTP_STATUS.get(code, 'Unknown'))

    def send_header(self, name, value):
        """Send the response header with the specified name and value.

        `value` must either be an `unicode` string or can be converted to one
        (e.g. numbers, ...)
        """
        if name.lower() == 'content-type':
            ctpos = value.find('charset=')
            if ctpos >= 0:
                self._outcharset = value[ctpos + 8:].strip()
        self._outheaders.append((name, unicode(value).encode('utf-8')))

    def _send_cookie_headers(self):
        for name in self.outcookie.keys():
            path = self.outcookie[name].get('path')
            if path:
                path = path.replace(' ', '%20') \
                           .replace(';', '%3B') \
                           .replace(',', '%3C')
            self.outcookie[name]['path'] = path

        cookies = self.outcookie.output(header='')
        for cookie in cookies.splitlines():
            self._outheaders.append(('Set-Cookie', cookie.strip()))

    def end_headers(self):
        """Must be called after all headers have been sent and before the actual
        content is written.
        """
        self._send_cookie_headers()
        self._write = self._start_response(self._status, self._outheaders)

    def check_modified(self, timesecs, extra=''):
        """Check the request "If-None-Match" header against an entity tag.

        The entity tag is generated from the specified last modified time
        in seconds (`timesecs`), optionally appending an `extra` string to
        indicate variants of the requested resource.

        That `extra` parameter can also be a list, in which case the MD5 sum
        of the list content will be used.

        If the generated tag matches the "If-None-Match" header of the request,
        this method sends a "304 Not Modified" response to the client.
        Otherwise, it adds the entity tag as an "ETag" header to the response
        so that consecutive requests can be cached.
        """
        if isinstance(extra, list):
            import md5
            m = md5.new()
            for elt in extra:
                m.update(repr(elt))
            extra = m.hexdigest()
        etag = 'W"%s/%d/%s"' % (self.authname, timesecs, extra)
        inm = self.get_header('If-None-Match')
        if (not inm or inm != etag):
            self.send_header('ETag', etag)
        else:
            self.send_response(304)
            self.end_headers()
            raise RequestDone

    def redirect(self, url, permanent=False):
        """Send a redirect to the client, forwarding to the specified URL. The
        `url` may be relative or absolute, relative URLs will be translated
        appropriately.
        """
        if self.session:
            self.session.save() # has to be done before the redirect is sent

        if permanent:
            status = 301 # 'Moved Permanently'
        elif self.method == 'POST':
            status = 303 # 'See Other' -- safe to use in response to a POST
        else:
            status = 302 # 'Found' -- normal temporary redirect

        self.send_response(status)
        if not url.startswith('http://') and not url.startswith('https://'):
            # Make sure the URL is absolute
            url = urlparse.urlunparse((self.scheme,
                                       urlparse.urlparse(self.base_url)[1],
                                       url, None, None, None))
        self.send_header('Location', url)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Cache-control', 'no-cache')
        self.send_header('Expires', 'Fri, 01 Jan 1999 00:00:00 GMT')
        self.end_headers()

        if self.method != 'HEAD':
            self.write('Redirecting...')
        raise RequestDone

    def display(self, template, content_type='text/html', status=200):
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

        self.send_response(status)
        self.send_header('Cache-control', 'must-revalidate')
        self.send_header('Expires', 'Fri, 01 Jan 1999 00:00:00 GMT')
        self.send_header('Content-Type', content_type + ';charset=utf-8')
        self.send_header('Content-Length', len(data))
        self.end_headers()

        if self.method != 'HEAD':
            self.write(data)
        raise RequestDone

    def send_error(self, exc_info, template='error.cs',
                   content_type='text/html', status=500):
        if self.hdf:
            if self.args.has_key('hdfdump'):
                # FIXME: the administrator should probably be able to disable HDF
                #        dumps
                content_type = 'text/plain'
                data = str(self.hdf)
            else:
                data = self.hdf.render(template)
        else:
            content_type = 'text/plain'
            data = get_last_traceback()

        self.send_response(status)
        self._outheaders = []
        self.send_header('Cache-control', 'must-revalidate')
        self.send_header('Expires', 'Fri, 01 Jan 1999 00:00:00 GMT')
        self.send_header('Content-Type', content_type + ';charset=utf-8')
        self.send_header('Content-Length', len(data))
        self._send_cookie_headers()

        self._write = self._start_response(self._status, self._outheaders,
                                           exc_info)

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
            raise HTTPNotFound("File %s not found" % path)

        stat = os.stat(path)
        last_modified = http_date(stat.st_mtime)
        if last_modified == self.get_header('If-Modified-Since'):
            self.send_response(304)
            self.end_headers()
            raise RequestDone

        if not mimetype:
            mimetype = mimetypes.guess_type(path)[0] or \
                       'application/octet-stream'

        self.send_response(200)
        self.send_header('Content-Type', mimetype)
        self.send_header('Content-Length', stat.st_size)
        self.send_header('Last-Modified', last_modified)
        self.end_headers()

        if self.method != 'HEAD':
            self._response = file(path, 'rb')
            file_wrapper = self.environ.get('wsgi.file_wrapper')
            if file_wrapper:
                self._response = file_wrapper(self._response, 4096)
        raise RequestDone

    def read(self, size=None):
        """Read the specified number of bytes from the request body."""
        fileobj = self.environ['wsgi.input']
        if size is None:
            size = int(self.get_header('Content-Length', -1))
        data = fileobj.read(size)
        return data

    def write(self, data):
        """Write the given data to the response body.

        `data` can be either a `str` or an `unicode` string.
        If it's the latter, the unicode string will be encoded
        using the charset specified in the ''Content-Type'' header
        or 'utf-8' otherwise.
        """
        if not self._write:
            self.end_headers()
        if isinstance(data, unicode):
            data = data.encode(self._outcharset or 'utf-8')
        self._write(data)


class IAuthenticator(Interface):
    """Extension point interface for components that can provide the name
    of the remote user."""

    def authenticate(req):
        """Return the name of the remote user, or `None` if the identity of the
        user is unknown."""


class IRequestHandler(Interface):
    """Extension point interface for request handlers."""

    # implementing classes should set this property to `True` if they
    # don't need session and authentication related information
    anonymous_request = False
    
    # implementing classes should set this property to `False` if they
    # don't need the HDF data and don't produce content using a template
    use_template = True
    
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


class IRequestFilter(Interface):
    """Extension point interface for components that want to filter HTTP
    requests, before and/or after they are processed by the main handler."""

    def pre_process_request(req, handler):
        """Do any pre-processing the request might need; typically adding
        values to req.hdf, or redirecting.
        
        Always returns the request handler, even if unchanged.
        """

    def post_process_request(req, template, content_type):
        """Do any post-processing the request might need; typically adding
        values to req.hdf, or changing template or mime type.
        
        Always returns a tuple of (template, content_type), even if
        unchanged.
        """
