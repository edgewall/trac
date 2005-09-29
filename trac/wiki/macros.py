# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
# Author: Christopher Lenz <cmlenz@gmx.de>

from __future__ import generators
import imp
import inspect
import os.path
import shutil
import re

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from trac.core import *
from trac.util import escape, format_date
from trac.env import IEnvironmentSetupParticipant
from trac.wiki.api import IWikiMacroProvider, WikiSystem
from trac.wiki.model import WikiPage


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
        prevdate = None

        for name, time in cursor:
            date = format_date(time)
            if date != prevdate:
                if prevdate:
                    buf.write('</ul>')
                buf.write('<h3>%s</h3><ul>' % date)
                prevdate = date
            buf.write('<li><a href="%s">%s</a></li>\n'
                      % (escape(self.env.href.wiki(name)), escape(name)))
        if prevdate:
            buf.write('</ul>')

        return buf.getvalue()


class PageOutlineMacro(Component):
    """
    Displays a structural outline of the current wiki page, each item in the
    outline being a link to the corresponding heading.

    This macro accepts three optional parameters:
    
     * The first is a number or range that allows configuring the minimum and
       maximum level of headings that should be included in the outline. For
       example, specifying "1" here will result in only the top-level headings
       being included in the outline. Specifying "2-3" will make the outline
       include all headings of level 2 and 3, as a nested list. The default is
       to include all heading levels.
     * The second parameter can be used to specify a custom title (the default
       is no title).
     * The third parameter selects the style of the outline. This can be
       either `inline` or `pullout` (the latter being the default). The `inline`
       style renders the outline as normal part of the content, while `pullout`
       causes the outline to be rendered in a box that is by default floated to
       the right side of the other content.
    """
    implements(IWikiMacroProvider)

    def get_macros(self):
        yield 'PageOutline'

    def get_macro_description(self, name):
        return inspect.getdoc(PageOutlineMacro)

    def render_macro(self, req, name, content):
        from trac.wiki.formatter import wiki_to_outline
        min_depth, max_depth = 1, 6
        title = None
        inline = 0
        if content:
            argv = [arg.strip() for arg in content.split(',')]
            if len(argv) > 0:
                depth = argv[0]
                if depth.find('-') >= 0:
                    min_depth, max_depth = [int(d) for d in depth.split('-', 1)]
                else:
                    min_depth, max_depth = int(depth), int(depth)
                if len(argv) > 1:
                    title = argv[1].strip()
                    if len(argv) > 2:
                        inline = argv[2].strip().lower() == 'inline'

        db = self.env.get_db_cnx()
        cursor = db.cursor()
        pagename = req.args.get('page') or 'WikiStart'
        page = WikiPage(self.env, pagename)

        buf = StringIO()
        if not inline:
            buf.write('<div class="wiki-toc">')
        if title:
            buf.write('<h4>%s</h4>' % escape(title))
        buf.write(wiki_to_outline(page.text, self.env, db=db,
                                  max_depth=max_depth, min_depth=min_depth))
        if not inline:
            buf.write('</div>')
        return buf.getvalue()


class ImageMacro(Component):
    """
    Embed an image in wiki-formatted text.
    
    The first argument is the file specification. The file specification may
    reference attachments or files in three ways:
     * `module:id:file`, where module can be either '''wiki''' or '''ticket''',
       to refer to the attachment named ''file'' of the specified wiki page or
       ticket.
     * `id:file`: same as above, but id is either a ticket shorthand or a Wiki
       page name.
     * `file` to refer to a local attachment named 'file'. This only works from
       within that wiki page or a ticket.
    
    Also, the file specification may refer to repository files, using the
    `source:file` syntax.
    
    The remaining arguments are optional and allow configuring the attributes
    and style of the rendered `<img>` element:
     * digits and unit are interpreted as the size (ex. 120, 25%)
       for the image
     * `right`, `left`, `top` or `bottom` are interpreted as the alignment for
       the image
     * `nolink` means without link to image source.
     * `key=value` style are interpreted as HTML attributes for the image
     * `key:value` style are interpreted as CSS style indications for the image
    
    Examples:
    {{{
        [[Image(photo.jpg)]]                           # simplest
        [[Image(photo.jpg, 120px)]]                    # with size
        [[Image(photo.jpg, right)]]                    # aligned by keyword
        [[Image(photo.jpg, nolink)]]                   # without link to source
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
        [[Image(htdocs:foo/bar.png)]]   # image file in project htdocs dir.
    }}}
    
    ''Adapted from the Image.py macro created by Shun-ichi Goto
    <gotoh@taiyo.co.jp>''
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
        nolink = False
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
            if arg == 'nolink':
                nolink = True
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
            from trac.versioncontrol.web_ui import BrowserModule
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
            else: # #ticket:attachment or WikiPage:attachment
                # FIXME: do something generic about shorthand forms...
                id, file = parts
                if id and id[0] == '#':
                    module = 'ticket'
                    id = id[1:]
                elif id == 'htdocs':
                    raw_url = url = self.env.href.chrome('site', file)
                    desc = os.path.basename(file)
                else:
                    module = 'wiki'
        elif len(parts) == 1:               # attachment
            # determine current object
            # FIXME: should be retrieved from the formatter...
            # ...and the formatter should be provided to the macro
            file = filespec
            module, id = 'wiki', 'WikiStart'
            path_info = req.path_info.split('/',2)
            if len(path_info) > 1:
                module = path_info[1]
            if len(path_info) > 2:
                id = path_info[2]
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
        result = '<img src="%s" %s style="%s" />' \
                 % (raw_url, img_attr, img_style)
        if not nolink:
            result = '<a href="%s" style="%s">%s</a>' % (url, a_style, result)
        return result


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
                if content and macro_name != content:
                    continue
                buf.write("<dt><code>[[%s]]</code></dt>" % escape(macro_name))
                description = macro_provider.get_macro_description(macro_name)
                if description:
                    buf.write("<dd>%s</dd>" % wiki_to_html(description, self.env, req))

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
