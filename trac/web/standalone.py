#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2020 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005-2006 Matthew Good <trac@matt-good.net>
# Copyright (C) 2005-2006 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.
#
# Author: Jonas Borgström <jonas@edgewall.com>
#         Matthew Good <trac@matt-good.net>
#         Christopher Lenz <cmlenz@gmx.de>

import argparse
import functools
import importlib
import os
import pkg_resources
import socket
import ssl
import sys
from socketserver import ThreadingMixIn

from trac import __version__ as VERSION
from trac.util import autoreload, daemon
from trac.util.text import printerr
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
        path_parts = list(filter(None, path_info.split('/')))
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
        for k, v in self.environ.items():
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


def parse_args(args=None):
    parser = argparse.ArgumentParser()

    class _AuthAction(argparse.Action):

        def __init__(self, option_strings, dest, nargs=None, **kwargs):
            self.cls = kwargs.pop('cls')
            super(_AuthAction, self).__init__(option_strings, dest, nargs,
                                              **kwargs)

        def __call__(self, parser, namespace, values, option_string=None):
            info = values.split(',')
            if len(info) != 3:
                raise argparse.ArgumentError(self,
                                             "Incorrect number of parameters")
            env_name, filename, realm = info
            filepath = os.path.abspath(filename)
            if not os.path.exists(filepath):
                raise argparse.ArgumentError(self,
                                             "Path does not exist: '%s'"
                                             % filename)
            auths = getattr(namespace, self.dest)
            if env_name in auths:
                printerr("Ignoring duplicate authentication option for "
                         "project: %s" % env_name)
            else:
                auths.update({env_name: self.cls(filepath, realm)})
                setattr(namespace, self.dest, auths)

    class _PathAction(argparse.Action):

        def __init__(self, option_strings, dest, nargs=None, **kwargs):
            self.must_exist = kwargs.pop('must_exist', False)
            super(_PathAction, self).__init__(option_strings, dest, nargs,
                                              **kwargs)

        def __call__(self, parser, namespace, values, option_string=None):
            def to_abspath(path):
                abspath = os.path.abspath(path)
                if self.must_exist and not os.path.exists(abspath):
                    raise argparse.ArgumentError(self,
                                                 "Path does not exist: '%s'"
                                                 % path)
                return abspath
            if isinstance(values, list):
                paths = [to_abspath(paths) for paths in values]
            else:
                paths = to_abspath(values)
            setattr(namespace, self.dest, paths)

    parser.add_argument('--version', action='version',
                        version='%%(prog)s %s' % VERSION)
    parser.add_argument('envs', action=_PathAction, must_exist=True,
                        nargs='*', help="path of the project environment(s)")

    parser_group = parser.add_mutually_exclusive_group()
    parser_group.add_argument('-e', '--env-parent-dir', action=_PathAction,
                              must_exist=True, metavar='PARENTDIR',
                              help="parent directory of the project "
                                   "environments")
    parser_group.add_argument('-s', '--single-env', action='store_true',
                              help="only serve a single project without the "
                                   "project list")

    parser_group = parser.add_mutually_exclusive_group()
    parser_group.add_argument('-a', '--auth', default={},
                              metavar='DIGESTAUTH', dest='auths',
                              action=_AuthAction, cls=DigestAuthentication,
                              help="[projectdir],[htdigest_file],[realm]")
    parser_group.add_argument('--basic-auth', default={},
                              metavar='BASICAUTH', dest='auths',
                              action=_AuthAction, cls=BasicAuthentication,
                              help="[projectdir],[htpasswd_file],[realm]")

    parser.add_argument('-p', '--port', type=int,
                        help="the port number to bind to")
    parser.add_argument('-b', '--hostname', default='',
                        help="the host name or IP address to bind to")
    parser.add_argument('--protocol', default='http',
                        choices=('http', 'https', 'scgi', 'ajp', 'fcgi'),
                        help="the server protocol (default: http)")
    parser.add_argument('--certfile', help="PEM certificate file for HTTPS")
    parser.add_argument('--keyfile', help="PEM key file for HTTPS")
    parser.add_argument('-q', '--unquote', action='store_true',
                        help="unquote PATH_INFO (may be needed when using "
                             "the ajp protocol)")
    parser.add_argument('--base-path', default='',  # XXX call this url_base_path?
                        help="the initial portion of the request URL's "
                             "\"path\"")

    parser_group = parser.add_mutually_exclusive_group()
    parser_group.add_argument('--http10', action='store_false', dest='http11',
                              help="use HTTP/1.0 protocol instead of "
                                   "HTTP/1.1")
    parser_group.add_argument('--http11', action='store_true', default=True,
                              help="use HTTP/1.1 protocol (default)")

    if os.name == 'posix':
        class _GroupAction(argparse.Action):

            def __call__(self, parser, namespace, values, option_string=None):
                import grp
                try:
                    value = int(values)
                except ValueError:
                    try:
                        value = grp.getgrnam(values)[2]
                    except KeyError:
                        raise argparse.ArgumentError(self, "group not found: "
                                                           "%r" % values)
                setattr(namespace, self.dest, value)

        class _UserAction(argparse.Action):

            def __call__(self, parser, namespace, values, option_string=None):
                import pwd
                try:
                    value = int(values)
                except ValueError:
                    try:
                        value = pwd.getpwnam(values)[2]
                    except KeyError:
                        raise argparse.ArgumentError(self, "user not found: "
                                                           "%r" % values)
                setattr(namespace, self.dest, value)

        class _OctalValueAction(argparse.Action):

            octal = functools.partial(int, base=8)

            def __call__(self, parser, namespace, values, option_string=None):
                try:
                    value = self.octal(values)
                except ValueError:
                    raise argparse.ArgumentError(self, "Invalid octal umask "
                                                       "value: %r" % values)
                setattr(namespace, self.dest, value)

        parser_group = parser.add_mutually_exclusive_group()
        parser_group.add_argument('-r', '--auto-reload', action='store_true',
                                  help="restart automatically when sources "
                                       "are modified")
        parser_group.add_argument('-d', '--daemonize', action='store_true',
                                  help="run in the background as a daemon")
        parser.add_argument('--pidfile', action=_PathAction,
                            help="file to write pid when daemonizing")
        parser.add_argument('--umask', action=_OctalValueAction,
                            default=0o022, metavar='MASK',
                            help="when daemonizing, file mode creation mask "
                                 "to use, in octal notation (default: 022)")
        parser.add_argument('--group', action=_GroupAction,
                            help="the group to run as")
        parser.add_argument('--user', action=_UserAction,
                            help="the user to run as")
    else:
        parser.add_argument('-r', '--auto-reload', action='store_true',
                            help="restart automatically when sources are "
                                 "modified")

    parser.set_defaults(daemonize=False, user=None, group=None)
    args = parser.parse_args(args)

    if not args.env_parent_dir and not args.envs:
        parser.error("either the --env-parent-dir (-e) option or at least "
                     "one environment must be specified")
    if args.single_env and len(args.envs) > 1:
        parser.error("the --single-env (-s) option cannot be used with more "
                     "than one environment")
    if args.protocol == 'https' and not args.certfile:
        parser.error("the --certfile option is required when using the https "
                     "protocol")

    if args.port is None:
        args.port = {
            'http': 80,
            'https': 443,
            'scgi': 4000,
            'ajp': 8009,
            'fcgi': 8000,
        }[args.protocol]

    return args


