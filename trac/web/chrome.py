# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2020 Edgewall Software
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
# Author: Christopher Lenz <cmlenz@gmx.de>

"""Content presentation for the web layer.

The Chrome module deals with delivering and shaping content to the end
user, mostly targeting (X)HTML generation but not exclusively, RSS or
other forms of web content are also using facilities provided here.

"""

from contextlib import contextmanager
import datetime
import itertools
import io
import operator
import os.path
import pkg_resources
import pprint
import re
from functools import partial

# Legacy Genshi support
from trac.util.html import genshi
if genshi:
    from genshi.core import Attrs, START
    from genshi.filters import Translator
    from genshi.input import HTML, XML
    from genshi.output import DocType
    from genshi.template import TemplateLoader, MarkupTemplate, NewTextTemplate

from jinja2 import FileSystemLoader

from trac.api import IEnvironmentSetupParticipant, ISystemInfoProvider
from trac.config import *
from trac.core import *
from trac.mimeview.api import RenderingContext, get_mimetype
from trac.perm import IPermissionRequestor
from trac.resource import *
from trac.util import as_bool, as_int, get_pkginfo, get_reporter_id, html, \
                      pathjoin, presentation, to_list, translation
from trac.util.html import (Element, Markup, escape, plaintext, tag,
                            to_fragment, valid_html_bytes)
from trac.util.text import (exception_to_unicode, is_obfuscated,
                            javascript_quote, jinja2env,
                            obfuscate_email_address, pretty_size, shorten_line,
                            to_js_string, to_unicode, unicode_quote_plus)
from trac.util.datefmt import (
    pretty_timedelta, datetime_now, format_datetime, format_date, format_time,
    from_utimestamp, http_date, utc, get_date_format_jquery_ui, is_24_hours,
    get_time_format_jquery_ui, user_time, get_month_names_jquery_ui,
    get_day_names_jquery_ui, get_timezone_list_jquery_ui,
    get_first_week_day_jquery_ui, get_timepicker_separator_jquery_ui,
    get_period_names_jquery_ui, localtz)
from trac.util.translation import _, get_available_locales
from trac.web.api import IRequestHandler, ITemplateStreamFilter, HTTPNotFound
from trac.web.href import Href
from trac.wiki import IWikiSyntaxProvider
from trac.wiki.formatter import format_to, format_to_html, format_to_oneliner

default_mainnav_order = ('wiki', 'timeline', 'roadmap', 'browser',
                         'tickets', 'newticket', 'search', 'admin')
default_metanav_order = ('login', 'logout', 'prefs', 'help', 'about')


class INavigationContributor(Interface):
    """Extension point interface for components that contribute items to the
    navigation.
    """

    def get_active_navigation_item(req):
        """This method is only called for the `IRequestHandler` processing
        the request.

        It should return the name of the navigation item to be highlighted
        as active/current.
        """

    def get_navigation_items(req):
        """Should return an iterable object over the list of navigation items
        to add, each being a tuple in the form (category, name, text).

        The category determines the location of the navigation item and
        can be `mainnav` or `metanav`. The name is a unique identifier that
        must match the string returned by get_active_navigation_item.
        The text is typically a link element with text that corresponds
        to the desired label for the navigation item, and an href.
        """


