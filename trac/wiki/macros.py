# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2006 Edgewall Software
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
# Author: Christopher Lenz <cmlenz@gmx.de>

import imp
import inspect
import os
import re
try:
    set
except NameError:
    from sets import Set as set
from StringIO import StringIO

from trac.config import default_dir
from trac.core import *
from trac.util import sorted
from trac.util.datefmt import format_date
from trac.util.markup import escape, html, Markup
from trac.wiki.api import IWikiMacroProvider, WikiSystem
from trac.wiki.model import WikiPage
from trac.web.chrome import add_stylesheet


class WikiMacroBase(Component):
    """Abstract base class for wiki macros."""

    implements(IWikiMacroProvider)
    abstract = True

    def get_macros(self):
        """Yield the name of the macro based on the class name."""
        name = self.__class__.__name__
        if name.endswith('Macro'):
            name = name[:-5]
        yield name

    def get_macro_description(self, name):
        """Return the subclass's docstring."""
        return inspect.getdoc(self.__class__)

    def render_macro(self, req, name, content):
        raise NotImplementedError


class TitleIndexMacro(WikiMacroBase):
    """Inserts an alphabetic list of all wiki pages into the output.

    Accepts a prefix string as parameter: if provided, only pages with names
    that start with the prefix are included in the resulting list. If this
    parameter is omitted, all pages are listed.
    """

    def render_macro(self, req, name, content):
        prefix = content or None

        wiki = WikiSystem(self.env)

        return html.UL[[html.LI(html.A(wiki.format_page_name(page),
                                       href=req.href.wiki(page)))
                        for page in sorted(wiki.get_pages(prefix))]]


class RecentChangesMacro(WikiMacroBase):
    """Lists all pages that have recently been modified, grouping them by the
    day they were last modified.

    This macro accepts two parameters. The first is a prefix string: if
    provided, only pages with names that start with the prefix are included in
    the resulting list. If this parameter is omitted, all pages are listed.

    The second parameter is a number for limiting the number of pages returned.
    For example, specifying a limit of 5 will result in only the five most
    recently changed pages to be included in the list.
    """

    def render_macro(self, req, name, content):
        prefix = limit = None
        if content:
            argv = [arg.strip() for arg in content.split(',')]
            if len(argv) > 0:
                prefix = argv[0]
                if len(argv) > 1:
                    limit = int(argv[1])

        db = self.env.get_db_cnx()
        cursor = db.cursor()

        sql = 'SELECT name, max(time) AS max_time FROM wiki'
        args = []
        if prefix:
            sql += ' WHERE name LIKE %s'
            args.append(prefix + '%')
        sql += ' GROUP BY name ORDER BY max_time DESC'
        if limit:
            sql += ' LIMIT %s'
            args.append(limit)
        cursor.execute(sql, args)

        entries_per_date = []
        prevdate = None
        for name, time in cursor:
            date = format_date(time)
            if date != prevdate:
                prevdate = date
                entries_per_date.append((date, []))
            entries_per_date[-1][1].append(name)

        wiki = WikiSystem(self.env)
        return html.DIV[[html.H3(date) +
                         html.UL[[html.LI(html.A(wiki.format_page_name(name),
                                                   href=req.href.wiki(name)))
                                    for name in entries]]
                         for date, entries in entries_per_date]]


