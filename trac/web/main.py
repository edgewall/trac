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

from trac.perm import PermissionCache, PermissionError
from trac.util import escape, href_join, TracError, TRUE
from trac.web.auth import Authenticator
from trac.web.href import Href
from trac.web.session import Session

import re


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
    session = None
    _headers = None # additional headers to send

    def __init__(self):
        import Cookie
        self.incookie = Cookie.SimpleCookie()
        self.outcookie = Cookie.SimpleCookie()
        self._headers = []

    def get_header(self, name):
        raise NotImplementedError

    def send_response(self, code):
        raise NotImplementedError

    def send_header(self, name, value):
        raise NotImplementedError

    def end_headers(self):
        raise NotImplementedError

    def check_modified(self, timesecs, extra=''):
        etag = 'W"%s/%d/%s"' % (self.authname, timesecs, extra)
        inm = self.get_header('If-None-Match')
        if (not inm or inm != etag):
            self._headers.append(('ETag', etag))
        else:
            self.send_response(304)
            self.end_headers()
            raise RequestDone()

    def redirect(self, url):
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

    def display(self, cs, content_type='text/html', response=200):
        assert self.hdf, 'HDF dataset not available'
        if self.args.has_key('hdfdump'):
            # FIXME: the administrator should probably be able to disable HDF
            #        dumps
            content_type = 'text/plain'
            data = str(self.hdf)
        else:
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

        raise RequestDone()

    def read(self, len):
        raise NotImplementedError

    def write(self, data):
        raise NotImplementedError


def add_link(req, rel, href, title=None, type=None, class_name=None):
    link = {'href': escape(href)}
    if title: link['title'] = escape(title)
    if type: link['type'] = type
    if class_name: link['class'] = class_name
    idx = 0
    while req.hdf.get('links.%s.%d.href' % (rel, idx)):
        idx += 1
    req.hdf['links.%s.%d' % (rel, idx)] = link

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
        'name': env.config.get('project', 'name'),
        'name.encoded': escape(env.config.get('project', 'name')),
        'descr': env.config.get('project', 'descr'),
        'footer': env.config.get('project', 'footer',
                 'Visit the Trac open source project at<br />'
                 '<a href="http://trac.edgewall.com/">'
                 'http://trac.edgewall.com/</a>'),
        'url': env.config.get('project', 'url')
    }

    htdocs_location = env.config.get('trac', 'htdocs_location')
    if htdocs_location[-1] != '/':
        htdocs_location += '/'
    hdf['htdocs_location'] = htdocs_location

    src = env.config.get('header_logo', 'src')
    src_abs = re.match(r'https?://', src) != None
    if not src[0] == '/' and not src_abs:
        src = htdocs_location + src
    hdf['header_logo'] = {
        'link': env.config.get('header_logo', 'link'),
        'alt': escape(env.config.get('header_logo', 'alt')),
        'src': src,
        'src_abs': src_abs,
        'width': env.config.get('header_logo', 'width'),
        'height': env.config.get('header_logo', 'height')
    }

    if req:
        hdf['base_url'] = req.base_url
        hdf['base_host'] = req.base_url[:req.base_url.rfind(req.cgi_location)]
        hdf['cgi_location'] = req.cgi_location
        hdf['trac.authname'] = escape(req.authname)

        add_link(req, 'start', env.href.wiki())
        add_link(req, 'search', env.href.search())
        add_link(req, 'help', env.href.wiki('TracGuide'))
        icon = env.config.get('project', 'icon')
        if icon:
            if not icon[0] == '/' and icon.find('://') < 0:
                icon = htdocs_location + icon
            mimetype = env.mimeview.get_mimetype(icon)
            add_link(req, 'icon', icon, type=mimetype)
            add_link(req, 'shortcut icon', icon, type=mimetype)

def absolute_url(req, path=None):
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
    # Re-parse the configuration file if it changed since the last the time it
    # was parsed
    env.config.parse_if_needed()

    base_url = env.config.get('trac', 'base_url')
    if not base_url:
        base_url = absolute_url(req)
    req.base_url = base_url

    env.href = Href(req.cgi_location)
    env.abs_href = Href(req.base_url)

    db = env.get_db_cnx()

    # Let the wiki module build a dictionary of all page names
    from trac.Wiki import populate_page_dict
    populate_page_dict(db, env)

    try:
        try:
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

            from trac.web.clearsilver import HDFWrapper
            req.hdf = HDFWrapper(loadpaths=[env.get_templates_dir(),
                                            env.config.get('trac', 'templates_dir')])
            populate_hdf(req.hdf, env, req)
            req.hdf['HTTP.PathInfo'] = path_info

            newsession = req.args.has_key('newsession')
            req.session = Session(env, db, req, newsession)

            try:
                # Load the selected module
                from trac.Module import module_factory, parse_path_info
                parse_path_info(req.args, path_info)
                module = module_factory(req.args.get('mode', 'wiki'))
                module.env = env
                module.config = env.config
                module.log = env.log
                module.db = db
                module.perm = PermissionCache(module.db, req.authname)
                req.hdf['trac.active_module'] = module._name
                for action in module.perm.permissions():
                    req.hdf['trac.acl.' + action] = 1
                module.render(req)
            finally:
                # Give the session a chance to persist changes
                req.session.save()

        except RequestDone:
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
