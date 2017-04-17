# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2010 Edgewall Software
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

"""Content presentation for the web layer.

The Chrome module deals with delivering and shaping content to the end user,
mostly targeting (X)HTML generation but not exclusively, RSS or other forms of
web content are also using facilities provided here.
"""

from __future__ import with_statement

import datetime
from functools import partial
import itertools
import os.path
import pkg_resources
import pprint
import re
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from genshi import Markup
from genshi.builder import tag, Element
from genshi.core import Attrs, START
from genshi.filters import Translator
from genshi.output import DocType
from genshi.template import TemplateLoader, MarkupTemplate, NewTextTemplate

from trac import __version__ as VERSION
from trac.config import *
from trac.core import *
from trac.env import IEnvironmentSetupParticipant, ISystemInfoProvider
from trac.mimeview.api import RenderingContext, get_mimetype
from trac.resource import *
from trac.util import as_bool, as_int, compat, get_reporter_id, html,\
                      presentation, get_pkginfo, pathjoin, translation
from trac.util.html import escape, plaintext
from trac.util.text import pretty_size, obfuscate_email_address, \
                           shorten_line, unicode_quote_plus, to_unicode, \
                           javascript_quote, exception_to_unicode, to_js_string
from trac.util.datefmt import (
    pretty_timedelta, datetime_now, format_datetime, format_date, format_time,
    from_utimestamp, http_date, utc, get_date_format_jquery_ui, is_24_hours,
    get_time_format_jquery_ui, user_time, get_month_names_jquery_ui,
    get_day_names_jquery_ui, get_timezone_list_jquery_ui,
    get_first_week_day_jquery_ui, get_timepicker_separator_jquery_ui,
    get_period_names_jquery_ui)
from trac.util.html import to_fragment
from trac.util.translation import _, get_available_locales
from trac.web.api import IRequestHandler, ITemplateStreamFilter, HTTPNotFound
from trac.web.href import Href
from trac.wiki import IWikiSyntaxProvider
from trac.wiki.formatter import format_to, format_to_html, format_to_oneliner


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
        """Should return an iterable object over the list of navigation items
        to add, each being a tuple in the form (category, name, text).
        """


class ITemplateProvider(Interface):
    """Extension point interface for components that provide their own
    Genshi templates and accompanying static resources.
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


def add_meta(req, content, http_equiv=None, name=None, scheme=None, lang=None):
    """Add a `<meta>` tag into the `<head>` of the generated HTML."""
    meta = {'content': content, 'http-equiv': http_equiv, 'name': name,
            'scheme': scheme, 'lang': lang, 'xml:lang': lang}
    req.chrome.setdefault('metas', []).append(meta)


def add_link(req, rel, href, title=None, mimetype=None, classname=None,
             **attrs):
    """Add a link to the chrome info that will be inserted as <link> element in
    the <head> of the generated HTML
    """
    linkid = '%s:%s' % (rel, href)
    linkset = req.chrome.setdefault('linkset', set())
    if linkid in linkset:
        return # Already added that link

    link = {'href': href, 'title': title, 'type': mimetype, 'class': classname}
    link.update(attrs)
    links = req.chrome.setdefault('links', {})
    links.setdefault(rel, []).append(link)
    linkset.add(linkid)


def add_stylesheet(req, filename, mimetype='text/css', media=None):
    """Add a link to a style sheet to the chrome info so that it gets included
    in the generated HTML page.

    If `filename` is a network-path reference (i.e. starts with a protocol
    or `//`), the return value will not be modified. If `filename` is absolute
    (i.e. starts with `/`), the generated link will be based off the
    application root path. If it is relative, the link will be based off the
    `/chrome/` path.
    """
    href = chrome_resource_path(req, filename)
    add_link(req, 'stylesheet', href, mimetype=mimetype, media=media)


def add_script(req, filename, mimetype='text/javascript', charset='utf-8',
               ie_if=None):
    """Add a reference to an external javascript file to the template.

    If `filename` is a network-path reference (i.e. starts with a protocol
    or `//`), the return value will not be modified. If `filename` is absolute
    (i.e. starts with `/`), the generated link will be based off the
    application root path. If it is relative, the link will be based off the
    `/chrome/` path.
    """
    scriptset = req.chrome.setdefault('scriptset', set())
    if filename in scriptset:
        return False # Already added that script

    href = chrome_resource_path(req, filename)
    script = {'href': href, 'type': mimetype, 'charset': charset,
              'prefix': Markup('<!--[if %s]>' % ie_if) if ie_if else None,
              'suffix': Markup('<![endif]-->') if ie_if else None}

    req.chrome.setdefault('scripts', []).append(script)
    scriptset.add(filename)


def add_script_data(req, data={}, **kwargs):
    """Add data to be made available in javascript scripts as global variables.

    The keys in `data` and the keyword argument names provide the names of the
    global variables. The values are converted to JSON and assigned to the
    corresponding variables.
    """
    script_data = req.chrome.setdefault('script_data', {})
    script_data.update(data)
    script_data.update(kwargs)


def add_javascript(req, filename):
    """:deprecated: since 0.10, use `add_script` instead."""
    add_script(req, filename, mimetype='text/javascript')


def add_warning(req, msg, *args):
    """Add a non-fatal warning to the request object.

    When rendering pages, all warnings will be rendered to the user. Note that
    the message is escaped (and therefore converted to `Markup`) before it is
    stored in the request object.
    """
    _add_message(req, 'warnings', msg, args)


def add_notice(req, msg, *args):
    """Add an informational notice to the request object.

    When rendering pages, all notices will be rendered to the user. Note that
    the message is escaped (and therefore converted to `Markup`) before it is
    stored in the request object.
    """
    _add_message(req, 'notices', msg, args)


def _add_message(req, name, msg, args):
    if args:
        msg %= args
    if not isinstance(msg, Markup):
        msg = Markup(to_fragment(msg))
    if msg not in req.chrome[name]:
        req.chrome[name].append(msg)


def add_ctxtnav(req, elm_or_label, href=None, title=None):
    """Add an entry to the current page's ctxtnav bar."""
    if href:
        elm = tag.a(elm_or_label, href=href, title=title)
    else:
        elm = elm_or_label
    req.chrome.setdefault('ctxtnav', []).append(elm)