class PageOutlineMacro(WikiMacroBase):
    """Displays a structural outline of the current wiki page, each item in the
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


class ImageMacro(WikiMacroBase):
    """Embed an image in wiki-formatted text.
    
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
    `source:file` syntax (`source:file@rev` works also).
    
    The remaining arguments are optional and allow configuring the attributes
    and style of the rendered `<img>` element:
     * digits and unit are interpreted as the size (ex. 120, 25%)
       for the image
     * `right`, `left`, `top` or `bottom` are interpreted as the alignment for
       the image
     * `nolink` means without link to image source.
     * `key=value` style are interpreted as HTML attributes or CSS style
        indications for the image. Valid keys are:
        * align, border, width, height, alt, title, longdesc, class, id
          and usemap
        * `border` can only be a number
    
    Examples:
    {{{
        [[Image(photo.jpg)]]                           # simplest
        [[Image(photo.jpg, 120px)]]                    # with size
        [[Image(photo.jpg, right)]]                    # aligned by keyword
        [[Image(photo.jpg, nolink)]]                   # without link to source
        [[Image(photo.jpg, align=right)]]              # aligned by attribute
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
        size_re = re.compile('[0-9]+%?$')
        attr_re = re.compile('(align|border|width|height|alt'
                             '|title|longdesc|class|id|usemap)=(.+)')
        quoted_re = re.compile("(?:[\"'])(.*)(?:[\"'])$")
        attr = {}
        style = {}
        nolink = False
        for arg in args[1:]:
            arg = arg.strip()
            if size_re.match(arg):
                # 'width' keyword
                attr['width'] = arg
                continue
            if arg == 'nolink':
                nolink = True
                continue
            match = attr_re.match(arg)
            if match:
                key, val = match.groups()
                m = quoted_re.search(val) # unquote "..." and '...'
                if m:
                    val = m.group(1)
                if key == 'align':
                    style['float'] = val
                elif key == 'border':
                    style['border'] = ' %dpx solid' % int(val);
                else:
                    attr[str(key)] = val # will be used as a __call__ keyword

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
                rev = None
                if '@' in file:
                    file, rev = file.split('@')
                url = req.href.browser(file, rev=rev)
                raw_url = req.href.browser(file, rev=rev, format='raw')
                desc = filespec
            else: # #ticket:attachment or WikiPage:attachment
                # FIXME: do something generic about shorthand forms...
                id, file = parts
                if id and id[0] == '#':
                    module = 'ticket'
                    id = id[1:]
                elif id == 'htdocs':
                    raw_url = url = req.href.chrome('site', file)
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
            url = attachment.href(req)
            raw_url = attachment.href(req, format='raw')
            desc = attachment.description
        for key in ['title', 'alt']:
            if desc and not attr.has_key(key):
                attr[key] = desc
        if style:
            attr['style'] = '; '.join(['%s:%s' % (k, escape(v))
                                       for k, v in style.iteritems()])
        result = Markup(html.IMG(src=raw_url, **attr)).sanitize()
        if not nolink:
            result = html.A(result, href=url, style='padding:0; border:none')
        return result


class MacroListMacro(WikiMacroBase):
    """Displays a list of all installed Wiki macros, including documentation if
    available.
    
    Optionally, the name of a specific macro can be provided as an argument. In
    that case, only the documentation for that macro will be rendered.
    
    Note that this macro will not be able to display the documentation of
    macros if the `PythonOptimize` option is enabled for mod_python!
    """

    def render_macro(self, req, name, content):
        from trac.wiki.formatter import wiki_to_html, system_message
        from trac.wiki import WikiSystem
        wiki = WikiSystem(self.env)

        def get_macro_descr():
            for macro_provider in wiki.macro_providers:
                for macro_name in macro_provider.get_macros():
                    if content and macro_name != content:
                        continue
                    try:
                        descr = macro_provider.get_macro_description(macro_name)
                        descr = wiki_to_html(descr or '', self.env, req)
                    except Exception, e:
                        descr = Markup(system_message(
                            "Error: Can't get description for macro %s" \
                            % macro_name, e))
                    yield (macro_name, descr)

        return html.DL[[(html.DT[html.CODE['[[',macro_name,']]']],
                         html.DD[description])
                        for macro_name, description in get_macro_descr()]]


class InterTracMacro(WikiMacroBase):
    """Provide a list of known InterTrac prefixes."""

    def render_macro(self, req, name, content):
        intertracs = {}
        for key, value in self.config.options('intertrac'):
            if '.' in key:
                prefix, attribute = key.split('.', 1)
                intertrac = intertracs.setdefault(prefix, {})
                intertrac[attribute] = value
            else:
                intertracs[key] = value # alias

        def generate_prefix(prefix):
            intertrac = intertracs[prefix]
            if isinstance(intertrac, basestring):
                yield html.TR[html.TD[html.B[prefix]],
                              html.TD['Alias for ', html.B[intertrac]]]
            else:
                url = intertrac.get('url', '')
                if url:
                    title = intertrac.get('title', url)
                    yield html.TR[html.TD[html.A(href=url+'/timeline')
                                          [html.B[prefix]]],
                                  html.TD[html.A(href=url)[title]]]

        return html.TABLE(class_="wiki intertrac")[
            html.TR[html.TH[html.EM['Prefix']], html.TH[html.EM['Trac Site']]],
            [generate_prefix(p) for p in sorted(intertracs.keys())]]


class TracIniMacro(WikiMacroBase):
    """Produce documentation for Trac configuration file.

    Typically, this will be used in the TracIni page.
    Optional arguments are a configuration section filter,
    and a configuration option name filter: only the configuration
    options whose section and name start with the filters are output.
    """

    def render_macro(self, req, name, filter):
        from trac.config import Option
        from trac.wiki.formatter import wiki_to_html, wiki_to_oneliner
        filter = filter or ''

        sections = set([section for section, option in Option.registry.keys()
                        if section.startswith(filter)])

        return html.DIV(class_="tracini")(
            [(html.H2(id="%s" % section)["[%s]" % section],
              html.TABLE(class_="wiki")(
                  html.TBODY([html.TR(html.TD(html.TT[option.name]),
                                      html.TD(wiki_to_oneliner(option.__doc__,
                                                               self.env)))
                              for option in Option.registry.values()
                              if option.section == section])))
             for section in sorted(sections)])


class UserMacroProvider(Component):
    """Adds macros that are provided as Python source files in the
    `wiki-macros` directory of the environment, or the global macros
    directory.
    """
    implements(IWikiMacroProvider)

    def __init__(self):
        self.env_macros = os.path.join(self.env.path, 'wiki-macros')
        self.site_macros = default_dir('macros')

    # IWikiMacroProvider methods

    def get_macros(self):
        found = []
        for path in (self.env_macros, self.site_macros):
            if not os.path.exists(path):
                continue
            for filename in [filename for filename in os.listdir(path)
                             if filename.lower().endswith('.py')
                             and not filename.startswith('__')]:
                try:
                    module = self._load_macro(filename[:-3])
                    name = module.__name__
                    if name in found:
                        continue
                    found.append(name)
                    yield name
                except Exception, e:
                    self.log.error('Failed to load wiki macro %s (%s)',
                                   filename, e, exc_info=True)

    def get_macro_description(self, name):
        return inspect.getdoc(self._load_macro(name))

    def render_macro(self, req, name, content):
        module = self._load_macro(name)
        try:
            return module.execute(req and req.hdf, content, self.env)
        except Exception, e:
            self.log.error('Wiki macro %s failed (%s)', name, e, exc_info=True)
            raise

    def _load_macro(self, name):
        for path in (self.env_macros, self.site_macros):
            macro_file = os.path.join(path, name + '.py')
            if os.path.isfile(macro_file):
                return imp.load_source(name, macro_file)
        raise TracError, 'Macro %s not found' % name
