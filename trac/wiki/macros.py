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

from __future__ import generators
import imp
import inspect
import os.path
import time
import shutil
import re

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from trac.core import *
from trac.util import escape
from trac.env import IEnvironmentSetupParticipant
from trac.wiki.api import IWikiMacroProvider, WikiSystem


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

        wiki = WikiSystem(self.env)
        pages = list(wiki.get_pages(prefix))
        pages.sort()

        buf = StringIO()
        buf.write('<ul>')
        for page in pages:
            buf.write('<li><a href="%s">' % escape(self.env.href.wiki(page)))
            buf.write(escape(page))
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
        if prefix:
            sql += "WHERE name LIKE '%s%%' " % prefix
        sql += 'GROUP BY name ORDER BY max(time) DESC'
        if limit:
            sql += ' LIMIT %d' % limit
        cursor.execute(sql)

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
    either '''inline''' or '''pullout''' (default is '''pullout''').
    The '''inline''' style renders the outline as normal part of the content,
    while '''pullout''' causes the outline to be rendered in a box
    that is by default floated to the right side of the other content.
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


class ImageMacro(Component):
    """
    Display an image into the wiki page.

    The first argument is the file specification.

    The file specification may refer attachments:
     * {{{module:id:file}}}, with module being either '''wiki''' or '''ticket''',
       to refer to the attachment named ''file'' in the module:id object
     * {{{id:file}}} same as above, but id is either a ticket shorthand or
       a Wiki page name.
     * {{{file}}} to refer to a local attachment named 'file'
       (but then, this works only from within a wiki page or a ticket).

    Also, the file specification may refer to repository files,
    using the {{{source:file}}} syntax (or the usual aliases for '''source''',
    like '''repos''' or '''browser''').

    Rest of optional arguments are attribute/style string of IMG element.
     * digits and unit are interpreted as the size (ex. 120, 25%)
       for the image
     * '''right''', '''left''', '''top''' or '''bottom'''
       are interpreted as the alignment for the image
     * {{{key=value}}} style are interpreted as HTML attributes for the image
     * {{{key:value}}} style are interpreted as CSS style indications for the image

    Examples:
    {{{
        [[Image(photo.jpg)]]                           # simplest
        [[Image(photo.jpg, 120px)]]                    # with size
        [[Image(photo.jpg, right)]]                    # aligned by keyword
        [[Image(photo.jpg, align=right)]]              # aligned by attribute
        [[Image(photo.jpg, float:right)]]              # aligned by style
        [[Image(photo.jpg, float:right, border:solid 5px green)]] # 2 style specs
    }}}

    You can use image from other page, other ticket or other module.
    {{{
        [[Image(OtherPage:foo.bmp)]]    # if current module is wiki
        [[Image(base/sub:bar.bmp)]]     # from hierarchical wiki page
        [[Image(#3:baz.bmp)]]           # if in a ticket, point to #3
        [[Image(ticket:36:boo.jpg)]]
        [[Image(source:/images/bee.jpg)]] # straight from the repository!
    }}}

    ''Adapted from the Image.py macro created by Shun-ichi Goto <gotoh@taiyo.co.jp>''
    """
    implements(IWikiMacroProvider)

    def get_macros(self):
        yield 'Image'

    def get_macro_description(self, name):
        return inspect.getdoc(ImageMacro)

    def render_macro(self, req, name, content):
        # args will be null if the macro is called without parenthesis.
        if not content:
            return ''
        # parse arguments
        # we expect the 1st argument to be a filename (filespec)
        args = content.split(',')
        if len(args) == 0:
            raise Exception("No argument.")
        filespec = args[0]
        size_re = re.compile('^[0-9]+%?$')
        align_re = re.compile('^(?:left|right|top|bottom)$')
        keyval_re = re.compile('^([-a-z0-9]+)([=:])(.*)')
        quoted_re = re.compile("^(?:&#34;|')(.*)(?:&#34;|')$")
        attr = {}
        style = {}
        for arg in args[1:]:
            arg = arg.strip()
            if size_re.search(arg):
                # 'width' keyword
                attr['width'] = arg
                continue
            if align_re.search(arg):
                # 'align' keyword
                attr['align'] = arg
                continue
            match = keyval_re.search(arg)
            if match:
                key = match.group(1)
                sep = match.group(2)
                val = match.group(3)
                m = quoted_re.search(val) # unquote &#34; character "
                if m:
                    val = m.group(1)
                if sep == '=':
                    attr[key] = val;
                elif sep == ':':
                    style[key] = val

        # parse filespec argument to get module and id if contained.
        parts = filespec.split(':')
        url = None
        if len(parts) == 3:                 # module:id:attachment
            if parts[0] in ['wiki', 'ticket']:
                module, id, file = parts
            else:
                raise Exception("%s module can't have attachments" % parts[0])
        elif len(parts) == 2:
            from trac.Browser import BrowserModule
            try:
                browser_links = [link for link,_ in 
                                 BrowserModule(self.env).get_link_resolvers()]
            except Exception:
                browser_links = []
            if parts[0] in browser_links:   # source:path
                module, file = parts
                url = self.env.href.browser(file)
                raw_url = self.env.href.browser(file, format='raw')
                desc = filespec
            else:                           # #ticket:attachment or WikiPage:attachment
                # FIXME: do something generic about shorthand forms...
                id, file = parts
                if id and id[0] == '#':
                    module = 'ticket'
                    id = id[1:]
                else:
                    module = 'wiki'
        elif len(parts) == 1:               # attachment
            # determine current object
            # FIXME: should be retrieved from the formatter...
            # ...and the formatter should be provided to the macro
            file = filespec
            module, id = req.hdf['HTTP.PathInfo'].split('/', 3)[1:]
            if module not in ['wiki', 'ticket']:
                raise Exception('Cannot reference local attachment from here')
        else:
            raise Exception('No filespec given')
        if not url: # this is an attachment
            from trac.attachment import Attachment
            attachment = Attachment(self.env, module, id, file)
            url = attachment.href()
            raw_url = attachment.href(format='raw')
            desc = attachment.description
        for key in ['title', 'alt']:
            if desc and not attr.has_key(key):
                attr[key] = desc
        a_style = 'padding:0; border:none' # style of anchor
        img_attr = ' '.join(['%s="%s"' % x for x in attr.iteritems()])
        img_style = '; '.join(['%s:%s' % x for x in style.iteritems()])
        return '<a href="%s" style="%s"><img src="%s" %s style="%s" /></a>' \
               % (url, a_style, raw_url, img_attr, img_style)


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
        from trac.wiki.formatter import wiki_to_html
        from trac.wiki import WikiSystem
        buf = StringIO()
        buf.write("<dl>")

        wiki = WikiSystem(self.env)
        for macro_provider in wiki.macro_providers:
            for macro_name in macro_provider.get_macros():
                buf.write("<dt><code>[[%s]]</code></dt>" % escape(macro_name))
                description = macro_provider.get_macro_description(macro_name)
                if description:
                    try:
                        buf.write("<dd>%s</dd>" % wiki_to_html(description, self.env, req))
                    except Exception, e:
                        import traceback
                        print traceback.print_exc()

        buf.write("</dl>")
        return buf.getvalue()