def prevnext_nav(req, prev_label, next_label, up_label=None):
    """Add Previous/Up/Next navigation links.

       :param        req: a `Request` object
       :param prev_label: the label to use for left (previous) link
       :param   up_label: the label to use for the middle (up) link
       :param next_label: the label to use for right (next) link
    """
    links = req.chrome['links']
    prev_link = next_link = None

    if not any(lnk in links for lnk in ('prev', 'up', 'next')): # Short circuit
        return

    if 'prev' in links:
        prev = links['prev'][0]
        prev_link = tag.a(prev_label, href=prev['href'], title=prev['title'],
                          class_='prev')

    add_ctxtnav(req, tag.span(Markup('&larr; '), prev_link or prev_label,
                              class_='missing' if not prev_link else None))

    if up_label and 'up' in links:
        up = links['up'][0]
        add_ctxtnav(req, tag.a(up_label, href=up['href'], title=up['title']))

    if 'next' in links:
        next_ = links['next'][0]
        next_link = tag.a(next_label, href=next_['href'], title=next_['title'],
                          class_='next')

    add_ctxtnav(req, tag.span(next_link or next_label, Markup(' &rarr;'),
                              class_='missing' if not next_link else None))


def web_context(req, resource=None, id=False, version=False, parent=False,
                absurls=False):
    """Create a rendering context from a request.

    The `perm` and `href` properties of the context will be initialized
    from the corresponding properties of the request object.

    >>> from trac.test import Mock, MockPerm
    >>> req = Mock(href=Mock(), perm=MockPerm())
    >>> context = web_context(req)
    >>> context.href is req.href
    True
    >>> context.perm is req.perm
    True

    :param      req: the HTTP request object
    :param resource: the `Resource` object or realm
    :param       id: the resource identifier
    :param  version: the resource version
    :param  absurls: whether URLs generated by the ``href`` object should
                     be absolute (including the protocol scheme and host
                     name)
    :return: a new rendering context
    :rtype: `RenderingContext`

    :since: version 1.0
    """
    if req:
        href = req.abs_href if absurls else req.href
        perm = req.perm
    else:
        href = None
        perm = None
    self = RenderingContext(Resource(resource, id=id, version=version,
                                     parent=parent), href=href, perm=perm)
    self.req = req
    return self


def auth_link(req, link):
    """Return an "authenticated" link to `link` for authenticated users.

    If the user is anonymous, returns `link` unchanged. For authenticated
    users, returns a link to `/login` that redirects to `link` after
    authentication.
    """
    if req.authname != 'anonymous':
        return req.href.login(referer=link)
    return link


def chrome_info_script(req, use_late=None):
    """Get script elements from chrome info of the request object during
    rendering template or after rendering.

    :param      req: the HTTP request object.
    :param use_late: if True, `late_links` will be used instead of `links`.
    """
    chrome = req.chrome
    if use_late:
        links = chrome.get('late_links', {}).get('stylesheet', [])
        scripts = chrome.get('late_scripts', [])
        script_data = chrome.get('late_script_data', {})
    else:
        links = chrome.get('early_links', {}).get('stylesheet', []) + \
                chrome.get('links', {}).get('stylesheet', [])
        scripts = chrome.get('early_scripts', []) + chrome.get('scripts', [])
        script_data = {}
        script_data.update(chrome.get('early_script_data', {}))
        script_data.update(chrome.get('script_data', {}))

    content = []
    content.extend('jQuery.loadStyleSheet(%s, %s);' %
                   (to_js_string(link['href']), to_js_string(link['type']))
                   for link in links or ())
    content.extend('var %s=%s;' % (name, presentation.to_json(value))
                   for name, value in (script_data or {}).iteritems())

    fragment = tag()
    if content:
        fragment.append(tag.script('\n'.join(content), type='text/javascript'))
    for script in scripts:
        fragment.append(script['prefix'])
        fragment.append(tag.script(
            'jQuery.loadScript(%s, %s, %s)' %
            (to_js_string(script['href']), to_js_string(script['type']),
             to_js_string(script['charset'])), type='text/javascript'))
        fragment.append(script['suffix'])

    return fragment


def chrome_resource_path(req, filename):
    """Get the path for a chrome resource given its `filename`.

    If `filename` is a network-path reference (i.e. starts with a protocol
    or `//`), the return value will not be modified. If `filename` is absolute
    (i.e. starts with `/`), the generated link will be based off the
    application root path. If it is relative, the link will be based off the
    `/chrome/` path.
    """
    if filename.startswith(('http://', 'https://', '//')):
        return filename
    elif filename.startswith('common/') and 'htdocs_location' in req.chrome:
        return Href(req.chrome['htdocs_location'])(filename[7:])
    else:
        href = req.href if filename.startswith('/') else req.href.chrome
        return href(filename)


