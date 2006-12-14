# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2006 Edgewall Software
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

import datetime
import os
import pprint
import re

from genshi import Markup
from genshi.builder import tag
from genshi.core import Attrs, START
from genshi.output import DocType
from genshi.template import TemplateLoader, MarkupTemplate, TextTemplate

from trac import __version__ as VERSION
from trac import mimeview
from trac.config import *
from trac.core import *
from trac.env import IEnvironmentSetupParticipant
from trac.util import compat, get_reporter_id, presentation, get_pkginfo, \
                      get_module_path
from trac.util.compat import partial, set
from trac.util.html import plaintext
from trac.util.text import pretty_size, shorten_line, unicode_quote_plus, \
                           to_unicode
from trac.util.datefmt import pretty_timedelta, format_datetime, format_date, \
                              format_time, http_date
from trac.web.api import IRequestHandler, HTTPNotFound
from trac.web.href import Href
from trac.wiki import IWikiSyntaxProvider

def add_link(req, rel, href, title=None, mimetype=None, classname=None):
    """Add a link to the HDF data set that will be inserted as <link> element in
    the <head> of the generated HTML
    """
    linkid = '%s:%s' % (rel, href)
    linkset = req.chrome.setdefault('linkset', set())
    if linkid in linkset:
        return # Already added that link

    link = {'href': href}
    if title:
        link['title'] = title
    if mimetype:
        link['type'] = mimetype
    if classname:
        link['class'] = classname

    links = req.chrome.setdefault('links', {})
    links.setdefault(rel, []).append(link)
    linkset.add(linkid)

def add_stylesheet(req, filename, mimetype='text/css'):
    """Add a link to a style sheet to the HDF data set so that it gets included
    in the generated HTML page.
    
    If the filename is absolute (i.e. starts with a slash), the generated link
    will be based off the application root path. If it is relative, the link
    will be based off the `/chrome/` path.
    """
    if filename.startswith('common/') and 'htdocs_location' in req.chrome:
        href = Href(req.chrome['htdocs_location'])
        filename = filename[7:]
    else:
        href = req.href
        if not filename.startswith('/'):
            href = href.chrome
    add_link(req, 'stylesheet', href(filename), mimetype=mimetype)

def add_script(req, filename, mimetype='text/javascript'):
    """Add a reference to an external javascript file to the template.
    
    If the filename is absolute (i.e. starts with a slash), the generated link
    will be based off the application root path. If it is relative, the link
    will be based off the `/chrome/` path.
    """
    scriptset = req.chrome.setdefault('trac.chrome.scriptset', set())
    if filename in scriptset:
        return False # Already added that script

    if filename.startswith('common/') and 'htdocs_location' in req.chrome:
        href = Href(req.chrome['htdocs_location'])
        path = filename[7:]
    else:
        href = req.href
        if not filename.startswith('/'):
            href = href.chrome
        path = filename
    script = {'href': href(path), 'type': mimetype}

    req.chrome.setdefault('scripts', []).append(script)
    scriptset.add(filename)

def add_javascript(req, filename):
    """Deprecated: use `add_script()` instead."""
    add_script(req, filename, mimetype='text/javascript')


class INavigationContributor(Interface):
    """Extension point interface for components that contribute items to the
    navigation.
    """

    def get_active_navigation_item(req):
        """This method is only called for the `IRequestHandler` processing the
        request.
        
        It should return the name of the navigation item that should be
        highlighted as active/current.
        """

    def get_navigation_items(req):
        """Should return an iterable object over the list of navigation items to
        add, each being a tuple in the form (category, name, text).
        """


class ITemplateProvider(Interface):
    """Extension point interface for components that provide their own
    ClearSilver templates and accompanying static resources.
    """

    def get_htdocs_dirs():
        """Return a list of directories with static resources (such as style
        sheets, images, etc.)

        Each item in the list must be a `(prefix, abspath)` tuple. The
        `prefix` part defines the path in the URL that requests to these
        resources are prefixed with.
        
        The `abspath` is the absolute path to the directory containing the
        resources on the local file system.
        """

    def get_templates_dirs():
        """Return a list of directories containing the provided template
        files.
        """