class ITemplateProvider(Interface):
    """Extension point interface for components that provide their own
    Jinja2 templates and/or accompanying static resources.

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


def accesskey(req, key):
    """Helper function for creating accesskey HTML attribute according
    to preference values"""
    return key if req.session.as_int('accesskeys') else None


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
        return  # Already added that link

    link = {'href': href, 'title': title, 'type': mimetype, 'class': classname}
    link.update(attrs)
    links = req.chrome.setdefault('links', {})
    links.setdefault(rel, []).append(link)
    linkset.add(linkid)


def add_stylesheet(req, filename, mimetype='text/css', **attrs):
    """Add a link to a style sheet to the chrome info so that it gets included
    in the generated HTML page.

    If `filename` is a network-path reference (i.e. starts with a protocol
    or `//`), the return value will not be modified. If `filename` is absolute
    (i.e. starts with `/`), the generated link will be based off the
    application root path. If it is relative, the link will be based off the
    `/chrome/` path.
    """
    href = chrome_resource_path(req, filename)
    add_link(req, 'stylesheet', href, mimetype=mimetype, **attrs)


def add_script(req, filename, mimetype='text/javascript', charset='utf-8',
               ie_if=None):
    """Add a reference to an external javascript file to the template.

    If `filename` is a network-path reference (i.e. starts with a protocol
    or `//`), the return value will not be modified. If `filename` is absolute
    (i.e. starts with `/`), the generated link will be based off the
    application root path. If it is relative, the link will be based off the
    `/chrome/` path.

    :deprecated: the `charset` attribute is deprecated for script elements,
                 and the `ie_if` logic is as deprecated as IE itself...
                 These parameters will be removed in Trac 1.5.1.
    """
    scriptset = req.chrome.setdefault('scriptset', set())
    if filename in scriptset:
        return False  # Already added that script

    href = chrome_resource_path(req, filename)
    script = {'attrs': { 'src': href },
              'prefix': Markup('<!--[if %s]>' % ie_if) if ie_if else None,
              'suffix': Markup('<![endif]-->') if ie_if else None}
    if mimetype != 'text/javascript' and mimetype is not None:
        script['attrs']['type'] = mimetype

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

    if not any(lnk in links for lnk in ('prev', 'up', 'next')):  # Short circuit
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
    if req.is_authenticated:
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
        attrs = script['attrs']
        fragment.append(tag.script(
            'jQuery.loadScript(%s, %s)' % (to_js_string(attrs['src']),
                                           to_js_string(attrs.get('type')))))
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


def _save_messages(req, url, permanent):
    """Save warnings and notices in case of redirect, so that they can
    be displayed after the redirect."""
    for type_ in ['warnings', 'notices']:
        for (i, message) in enumerate(req.chrome[type_]):
            req.session['chrome.%s.%d' % (type_, i)] = escape(message, False)


@contextmanager
def component_guard(env, req, component):
    """Traps any runtime exception raised when working with a
    component, logs the error and adds a warning for the user.

    """
    with env.component_guard(component):
        try:
            yield
        except Exception as e:
            add_warning(req, _("%(component)s failed with %(exc)s",
                               component=component.__class__.__name__,
                               exc=exception_to_unicode(e)))
            raise


class Chrome(Component):
    """Web site chrome assembly manager.

    Chrome is everything that is not actual page content.
    """

    implements(ISystemInfoProvider, IEnvironmentSetupParticipant,
               IPermissionRequestor, IRequestHandler, ITemplateProvider,
               IWikiSyntaxProvider)

    required = True
    is_valid_default_handler = False

    navigation_contributors = ExtensionPoint(INavigationContributor)
    template_providers = ExtensionPoint(ITemplateProvider)
    stream_filters = ExtensionPoint(ITemplateStreamFilter)  # TODO (1.5.1): del

    shared_templates_dir = PathOption('inherit', 'templates_dir', '',
        """Path to the //shared templates directory//.

        Templates in that directory are loaded in addition to those in the
        environments `templates` directory, but the latter take precedence.

        Non-absolute paths are relative to the Environment `conf`
        directory.
        """)

    shared_htdocs_dir = PathOption('inherit', 'htdocs_dir', '',
        """Path to the //shared htdocs directory//.

        Static resources in that directory are mapped to /chrome/shared
        under the environment URL, in addition to common and site locations.

        This can be useful in site.html for common interface customization
        of multiple Trac environments.

        Non-absolute paths are relative to the Environment `conf`
        directory.
        (''since 1.0'')""")

    auto_reload = BoolOption('trac', 'auto_reload', False,
        """Automatically reload template files after modification.""")

    genshi_cache_size = IntOption('trac', 'genshi_cache_size', 128,
        """The maximum number of templates that the template loader will cache
        in memory. You may want to choose a higher value if your site uses a
        larger number of templates, and you have enough memory to spare, or
        you can reduce it if you are short on memory.

        (''deprecated, will be removed in Trac 1.5.1'')
        """)

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
        """Location of the jQuery !JavaScript library (version %(version)s).

        An empty value loads jQuery from the copy bundled with Trac.

        Alternatively, jQuery could be loaded from a CDN, for example:
        http://code.jquery.com/jquery-%(version)s.min.js,
        http://ajax.aspnetcdn.com/ajax/jQuery/jquery-%(version)s.min.js or
        https://ajax.googleapis.com/ajax/libs/jquery/%(version)s/jquery.min.js.

        (''since 1.0'')""", doc_args={'version': '1.12.4'})

    jquery_ui_location = Option('trac', 'jquery_ui_location', '',
        """Location of the jQuery UI !JavaScript library (version %(version)s).

        An empty value loads jQuery UI from the copy bundled with Trac.

        Alternatively, jQuery UI could be loaded from a CDN, for example:
        https://ajax.googleapis.com/ajax/libs/jqueryui/%(version)s/jquery-ui.min.js
        or
        http://ajax.aspnetcdn.com/ajax/jquery.ui/%(version)s/jquery-ui.min.js.

        (''since 1.0'')""", doc_args={'version': '1.12.1'})

    jquery_ui_theme_location = Option('trac', 'jquery_ui_theme_location', '',
        """Location of the theme to be used with the jQuery UI !JavaScript
        library (version %(version)s).

        An empty value loads the custom Trac jQuery UI theme from the copy
        bundled with Trac.

        Alternatively, a jQuery UI theme could be loaded from a CDN, for
        example:
        https://ajax.googleapis.com/ajax/libs/jqueryui/%(version)s/themes/start/jquery-ui.css
        or
        http://ajax.aspnetcdn.com/ajax/jquery.ui/%(version)s/themes/start/jquery-ui.css.

        (''since 1.0'')""", doc_args={'version': '1.12.1'})

    mainnav = ConfigSection('mainnav', """Configures the main navigation bar,
        which by default contains //Wiki//, //Timeline//, //Roadmap//,
        //Browse Source//, //View Tickets//, //New Ticket//, //Search// and
        //Admin//.

        The `label`, `href`, and `order` attributes can be specified. Entries
        can be disabled by setting the value of the navigation item to
        `disabled`.

        The following example renames the link to WikiStart to //Home//,
        links the //View Tickets// entry to a specific report and disables
        the //Search// entry.
        {{{#!ini
        [mainnav]
        wiki.label = Home
        tickets.href = /report/24
        search = disabled
        }}}

        See TracNavigation for more details.
        """)

    metanav = ConfigSection('metanav', """Configures the meta navigation
        entries, which by default are //Login//, //Logout//, //Preferences//,
        ''!Help/Guide'' and //About Trac//. The allowed attributes are the
        same as for `[mainnav]`. Additionally, a special entry is supported -
        `logout.redirect` is the page the user sees after hitting the logout
        button. For example:

        {{{#!ini
        [metanav]
        logout.redirect = wiki/Logout
        }}}

        See TracNavigation for more details.
        """)

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
        permission.
        """)

    show_full_names = BoolOption('trac', 'show_full_names', 'true',
        """Show full names instead of usernames. (//since 1.2//)""")

    never_obfuscate_mailto = BoolOption('trac', 'never_obfuscate_mailto',
        'false',
        """Never obfuscate `mailto:` links explicitly written in the wiki,
        even if `show_email_addresses` is false or the user doesn't have
        EMAIL_VIEW permission.
        """)

    resizable_textareas = BoolOption('trac', 'resizable_textareas', 'true',
        """Make `<textarea>` fields resizable. Requires !JavaScript.
        """)

    wiki_toolbars = BoolOption('trac', 'wiki_toolbars', 'true',
        """Add a simple toolbar on top of Wiki <textarea>s.
        (''since 1.0.2'')""")

    auto_preview_timeout = FloatOption('trac', 'auto_preview_timeout', 2.0,
        """Inactivity timeout in seconds after which the automatic wiki preview
        triggers an update. This option can contain floating-point values. The
        lower the setting, the more requests will be made to the server. Set
        this to 0 to disable automatic preview.
        """)

    default_dateinfo_format = ChoiceOption('trac', 'default_dateinfo_format',
                                           ('relative', 'absolute'),
        """The date information format. Valid options are 'relative' for
        displaying relative format and 'absolute' for displaying absolute
        format. (''since 1.0'')""")

    use_chunked_encoding = BoolOption('trac', 'use_chunked_encoding', 'true',
        """If enabled, send contents as chunked encoding in HTTP/1.1.
        Otherwise, send contents with `Content-Length` header after entire of
        the contents are rendered. (''since 1.0.6'')""")

    templates = None
    jenv = None
    jenv_text = None

    # A dictionary of default context data for templates
    _default_context_data = {
        'all': all,
        'any': any,
        'as_bool': as_bool,
        'as_int': as_int,
        'date': datetime.date,
        'datetime': datetime.datetime,
        'find_element': html.find_element,
        'get_reporter_id': get_reporter_id,
        'groupby': itertools.groupby,
        'http_date': http_date,
        'is_obfuscated': is_obfuscated,
        'javascript_quote': javascript_quote,
        'operator': operator,
        'partial': partial,
        'pathjoin': pathjoin,
        'plaintext': plaintext,
        'pprint': pprint.pformat,
        'pretty_size': pretty_size,
        'pretty_timedelta': pretty_timedelta,
        'quote_plus': unicode_quote_plus,
        'reversed': reversed,
        'shorten_line': shorten_line,
        'sorted': sorted,
        'time': datetime.time,
        'timedelta': datetime.timedelta,
        'to_unicode': to_unicode,
        'utc': utc,
    }

    def __init__(self):
        self._warned_stream_filters = set()
        self._warned_genshi_templates = set()

    # ISystemInfoProvider methods

    def get_system_info(self):
        global genshi
        # Optional and legacy Genshi
        if genshi:
            info = get_pkginfo(genshi).get('version')
            if hasattr(genshi, '_speedups'):
                info += ' (with speedups)'
            else:
                info += ' (without speedups)'
        else:
            info = '(not installed, some old plugins may not work as expected)'
        yield 'Genshi', info
        # Mandatory Jinja2
        import jinja2
        info = get_pkginfo(jinja2).get('version')
        yield 'Jinja2', info
        # Optional Babel
        try:
            import babel
        except ImportError:
            babel = None
        if babel is not None:
            info = get_pkginfo(babel).get('version')
            if not get_available_locales():
                info += " (translations unavailable)"  # No i18n on purpose
                self.log.warning("Locale data is missing")
            yield 'Babel', info

    # IEnvironmentSetupParticipant methods

    def environment_created(self):
        """Add the sample templates to the environment templates dir."""

        def write_sample_template(filename, kind, example=''):
            site_path = os.path.join(self.env.templates_dir,
                                     filename + '.sample')
            with open(site_path, 'w') as fileobj:
                fileobj.write("""\
{#  This file allows customizing the appearance of the Trac installation.

    Add your customizations to the %s here
    and rename the file to %s.

    Note that it will take precedence over a global %s placed
    in the directory specified by [inherit] templates_dir.

    More information about site appearance customization can be found here:

      https://trac.edgewall.org/wiki/TracInterfaceCustomization#SiteAppearance
#}
%s
"""                           % (kind, filename, filename, example))

        write_sample_template('site_head.html',
                              'the end of the HTML <head>', """
<link rel="stylesheet" type="text/css" href="${href.chrome('site/style.css')}"/>
""")
        write_sample_template('site_header.html',
                              'the start of the HTML <body> content')
        write_sample_template('site_footer.html',
                              'the end of the HTML <body> content')

        # Set default values for mainnav and metanav ConfigSections.
        def add_nav_order_options(section, default):
            for i, name in enumerate(default, 1):
                self.env.config.set(section, name + '.order', float(i))
        add_nav_order_options('mainnav', default_mainnav_order)
        add_nav_order_options('metanav', default_metanav_order)

    def environment_needs_upgrade(self):
        return False

    def upgrade_environment(self):
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

    # IPermissionRequestor methods

    def get_permission_actions(self):
        """`EMAIL_VIEW` permission allows for showing email addresses even
        if `[trac] show_email_addresses` is `false`."""
        return ['EMAIL_VIEW']

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return [('common', pkg_resources.resource_filename('trac', 'htdocs')),
                ('shared', self.shared_htdocs_dir),
                ('site', self.env.htdocs_dir)]

    def get_templates_dirs(self):
        return filter(None, [
            self.env.templates_dir,
            self.shared_templates_dir,
            # pkg_resources.resource_filename('trac', 'templates'),
            # TODO (1.5.1) reenable
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
        add_script(req, 'common/js/folding.js')

        # Shortcut icon
        chrome['icon'] = self.get_icon_data(req)
        if chrome['icon']:
            src = chrome['icon']['src']
            mimetype = chrome['icon']['mimetype']
            add_link(req, 'icon', src, mimetype=mimetype)

        # Logo image
        chrome['logo'] = self.get_logo_data(req.href, req.abs_href)

        # Navigation links
        chrome['nav'] = self.get_navigation_items(req, handler)

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

    def get_navigation_items(self, req, handler):

        def get_item_attributes(category, name, text):
            section = self.config[category]
            href = section.get(name + '.href')
            label = section.get(name + '.label')
            if href and href.startswith('/'):
                href = req.href + href
            if isinstance(text, Element) and text.tag == u'a':
                link = text
                if label:
                    link.children[0] = label
                if href:
                    link = link(href=href)
            else:
                if href or label:
                    link = tag.a(label or text or name, href=href)
                else:
                    link = text
            return {
                'enabled': section.getbool(name, True),
                'order': section.getfloat(name + '.order', float('inf')),
                'label': label,
                'href': href,
                'link': link,
                'perm': section.get(name + '.permission')
            }

        all_items = {}
        active = None
        for contributor in self.navigation_contributors:
            with component_guard(self.env, req, contributor):
                for category, name, text in \
                        contributor.get_navigation_items(req) or []:
                    all_items.setdefault(category, {})[name] = \
                        get_item_attributes(category, name, text)
                if contributor is handler:
                    active = contributor.get_active_navigation_item(req)

        # Extra navigation items.
        categories = ('mainnav', 'metanav')
        for category, other_category in zip(categories, reversed(categories)):
            section = self.config[category]
            for name in section:
                if '.' not in name and \
                        name not in all_items.get(category, []):
                    text = None
                    # Allow items to be moved between categories.
                    if other_category in all_items and \
                            name in all_items[other_category]:
                        all_items[category][name] = \
                            all_items[other_category][name]
                        del all_items[other_category][name]
                        text = all_items[category][name].get('link')
                    attributes = get_item_attributes(category, name, text)
                    all_items.setdefault(category, {})[name] = attributes
                    if attributes['href'] and \
                            attributes['href'] == req.href(req.path_info):
                        active = name

        nav_items = {}
        for category, category_items in all_items.iteritems():
            nav_items.setdefault(category, [])
            for name, attributes in \
                    sorted(category_items.iteritems(),
                           key=lambda name_attr: (name_attr[1]['order'], name_attr[0])):
                if attributes['enabled'] and attributes['link'] and \
                        (not attributes['perm'] or
                         attributes['perm'] in req.perm):
                    nav_items[category].append({
                        'name': name,
                        'label': attributes['link'],
                        'active': name == active
                    })
        return nav_items

    def get_interface_customization_files(self):
        """Returns a dictionary containing the lists of files present in the
        site and shared templates and htdocs directories.
        """
        def list_dir(path, suffix=None):
            if not os.path.isdir(path):
                return []
            return sorted(to_unicode(name) for name in os.listdir(path)
                          if suffix is None or name.endswith(suffix))

        files = {}
        # Collect templates list
        exts = ('.html', '.txt')
        site_templates = list_dir(self.env.templates_dir, exts)
        shared_templates = list_dir(self.shared_templates_dir, exts)

        # Collect static resources list
        site_htdocs = list_dir(self.env.htdocs_dir)
        shared_htdocs = list_dir(self.shared_htdocs_dir)

        if any((site_templates, shared_templates, site_htdocs, shared_htdocs)):
            files = {
                'site-templates': site_templates,
                'shared-templates': shared_templates,
                'site-htdocs': site_htdocs,
                'shared-htdocs': shared_htdocs,
            }
        return files

    # E-mail formatting utilities

    def author_email(self, author, email_map):
        """Returns the author email from the `email_map` if `author`
        doesn't look like an email address."""
        if email_map and '@' not in author and email_map.get(author):
            author = email_map.get(author)
        return author

    def authorinfo(self, req, author, email_map=None, resource=None):
        """Format a username to HTML.

        Calls `Chrome.format_author` to format the username, and wraps
        the formatted username in a `span` with class `trac-author`,
        `trac-author-anonymous` or `trac-author-none`.

        :param req: the `Request` object.
        :param author: the author string to be formatted.
        :param email_map: dictionary mapping usernames to email addresses.
        :param resource: optional `Resource` object for `EMAIL_VIEW`
                         fine-grained permissions checks.

        :since 1.1.6: accepts the optional `resource` keyword parameter.
        """
        author = self.author_email(author, email_map)
        return tag.span(self.format_author(req, author, resource),
                        class_=self.author_class(req, author))

    def author_class(self, req, author):
        suffix = ''
        if author == 'anonymous':
            suffix = '-anonymous'
        elif not author:
            suffix = '-none'
        elif req and author == req.authname:
            suffix = '-user'
        return 'trac-author' + suffix

    _long_author_re = re.compile(r'.*<([^@]+)@[^@]+>\s*|([^@]+)@[^@]+')

    def authorinfo_short(self, author):
        shortened = None
        match = self._long_author_re.match(author or '')
        if match:
            shortened = match.group(1) or match.group(2)
        return self.authorinfo(None, shortened or author)

    def cc_list(self, cc_field):
        """Split a CC: value in a list of addresses."""
        return to_list(cc_field, r'[;,]')

    def format_author(self, req, author, resource=None, show_email=None):
        """Format a username in plain text.

        If `[trac]` `show_email_addresses` is `False`, email addresses
        will be obfuscated when the user doesn't have `EMAIL_VIEW`
        (for the resource) and the optional parameter `show_email` is
        `None`. Returns translated `anonymous` or `none`, when the
        author string is `anonymous` or evaluates to `False`,
        respectively.

        :param req: a `Request` or `RenderingContext` object.
        :param author: the author string to be formatted.
        :param resource: an optional `Resource` object for performing
                         fine-grained permission checks for `EMAIL_VIEW`.
        :param show_email: an optional parameter that allows explicit
                           control of e-mail obfuscation.

        :since 1.1.6: accepts the optional `resource` keyword parameter.
        :since 1.2: Full name is returned when `[trac]` `show_full_names`
                    is `True`.
        :since 1.2: Email addresses are obfuscated when
                    `show_email_addresses` is False and `req` is Falsy.
                    Previously email addresses would not be obfuscated
                    whenever `req` was Falsy (typically `None`).
        """
        if author == 'anonymous':
            return _("anonymous")
        if not author:
            return _("(none)")
        users = self.env.get_known_users(as_dict=True)
        if self.show_full_names and author in users:
            name = users[author][0]
            if name:
                return name
        if show_email is None:
            show_email = self.show_email_addresses
            if not show_email and req:
                show_email = 'EMAIL_VIEW' in req.perm(resource)
        return author if show_email else obfuscate_email_address(author)

    def format_emails(self, context, value, sep=', '):
        """Normalize a list of e-mails and obfuscate them if needed.

        :param context: the context in which the check for obfuscation should
                        be done
        :param   value: a string containing a comma-separated list of e-mails
        :param     sep: the separator to use when rendering the list again
        """
        formatted = [self.format_author(context, author)
                     for author in self.cc_list(value)]
        return sep.join(formatted)

    def get_email_map(self):
        """Get the email addresses of all known users."""
        email_map = {}
        if self.show_email_addresses:
            for username, name, email in self.env.get_known_users():
                if email:
                    email_map[username] = email
        return email_map

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
        auto_preview_timeout = req.session.as_float('ui.auto_preview_timeout',
                                                    self.auto_preview_timeout,
                                                    min=0)
        add_script_data(req, auto_preview_timeout=auto_preview_timeout,
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
        default_timezone = (-1 if tzoffset.startswith('-') else 1) * \
                           (int(tzoffset[1:3]) * 60 + int(tzoffset[3:5]))
        timezone_list = get_timezone_list_jquery_ui(now) \
                        if is_iso8601 else None
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

    # Template data (Jinja2 + legacy Genshi)

    def populate_data(self, req=None, data=None, d=None):
        """Fills a dictionary with the standard set of fields expected
        by templates.

        :param req: a `Request` object; if `None`, no request related fields
                    will be set
        :param data: user-provided `dict`, which can be used to override
                     the defaults; if `None`, the defaults will be returned
        :param d: `dict` which is populated with the defaults; if `None`,
                  an empty `dict` will be used
        """
        if d is None:
            d = {}
        d['trac'] = {
            'version': self.env.trac_version,
            'homepage': 'https://trac.edgewall.org/',  # FIXME: use setup data
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

        def pretty_dateinfo(date, format=None, dateonly=False):
            if not date:
                return ''
            if format == 'date':
                absolute = user_time(req, format_date, date)
            else:
                absolute = user_time(req, format_datetime, date)
            now = datetime_now(localtz)
            relative = pretty_timedelta(date, now)
            if not format:
                format = req.session.get('dateinfo',
                                         self.default_dateinfo_format)
            in_or_ago = _("in %(relative)s", relative=relative) \
                        if date > now else \
                        _("%(relative)s ago", relative=relative)
            if format == 'relative':
                label = in_or_ago if not dateonly else relative
                title = absolute
            else:
                if dateonly:
                    label = absolute
                elif req.lc_time == 'iso8601':
                    label = _("at %(iso8601)s", iso8601=absolute)
                elif format == 'date':
                    label = _("on %(date)s", date=absolute)
                else:  # format == 'datetime'
                    label = _("on %(date)s at %(time)s",
                              date=user_time(req, format_date, date),
                              time=user_time(req, format_time, date))
                title = in_or_ago
            return tag.span(label, title=title)

        def dateinfo(date):
            return pretty_dateinfo(date, format='relative', dateonly=True)

        def get_rel_url(resource, **kwargs):
            return get_resource_url(self.env, resource, href, **kwargs)

        def get_abs_url(resource, **kwargs):
            return get_resource_url(self.env, resource, abs_href, **kwargs)

        def accesskey_attr(key):
            key = accesskey(req, key)
            return Markup('accesskey="%s"') % key if key else ''

        dateinfo_format = \
            req.session.get('dateinfo', self.default_dateinfo_format) \
            if req else self.default_dateinfo_format

        locale = req and req.locale
        if locale:
            trac_lang = locale.language
            if locale.territory:
                trac_lang += '-' + locale.territory
        else:
            trac_lang = 'en'

        d.update({
            'env': self.env,
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
            'form_token': req and req.form_token,
            'authname': req.authname if req else '<trac>',
            'locale': locale,
            'trac_lang': trac_lang,
            'author_email': partial(self.author_email,
                                    email_map=self.get_email_map()),
            'authorinfo': partial(self.authorinfo, req),
            'authorinfo_short': self.authorinfo_short,
            'format_author': partial(self.format_author, req),
            'format_emails': self.format_emails,
            'get_systeminfo': self.env.get_systeminfo,  # TODO (1.5.1) remove
            'captioned_button': partial(presentation.captioned_button, req),
            'accesskey': accesskey_attr,

            # Date/time formatting
            'dateinfo': dateinfo,
            'dateinfo_format': dateinfo_format,
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
        if data:
            d.update(data)
        return d

    # Template rendering (Jinja2 + legacy Genshi)

    def load_template(self, filename, text=False):
        """Retrieves a template with the given name.

        This simply loads the template. If you want to make use of the
        "standard" Trac API for templates, also call `populate_data`,
        or consider using the shortcut method `prepare_template`
        instead.

        :param text: in text mode (``True``) XML/HTML auto-escape of
                     variable expansion is disabled.

        .. note::

           If the `text` argument is set to a string instead of a
           boolean, this corresponds to the legacy API and it will be
           assumed that you want to load a Genshi template instead of
           a Jinja2 template. If *text* is ``'text'`` , a
           `NewTextTemplate` instance will be created. If it is set to
           ``None`` or to another string value, a `MarkupTemplate`
           instance will be created and returned.

           This backward compatibility behavior will be removed in
           Trac 1.5.1.

        """
        if text in (True, False):
            return self._load_jinja_template(filename, text)
        elif genshi:
            return self._load_genshi_template(filename, text)

    def _load_jinja_template(self, filename, text=False):
        """Retrieves the Jinja2 `Template` corresponding to the given name.

        Also responsible for initializing the main Jinja2
        `Environment`s on first use.

        """
        # TODO (1.5.1) merge in `load_template`
        if not self.jenv:
            jinja2_dirs = [
                pkg_resources.resource_filename('trac', 'templates')
            ] + self.get_all_templates_dirs()
            self.jenv = jinja2env(
                loader=FileSystemLoader(jinja2_dirs),
                auto_reload=self.auto_reload,
                autoescape=True,
            )
            self.jenv.globals.update(self._default_context_data.copy())
            self.jenv.globals.update(translation.functions)
            self.jenv.globals.update(unicode=to_unicode)
            presentation.jinja2_update(self.jenv)
            self.jenv_text = self.jenv.overlay(autoescape=False)
        return (self.jenv_text if text else self.jenv).get_template(filename)

    def render_template(self, req, filename, data, metadata=None,
                        fragment=False, iterable=False, method=None):
        """Renders the ``filename`` template using ``data`` for the context.

        It attempts to load a Jinja2 template, augments the provided
        *data* with standard data, and renders it according to the
        options provided in *metadata*.

        The ``fragment``, ``iterable`` and ``method`` parameters are
        deprecated and will be removed in Trac 1.5.1. Instead, use
        the ``metadata`` dictionary with keys with the same name. The
        ``method`` key is itself deprecated, use ``text=True`` instead
        of ``method='text'`` to indicate that the template is a plain
        text one, with no need for HTML/XML escaping to take place.

        When ``fragment`` is specified, or ``method`` is ``'text'``,
        or ``text`` is ``True``, we generate some content which does
        not need all of the chrome related data, typically HTML
        fragments, XML or plain text.

        If ``iterable`` is set, we use `generate_template_stream` to
        produce the output (iterable of UTF-8 encoded bytes),
        otherwise we use `render_template_string` and UTF-8 encode the
        result.

        .. note::

           If the Jinja2 template is not found, this method will try
           to load a Genshi template instead.

           Also if ``metadata`` is *not* a dictionary, we assume that
           it is the ``content_type`` value from the legacy API (a
           string or `None`). As a consequence, we assume the template
           will be a Genshi template and we'll use the legacy Genshi
           template engine for the rendering.

           This backward compatibility behavior will be removed in
           Trac 1.5.1.

        """
        # TODO (1.5.1) merge with _render_jinja_template
        if isinstance(metadata, dict):
            return self._render_jinja_template(req, filename, data, metadata,
                                               fragment, iterable, method)
        elif not genshi:
            self.log.error("Genshi template (%s) detected but "
                           "Genshi is not installed", filename)
            raise TracError(
                _("Legacy Genshi template needs the 'genshi' package to be "
                  "installed. Please contact your Trac administrator."))

        return self._render_genshi_template(req, filename, data, metadata,
                                            fragment, iterable, method)

    def _render_jinja_template(self, req, filename, data, metadata=None,
                               fragment=False, iterable=False, method=None):
        """Render the `filename` using the `data` for the context.

        TODO (1.5.1): merge into render_template

        """
        content_type = text = domain = None

        if metadata:
            content_type = metadata.get('content_type')
            text = metadata.get('text')
            domain = metadata.get('domain')
            if fragment is False:
                fragment = metadata.get('fragment')
            if iterable is False:
                iterable = metadata.get('iterable')
            if method is None:
                method = metadata.get('method')

        if content_type is None:
            content_type = 'text/html'

        if method is None:
            method = {'text/html': 'html',
                      'text/plain': 'text'}.get(content_type, 'xml')

        if method == "html":
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

        if text is None:
            text = method == 'text'

        template, data = self.prepare_template(req, filename, data, text,
                                               domain)

        # TODO (1.5.1) - have another try at simplifying all this...
        # With Jinja2, it's certainly possible to do things
        # differently, but for as long as we have to support Genshi,
        # better keep one way.
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

        # Hack for supporting Genshi stream filters - TODO (1.5.1) remove
        if genshi and self._check_for_stream_filters(req, method, filename,
                                                     data):
            page = self.render_template_string(template, data, text)
            return self._filter_jinja_page(req, page, method, filename,
                                           content_type, data, fragment,
                                           iterable)

        if fragment or text:
            if iterable:
                return self.generate_template_stream(template, data, text,
                                                     iterable)
            else:
                s = self.render_template_string(template, data, text)
                return s.encode('utf-8')

        data['chrome']['content_type'] = content_type

        try:
            return self.generate_template_stream(template, data, text,
                                                 iterable)
        except Exception:
            # restore what may be needed by the error template
            req.chrome.update({'early_links': None, 'early_scripts': None,
                               'early_script_data': None, 'links': links,
                               'scripts': scripts, 'script_data': script_data})
            raise

    def generate_fragment(self, req, filename, data, text=False, domain=None):
        """Produces content ready to be sent from the given template
        *filename* and input *data*, with minimal overhead.

        It calls `prepare_template` to augment the *data* with the
        usual helper functions that can be expected in Trac templates,
        including the translation helper functions adapted to the given
        *domain*, except for some of the chrome "late" data.

        If you don't need that and don't want the overhead, use
        `load_template` and `generate_template_stream` directly.

        The generated output is suitable to pass directly to
        `Request.send`, see `generate_template_stream` for details.

        See also `render_fragment`, which returns a string instead.

        """
        template, data = self.prepare_template(req, filename, data, text,
                                               domain)
        return self.generate_template_stream(template, data, text)

    def render_fragment(self, req, filename, data, text=False, domain=None):
        """Produces a string from given template *filename* and input *data*,
        with minimal overhead.

        It calls `prepare_template` to augment the *data* with the
        usual helper functions that can be expected in Trac templates,
        including the translation helper functions adapted to the given
        *domain*, except for some of the chrome "late" data.

        If you don't need that and don't want the overhead, use
        `load_template` and `render_template_string` directly.

        :rtype: the generated output is an `unicode` string if *text*
                is ``True``, or a `Markup` string otherwise.

        See also `generate_fragment`, which produces an output
        suitable to pass directly to `Request.send` instead.

        """
        template, data = self.prepare_template(req, filename, data, text,
                                               domain)
        return self.render_template_string(template, data, text)

    def prepare_template(self, req, filename, data, text=False, domain=None):
        """Prepares the rendering of a Jinja2 template.

        This loads the template and prepopulates a data `dict` with
        the "standard" Trac API for templates.

        :param req: a `Request` instance (optional)
        :param filename: the name of a Jinja2 template, which must be
                         found in one of the template directories (see
                         `get_templates_dirs`)
        :param data: user specified data dictionary, used to override
                     the default context set from the request *req*
                     (see `populate_data`)
        :param text: in text mode (``True``) XML/HTML auto-escape of
                     variable expansion is disabled.

        :rtype: a pair of Jinja2 `Template` and a `dict`.

        """
        template = self._load_jinja_template(filename, text)
        if domain:
            symbols = list(translation.functions)
            domain_functions = translation.domain_functions(domain, symbols)
            data.update(dict(zip(symbols, domain_functions)))
        data = self.populate_data(req, data)
        return template, data

    def generate_template_stream(self, template, data, text=False,
                                 iterable=None):
        """Returns the rendered template in a form that can be "sent".

        This will be either a single UTF-8 encoded `str` object, or an
        iterable made of chunks of the above.

        :param template: the Jinja2 template
        :type template: ``jinja2.Template``

        :param text: in text mode (``True``) the generated bytes will
                     not be sanitized (see `valid_html_bytes`).

        :param iterable: determine whether the output should be
                         generated in chunks or as a single `str`; if
                         `None`, the `use_chunked_encoding` property
                         will be used to determine this instead

        :rtype: `str` or an iterable of `str`, depending on *iterable*

        .. note:

        Turning off the XML/HTML auto-escape feature for variable
        expansions has to be disabled when loading the template (see
        `load_template`), so remember to stay consistent with the
        *text* parameter.

        """
        stream = template.stream(data)
        stream.enable_buffering(75)  # buffer_size
        if iterable or iterable is None and self.use_chunked_encoding:
            return self._iterable_jinja_content(stream, text)
        else:
            if text:
                def generate():
                    for chunk in stream:
                        yield chunk.encode('utf-8')
            else:
                def generate():
                    for chunk in stream:
                        yield valid_html_bytes(chunk.encode('utf-8'))
            return b''.join(generate())

    def render_template_string(self, template, data, text=False):
        """Renders the template as an unicode or Markup string.

        :param template: the Jinja2 template
        :type template: ``jinja2.Template``

        :param text: in text mode (``True``) the generated string
                     will not be wrapped in `Markup`

        :rtype: `unicode` if *text* is ``True``, `Markup` otherwise.

        .. note:

        Turning off the XML/HTML auto-escape feature for variable
        expansions has to be disabled when loading the template (see
        `load_template`), so remember to stay consistent with the
        *text* parameter.

        """
        string = template.render(data)
        return string if text else Markup(string)

    def iterable_content(self, stream, text=False, **kwargs):
        """Generate an iterable object which iterates `str` instances
        from the given stream instance.

        :param text: in text mode (``True``) XML/HTML auto-escape of
                     variable expansion is disabled.

        .. note:

        If text is a string, this corresponds to the old API and we
        assume to have a Genshi stream. This backward compatibility
        behavior will be removed in Trac 1.5.1.

        """
        if text in (True, False):
            return self._iterable_jinja_content(stream, text)
        elif genshi:
            return self._iterable_genshi_content(stream, text, **kwargs)

    def _iterable_jinja_content(self, stream, text):
        # TODO (1.5.1) merge with iterable_content
        try:
            if text:
                for chunk in stream:
                    yield chunk.encode('utf-8')
            else:
                for chunk in stream:
                    yield valid_html_bytes(chunk.encode('utf-8'))
        except TracBaseError:
            raise
        except Exception as e:
            self.log.error('Jinja2 %s error while rendering %s template %s',
                           e.__class__.__name__,
                           'text' if text else 'XML/HTML',
                           exception_to_unicode(e, traceback=True))

    # Template rendering (legacy Genshi support) - TODO (1.5.1) remove

    if genshi:
        # DocType for 'text/html' output
        html_doctype = DocType.XHTML_STRICT

        def _load_genshi_template(self, filename, method=None):
            if not self.templates:
                genshi_dirs = [
                    pkg_resources.resource_filename('trac', 'templates/genshi')
                ] + self.get_all_templates_dirs()
                self.templates = TemplateLoader(
                    genshi_dirs,
                    auto_reload=self.auto_reload,
                    max_cache_size=self.genshi_cache_size,
                    default_encoding="utf-8",
                    variable_lookup='lenient', callback=lambda template:
                    Translator(translation.get_translations()).setup(template))

            if method == 'text':
                cls = NewTextTemplate
            else:
                cls = MarkupTemplate
            return self.templates.load(filename, cls=cls)

        def _get_genshi_data(self):
            def classes(*args, **kwargs):
                s = presentation.classes(*args, **kwargs)
                return s or None
            def styles(*args, **kwargs):
                s = presentation.styles(*args, **kwargs)
                return s or None
            d = self._default_context_data.copy()
            d.update({
                'classes': classes,
                'first_last': presentation.first_last,
                'group': presentation.group,
                'istext': presentation.istext,
                'paginate': presentation.paginate,
                'separated': presentation.separated,
                'styles': styles,
                'to_json': presentation.to_json,
            })
            d.update(translation.functions)
            return d

        def _render_genshi_template(self, req, filename, data,
                                    content_type=None, fragment=False,
                                    iterable=False, method=None):
            if filename not in self._warned_genshi_templates:
                self.log.warning("Rendering Genshi template '%s' (convert to "
                                 "Jinja2 before Trac 1.5.1)", filename)
                self._warned_genshi_templates.add(filename)
            if content_type is None:
                content_type = 'text/html'

            if method is None:
                method = {'text/html': 'html',
                          'text/plain': 'text'}.get(content_type, 'xml')

            if method == "html":
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

            template = self.load_template(filename, method)

            # Populate data with request dependent data
            data = self.populate_data(req, data, self._get_genshi_data())
            data['chrome']['content_type'] = content_type
            stream = template.generate(**data)
            # Filter through ITemplateStreamFilter plugins
            if self.stream_filters:
                stream |= self._filter_stream(req, method, filename, data)
            if fragment:
                return stream

            doctype = None
            if content_type == 'text/html':
                doctype = self.html_doctype
                if req.form_token:
                    stream |= self._add_form_token(req.form_token)
                if not req.session.as_int('accesskeys'):
                    stream |= self._strip_accesskeys

            return self._send_genshi_content(req, stream, filename, method,
                                             doctype, data, iterable)

        def _send_genshi_content(self, req, stream, filename, method, doctype,
                                 data, iterable):
            if method == 'text':
                buffer = io.BytesIO()
                stream.render('text', out=buffer, encoding='utf-8')
                return buffer.getvalue()

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
                buffer = io.BytesIO()
                stream.render(method, doctype=doctype, out=buffer,
                              encoding='utf-8')
                return valid_html_bytes(buffer.getvalue())
            except Exception as e:
                # restore what may be needed by the error template
                req.chrome.update({'early_links': None, 'early_scripts': None,
                                   'early_script_data': None, 'links': links,
                                   'scripts': scripts,
                                   'script_data': script_data})
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

        def _iterable_genshi_content(self, stream, method, **kwargs):
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
                        yield valid_html_bytes(chunk.encode('utf-8'))
            except Exception as e:
                pos = self._stream_location(stream)
                if pos:
                    location = "'%s', line %s, char %s" % pos
                else:
                    location = '(unknown template location)'
                self.log.error('Genshi %s error while rendering template %s%s',
                               e.__class__.__name__, location,
                               exception_to_unicode(e, traceback=True))

        # Genshi Template filters

        def _add_form_token(self, token):
            from genshi.builder import tag as gtag
            elem = gtag.div(
                gtag.input(type='hidden', name='__FORM_TOKEN', value=token)
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

        def _filter_stream(self, req, method, filename, data):
            def inner(stream, ctxt=None):
                for filter in self.stream_filters:
                    stream = filter.filter_stream(req, method, filename,
                                                  stream, data)
                return stream
            return inner

        def _stream_location(self, stream):
            for kind, data, pos in stream:
                return pos

        def _check_for_stream_filters(self, req, method, filename, data):
            class FakeStream(object):
                def __or__(self, x):
                    raise GenshiStreamFilterUsed()
            class GenshiStreamFilterUsed(Exception):
                pass
            stream = FakeStream()
            for filter in self.stream_filters:
                try:
                    stream = filter.filter_stream(req, method, filename,
                                                  stream, data)
                except GenshiStreamFilterUsed:
                    name = filter.__class__.__name__
                    if name not in self._warned_stream_filters:
                        self.log.warning("Component %s relies on deprecated"
                                         " Genshi stream filtering", name)
                        self._warned_stream_filters.add(name)
                    return True
            return False

        def _filter_jinja_page(self, req, content, method, filename,
                               content_type, data, fragment, iterable):
            if content_type == 'text/plain':
                # Avoid to apply filters to text/plain content
                return content.encode('utf-8') \
                       if isinstance(content, unicode) else content
            if content_type == 'text/html':
                doctype = self.html_doctype
                stream = HTML(content)
            else:
                doctype = None
                stream = XML(content)
            stream |= self._filter_stream(req, method, filename, data)
            if fragment:
                return stream
            else:
                return self._send_genshi_content(req, stream, filename, method,
                                                 doctype, data, iterable)
