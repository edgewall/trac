# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
# Copyright (C) 2005-2006 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

from abc import ABCMeta, abstractmethod
import errno
import sys
import urllib

from six.moves.socketserver import ForkingMixIn, ThreadingMixIn
from six.moves.BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

# winsock errors
_WSAECONNABORTED = 10053
_WSAECONNRESET = 10054


def is_client_disconnect_exception(e):
    """Determines whether the exception was caused by a disconnecting client.

    :type e: IOError
    :rtype: bool
    """
    return e.errno in (errno.EPIPE, errno.ECONNRESET, # Unix
                       _WSAECONNABORTED, _WSAECONNRESET, # Windows
                       None) # mod_wsgi, uwsgi, ... (see #12650)


class _ErrorsWrapper(object):

    def __init__(self, logfunc):
        self.logfunc = logfunc

    def flush(self):
        pass

    def write(self, msg):
        self.logfunc(msg)

    def writelines(self, seq):
        map(self.write, seq)


class _FileWrapper(object):
    """Wrapper for sending a file as response."""

    def __init__(self, fileobj, blocksize=None):
        self.fileobj = fileobj
        self.blocksize = blocksize
        self.read = self.fileobj.read
        if hasattr(fileobj, 'close'):
            self.close = fileobj.close

    def __iter__(self):
        return self

    def __next__(self):
        data = self.fileobj.read(self.blocksize)
        if not data:
            raise StopIteration
        return data

    next = __next__


class WSGIGateway(object):
    """Abstract base class for WSGI servers or gateways."""

    __metaclass__ = ABCMeta

    wsgi_version = (1, 0)
    wsgi_multithread = True
    wsgi_multiprocess = True
    wsgi_run_once = False
    wsgi_file_wrapper = _FileWrapper

    def __init__(self, environ, stdin=sys.stdin, stderr=sys.stderr):
        """Initialize the gateway object."""
        environ['wsgi.version'] = self.wsgi_version
        environ['wsgi.url_scheme'] = 'http'
        if environ.get('HTTPS', '').lower() in ('yes', 'on', '1'):
            environ['wsgi.url_scheme'] = 'https'
        elif environ.get('HTTP_X_FORWARDED_PROTO', '').lower() == 'https':
            environ['wsgi.url_scheme'] = 'https'
        environ['wsgi.input'] = stdin
        environ['wsgi.errors'] = stderr
        environ['wsgi.multithread'] = self.wsgi_multithread
        environ['wsgi.multiprocess'] = self.wsgi_multiprocess
        environ['wsgi.run_once'] = self.wsgi_run_once
        if self.wsgi_file_wrapper is not None:
            environ['wsgi.file_wrapper'] = self.wsgi_file_wrapper
        self.environ = environ

        self.headers_set = []
        self.headers_sent = []
        self.use_chunked = False

    def run(self, application):
        """Start the gateway with the given WSGI application."""
        response = application(self.environ, self._start_response)
        try:
            if self.wsgi_file_wrapper is not None \
                    and isinstance(response, self.wsgi_file_wrapper) \
                    and hasattr(self, '_sendfile'):
                self._sendfile(response.fileobj)
            else:
                for chunk in response:
                    if chunk:
                        self._write(chunk)
                if not self.headers_sent or self.use_chunked:
                    self._write('') # last chunk '\r\n0\r\n' if use_chunked
        finally:
            if hasattr(response, 'close'):
                response.close()

    def _start_response(self, status, headers, exc_info=None):
        """Callback for starting a HTTP response."""
        if exc_info:
            try:
                if self.headers_sent: # Re-raise original exception
                    raise exc_info[0], exc_info[1], exc_info[2]
            finally:
                exc_info = None # avoid dangling circular ref
        else:
            assert not self.headers_set, 'Response already started'

        self.headers_set = [status, headers]
        return self._write

    @abstractmethod
    def _write(self, data):
        """Callback for writing data to the response.

        Concrete subclasses must implement this method."""
        pass