_chrome_resource_path = chrome_resource_path  # will be removed in 1.3.1


def _save_messages(req, url, permanent):
    """Save warnings and notices in case of redirect, so that they can
    be displayed after the redirect."""
    for type_ in ['warnings', 'notices']:
        for (i, message) in enumerate(req.chrome[type_]):
            req.session['chrome.%s.%d' % (type_, i)] = escape(message, False)


# Mappings for removal of control characters
_translate_nop = "".join([chr(i) for i in range(256)])
_invalid_control_chars = "".join([chr(i) for i in range(32)
                                  if i not in [0x09, 0x0a, 0x0d]])


class Chrome(Component):
    """Web site chrome assembly manager.

    Chrome is everything that is not actual page content.
    """
    required = True

    implements(ISystemInfoProvider, IEnvironmentSetupParticipant,
               IRequestHandler, ITemplateProvider, IWikiSyntaxProvider)

    navigation_contributors = ExtensionPoint(INavigationContributor)
    template_providers = ExtensionPoint(ITemplateProvider)
    stream_filters = ExtensionPoint(ITemplateStreamFilter)

    shared_templates_dir = PathOption('inherit', 'templates_dir', '',
        """Path to the //shared templates directory//.

        Templates in that directory are loaded in addition to those in the
        environments `templates` directory, but the latter take precedence.

        (''since 0.11'')""")

    shared_htdocs_dir = PathOption('inherit', 'htdocs_dir', '',
        """Path to the //shared htdocs directory//.

        Static resources in that directory are mapped to /chrome/shared
        under the environment URL, in addition to common and site locations.

        This can be useful in site.html for common interface customization
        of multiple Trac environments.

        (''since 1.0'')""")

    auto_reload = BoolOption('trac', 'auto_reload', False,
        """Automatically reload template files after modification.""")

    genshi_cache_size = IntOption('trac', 'genshi_cache_size', 128,
        """The maximum number of templates that the template loader will cache
        in memory. The default value is 128. You may want to choose a higher
        value if your site uses a larger number of templates, and you have
        enough memory to spare, or you can reduce it if you are short on
        memory.""")

    htdocs_location = Option('trac', 'htdocs_location', '',
        """Base URL for serving the core static resources below
        `/chrome/common/`.

        It can be left empty, and Trac will simply serve those resources
        itself.

        Advanced users can use this together with
        [TracAdmin trac-admin ... deploy <deploydir>] to allow serving the
        static resources for Trac directly from the web server.
        Note however that this only applies to the `<deploydir>/htdocs/common`
        directory, the other deployed resources (i.e. those from plugins)
        will not be made available this way and additional rewrite
        rules will be needed in the web server.""")

    jquery_location = Option('trac', 'jquery_location', '',
        """Location of the jQuery !JavaScript library (version 1.7.2).

        An empty value loads jQuery from the copy bundled with Trac.

        Alternatively, jQuery could be loaded from a CDN, for example:
        http://code.jquery.com/jquery-1.7.2.min.js,
        http://ajax.aspnetcdn.com/ajax/jQuery/jquery-1.7.2.min.js or
        https://ajax.googleapis.com/ajax/libs/jquery/1.7.2/jquery.min.js.

        (''since 1.0'')""")

    jquery_ui_location = Option('trac', 'jquery_ui_location', '',
        """Location of the jQuery UI !JavaScript library (version 1.8.21).

        An empty value loads jQuery UI from the copy bundled with Trac.

        Alternatively, jQuery UI could be loaded from a CDN, for example:
        https://ajax.googleapis.com/ajax/libs/jqueryui/1.8.21/jquery-ui.min.js
        or
        http://ajax.aspnetcdn.com/ajax/jquery.ui/1.8.21/jquery-ui.min.js.

        (''since 1.0'')""")

    jquery_ui_theme_location = Option('trac', 'jquery_ui_theme_location', '',
        """Location of the theme to be used with the jQuery UI !JavaScript
        library (version 1.8.21).

        An empty value loads the custom Trac jQuery UI theme from the copy
        bundled with Trac.

        Alternatively, a jQuery UI theme could be loaded from a CDN, for
        example:
        https://ajax.googleapis.com/ajax/libs/jqueryui/1.8.21/themes/start/jquery-ui.css
        or
        http://ajax.aspnetcdn.com/ajax/jquery.ui/1.8.21/themes/start/jquery-ui.css.

        (''since 1.0'')""")

    metanav_order = ListOption('trac', 'metanav',
                               'login, logout, prefs, help, about', doc=
        """Order of the items to display in the `metanav` navigation bar,
           listed by IDs. See also TracNavigation.""")

    mainnav_order = ListOption('trac', 'mainnav',
                               'wiki, timeline, roadmap, browser, tickets, '
                               'newticket, search', doc=
        """Order of the items to display in the `mainnav` navigation bar,
           listed by IDs. See also TracNavigation.""")

    logo_link = Option('header_logo', 'link', '',
        """URL to link to, from the header logo.""")

    logo_src = Option('header_logo', 'src', 'site/your_project_logo.png',
        """URL of the image to use as header logo.
        It can be absolute, server relative or relative.

        If relative, it is relative to one of the `/chrome` locations:
        `site/your-logo.png` if `your-logo.png` is located in the `htdocs`
        folder within your TracEnvironment;
        `common/your-logo.png` if `your-logo.png` is located in the
        folder mapped to the [#trac-section htdocs_location] URL.
        Only specifying `your-logo.png` is equivalent to the latter.""")

    logo_alt = Option('header_logo', 'alt',
        "(please configure the [header_logo] section in trac.ini)",
        """Alternative text for the header logo.""")

    logo_width = IntOption('header_logo', 'width', -1,
        """Width of the header logo image in pixels.""")

    logo_height = IntOption('header_logo', 'height', -1,
        """Height of the header logo image in pixels.""")

    show_email_addresses = BoolOption('trac', 'show_email_addresses', 'false',
        """Show email addresses instead of usernames. If false, email
        addresses are obfuscated for users that don't have EMAIL_VIEW
        permission. (''since 0.11'')
        """)

    never_obfuscate_mailto = BoolOption('trac', 'never_obfuscate_mailto',
        'false',
        """Never obfuscate `mailto:` links explicitly written in the wiki,
        even if `show_email_addresses` is false or the user doesn't have
        EMAIL_VIEW permission (''since 0.11.6'').
        """)

    show_ip_addresses = BoolOption('trac', 'show_ip_addresses', 'false',
        """Show IP addresses for resource edits (e.g. wiki). Since 1.0.5 this
        option is deprecated and will be removed in 1.3.1. (''since 0.11.3'')
        """)

    resizable_textareas = BoolOption('trac', 'resizable_textareas', 'true',
        """Make `<textarea>` fields resizable. Requires !JavaScript.
        (''since 0.12'')""")

    wiki_toolbars = BoolOption('trac', 'wiki_toolbars', 'true',
        """Add a simple toolbar on top of Wiki <textarea>s.
        (''since 1.0.2'')""")

    auto_preview_timeout = FloatOption('trac', 'auto_preview_timeout', 2.0,
        """Inactivity timeout in seconds after which the automatic wiki preview
        triggers an update. This option can contain floating-point values. The
        lower the setting, the more requests will be made to the server. Set
        this to 0 to disable automatic preview. The default is 2.0 seconds.
        (''since 0.12'')""")

    default_dateinfo_format = Option('trac', 'default_dateinfo_format',
        'relative',
        """The date information format. Valid options are 'relative' for
        displaying relative format and 'absolute' for displaying absolute
        format. (''since 1.0'')
        """)

    use_chunked_encoding = BoolOption('trac', 'use_chunked_encoding', 'false',
        """If enabled, send contents as chunked encoding in HTTP/1.1.
        Otherwise, send contents with `Content-Length` header after entire of
        the contents are rendered. (''since 1.0.6'')""")

    templates = None

    # DocType for 'text/html' output
    html_doctype = DocType.XHTML_STRICT

    # A dictionary of default context data for templates
    _default_context_data = {
        '_': translation.gettext,
        'all': all,
        'any': any,
        'as_bool': as_bool,
        'as_int': as_int,
        'classes': presentation.classes,
        'date': datetime.date,
        'datetime': datetime.datetime,
        'dgettext': translation.dgettext,
        'dngettext': translation.dngettext,
        'first_last': presentation.first_last,
        'find_element': html.find_element,
        'get_reporter_id': get_reporter_id,
        'gettext': translation.gettext,
        'group': presentation.group,
        'groupby': compat.py_groupby, # http://bugs.python.org/issue2246
        'http_date': http_date,
        'istext': presentation.istext,
        'javascript_quote': javascript_quote,
        'ngettext': translation.ngettext,
        'paginate': presentation.paginate,
        'partial': partial,
        'pathjoin': pathjoin,
        'plaintext': plaintext,
        'pprint': pprint.pformat,
        'pretty_size': pretty_size,
        'pretty_timedelta': pretty_timedelta,
        'quote_plus': unicode_quote_plus,
        'reversed': reversed,
        'separated': presentation.separated,
        'shorten_line': shorten_line,
        'sorted': sorted,
        'time': datetime.time,
        'timedelta': datetime.timedelta,
        'to_json': presentation.to_json,
        'to_unicode': to_unicode,
        'utc': utc,
    }

    # ISystemInfoProvider methods

    def get_system_info(self):
        import genshi
        info = get_pkginfo(genshi).get('version')
        if hasattr(genshi, '_speedups'):
            info += ' (with speedups)'
        else:
            info += ' (without speedups)'
        yield 'Genshi', info
        try:
            import babel
        except ImportError:
            babel = None
        if babel is not None:
            info = get_pkginfo(babel).get('version')
            if not get_available_locales():
                info += " (translations unavailable)" # No i18n on purpose
                self.log.warning("Locale data is missing")
            yield 'Babel', info

    # IEnvironmentSetupParticipant methods

    def environment_created(self):
        """Create the environment templates directory."""
        if self.env.path:
            templates_dir = os.path.join(self.env.path, 'templates')
            if not os.path.exists(templates_dir):
                os.mkdir(templates_dir)

            site_path = os.path.join(templates_dir, 'site.html.sample')
            with open(site_path, 'w') as fileobj:
                fileobj.write("""\
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:xi="http://www.w3.org/2001/XInclude"
      xmlns:py="http://genshi.edgewall.org/"
      py:strip="">
  <!--!
    This file allows customizing the appearance of the Trac installation.
    Add your customizations here and rename the file to site.html. Note that
    it will take precedence over a global site.html placed in the directory
    specified by [inherit] templates_dir.

    More information about site appearance customization can be found here:

      http://trac.edgewall.org/wiki/TracInterfaceCustomization#SiteAppearance
  -->
</html>
""")

    def environment_needs_upgrade(self, db):
        return False

    def upgrade_environment(self, db):
        pass

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'/chrome/(?P<prefix>[^/]+)/+(?P<filename>.+)',
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
                        in provider.get_htdocs_dirs() or []
                        if dir[0] == prefix and dir[1]]:
                dirs.append(dir)
                path = os.path.normpath(os.path.join(dir, filename))
                if os.path.commonprefix([dir, path]) != dir:
                    raise TracError(_("Invalid chrome path %(path)s.",
                                      path=filename))
                elif os.path.isfile(path):
                    req.send_file(path, get_mimetype(path))

        self.log.warning('File %s not found in any of %s', filename, dirs)
        raise HTTPNotFound('File %s not found', filename)

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return [('common', pkg_resources.resource_filename('trac', 'htdocs')),
                ('shared', self.shared_htdocs_dir),
                ('site', self.env.htdocs_dir)]

    def get_templates_dirs(self):
        return filter(None, [
            self.env.templates_dir,
            self.shared_templates_dir,
            pkg_resources.resource_filename('trac', 'templates'),
        ])

    # IWikiSyntaxProvider methods

    def get_wiki_syntax(self):
        return []

    def get_link_resolvers(self):
        yield ('htdocs', self._format_link)

    def _format_link(self, formatter, ns, file, label):
        file, query, fragment = formatter.split_link(file)
        href = formatter.href.chrome('site', file) + query + fragment
        return tag.a(label, href=href)

    # Public API methods

    def get_all_templates_dirs(self):
        """Return a list of the names of all known templates directories."""
        dirs = []
        for provider in self.template_providers:
            dirs.extend(provider.get_templates_dirs() or [])
        return dirs

    def prepare_request(self, req, handler=None):
        """Prepare the basic chrome data for the request.

        :param     req: the request object
        :param handler: the `IRequestHandler` instance that is processing the
                        request
        """
        self.log.debug('Prepare chrome data for request')

        chrome = {'metas': [], 'links': {}, 'scripts': [], 'script_data': {},
                  'ctxtnav': [], 'warnings': [], 'notices': []}
        req.chrome = chrome

        htdocs_location = self.htdocs_location or req.href.chrome('common')
        chrome['htdocs_location'] = htdocs_location.rstrip('/') + '/'

        # HTML <head> links
        add_link(req, 'start', req.href.wiki())
        add_link(req, 'search', req.href.search())
        add_link(req, 'help', req.href.wiki('TracGuide'))
        add_stylesheet(req, 'common/css/trac.css')
        add_script(req, self.jquery_location or 'common/js/jquery.js')
        # Only activate noConflict mode if requested to by the handler
        if handler is not None and \
                getattr(handler.__class__, 'jquery_noconflict', False):
            add_script(req, 'common/js/noconflict.js')
        add_script(req, 'common/js/babel.js')
        if req.locale is not None and str(req.locale) != 'en_US':
            add_script(req, 'common/js/messages/%s.js' % req.locale)
        add_script(req, 'common/js/trac.js')
        add_script(req, 'common/js/search.js')

        # Shortcut icon
        chrome['icon'] = self.get_icon_data(req)
        if chrome['icon']:
            src = chrome['icon']['src']
            mimetype = chrome['icon']['mimetype']
            add_link(req, 'icon', src, mimetype=mimetype)
            add_link(req, 'shortcut icon', src, mimetype=mimetype)

        # Logo image
        chrome['logo'] = self.get_logo_data(req.href, req.abs_href)

        # Navigation links
        allitems = {}
        active = None
        for contributor in self.navigation_contributors:
            try:
                for category, name, text in \
                        contributor.get_navigation_items(req) or []:
                    category_section = self.config[category]
                    if category_section.getbool(name, True):
                        # the navigation item is enabled (this is the default)
                        item = text if isinstance(text, Element) and \
                                       text.tag.localname == 'a' \
                                    else None
                        label = category_section.get(name + '.label')
                        href = category_section.get(name + '.href')
                        if href and href.startswith('/'):
                            href = req.href + href
                        if item:
                            if label:
                                item.children[0] = label
                            if href:
                                item = item(href=href)
                        else:
                            if href or label:
                                item = tag.a(label or text, href=href)
                            else:
                                item = text
                        allitems.setdefault(category, {})[name] = item
                if contributor is handler:
                    active = contributor.get_active_navigation_item(req)
            except Exception, e:
                name = contributor.__class__.__name__
                if isinstance(e, TracError):
                    self.log.warning("Error with navigation contributor %s: "
                                     "%s", name, exception_to_unicode(e))
                else:
                    self.log.error("Error with navigation contributor %s: %s",
                                   name,
                                   exception_to_unicode(e, traceback=True))
                add_warning(req, _("Error with navigation contributor "
                                   '"%(name)s"', name=name))

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
                nav[category].append({
                    'name': name,
                    'label': label,
                    'active': name == active
                })

        chrome['nav'] = nav

        # Default theme file
        chrome['theme'] = 'theme.html'

        # Avoid recursion by registering as late as possible (#8583)
        req.add_redirect_listener(_save_messages)

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
            mimetype = get_mimetype(icon_src)
            icon = {'src': icon_src, 'abs_src': icon_abs_src,
                    'mimetype': mimetype}
        return icon

    def get_logo_data(self, href, abs_href=None):
        # TODO: Possibly, links to 'common/' could use chrome.htdocs_location
        logo = {}
        logo_src = self.logo_src
        if logo_src:
            abs_href = abs_href or href
            if logo_src.startswith(('http://', 'https://', '/')):
                # Nothing further can be calculated
                logo_src_abs = logo_src
            elif '/' in logo_src:
                # Like 'common/trac_banner.png' or 'site/my_banner.png'
                logo_src_abs = abs_href.chrome(logo_src)
                logo_src = href.chrome(logo_src)
            else:
                # Like 'trac_banner.png'
                logo_src_abs = abs_href.chrome('common', logo_src)
                logo_src = href.chrome('common', logo_src)
            width = self.logo_width if self.logo_width > -1 else None
            height = self.logo_height if self.logo_height > -1 else None
            logo = {
                'link': self.logo_link, 'src': logo_src,
                'src_abs': logo_src_abs, 'alt': self.logo_alt,
                'width': width, 'height': height
            }
        else:
            logo = {'link': self.logo_link, 'alt': self.logo_alt}
        return logo

    def populate_data(self, req, data):
        d = self._default_context_data.copy()
        d['trac'] = {
            'version': VERSION,
            'homepage': 'http://trac.edgewall.org/', # FIXME: use setup data
        }

        href = req and req.href
        abs_href = req.abs_href if req else self.env.abs_href
        admin_href = None
        if self.env.project_admin_trac_url == '.':
            admin_href = href
        elif self.env.project_admin_trac_url:
            admin_href = Href(self.env.project_admin_trac_url)

        d['project'] = {
            'name': self.env.project_name,
            'descr': self.env.project_description,
            'url': self.env.project_url,
            'admin': self.env.project_admin,
            'admin_href': admin_href,
            'admin_trac_url': self.env.project_admin_trac_url,
        }
        footer = self.env.project_footer
        d['chrome'] = {
            'footer': Markup(footer and translation.gettext(footer))
        }
        if req:
            d['chrome'].update(req.chrome)
        else:
            d['chrome'].update({
                'htdocs_location': self.htdocs_location,
                'logo': self.get_logo_data(self.env.abs_href),
            })

        try:
            show_email_addresses = self.show_email_addresses or \
                                   not req or 'EMAIL_VIEW' in req.perm
        except Exception, e:
            # simply log the exception here, as we might already be rendering
            # the error page
            self.log.error("Error during check of EMAIL_VIEW: %s",
                           exception_to_unicode(e))
            show_email_addresses = False

        def pretty_dateinfo(date, format=None, dateonly=False):
            absolute = user_time(req, format_datetime, date)
            relative = pretty_timedelta(date)
            if not format:
                format = req.session.get('dateinfo',
                                         self.default_dateinfo_format)
            if format == 'absolute':
                if dateonly:
                    label = absolute
                elif req.lc_time == 'iso8601':
                    label = _("at %(iso8601)s", iso8601=absolute)
                else:
                    label = _("on %(date)s at %(time)s",
                              date=user_time(req, format_date, date),
                              time=user_time(req, format_time, date))
                title = _("%(relativetime)s ago", relativetime=relative)
            else:
                label = _("%(relativetime)s ago", relativetime=relative) \
                        if not dateonly else relative
                title = absolute
            return tag.span(label, title=title)

        def dateinfo(date):
            return pretty_dateinfo(date, format='relative', dateonly=True)

        def get_rel_url(resource, **kwargs):
            return get_resource_url(self.env, resource, href, **kwargs)

        def get_abs_url(resource, **kwargs):
            return get_resource_url(self.env, resource, abs_href, **kwargs)

        d.update({
            'context': web_context(req) if req else None,
            'Resource': Resource,
            'url_of': get_rel_url,
            'abs_url_of': get_abs_url,
            'name_of': partial(get_resource_name, self.env),
            'shortname_of': partial(get_resource_shortname, self.env),
            'summary_of': partial(get_resource_summary, self.env),
            'resource_link': partial(render_resource_link, self.env),
            'req': req,
            'abs_href': abs_href,
            'href': href,
            'perm': req and req.perm,
            'authname': req.authname if req else '<trac>',
            'locale': req and req.locale,
            'show_email_addresses': show_email_addresses,
            'show_ip_addresses': self.show_ip_addresses,
            'authorinfo': partial(self.authorinfo, req),
            'authorinfo_short': self.authorinfo_short,
            'format_author': partial(self.format_author, req),
            'format_emails': self.format_emails,
            'get_systeminfo': self.env.get_systeminfo,
            'captioned_button': partial(presentation.captioned_button, req),

            # Date/time formatting
            'dateinfo': dateinfo,
            'pretty_dateinfo': pretty_dateinfo,
            'format_datetime': partial(user_time, req, format_datetime),
            'format_date': partial(user_time, req, format_date),
            'format_time': partial(user_time, req, format_time),
            'fromtimestamp': partial(datetime.datetime.fromtimestamp,
                                     tz=req and req.tz),
            'from_utimestamp': from_utimestamp,

            # Wiki-formatting functions
            'wiki_to': partial(format_to, self.env),
            'wiki_to_html': partial(format_to_html, self.env),
            'wiki_to_oneliner': partial(format_to_oneliner, self.env),
        })

        # Finally merge in the page-specific data
        d.update(data)
        return d

    def load_template(self, filename, method=None):
        """Retrieve a Template and optionally preset the template data.

        Also, if the optional `method` argument is set to `'text'`, a
        `NewTextTemplate` instance will be created instead of a
        `MarkupTemplate`.
        """
        if not self.templates:
            self.templates = TemplateLoader(
                self.get_all_templates_dirs(), auto_reload=self.auto_reload,
                max_cache_size=self.genshi_cache_size,
                default_encoding="utf-8",
                variable_lookup='lenient', callback=lambda template:
                Translator(translation.get_translations()).setup(template))

        if method == 'text':
            cls = NewTextTemplate
        else:
            cls = MarkupTemplate

        return self.templates.load(filename, cls=cls)

    def render_template(self, req, filename, data, content_type=None,
                        fragment=False, iterable=False):
        """Render the `filename` using the `data` for the context.

        The `content_type` argument is used to choose the kind of template
        used (`NewTextTemplate` if `'text/plain'`, `MarkupTemplate`
        otherwise), and tweak the rendering process. Doctype for `'text/html'`
        can be specified by setting the `html_doctype` attribute (default
        is `XHTML_STRICT`)

        When `fragment` is specified, the (filtered) Genshi stream is
        returned.

        When `iterable` is specified, the content as an iterable instance
        which is generated from filtered Genshi stream is returned.
        """
        if content_type is None:
            content_type = 'text/html'
        method = {'text/html': 'xhtml',
                  'text/plain': 'text'}.get(content_type, 'xml')

        if method == "xhtml":
            # Retrieve post-redirect messages saved in session
            for type_ in ['warnings', 'notices']:
                try:
                    for i in itertools.count():
                        message = Markup(req.session.pop('chrome.%s.%d'
                                                         % (type_, i)))
                        if message not in req.chrome[type_]:
                            req.chrome[type_].append(message)
                except KeyError:
                    pass

        template = self.load_template(filename, method=method)
        data = self.populate_data(req, data)
        data['chrome']['content_type'] = content_type

        stream = template.generate(**data)

        # Filter through ITemplateStreamFilter plugins
        if self.stream_filters:
            stream |= self._filter_stream(req, method, filename, stream, data)

        if fragment:
            return stream

        if method == 'text':
            buffer = StringIO()
            stream.render('text', out=buffer, encoding='utf-8')
            return buffer.getvalue()

        doctype = None
        if content_type == 'text/html':
            doctype = self.html_doctype
            if req.form_token:
                stream |= self._add_form_token(req.form_token)
            if not int(req.session.get('accesskeys', 0)):
                stream |= self._strip_accesskeys

        links = req.chrome.get('links')
        scripts = req.chrome.get('scripts')
        script_data = req.chrome.get('script_data')
        req.chrome.update({'early_links': links, 'early_scripts': scripts,
                           'early_script_data': script_data,
                           'links': {}, 'scripts': [], 'script_data': {}})
        data.setdefault('chrome', {}).update({
            'late_links': req.chrome['links'],
            'late_scripts': req.chrome['scripts'],
            'late_script_data': req.chrome['script_data'],
        })

        if iterable:
            return self.iterable_content(stream, method, doctype=doctype)

        try:
            buffer = StringIO()
            stream.render(method, doctype=doctype, out=buffer,
                          encoding='utf-8')
            return buffer.getvalue().translate(_translate_nop,
                                               _invalid_control_chars)
        except Exception, e:
            # restore what may be needed by the error template
            req.chrome.update({'early_links': None, 'early_scripts': None,
                               'early_script_data': None, 'links': links,
                               'scripts': scripts, 'script_data': script_data})
            # give some hints when hitting a Genshi unicode error
            if isinstance(e, UnicodeError):
                pos = self._stream_location(stream)
                if pos:
                    location = "'%s', line %s, char %s" % pos
                else:
                    location = '%s %s' % (filename,
                                          _("(unknown template location)"))
                raise TracError(_("Genshi %(error)s error while rendering "
                                  "template %(location)s",
                                  error=e.__class__.__name__,
                                  location=location))
            raise

    def get_interface_customization_files(self):
        """Returns a dictionary containing the lists of files present in the
        site and shared templates and htdocs directories.
        """
        def list_dir(path, suffix=None):
            if not os.path.isdir(path):
                return []
            return sorted(name for name in os.listdir(path)
                               if suffix is None or name.endswith(suffix))

        files = {}
        # Collect templates list
        site_templates = list_dir(self.env.templates_dir, '.html')
        shared_templates = list_dir(Chrome(self.env).shared_templates_dir,
                                    '.html')

        # Collect static resources list
        site_htdocs = list_dir(self.env.htdocs_dir)
        shared_htdocs = list_dir(Chrome(self.env).shared_htdocs_dir)

        if any((site_templates, shared_templates, site_htdocs, shared_htdocs)):
            files = {
                'site-templates': site_templates,
                'shared-templates': shared_templates,
                'site-htdocs': site_htdocs,
                'shared-htdocs': shared_htdocs,
            }
        return files

    def iterable_content(self, stream, method, **kwargs):
        """Generate an iterable object which iterates `str` instances
        from the given stream instance.

        :param method: the serialization method; can be either "xml",
                       "xhtml", "html", "text", or a custom serializer
                       class
        """
        try:
            if method == 'text':
                for chunk in stream.serialize(method, **kwargs):
                    yield chunk.encode('utf-8')
            else:
                for chunk in stream.serialize(method, **kwargs):
                    yield chunk.encode('utf-8') \
                               .translate(_translate_nop,
                                          _invalid_control_chars)
        except Exception, e:
            pos = self._stream_location(stream)
            if pos:
                location = "'%s', line %s, char %s" % pos
            else:
                location = '(unknown template location)'
            self.log.error('Genshi %s error while rendering template %s%s',
                           e.__class__.__name__, location,
                           exception_to_unicode(e, traceback=True))

    # E-mail formatting utilities

    def cc_list(self, cc_field):
        """Split a CC: value in a list of addresses."""
        ccs = []
        for cc in re.split(r'[;,]', cc_field or ''):
            cc = cc.strip()
            if cc:
                ccs.append(cc)
        return ccs

    def format_emails(self, context, value, sep=', '):
        """Normalize a list of e-mails and obfuscate them if needed.

        :param context: the context in which the check for obfuscation should
                        be done
        :param   value: a string containing a comma-separated list of e-mails
        :param     sep: the separator to use when rendering the list again
        """
        all_cc = self.cc_list(value)
        if not (self.show_email_addresses or 'EMAIL_VIEW' in context.perm):
            all_cc = [obfuscate_email_address(cc) for cc in all_cc]
        return sep.join(all_cc)

    def authorinfo(self, req, author, email_map=None):
        return self.format_author(req,
                                  email_map and '@' not in author and
                                  email_map.get(author) or author)

    def get_email_map(self):
        """Get the email addresses of all known users."""
        email_map = {}
        if self.show_email_addresses:
            for username, name, email in self.env.get_known_users():
                if email:
                    email_map[username] = email
        return email_map

    _long_author_re = re.compile(r'.*<([^@]+)@[^@]+>\s*|([^@]+)@[^@]+')

    def authorinfo_short(self, author):
        if not author or author == 'anonymous':
            return _("anonymous")
        match = self._long_author_re.match(author)
        if match:
            return match.group(1) or match.group(2)
        return author

    def format_author(self, req, author):
        if not author or author == 'anonymous':
            return _("anonymous")
        if self.show_email_addresses or not req or 'EMAIL_VIEW' in req.perm:
            return author
        return obfuscate_email_address(author)

    # Element modifiers

    def add_textarea_grips(self, req):
        """Make `<textarea class="trac-resizable">` fields resizable if enabled
        by configuration."""
        if self.resizable_textareas:
            add_script(req, 'common/js/resizer.js')

    def add_wiki_toolbars(self, req):
        """Add wiki toolbars to `<textarea class="wikitext">` fields."""
        if self.wiki_toolbars:
            add_script(req, 'common/js/wikitoolbar.js')
        self.add_textarea_grips(req)

    def add_auto_preview(self, req):
        """Setup auto-preview for `<textarea>` fields."""
        add_script(req, 'common/js/auto_preview.js')
        add_script_data(req, auto_preview_timeout=self.auto_preview_timeout,
                        form_token=req.form_token)

    def add_jquery_ui(self, req):
        """Add a reference to the jQuery UI script and link the stylesheet."""
        add_script(req, self.jquery_ui_location
                        or 'common/js/jquery-ui.js')
        add_stylesheet(req, self.jquery_ui_theme_location
                            or 'common/css/jquery-ui/jquery-ui.css')
        add_script(req, 'common/js/jquery-ui-addons.js')
        add_stylesheet(req, 'common/css/jquery-ui-addons.css')
        is_iso8601 = req.lc_time == 'iso8601'
        now = datetime_now(req.tz)
        tzoffset = now.strftime('%z')
        default_timezone = 'Z' if tzoffset == '+0000' else \
                           tzoffset[:-2] + ':' + tzoffset[-2:]
        if is_iso8601:
            timezone_list = get_timezone_list_jquery_ui(now)
        else:
            # default timezone must be included
            timezone_list = [default_timezone if default_timezone != 'Z' else
                             {'value': 'Z', 'label': '+00:00'}]
        add_script_data(req, jquery_ui={
            'month_names': get_month_names_jquery_ui(req),
            'day_names': get_day_names_jquery_ui(req),
            'date_format': get_date_format_jquery_ui(req.lc_time),
            'time_format': get_time_format_jquery_ui(req.lc_time),
            'ampm': not is_24_hours(req.lc_time),
            'period_names': get_period_names_jquery_ui(req),
            'first_week_day': get_first_week_day_jquery_ui(req),
            'timepicker_separator': get_timepicker_separator_jquery_ui(req),
            'show_timezone': is_iso8601,
            'default_timezone': default_timezone,
            'timezone_list': timezone_list,
            'timezone_iso8601': is_iso8601,
        })
        add_script(req, 'common/js/jquery-ui-i18n.js')

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
                data = data[0], Attrs([(k, v) for k, v in data[1]
                                       if k != 'accesskey'])
            yield kind, data, pos

    def _filter_stream(self, req, method, filename, stream, data):
        def inner(stream, ctxt=None):
            for filter in self.stream_filters:
                stream = filter.filter_stream(req, method, filename, stream,
                                              data)
            return stream
        return inner

    def _stream_location(self, stream):
        for kind, data, pos in stream:
            return pos
