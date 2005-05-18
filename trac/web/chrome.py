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

import os.path
import re

from trac import mimeview, util
from trac.core import *
from trac.web.href import Href
from trac.web.main import IRequestHandler

def add_link(req, rel, href, title=None, mimetype=None, classname=None):
    """
    Add a link to the HDF data set that will be inserted as <link> element in
    the <head> of the generated HTML
    """
    link = {'href': util.escape(href)}
    if title:
        link['title'] = util.escape(title)
    if mimetype:
        link['type'] = mimetype
    if classname:
        link['class'] = classname
    idx = 0
    while req.hdf.get('chrome.links.%s.%d.href' % (rel, idx)):
        idx += 1
    req.hdf['chrome.links.%s.%d' % (rel, idx)] = link

def add_stylesheet(req, filename, mimetype='text/css'):
    """
    Add a link to a style sheet to the HDF data set so that it gets included
    in the generated HTML page.
    """
    href = Href(req.hdf['htdocs_location'])
    add_link(req, 'stylesheet', href.css(filename), mimetype=mimetype)


class INavigationContributor(Interface):
    """
    Extension point interface for components that contribute items to the
    navigation.
    """

    def get_active_navigation_item(req):
        """
        This method is only called for the `IRequestHandler` processing the
        request. It should return the name of the navigation item that should
        be highlighted as active/current.
        """

    def get_navigation_items(req):
        """
        Should return an iterable object over the list of navigation items to
        add, each being a tuple in the form (category, name, text).
        """


class Chrome(Component):
    """
    Responsible for assembling the web site chrome, i.e. everything that
    is not actual page content.
    """
    implements(IRequestHandler)

    navigation_contributors = ExtensionPoint(INavigationContributor)

    # IRequestHandler methods

    def match_request(self, req):
        m = re.match(r'/chrome/([/\w\-\.]+)', req.path_info)
        if m:
            req.args['path'] = m.group(1)
            return True

    def process_request(self, req):
        from trac.siteconfig import __default_htdocs_dir__
        path = os.path.join(__default_htdocs_dir__, req.args.get('path'))
        if not os.path.isfile(path):
            raise TracError, 'File not found'
        req.send_file(path)

    # Public API methods

    def populate_hdf(self, req, handler):
        """
        Add chrome-related data to the HDF.
        """

        # Provided for template customization
        req.hdf['HTTP.PathInfo'] = req.path_info

        htdocs_location = self.config.get('trac', 'htdocs_location', '')
        if not htdocs_location:
            htdocs_location = Href(req.cgi_location).chrome()
        if htdocs_location[-1] != '/':
            htdocs_location += '/'
        req.hdf['htdocs_location'] = htdocs_location

        # HTML <head> links
        add_link(req, 'start', self.env.href.wiki())
        add_link(req, 'search', self.env.href.search())
        add_link(req, 'help', self.env.href.wiki('TracGuide'))
        add_stylesheet(req, 'trac.css')
        icon = self.config.get('project', 'icon')
        if icon:
            if icon[0] != '/' and icon.find('://') == -1:
                icon = htdocs_location + icon
            mimetype = mimeview.get_mimetype(icon)
            add_link(req, 'icon', icon, mimetype=mimetype)
            add_link(req, 'shortcut icon', icon, mimetype=mimetype)

        # Logo image
        logo_src = self.config.get('header_logo', 'src')
        if logo_src:
            logo_src_abs = logo_src.startswith('http://') or \
                           logo_src.startswith('https://')
            if not logo_src.startswith('/') and not logo_src_abs:
                logo_src = htdocs_location + logo_src
            req.hdf['chrome.logo'] = {
                'link': self.config.get('header_logo', 'link') or None,
                'alt': util.escape(self.config.get('header_logo', 'alt')),
                'src': logo_src,
                'src_abs': logo_src_abs,
                'width': self.config.get('header_logo', 'width') or None,
                'height': self.config.get('header_logo', 'height') or None
            }

        # Navigation links
        navigation = {}
        active = None
        for contributor in self.navigation_contributors:
            for category, name, text in contributor.get_navigation_items(req):
                navigation.setdefault(category, {})[name] = text
            if contributor is handler:
                active = contributor.get_active_navigation_item(req)

        for category, items in [(k, v.items()) for k, v in navigation.items()]:
            order = [x.strip() for x
                     in self.config.get('trac', category).split(',')]
            def navcmp(x, y):
                if x[0] not in order:
                    return int(y[0] in order)
                if y[0] not in order:
                    return -int(x[0] in order)
                return cmp(order.index(x[0]), order.index(y[0]))
            items.sort(navcmp)

            for name, text in items:
                req.hdf['chrome.nav.%s.%s' % (category, name)] = text
                if name == active:
                    req.hdf['chrome.nav.%s.%s.active' % (category, name)] = 1