class WSGIRequestHandler(BaseHTTPRequestHandler):

    def setup_environ(self):
        self.raw_requestline = self.rfile.readline()
        if (self.rfile.closed or              # disconnect
                not self.raw_requestline or   # empty request
                not self.parse_request()):    # invalid request
            self.close_connection = 1
            # note that in the latter case, an error code has already been sent
            return

        environ = self.server.environ.copy()
        environ['SERVER_PROTOCOL'] = self.request_version
        environ['REQUEST_METHOD'] = self.command

        if '?' in self.path:
            path_info, query_string = self.path.split('?', 1)
        else:
            path_info, query_string = self.path, ''
        environ['PATH_INFO'] = urllib.unquote(path_info)
        environ['QUERY_STRING'] = query_string

        host = self.address_string()
        if host != self.client_address[0]:
            environ['REMOTE_HOST'] = host
        environ['REMOTE_ADDR'] = self.client_address[0]

        if self.headers.typeheader is None:
            environ['CONTENT_TYPE'] = self.headers.type
        else:
            environ['CONTENT_TYPE'] = self.headers.typeheader

        length = self.headers.getheader('content-length')
        if length:
            environ['CONTENT_LENGTH'] = length

        for name, value in [header.split(':', 1) for header
                            in self.headers.headers]:
            name = name.replace('-', '_').upper()
            value = value.strip()
            if name in environ:
                # skip content length, type, etc.
                continue
            if 'HTTP_' + name in environ:
                # comma-separate multiple headers
                environ['HTTP_' + name] += ',' + value
            else:
                environ['HTTP_' + name] = value

        return environ

    def handle_one_request(self):
        try:
            environ = self.setup_environ()
        except IOError as e:
            environ = None
            if is_client_disconnect_exception(e):
                self.close_connection = 1
            else:
                raise
        if environ:
            gateway = self.server.gateway(self, environ)
            gateway.run(self.server.application)
        # else we had no request or a bad request: we simply exit (#3043)

    def finish(self):
        """We need to help the garbage collector a little."""
        try:
            BaseHTTPRequestHandler.finish(self)
        except IOError as e:
            # ignore an exception if client disconnects
            if not is_client_disconnect_exception(e):
                raise
        finally:
            self.wfile = None
            self.rfile = None


class WSGIServerGateway(WSGIGateway):

    def __init__(self, handler, environ):
        WSGIGateway.__init__(self, environ, handler.rfile,
                             _ErrorsWrapper(lambda x: handler.log_error('%s', x)))
        self.handler = handler

    def _write(self, data):
        assert self.headers_set, 'Response not started'
        if self.handler.wfile.closed:
            return # don't write to an already closed file (fix for #1183)

        try:
            if not self.headers_sent:
                # Worry at the last minute about Content-Length. If not
                # yet set, use either chunked encoding or close connection
                status, headers = self.headers_sent = self.headers_set
                if any(n.lower() == 'content-length' for n, v in headers):
                    self.use_chunked = False
                else:
                    self.use_chunked = (
                        self.environ['SERVER_PROTOCOL'] >= 'HTTP/1.1' and
                        self.handler.protocol_version >= 'HTTP/1.1')
                    if self.use_chunked:
                        headers.append(('Transfer-Encoding', 'chunked'))
                    else:
                        headers.append(('Connection', 'close'))
                self.handler.send_response(int(status[:3]))
                for name, value in headers:
                    self.handler.send_header(name, value)
                self.handler.end_headers()
            if self.use_chunked:
                self.handler.wfile.write('%x\r\n%s\r\n' % (len(data), data))
            else:
                self.handler.wfile.write(data)
        except IOError as e:
            if is_client_disconnect_exception(e):
                self.handler.close_connection = 1
            else:
                raise


class WSGIServer(HTTPServer):

    def __init__(self, server_address, application, gateway=WSGIServerGateway,
                 request_handler=WSGIRequestHandler):
        HTTPServer.__init__(self, server_address, request_handler)

        self.application = application

        gateway.wsgi_multithread = isinstance(self, ThreadingMixIn)
        gateway.wsgi_multiprocess = isinstance(self, ForkingMixIn)
        self.gateway = gateway

        self.environ = {'SERVER_NAME': self.server_name,
                        'SERVER_PORT': str(self.server_port),
                        'SCRIPT_NAME': ''}
