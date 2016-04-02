#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005-2006 Matthew Good <trac@matt-good.net>
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
# Author: Jonas Borgström <jonas@edgewall.com>
#         Matthew Good <trac@matt-good.net>
#         Christopher Lenz <cmlenz@gmx.de>

from __future__ import print_function

import pkg_resources
import os
import socket
import sys
from SocketServer import ThreadingMixIn

from trac import __version__ as VERSION
from trac.util import autoreload, daemon
from trac.web.auth import BasicAuthentication, DigestAuthentication
from trac.web.main import dispatch_request
from trac.web.wsgi import WSGIServer, WSGIRequestHandler


class AuthenticationMiddleware(object):

    def __init__(self, application, auths, single_env_name=None):
        self.application = application
        self.auths = auths
        self.single_env_name = single_env_name
        if single_env_name:
            self.part = 0
        else:
            self.part = 1

    def __call__(self, environ, start_response):
        path_info = environ.get('PATH_INFO', '')
        path_parts = filter(None, path_info.split('/'))
        if len(path_parts) > self.part and path_parts[self.part] == 'login':
            env_name = self.single_env_name or path_parts[0]
            if env_name:
                auth = self.auths.get(env_name, self.auths.get('*'))
                if auth:
                    remote_user = auth.do_auth(environ, start_response)
                    if not remote_user:
                        return []
                    environ['REMOTE_USER'] = remote_user
        return self.application(environ, start_response)


class BasePathMiddleware(object):

    def __init__(self, application, base_path):
        self.base_path = '/' + base_path.strip('/')
        self.application = application

    def __call__(self, environ, start_response):
        path = environ['SCRIPT_NAME'] + environ.get('PATH_INFO', '')
        environ['PATH_INFO'] = path[len(self.base_path):]
        environ['SCRIPT_NAME'] = self.base_path
        return self.application(environ, start_response)


class TracEnvironMiddleware(object):

    def __init__(self, application, env_parent_dir, env_paths, single_env):
        self.application = application
        self.environ = {'trac.env_path': None}
        if env_parent_dir:
            self.environ['trac.env_parent_dir'] = env_parent_dir
        elif single_env:
            self.environ['trac.env_path'] = env_paths[0]
        else:
            self.environ['trac.env_paths'] = env_paths

    def __call__(self, environ, start_response):
        for k, v in self.environ.iteritems():
            environ.setdefault(k, v)
        return self.application(environ, start_response)


class TracHTTPServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True

    def __init__(self, server_address, application, env_parent_dir, env_paths,
                 use_http_11=False):
        request_handlers = (TracHTTPRequestHandler, TracHTTP11RequestHandler)
        WSGIServer.__init__(self, server_address, application,
                            request_handler=request_handlers[bool(use_http_11)])


class TracHTTPRequestHandler(WSGIRequestHandler):

    server_version = 'tracd/' + VERSION

    def address_string(self):
        # Disable reverse name lookups
        return self.client_address[:2][0]


