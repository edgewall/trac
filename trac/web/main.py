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

from trac.core import module_factory, open_environment
from trac.Href import Href
from trac.util import escape
from trac.web.auth import Authenticator
from trac.web.session import Session

import cgi
import re
from types import ListType
import urllib


class NotModifiedException(Exception):
    pass


class RedirectException(Exception):
    pass


class Request:
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

    hdf = None
    authname = None
    session = None
    _headers = None # additional headers to send

    def __init__(self):
        import Cookie
        self.incookie = Cookie.SimpleCookie()
        self.outcookie = Cookie.SimpleCookie()
        self._headers = []

    def get_header(self, name):
        raise RuntimeError, 'Virtual method not implemented'

    def send_response(self, code):
        raise RuntimeError, 'Virtual method not implemented'

    def send_header(self, name, value):
        raise RuntimeError, 'Virtual method not implemented'

    def end_headers(self):
        raise RuntimeError, 'Virtual method not implemented'

    def check_modified(self, timesecs, extra=''):
        etag = 'W"%s/%d/%s"' % (self.authname, timesecs, extra)
        inm = self.get_header('If-None-Match')
        if (not inm or inm != etag):
            self._headers.append(('ETag', etag))
        else:
            self.send_response(304)
            self.end_headers()
            raise NotModifiedException()

    def redirect(self, url):
        self.send_response(302)
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
        raise RedirectException()

    def display(self, cs, content_type='text/html', response=200):
        assert self.hdf, 'HDF dataset not available'
        data = self.hdf.render(cs)
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

    def read(self, len):
        raise RuntimeError, 'Virtual method not implemented'

    def write(self, data):
        raise RuntimeError, 'Virtual method not implemented'


def _add_args_to_hdf(args, hdf):
    for k in [k for k in args.keys() if k]:
        if type(args[k]) == ListType:
            for i in range(len(args[k])):
                hdf['args.%s.%d' % (k, i)] = args[k][i].value
        else:
            hdf['args.%s' % k] = args[k].value

def _parse_path_info(args, path_info):
    def set_if_missing(fs, name, value):
        if value and not fs.has_key(name):
            fs.list.append(cgi.MiniFieldStorage(name, value))

    if not path_info or path_info in ['/login', '/logout']:
        return args
    match = re.search('^/(about_trac|wiki)(?:/(.*))?', path_info)
    if match:
        set_if_missing(args, 'mode', match.group(1))
        if match.group(2):
            set_if_missing(args, 'page', match.group(2))
        return args
    match = re.search('^/(newticket|timeline|search|roadmap|settings|query)/?', path_info)
    if match:
        set_if_missing(args, 'mode', match.group(1))
        return args
    match = re.search('^/(ticket|report)(?:/([0-9]+)/*)?', path_info)
    if match:
        set_if_missing(args, 'mode', match.group(1))
        if match.group(2):
            set_if_missing(args, 'id', match.group(2))
        return args
    match = re.search('^/(browser|log|file)(?:(/.*))?', path_info)
    if match:
        set_if_missing(args, 'mode', match.group(1))
        if match.group(2):
            set_if_missing(args, 'path', match.group(2))
        return args
    match = re.search('^/changeset/([0-9]+)/?', path_info)
    if match:
        set_if_missing(args, 'mode', 'changeset')
        set_if_missing(args, 'rev', match.group(1))
        return args
    match = re.search('^/attachment/([a-zA-Z_]+)/([^/]+)(?:/(.*)/?)?', path_info)
    if match:
        set_if_missing(args, 'mode', 'attachment')
        set_if_missing(args, 'type', match.group(1))
        set_if_missing(args, 'id', urllib.unquote(match.group(2)))
        set_if_missing(args, 'filename', match.group(3))
        return args
    match = re.search('^/milestone(?:/([^\?]+))?(?:/(.*)/?)?', path_info)
    if match:
        set_if_missing(args, 'mode', 'milestone')
        if match.group(1):
            set_if_missing(args, 'id', urllib.unquote(match.group(1)))
        return args
    return args

