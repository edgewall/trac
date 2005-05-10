# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004, 2005 Edgewall Software
# Copyright (C) 2003, 2004, 2005 Jonas Borgström <jonas@edgewall.com>
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
# Author: Jonas Borgström <jonas@edgewall.com>

from trac.core import *
from trac.util import escape
from trac.wiki.api import IWikiMacroProvider

import imp
import inspect
import os.path
import time
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


class TitleIndexMacro(Component):
    """
    Inserts an alphabetic list of all wiki pages into the output.

    Accepts a prefix string as parameter: if provided, only pages with names
    that start with the prefix are included in the resulting list. If this
    parameter is omitted, all pages are listed.
    """
    implements(IWikiMacroProvider)

    def get_macros(self):
        yield 'TitleIndex'

    def get_macro_description(self, name):
        return inspect.getdoc(TitleIndexMacro)

    def render_macro(self, req, name, content):
        prefix = None
        if content:
            prefix = content.replace('\'', '\'\'')

        db = self.env.get_db_cnx()
        cursor = db.cursor()

        sql = 'SELECT DISTINCT name FROM wiki '
        params = []
        if prefix:
            sql += 'WHERE name LIKE %s%% '
            params.append(prefix)
        sql += 'ORDER BY name'
        cursor.execute(sql, params)

        buf = StringIO()
        buf.write('<ul>')
        for (name,) in cursor:
            buf.write('<li><a href="%s">' % escape(self.env.href.wiki(name)))
            buf.write(escape(name))
            buf.write('</a></li>\n')
        buf.write('</ul>')

        return buf.getvalue()


class RecentChangesMacro(Component):
    """
    Lists all pages that have recently been modified, grouping them by the day
    they were last modified.

    This macro accepts two parameters. The first is a prefix string: if
    provided, only pages with names that start with the prefix are included in
    the resulting list. If this parameter is omitted, all pages are listed.

    The second parameter is a number for limiting the number of pages returned.
    For example, specifying a limit of 5 will result in only the five most
    recently changed pages to be included in the list.
    """
    implements(IWikiMacroProvider)

    def get_macros(self):
        yield 'RecentChanges'

    def get_macro_description(self, name):
        return inspect.getdoc(RecentChangesMacro)

    def render_macro(self, req, name, content):
        prefix = limit = None
        if content:
            argv = [arg.strip() for arg in content.split(',')]
            if len(argv) > 0:
                prefix = argv[0].replace('\'', '\'\'')
                if len(argv) > 1:
                    limit = int(argv[1])

        db = self.env.get_db_cnx()
        cursor = db.cursor()

        sql = 'SELECT name, max(time) FROM wiki '
        params = []
        if prefix:
            sql += 'WHERE name LIKE %s%% '
            params.append(prefix)
        sql += 'GROUP BY name ORDER BY max(time) DESC'
        if limit:
            sql += ' LIMIT %d' % limit
        cursor.execute(sql, params)

        buf = StringIO()
        prevtime = None

        for name,t in cursor:
            t = time.strftime('%x', time.localtime(t))
            if t != prevtime:
                if prevtime:
                    buf.write('</ul>')
                buf.write('<h3>%s</h3><ul>' % t)
                prevtime = t
            buf.write('<li><a href="%s">%s</a></li>\n'
                      % (escape(self.env.href.wiki(name)), escape(name)))
        if prevtime:
            buf.write('</ul>')

        return buf.getvalue()


class PageOutlineMacro(Component):
    """
    Displays a structural outline of the current wiki page, each item in the
    outline being a link to the corresponding heading.

    This macro accepts three optional parameters: The first must be a number
    between 1 and 6 that specifies the maximum depth of the outline (the default
    is 6). The second can be used to specify a custom title (the default is no
    title). The third parameter selects the style of the outline. This can be
    either 'inline' or 'pullout' (default is 'pullout'). The 'inline' style
    renders the outline as normal part of the content, while 'pullout' causes
    the outline to be rendered in a box that is by default floated to the right
    side of the other content.
    """
    implements(IWikiMacroProvider)

    def get_macros(self):
        yield 'PageOutline'

    def get_macro_description(self, name):
        return inspect.getdoc(PageOutlineMacro)

    def render_macro(self, req, name, content):
        from trac.wiki.formatter import wiki_to_outline
        max_depth = 6
        title = None
        inline = 0
        if content:
            argv = [arg.strip() for arg in content.split(',')]
            if len(argv) > 0:
                max_depth = int(argv[0])
                if len(argv) > 1:
                    title = argv[1].strip()
                    if len(argv) > 2:
                        inline = argv[2].strip().lower() == 'inline'

        db = self.env.get_db_cnx()
        cursor = db.cursor()
        page = req.args.get('page')
        cursor.execute("SELECT text FROM wiki WHERE name=%s "
                       "ORDER BY version DESC LIMIT 1", (page,))
        (text,) = cursor.fetchone()

        buf = StringIO()
        if not inline:
            buf.write('<div class="wiki-toc">')
        if title:
            buf.write('<h4>%s</h4>' % escape(title))
        buf.write(wiki_to_outline(text, self.env, db=db, max_depth=max_depth))
        if not inline:
            buf.write('</div>')
        return buf.getvalue()


class MacroListMacro(Component):
    """
    Displays a list of all installed Wiki macros, including documentation if
    available.
    """
    implements(IWikiMacroProvider)

    def get_macros(self):
        yield 'MacroList'

    def get_macro_description(self, name):
        return inspect.getdoc(MacroListMacro)

    def render_macro(self, req, name, content):
        from trac.wiki import WikiSystem
        buf = StringIO()
        buf.write("<dl>")

        wiki = WikiSystem(self.env)
        for macro_provider in wiki.macro_providers:
            for macro_name in macro_provider.get_macros():
                buf.write("<dt><code>[[%s]]</code></dt>" % escape(macro_name))
                description = macro_provider.get_macro_description(macro_name)
                if description:
                    buf.write("<dd><p style='white-space: pre'>%s</p></dd>"
                              % escape(description))

        buf.write("</dl>")
        return buf.getvalue()


class UserMacroProvider(Component):
    """
    Adds macros that are provided as Python source files in the environments
    `wiki-macros` directory.
    """
    implements(IWikiMacroProvider)

    def get_macros(self):
        path = os.path.join(self.env.path, 'wiki-macros')
        if not os.path.exists(path):
            return
        for file in [f for f in os.listdir(path)
                     if f.lower().endswith('.py') and not f.startswith('__')]:
            try:
                module = self._load_macro(file[:-3])
                yield module.__name__
            except Exception, e:
                self.log.error("Failed to load wiki macro %s (%s)" % (f, e), e)

    def get_macro_description(self, name):
        return inspect.getdoc(self._load_macro(name))

    def render_macro(self, req, name, content):
        module = self._load_macro(name)
        try:
            return module.execute(req and req.hdf, content, self.env)
        except Exception, e:
            self.log.error('Wiki macro failed', e)
            raise e

    def _load_macro(self, name):
        path = os.path.join(self.env.path, 'wiki-macros', name + '.py')
        return imp.load_source(name, path)