class TracHTTP11RequestHandler(TracHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'


def main():
    from optparse import OptionParser, OptionValueError
    parser = OptionParser(usage='usage: %prog [options] [projenv] ...',
                          version='%%prog %s' % VERSION)

    auths = {}
    def _auth_callback(option, opt_str, value, parser, cls):
        info = value.split(',', 3)
        if len(info) != 3:
            raise OptionValueError("Incorrect number of parameters for %s"
                                   % option)

        env_name, filename, realm = info
        if env_name in auths:
            print('Ignoring duplicate authentication option for project: %s'
                  % env_name, file=sys.stderr)
        else:
            auths[env_name] = cls(os.path.abspath(filename), realm)

    def _validate_callback(option, opt_str, value, parser, valid_values):
        if value not in valid_values:
            raise OptionValueError('%s must be one of: %s, not %s'
                                   % (opt_str, '|'.join(valid_values), value))
        setattr(parser.values, option.dest, value)

    def _octal(option, opt_str, value, parser):
        try:
            setattr(parser.values, option.dest, int(value, 8))
        except ValueError:
            raise OptionValueError('Invalid octal umask value: %r' % value)

    parser.add_option('-a', '--auth', action='callback', type='string',
                      metavar='DIGESTAUTH', callback=_auth_callback,
                      callback_args=(DigestAuthentication,),
                      help='[projectdir],[htdigest_file],[realm]')
    parser.add_option('--basic-auth', action='callback', type='string',
                      metavar='BASICAUTH', callback=_auth_callback,
                      callback_args=(BasicAuthentication,),
                      help='[projectdir],[htpasswd_file],[realm]')

    parser.add_option('-p', '--port', action='store', type='int', dest='port',
                      help='the port number to bind to')
    parser.add_option('-b', '--hostname', action='store', dest='hostname',
                      help='the host name or IP address to bind to')
    parser.add_option('--protocol', action='callback', type="string",
                      dest='protocol', callback=_validate_callback,
                      callback_args=(('http', 'scgi', 'ajp', 'fcgi'),),
                      help='http|scgi|ajp|fcgi')
    parser.add_option('-q', '--unquote', action='store_true',
                      dest='unquote',
                      help='unquote PATH_INFO (may be needed when using ajp)')
    parser.add_option('--http10', action='store_false', dest='http11',
                      help='use HTTP/1.0 protocol version instead of HTTP/1.1')
    parser.add_option('--http11', action='store_true', dest='http11',
                      help='use HTTP/1.1 protocol version (default)')
    parser.add_option('-e', '--env-parent-dir', action='store',
                      dest='env_parent_dir', metavar='PARENTDIR',
                      help='parent directory of the project environments')
    parser.add_option('--base-path', action='store', type='string', # XXX call this url_base_path?
                      dest='base_path',
                      help='the initial portion of the request URL\'s "path"')

    parser.add_option('-r', '--auto-reload', action='store_true',
                      dest='autoreload',
                      help='restart automatically when sources are modified')

    parser.add_option('-s', '--single-env', action='store_true',
                      dest='single_env', help='only serve a single '
                      'project without the project list', default=False)

    if os.name == 'posix':
        parser.add_option('-d', '--daemonize', action='store_true',
                          dest='daemonize',
                          help='run in the background as a daemon')
        parser.add_option('--pidfile', action='store',
                          dest='pidfile',
                          help='when daemonizing, file to which to write pid')
        parser.add_option('--umask', action='callback', type='string',
                          dest='umask', metavar='MASK', callback=_octal,
                          help='when daemonizing, file mode creation mask '
                          'to use, in octal notation (default 022)')

        try:
            import grp, pwd

            def _group(option, opt_str, value, parser):
                try:
                    value = int(value)
                except ValueError:
                    try:
                        value = grp.getgrnam(value)[2]
                    except KeyError:
                        raise OptionValueError('group not found: %r' % value)
                setattr(parser.values, option.dest, value)

            def _user(option, opt_str, value, parser):
                try:
                    value = int(value)
                except ValueError:
                    try:
                        value = pwd.getpwnam(value)[2]
                    except KeyError:
                        raise OptionValueError('user not found: %r' % value)
                setattr(parser.values, option.dest, value)

            parser.add_option('--group', action='callback', type='string',
                              dest='group', metavar='GROUP', callback=_group,
                              help='the group to run as')
            parser.add_option('--user', action='callback', type='string',
                              dest='user', metavar='USER', callback=_user,
                              help='the user to run as')
        except ImportError:
            pass

    parser.set_defaults(port=None, hostname='', base_path='', daemonize=False,
                        protocol='http', http11=True, umask=022, user=None,
                        group=None)
    options, args = parser.parse_args()

    if not args and not options.env_parent_dir:
        parser.error('either the --env-parent-dir option or at least one '
                     'environment must be specified')
    if options.single_env:
        if options.env_parent_dir:
            parser.error('the --single-env option cannot be used with '
                         '--env-parent-dir')
        elif len(args) > 1:
            parser.error('the --single-env option cannot be used with '
                         'more than one enviroment')
    if options.daemonize and options.autoreload:
        parser.error('the --auto-reload option cannot be used with '
                     '--daemonize')

    if options.port is None:
        options.port = {
            'http': 80,
            'scgi': 4000,
            'ajp': 8009,
            'fcgi': 8000,
        }[options.protocol]
    server_address = (options.hostname, options.port)

    # relative paths don't work when daemonized
    args = [os.path.abspath(a) for a in args]
    if options.env_parent_dir:
        options.env_parent_dir = os.path.abspath(options.env_parent_dir)
    if parser.has_option('pidfile') and options.pidfile:
        options.pidfile = os.path.abspath(options.pidfile)

    wsgi_app = TracEnvironMiddleware(dispatch_request,
                                     options.env_parent_dir, args,
                                     options.single_env)
    if auths:
        if options.single_env:
            project_name = os.path.basename(args[0])
            wsgi_app = AuthenticationMiddleware(wsgi_app, auths, project_name)
        else:
            wsgi_app = AuthenticationMiddleware(wsgi_app, auths)
    base_path = options.base_path.strip('/')
    if base_path:
        wsgi_app = BasePathMiddleware(wsgi_app, base_path)

    if options.protocol == 'http':
        def serve():
            addr, port = server_address
            if not addr or addr == '0.0.0.0':
                loc = '0.0.0.0:%s view at http://127.0.0.1:%s/%s' \
                       % (port, port, base_path)
            else:
                loc = 'http://%s:%s/%s' % (addr, port, base_path)

            try:
                httpd = TracHTTPServer(server_address, wsgi_app,
                                       options.env_parent_dir, args,
                                       use_http_11=options.http11)
            except socket.error as e:
                print("Error starting Trac server on %s" % loc)
                print("[Errno %s] %s" % e.args)
                sys.exit(1)

            print("Server starting in PID %s." % os.getpid())
            print("Serving on %s" % loc)
            if options.http11:
                print("Using HTTP/1.1 protocol version")
            httpd.serve_forever()
    elif options.protocol in ('scgi', 'ajp', 'fcgi'):
        def serve():
            server_cls = __import__('flup.server.%s' % options.protocol,
                                    None, None, ['']).WSGIServer
            flup_app = wsgi_app
            if options.unquote:
                from trac.web.fcgi_frontend import FlupMiddleware
                flup_app = FlupMiddleware(flup_app)
            ret = server_cls(flup_app, bindAddress=server_address).run()
            sys.exit(42 if ret else 0) # if SIGHUP exit with status 42

    try:
        if options.daemonize:
            daemon.daemonize(pidfile=options.pidfile, progname='tracd',
                             umask=options.umask)
        if options.group is not None:
            os.setgid(options.group)
        if options.user is not None:
            os.setuid(options.user)

        if options.autoreload:
            def modification_callback(file):
                print("Detected modification of %s, restarting." % file,
                      file=sys.stderr)
            autoreload.main(serve, modification_callback)
        else:
            serve()

    except OSError as e:
        print("%s: %s" % (e.__class__.__name__, e), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    pkg_resources.require('Trac==%s' % VERSION)
    main()