class Chrome(Component):
    """Responsible for assembling the web site chrome, i.e. everything that
    is not actual page content.
    """
    implements(IEnvironmentSetupParticipant, IRequestHandler, ITemplateProvider,
               IWikiSyntaxProvider)

    navigation_contributors = ExtensionPoint(INavigationContributor)
    template_providers = ExtensionPoint(ITemplateProvider)

    templates_dir = Option('trac', 'templates_dir', default_dir('templates'),
        """Path to the template files.""")

    auto_reload = Option('trac', 'auto_reload', False,
        """Automatically reload template files after modification.""")

    htdocs_location = Option('trac', 'htdocs_location', '',
        """Base URL of the core static resources.""")

    metanav_order = ListOption('trac', 'metanav',
                               'login,logout,prefs,help,about', doc=
        """List of items IDs to display in the navigation bar `metanav`.""")

    mainnav_order = ListOption('trac', 'mainnav',
                               'wiki,timeline,roadmap,browser,tickets,'
                               'newticket,search', doc=
        """List of item IDs to display in the navigation bar `mainnav`.""")

    logo_link = Option('header_logo', 'link', 'http://example.org/',
        """URL to link to from header logo.""")

    logo_src = Option('header_logo', 'src', 'common/trac_banner.png',
        """URL of the image to use as header logo.""")

    logo_alt = Option('header_logo', 'alt', '',
        """Alternative text for the header logo.""")

    logo_width = IntOption('header_logo', 'width', -1,
        """Width of the header logo image in pixels.""")

    logo_height = IntOption('header_logo', 'height', -1,
        """Height of the header logo image in pixels.""")

    templates = None

    # A dictionary of default context data for templates
    _default_context_data = {
        'all': compat.all,
        'any': compat.any,
        'attrgetter': compat.attrgetter,
        'date': datetime.date,
        'datetime': datetime.datetime,
        'first_last': presentation.first_last,
        'get_reporter_id': get_reporter_id,
        'group': presentation.group,
        'groupby': compat.groupby,
        'http_date': http_date,
        'itemgetter': compat.itemgetter,
        'paginate': presentation.paginate,
        'partial': partial,
        'plaintext': plaintext,
        'pprint': pprint.pformat,
        'pretty_size': pretty_size,
        'pretty_timedelta': pretty_timedelta,
        'quote_plus': unicode_quote_plus,
        'reversed': compat.reversed,
        'shorten_line': shorten_line,
        'sorted': compat.sorted,
        'time': datetime.time,
        'timedelta': datetime.timedelta,
        'to_unicode': to_unicode,
    }

    def __init__(self):
        import genshi
        self.env.systeminfo.append(('Genshi',
                                    get_pkginfo(genshi).get('version')))

    # IEnvironmentSetupParticipant methods

    def environment_created(self):
        """Create the environment templates directory."""
        if self.env.path:
            templates_dir = os.path.join(self.env.path, 'templates')
            if not os.path.exists(templates_dir):
                os.mkdir(templates_dir)

            fileobj = open(os.path.join(templates_dir, 'site.html'), 'w')
            try:
                fileobj.write("""<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:py="http://genshi.edgewall.org/" py:strip="">
  <!-- Custom match templates fo here -->
</html>""")
            finally:
                fileobj.close()


    def environment_needs_upgrade(self, db):
        return False

    def upgrade_environment(self, db):
        pass

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'/chrome/(?P<prefix>[^/]+)/+(?P<filename>[/\w\-\.]+)',
                         req.path_info)
        if match:
            req.args['prefix'] = match.group('prefix')
            req.args['filename'] = match.group('filename')
            return True

    def process_request(self, req):
        prefix = req.args['prefix']
        filename = req.args['filename']

        dirs = []
        for provider in self.template_providers:
            for dir in [os.path.normpath(dir[1]) for dir
                        in provider.get_htdocs_dirs() if dir[0] == prefix]:
                dirs.append(dir)
                path = os.path.normpath(os.path.join(dir, filename))
                assert os.path.commonprefix([dir, path]) == dir
                if os.path.isfile(path):
                    req.send_file(path, mimeview.get_mimetype(path))

        self.log.warning('File %s not found in any of %s', filename, dirs)
        raise HTTPNotFound('File %s not found', filename)

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        from trac.config import default_dir
        return [('common', default_dir('htdocs')),
                ('site', self.env.get_htdocs_dir())]

    def get_templates_dirs(self):
        return [self.env.get_templates_dir(), self.templates_dir]

    # IWikiSyntaxProvider methods
    
    def get_wiki_syntax(self):
        return []
    
    def get_link_resolvers(self):
        yield ('htdocs', self._format_link)

    def _format_link(self, formatter, ns, file, label):
        return tag.a(label, href=formatter.href.chrome('site', file))

    # Public API methods

    def get_all_templates_dirs(self):
        """Return a list of the names of all known templates directories."""
        dirs = []
        for provider in self.template_providers:
            dirs += provider.get_templates_dirs()
        return dirs

    def prepare_request(self, req, handler=None):
        """Prepare the basic chrome data for the request.
        
        @param req: the request object
        @param handler: the `IRequestHandler` instance that is processing the
            request
        """
        self.log.debug('Prepare chrome data for request')

        chrome = {'links': {}, 'scripts': []}

        # This is ugly... we can't pass the real Request object to the
        # add_xxx methods, because it doesn't yet have the chrome attribute
        class FakeRequest(object):
            def __init__(self, req):
                self.base_path = req.base_path
                self.chrome = chrome
        fakereq = FakeRequest(req)

        htdocs_location = self.htdocs_location or req.href.chrome('common')
        chrome['htdocs_location'] = htdocs_location.rstrip('/') + '/'

        # HTML <head> links
        add_link(fakereq, 'start', req.href.wiki())
        add_link(fakereq, 'search', req.href.search())
        add_link(fakereq, 'help', req.href.wiki('TracGuide'))
        add_stylesheet(fakereq, 'common/css/trac.css')
        add_script(fakereq, 'common/js/jquery.js')
        add_script(fakereq, 'common/js/trac.js')
        add_script(fakereq, 'common/js/search.js')

        # Shortcut icon
        chrome['icon'] = self.get_icon_data(req)
        if chrome['icon']:
            src = chrome['icon']['src']
            mimetype = chrome['icon']['mimetype']
            add_link(fakereq, 'icon', src, mimetype=mimetype)
            add_link(fakereq, 'shortcut icon', src, mimetype=mimetype)

        # Logo image
        chrome['logo'] = self.get_logo_data(req.href)

        # Navigation links
        allitems = {}
        active = None
        for contributor in self.navigation_contributors:
            for category, name, text in contributor.get_navigation_items(req):
                allitems.setdefault(category, {})[name] = text
            if contributor is handler:
                active = contributor.get_active_navigation_item(req)

        nav = {}
        for category, items in [(k, v.items()) for k, v in allitems.items()]:
            category_order = category + '_order'
            if hasattr(self, category_order):
                order = getattr(self, category_order)
                def navcmp(x, y):
                    if x[0] not in order:
                        return int(y[0] in order)
                    if y[0] not in order:
                        return -int(x[0] in order)
                    return cmp(order.index(x[0]), order.index(y[0]))
                items.sort(navcmp)

            nav[category] = []
            for name, label in items:
                nav[category].append({'name': name, 'label': label})
                if name == active:
                    nav[category][-1]['active'] = True

        chrome['nav'] = nav

        return chrome


    def get_icon_data(self, req):
        icon = {}
        icon_src = icon_abs_src = self.env.project_icon
        if icon_src:
            if not icon_src.startswith('/') and icon_src.find('://') == -1:
                if '/' in icon_src:
                    icon_abs_src = req.abs_href.chrome(icon_src)
                    icon_src = req.href.chrome(icon_src)
                else:
                    icon_abs_src = req.abs_href.chrome('common', icon_src)
                    icon_src = req.href.chrome('common', icon_src)
            mimetype = mimeview.get_mimetype(icon_src)
            icon = {'src': icon_src, 'abs_src': icon_abs_src,
                    'mimetype': mimetype}
        return icon

    def get_logo_data(self, href):
        logo = {}
        logo_src = self.logo_src
        if logo_src:
            logo_src_abs = logo_src.startswith('http://') or \
                           logo_src.startswith('https://')
            if not logo_src.startswith('/') and not logo_src_abs:
                if '/' in logo_src:
                    logo_src = href.chrome(logo_src)
                else:
                    logo_src = href.chrome('common', logo_src)
            width = self.logo_width > -1 and self.logo_width or None
            height = self.logo_height > -1 and self.logo_height or None
            logo = {
                'link': self.logo_link, 'src': logo_src,
                'src_abs': logo_src_abs, 'alt': self.logo_alt,
                'width': width, 'height': height
            }
        else:
            logo = {'link': self.logo_link, 'alt': self.logo_alt}
        return logo

    def populate_hdf(self, req):
        """Add chrome-related data to the HDF (deprecated)."""
        req.hdf['HTTP.PathInfo'] = req.path_info
        req.hdf['htdocs_location'] = req.chrome['htdocs_location']

        req.hdf['chrome.href'] = req.href.chrome()
        req.hdf['chrome.links'] = req.chrome['links']
        req.hdf['chrome.scripts'] = req.chrome['scripts']
        req.hdf['chrome.logo'] = req.chrome['logo']

        for category, items in req.chrome['nav'].items():
            for item in items:
                prefix = 'chrome.nav.%s.%s' % (category, item['name'])
                req.hdf[prefix] = item['label']

    def populate_data(self, req, data):
        d = self._default_context_data.copy()
        d['trac'] = {
            'version': VERSION,
            'homepage': 'http://trac.edgewall.org/', # FIXME: use setup data
            'systeminfo': self.env.systeminfo,
        }
        d['project'] = {
            'name': self.env.project_name,
            'descr': self.env.project_description,
            'url': self.env.project_url,
            'admin': self.env.project_admin,
        }
        d['chrome'] = {
            'footer': Markup(self.env.project_footer)
        }
        if req:
            d['chrome'].update(req.chrome)
        else:
            d['chrome'].update({
                'htdocs_location': self.htdocs_location,
                'logo': self.get_logo_data(self.env.abs_href),
            })

        tzinfo = None
        if req:
            tzinfo = req.tz

        d.update({
            'req': req,
            'abs_href': req and req.abs_href or self.env.abs_href,
            'href': req and req.href,
            'perm': req and req.perm,
            'authname': req and req.authname or '<trac>',

            # Date/time formatting
            'format_datetime': partial(format_datetime, tzinfo=tzinfo),
            'format_date': partial(format_date, tzinfo=tzinfo),
            'format_time': partial(format_time, tzinfo=tzinfo),
            'fromtimestamp': partial(datetime.datetime.fromtimestamp,
                                     tz=tzinfo),
        })

        # Finally merge in the page-specific data
        d.update(data)
        return d

    def load_template(self, filename, method=None):
        """Retrieve a Template and optionally preset the template data.

        Also, if the optional `method` argument is set to `'text'`, a
        TextTemplate instance will be created instead of a MarkupTemplate.
        """
        if not self.templates:
            self.templates = TemplateLoader(self.get_all_templates_dirs(),
                                            auto_reload=self.auto_reload)
        if method == 'text':
            cls = TextTemplate
        else:
            cls = MarkupTemplate

        return self.templates.load(filename, cls=cls)

    def render_template(self, req, filename, data, content_type=None,
                        fragment=False):
        """Render the `filename` using the `data` for the context.

        The `content_type` argument is used to choose the kind of template
        used (TextTemplate if `'text/plain'`, MarkupTemplate otherwise), and
        tweak the rendering process (use of XHTML Strict doctype if
        `'text/html'` is given).
        """
        if content_type is None:
            content_type = 'text/html'
        method = {'text/html': 'xhtml',
                  'text/plain': 'text'}.get(content_type, 'xml')

        template = self.load_template(filename, method=method)
        data = self.populate_data(req, data)

        stream = template.generate(**data)
        if fragment:
            return stream

        if method == 'text':
            return stream.render('text')

        doctype = {'text/html': DocType.XHTML_STRICT}.get(content_type)
        if doctype:
            if req.form_token:
                stream |= self._add_form_token(req.form_token)
            if not req.session or not int(req.session.get('accesskeys', 0)):
                stream |= self._strip_accesskeys

        req.chrome['links'] = {}
        req.chrome['scripts'] = []
        data.setdefault('chrome', {}).update({
            'late_links': req.chrome['links'],
            'late_scripts': req.chrome['scripts'],
        })

        return stream.render(method, doctype=doctype)

    # Template filters

    def _add_form_token(self, token):
        elem = tag.div(
            tag.input(type='hidden', name='__FORM_TOKEN', value=token)
        )
        def _generate(stream, ctxt=None):
            for kind, data, pos in stream:
                if kind is START and data[0].localname == 'form' \
                                 and data[1].get('method', '').lower() == 'post':
                    yield kind, data, pos
                    for event in elem.generate():
                        yield event
                else:
                    yield kind, data, pos
        return _generate

    def _strip_accesskeys(self, stream, ctxt=None):
        for kind, data, pos in stream:
            if kind is START and 'accesskey' in data[1]:
                data = data[0], Attrs([(k,v) for k,v in data[1]
                                       if k != 'accesskey'])
            yield kind, data, pos