def main():
    args = parse_args()

    wsgi_app = TracEnvironMiddleware(dispatch_request, args.env_parent_dir,
                                     args.envs, args.single_env)
    if args.auths:
        if args.single_env:
            project_name = os.path.basename(args.envs[0])
            wsgi_app = AuthenticationMiddleware(wsgi_app, args.auths,
                                                project_name)
        else:
            wsgi_app = AuthenticationMiddleware(wsgi_app, args.auths)
    base_path = args.base_path.strip('/')
    if base_path:
        wsgi_app = BasePathMiddleware(wsgi_app, base_path)

    server_address = (args.hostname, args.port)
    if args.protocol in ('http', 'https'):
        def serve():
            addr, port = server_address
            if not addr or addr == '0.0.0.0':
                loc = '0.0.0.0:%s view at %s://127.0.0.1:%s/%s' \
                       % (port, args.protocol, port, base_path)
            else:
                loc = '%s://%s:%s/%s' % (args.protocol, addr, port, base_path)

            try:
                httpd = TracHTTPServer(server_address, wsgi_app,
                                       args.env_parent_dir, args.envs,
                                       use_http_11=args.http11)
            except socket.error as e:
                print("Error starting Trac server on %s" % loc)
                print("[Errno %s] %s" % e.args)
                sys.exit(1)

            print("Server starting in PID %s." % os.getpid())
            print("Serving on %s" % loc)
            if args.http11:
                print("Using HTTP/1.1 protocol version")
            if args.protocol == 'https':
                httpd.socket = ssl.wrap_socket(httpd.socket, server_side=True,
                                               certfile=args.certfile,
                                               keyfile=args.keyfile)
            httpd.serve_forever()
    elif args.protocol in ('scgi', 'ajp', 'fcgi'):
        def serve():
            module = 'flup.server.%s' % args.protocol
            try:
                server_cls = importlib.import_module(module).WSGIServer
            except ImportError:
                printerr("Install the flup package to use the '%s' "
                         "protocol" % args.protocol)
                sys.exit(1)
            flup_app = wsgi_app
            if args.unquote:
                from trac.web.fcgi_frontend import FlupMiddleware
                flup_app = FlupMiddleware(flup_app)
            ret = server_cls(flup_app, bindAddress=server_address).run()
            sys.exit(42 if ret else 0)  # if SIGHUP exit with status 42

    try:
        if args.daemonize:
            daemon.daemonize(pidfile=args.pidfile, progname='tracd',
                             umask=args.umask)
        if args.group is not None:
            os.setgid(args.group)
        if args.user is not None:
            os.setuid(args.user)

        if args.auto_reload:
            def modification_callback(file):
                printerr("Detected modification of %s, restarting." % file)
            autoreload.main(serve, modification_callback)
        else:
            serve()

    except OSError as e:
        printerr("%s: %s" % (e.__class__.__name__, e))
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    pkg_resources.require('Trac==%s' % VERSION)
    main()