class UserMacroProvider(Component):
    """
    Adds macros that are provided as Python source files in the environments
    `wiki-macros` directory.
    """
    implements(IEnvironmentSetupParticipant, IWikiMacroProvider)

    # IEnvironmentSetupParticipant methods

    def environment_created(self):
        pass

    def environment_needs_upgrade(self, db):
        for _ in self._new_macros():
            return True
        return False
    
    def upgrade_environment(self, db):
        # Copy the new default wiki macros over to the environment
        for src, dst in self._new_macros():
            shutil.copy2(src, dst)
            
    def _new_macros(self):
        from trac.config import default_dir
        macros_dir = default_dir('macros')
        for f in os.listdir(macros_dir):
            if not f.endswith('.py'):
                continue
            src = os.path.join(macros_dir, f)
            dst = os.path.join(self.env.path, 'wiki-macros', f)
            if not os.path.isfile(dst):
                yield src, dst

    # IWikiMacroProvider methods

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
                self.log.error('Failed to load wiki macro %s (%s)' % (f, e))

    def get_macro_description(self, name):
        return inspect.getdoc(self._load_macro(name))

    def render_macro(self, req, name, content):
        module = self._load_macro(name)
        try:
            return module.execute(req and req.hdf, content, self.env)
        except Exception, e:
            self.log.error('Wiki macro %s failed (%s)' % (name, e))
            raise e

    def _load_macro(self, name):
        path = os.path.join(self.env.path, 'wiki-macros', name + '.py')
        return imp.load_source(name, path)