def populate_hdf(hdf, env, req=None):
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
        'name': env.get_config('project', 'name'),
        'name.encoded': escape(env.get_config('project', 'name')),
        'descr': env.get_config('project', 'descr'),
        'footer': env.get_config('project', 'footer',
                 'Visit the Trac open source project at<br />'
                 '<a href="http://trac.edgewall.com/">'
                 'http://trac.edgewall.com/</a>'),
        'url': env.get_config('project', 'url')
    }

    htdocs_location = env.get_config('trac', 'htdocs_location')
    if htdocs_location[-1] != '/':
        htdocs_location += '/'
    hdf['htdocs_location'] = htdocs_location

    src = env.get_config('header_logo', 'src')
    src_abs = re.match(r'https?://', src) != None
    if not src[0] == '/' and not src_abs:
        src = htdocs_location + src
    hdf['header_logo'] = {
        'link': env.get_config('header_logo', 'link'),
        'alt': escape(env.get_config('header_logo', 'alt')),
        'src': src,
        'src_abs': src_abs,
        'width': env.get_config('header_logo', 'width'),
        'height': env.get_config('header_logo', 'height')
    }

    if req:
        hdf['base_url'] = req.base_url
        hdf['base_host'] = req.base_url[:req.base_url.rfind(req.cgi_location)]
        hdf['cgi_location'] = req.cgi_location
        hdf['trac.authname'] = escape(req.authname)

def _reconstruct_base_url(req):
    host = req.get_header('Host')
    if req.get_header('X-Forwarded-Host'):
        host = req.get_header('X-Forwarded-Host')
    if not host:
        # Missing host header, so reconstruct the host from the
        # server name and port
        default_port = {'http': 80, 'https': 443}
        name = req.server_name
        if req.server_port and req.server_port != default_port[req.scheme]:
            host = '%s:%d' % (req.server_name, req.server_port)
        else:
            host = req.server_name
    from urlparse import urlunparse
    return urlunparse((req.scheme, host, req.cgi_location, None, None, None))

def dispatch_request(path_info, req, env):
    base_url = env.get_config('trac', 'base_url')
    if not base_url:
        base_url = _reconstruct_base_url(req)
    req.base_url = base_url
    _parse_path_info(req.args, path_info)

    env.href = Href(req.cgi_location)
    env.abs_href = Href(req.base_url)

    db = env.get_db_cnx()

    # Let the wiki module build a dictionary of all page names
    from trac.Wiki import populate_page_dict
    populate_page_dict(db, env)

    try:
        try:
            authenticator = Authenticator(db, req)
            if path_info == '/logout':
                authenticator.logout()
                referer = req.get_header('Referer')
                if referer and referer[0:len(req.base_url)] != req.base_url:
                    # only redirect to referer if the latter is from the same
                    # instance
                    referer = None
                req.redirect(referer or env.href.wiki())
            elif req.remote_user and authenticator.authname == 'anonymous':
                authenticator.login(req)
            if path_info == '/login':
                referer = req.get_header('Referer')
                if referer and referer[0:len(req.base_url)] != req.base_url:
                    # only redirect to referer if the latter is from the same
                    # instance
                    referer = None
                req.redirect(referer or env.href.wiki())
            req.authname = authenticator.authname

            from trac.web.clearsilver import HDFWrapper
            req.hdf = HDFWrapper(loadpaths=[env.get_templates_dir(),
                                            env.get_config('trac', 'templates_dir')])
            req.hdf['HTTP.PathInfo'] = path_info
            _add_args_to_hdf(req.args, req.hdf)

            newsession = req.args.has_key('newsession')
            req.session = Session(env, db, req, newsession)

            try:
                pool = None
                # Load the selected module
                module = module_factory(env, db, req)
                pool = module.pool
                module.run(req)
            finally:
                # We do this even if the cgi will terminate directly after. A
                # pool destruction might trigger important clean-up functions.
                if pool:
                    import svn.core
                    svn.core.svn_pool_destroy(pool)

                # Give the session a chance to persist changes
                req.session.save()

        except NotModifiedException:
            pass
        except RedirectException:
            pass

    finally:
        db.close()

def send_pretty_error(e, env, req=None):
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
            env = open_environment()
        from trac.Href import Href
        env.href = Href(req.cgi_location)
        populate_hdf(req.hdf, env, req)

        from trac.util import TracError
        from trac.perm import PermissionError

        if isinstance(e, TracError):
            req.hdf['title'] = e.title or 'Error'
            req.hdf['error.title'] = e.title or 'Error'
            req.hdf['error.type'] = 'TracError'
            req.hdf['error.message'] = e.message
            if e.show_traceback:
                req.hdf['error.traceback'] = escape(tb.getvalue())
        elif isinstance(e, PermissionError):
            req.hdf['title'] = 'Permission Denied'
            req.hdf['error.type'] = 'permission'
            req.hdf['error.action'] = e.action
            req.hdf['error.message'] = e
        else:
            req.hdf['title'] = 'Oops'
            req.hdf['error.type'] = 'internal'
            req.hdf['error.message'] = escape(str(e))
            req.hdf['error.traceback'] = escape(tb.getvalue())
        req.display('error.cs', response=500)
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
    if env and env.log:
        env.log.error(str(e))
        env.log.error(tb.getvalue())
