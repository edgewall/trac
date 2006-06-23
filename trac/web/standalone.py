# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005-2006 Matthew Good <trac@matt-good.net>
# Copyright (C) 2005-2006 Christopher Lenz <cmlenz@gmx.de>
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
# Author: Jonas Borgström <jonas@edgewall.com>
#         Matthew Good <trac@matt-good.net>
#         Christopher Lenz <cmlenz@gmx.de>

import errno
import os
import sys
from SocketServer import ThreadingMixIn

from trac import __version__ as VERSION
from trac.util import autoreload, daemon
from trac.web.auth import BasicAuthentication, DigestAuthentication
from trac.web.main import dispatch_request
from trac.web.wsgi import WSGIServer, WSGIRequestHandler


class AuthenticationMiddleware(object):

    def __init__(self, application, auths):
        self.application = application
        self.auths = auths

    def __call__(self, environ, start_response):
        path_info = environ.get('PATH_INFO', '')
        path_parts = filter(None, path_info.split('/'))
        if len(path_parts) > 1 and path_parts[1] == 'login':
            env_name = path_parts[0]
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

    def __init__(self, application, env_parent_dir, env_paths):
        self.application = application
        self.environ = {}
        self.environ['trac.env_path'] = None
        if env_parent_dir:
            self.environ['trac.env_parent_dir'] = env_parent_dir
        else:
            self.environ['trac.env_paths'] = env_paths

    def __call__(self, environ, start_response):
        for k,v in self.environ.iteritems():
            environ.setdefault(k, v)
        return self.application(environ, start_response)


class TracHTTPServer(ThreadingMixIn, WSGIServer):

    def __init__(self, server_address, application, env_parent_dir, env_paths):
        WSGIServer.__init__(self, server_address, application,
                            request_handler=TracHTTPRequestHandler)


class TracHTTPRequestHandler(WSGIRequestHandler):

    server_version = 'tracd/' + VERSION


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
            print >>sys.stderr, 'Ignoring duplicate authentication option for ' \
                                'project: %s' % env_name
        else:
            auths[env_name] = cls(filename, realm)

    def _validate_callback(option, opt_str, value, parser, valid_values):
        if value not in valid_values:
            raise OptionValueError('%s must be one of: %s, not %s'
                                   % (opt_str, '|'.join(valid_values), value))
        setattr(parser.values, option.dest, value)

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
                      callback_args=(('http', 'scgi', 'ajp'),),
                      help='http|scgi|ajp')
    parser.add_option('-e', '--env-parent-dir', action='store',
                      dest='env_parent_dir', metavar='PARENTDIR',
                      help='parent directory of the project environments')
    parser.add_option('--base-path', action='store', type='string', # XXX call this url_base_path?
                      dest='base_path',
                      help='base path')

    parser.add_option('-r', '--auto-reload', action='store_true',
                      dest='autoreload',
                      help='restart automatically when sources are modified')

    if os.name == 'posix':
        parser.add_option('-d', '--daemonize', action='store_true',
                          dest='daemonize',
                          help='run in the background as a daemon')
        parser.add_option('--pidfile', action='store',
                          dest='pidfile',
                          help='When daemonizing, file to which to write pid')

    parser.set_defaults(port=None, hostname='', base_path='', daemonize=False,
                        protocol='http')
    options, args = parser.parse_args()

    if not args and not options.env_parent_dir:
        parser.error('either the --env-parent-dir option or at least one '
                     'environment must be specified')

    if options.port is None:
        options.port = {
            'http': 80,
            'scgi': 4000,
            'ajp': 8009,
        }[options.protocol]
    server_address = (options.hostname, options.port)

    wsgi_app = TracEnvironMiddleware(dispatch_request,
                                     options.env_parent_dir, args)
    if auths:
        wsgi_app = AuthenticationMiddleware(wsgi_app, auths)
    base_path = options.base_path.strip('/')
    if base_path:
        wsgi_app = BasePathMiddleware(wsgi_app, base_path)

    if options.protocol == 'http':
        def serve():
            httpd = TracHTTPServer(server_address, wsgi_app,
                                   options.env_parent_dir, args)
            httpd.serve_forever()
    elif options.protocol in ('scgi', 'ajp'):
        def serve():
            server_cls = __import__('flup.server.%s' % options.protocol,
                                    None, None, ['']).WSGIServer
            ret = server_cls(wsgi_app, bindAddress=server_address).run()
            sys.exit(ret and 42 or 0) # if SIGHUP exit with status 42

    try:
        if os.name == 'posix':
            if options.pidfile:
                options.pidfile = os.path.abspath(options.pidfile)
                if os.path.exists(options.pidfile):
                    pidfile = open(options.pidfile)
                    try:
                        pid = int(pidfile.read())
                    finally:
                        pidfile.close()

                    try:
                        # signal the process to see if it is still running
                        os.kill(pid, 0)
                    except OSError, e:
                        if e.errno != errno.ESRCH:
                            raise
                    else:
                        sys.exit("tracd is already running with pid %s" % pid)
                realserve = serve
                def serve():
                    try:
                        pidfile = open(options.pidfile, 'w')
                        try:
                            pidfile.write(str(os.getpid()))
                        finally:
                            pidfile.close()
                        realserve()
                    finally:
                       if os.path.exists(options.pidfile):
                           os.remove(options.pidfile)

            if options.daemonize:
                daemon.daemonize()

        if options.autoreload:
            def modification_callback(file):
                print>>sys.stderr, 'Detected modification of %s, restarting.' \
                                   % file
            autoreload.main(serve, modification_callback)
        else:
            serve()

    except OSError:
        sys.exit(1)
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
