# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
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

from datetime import datetime
import imp
import inspect
import os
import re
from StringIO import StringIO

from genshi.builder import Element, tag
from genshi.core import Markup

from trac.core import *
from trac.resource import Resource, get_resource_url, get_resource_summary
from trac.util.datefmt import format_date, utc
from trac.util.compat import sorted, groupby, any, set
from trac.util.html import escape
from trac.util.text import unquote, to_unicode
from trac.util.translation import _
from trac.wiki.api import IWikiMacroProvider, WikiSystem, parse_args
from trac.wiki.formatter import format_to_html, format_to_oneliner, \
                                extract_link, OutlineFormatter
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
        return to_unicode(inspect.getdoc(self.__class__))

    def parse_macro(self, parser, name, content):
        raise NotImplementedError

    def expand_macro(self, formatter, name, content):
        # -- TODO: remove in 0.12
        if hasattr(self, 'render_macro'):
            self.log.warning('Executing pre-0.11 Wiki macro %s by provider %s'
                             % (name, self.__class__))            
            return self.render_macro(formatter.req, name, content)
        # -- 
        raise NotImplementedError


class TitleIndexMacro(WikiMacroBase):
    """Inserts an alphabetic list of all wiki pages into the output.

    Accepts a prefix string as parameter: if provided, only pages with names
    that start with the prefix are included in the resulting list. If this
    parameter is omitted, all pages are listed.

    Alternate `format` and `depth` can be specified:
     - `format=group`: The list of page will be structured in groups
       according to common prefix. This format also supports a `min=n`
       argument, where `n` is the minimal number of pages for a group.
     - `depth=n`: limit the depth of the pages to list. If set to 0,
       only toplevel pages will be shown, if set to 1, only immediate
       children pages will be shown, etc. If not set, or set to -1,
       all pages in the hierarchy will be shown.
    """

    SPLIT_RE = re.compile(r"( |/|[0-9])")

    def expand_macro(self, formatter, name, content):
        args, kw = parse_args(content)
        prefix = args and args[0] or None
        format = kw.get('format', '')
        minsize = max(int(kw.get('min', 2)), 2)
        depth = int(kw.get('depth', -1))
        start = prefix and prefix.count('/') or 0

        wiki = formatter.wiki
        pages = sorted([page for page in wiki.get_pages(prefix) \
                        if 'WIKI_VIEW' in formatter.perm('wiki', page)])

        if format != 'group':
            return tag.ul([tag.li(tag.a(wiki.format_page_name(page),
                                        href=formatter.href.wiki(page)))
                           for page in pages
                           if depth < 0 or depth >= page.count('/') - start])
        
        # Group by Wiki word and/or Wiki hierarchy
        pages = [(self.SPLIT_RE.split(wiki.format_page_name(page, split=True)),
                  page) for page in pages
                 if depth < 0 or depth >= page.count('/') - start]
        def split_in_groups(group):
            """Return list of pagename or (key, sublist) elements"""
            groups = []
            for key, subgrp in groupby(group, lambda (k,p): k and k[0] or ''):
                subgrp = [(k[1:],p) for k,p in subgrp]
                if key and len(subgrp) >= minsize:
                    sublist = split_in_groups(sorted(subgrp))
                    if len(sublist) == 1:
                        elt = (key+sublist[0][0], sublist[0][1])
                    else:
                        elt = (key, sublist)
                    groups.append(elt)
                else:
                    for elt in subgrp:
                        groups.append(elt[1])
            return groups

        def render_groups(groups):
            return tag.ul(
                [tag.li(isinstance(elt, tuple) and 
                        tag(tag.strong(elt[0]), render_groups(elt[1])) or
                        tag.a(wiki.format_page_name(elt),
                              href=formatter.href.wiki(elt)))
                 for elt in groups])
        return render_groups(split_in_groups(pages))


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

    def expand_macro(self, formatter, name, content):
        prefix = limit = None
        if content:
            argv = [arg.strip() for arg in content.split(',')]
            if len(argv) > 0:
                prefix = argv[0]
                if len(argv) > 1:
                    limit = int(argv[1])

        cursor = formatter.db.cursor()

        sql = 'SELECT name, ' \
              '  max(version) AS max_version, ' \
              '  max(time) AS max_time ' \
              'FROM wiki'
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
        for name, version, ts in cursor:
            if not 'WIKI_VIEW' in formatter.perm('wiki', name, version):
                continue
            time = datetime.fromtimestamp(ts, utc)
            date = format_date(time)
            if date != prevdate:
                prevdate = date
                entries_per_date.append((date, []))
            version = int(version)
            diff_href = None
            if version > 1:
                diff_href = formatter.href.wiki(name, action='diff',
                                                version=version)
            page_name = formatter.wiki.format_page_name(name)
            entries_per_date[-1][1].append((page_name, name, version,
                                            diff_href))

        return tag.div([tag.h3(date) +
                        tag.ul([tag.li(tag.a(page_name,
                                             href=formatter.href.wiki(name)),
                                       ' ',
                                       diff_href and 
                                       tag.small('(', tag.a('diff',
                                                            href=diff_href),
                                                 ')') or
                                       None)
                                for page_name, name, version, diff_href
                                in entries])
                        for date, entries in entries_per_date])


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

    def expand_macro(self, formatter, name, content):
        min_depth, max_depth = 1, 6
        title = None
        inline = 0
        if content:
            argv = [arg.strip() for arg in content.split(',')]
            if len(argv) > 0:
                depth = argv[0]
                if '-' in depth:
                    min_depth, max_depth = [int(d) for d in depth.split('-', 1)]
                else:
                    min_depth = max_depth = int(depth)
                if len(argv) > 1:
                    title = argv[1].strip()
                    if len(argv) > 2:
                        inline = argv[2].strip().lower() == 'inline'

        # TODO: - integrate the rest of the OutlineFormatter directly here
        #       - use formatter.wikidom instead of formatter.source
        out = StringIO()
        OutlineFormatter(self.env, formatter.context).format(formatter.source,
                                                             out, max_depth,
                                                             min_depth)
        outline = Markup(out.getvalue())

        if title:
            outline = tag.h4(title) + outline
        if not inline:
            outline = tag.div(outline, class_="wiki-toc")
        return outline


class ImageMacro(WikiMacroBase):
    """Embed an image in wiki-formatted text.
    
    The first argument is the file specification. The file specification may
    reference attachments in three ways:
     * `module:id:file`, where module can be either '''wiki''' or '''ticket''',
       to refer to the attachment named ''file'' of the specified wiki page or
       ticket.
     * `id:file`: same as above, but id is either a ticket shorthand or a Wiki
       page name.
     * `file` to refer to a local attachment named 'file'. This only works from
       within that wiki page or a ticket.
    
    Also, the file specification may refer to repository files, using the
    `source:file` syntax (`source:file@rev` works also).
    
    Files can also be accessed with a direct URLs; `/file` for a
    project-relative, `//file` for a server-relative, or `http://server/file`
    for absolute location of the file.
    
    The remaining arguments are optional and allow configuring the attributes
    and style of the rendered `<img>` element:
     * digits and unit are interpreted as the size (ex. 120, 25%)
       for the image
     * `right`, `left`, `top` or `bottom` are interpreted as the alignment for
       the image
     * `link=some TracLinks...` replaces the link to the image source by the
       one specified using a TracLinks. If no value is specified, the link is
       simply removed.
     * `nolink` means without link to image source (deprecated, use `link=`)
     * `key=value` style are interpreted as HTML attributes or CSS style
       indications for the image. Valid keys are:
        * align, border, width, height, alt, title, longdesc, class, id
          and usemap
        * `border` can only be a number
    
    Examples:
    {{{
        [[Image(photo.jpg)]]                           # simplest
        [[Image(photo.jpg, 120px)]]                    # with image width size
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

    def expand_macro(self, formatter, name, content):
        # args will be null if the macro is called without parenthesis.
        if not content:
            return ''
        # parse arguments
        # we expect the 1st argument to be a filename (filespec)
        args = content.split(',')
        if len(args) == 0:
            raise Exception("No argument.")
        filespec = args[0]

        # style information
        size_re = re.compile('[0-9]+(%|px)?$')
        attr_re = re.compile('(align|border|width|height|alt'
                             '|title|longdesc|class|id|usemap)=(.+)')
        quoted_re = re.compile("(?:[\"'])(.*)(?:[\"'])$")
        attr = {}
        style = {}
        link = ''
        for arg in args[1:]:
            arg = arg.strip()
            if size_re.match(arg):
                # 'width' keyword
                attr['width'] = arg
                continue
            if arg == 'nolink':
                link = None
                continue
            if arg.startswith('link='):
                val = arg.split('=', 1)[1]
                elt = extract_link(self.env, formatter.context, val.strip())
                link = None
                if isinstance(elt, Element):
                    link = elt.attrib.get('href')
                continue
            if arg in ('left', 'right', 'top', 'bottom'):
                style['float'] = arg
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

        # parse filespec argument to get realm and id if contained.
        parts = filespec.split(':')
        url = raw_url = desc = None
        attachment = None
        if (parts and parts[0] in ('http', 'https', 'ftp')): # absolute
            raw_url = url = desc = filespec
        elif filespec.startswith('//'):       # server-relative
            raw_url = url = desc = filespec[1:]
        elif filespec.startswith('/'):        # project-relative
            # use href, but unquote to allow args (use default html escaping)
            raw_url = url = desc = unquote(formatter.href(filespec))
        elif len(parts) == 3:                 # realm:id:attachment-filename
            realm, id, filename = parts
            attachment = Resource(realm, id).child('attachment', filename)
        elif len(parts) == 2:
            # FIXME: somehow use ResourceSystem.get_known_realms()
            #        ... or directly trac.wiki.extract_link
            from trac.versioncontrol.web_ui import BrowserModule
            try:
                browser_links = [res[0] for res in
                                 BrowserModule(self.env).get_link_resolvers()]
            except Exception:
                browser_links = []
            if parts[0] in browser_links:   # source:path
                # TODO: use context here as well
                realm, filename = parts
                rev = None
                if '@' in filename:
                    filename, rev = filename.split('@')
                url = formatter.href.browser(filename, rev=rev)
                raw_url = formatter.href.browser(filename, rev=rev,
                                                 format='raw')
                desc = filespec
            else: # #ticket:attachment or WikiPage:attachment
                # FIXME: do something generic about shorthand forms...
                realm = None
                id, filename = parts
                if id and id[0] == '#':
                    realm = 'ticket'
                    id = id[1:]
                elif id == 'htdocs':
                    raw_url = url = formatter.href.chrome('site', filename)
                    desc = os.path.basename(filename)
                else:
                    realm = 'wiki'
                if realm:
                    attachment = Resource(realm, id).child('attachment',
                                                           filename)
        elif len(parts) == 1: # it's an attachment of the current resource
            attachment = formatter.resource.child('attachment', filespec)
        else:
            raise TracError('No filespec given')
        if attachment and 'ATTACHMENT_VIEW' in formatter.perm(attachment):
            url = get_resource_url(self.env, attachment, formatter.href)
            raw_url = get_resource_url(self.env, attachment, formatter.href,
                                       format='raw')
            desc = get_resource_summary(self.env, attachment)
        for key in ('title', 'alt'):
            if desc and not key in attr:
                attr[key] = desc
        if style:
            attr['style'] = '; '.join(['%s:%s' % (k, escape(v))
                                       for k, v in style.iteritems()])
        result = tag.img(src=raw_url, **attr)
        if link is not None:
            result = tag.a(result, href=link or url,
                           style='padding:0; border:none')
        return result


class MacroListMacro(WikiMacroBase):
    """Displays a list of all installed Wiki macros, including documentation if
    available.
    
    Optionally, the name of a specific macro can be provided as an argument. In
    that case, only the documentation for that macro will be rendered.
    
    Note that this macro will not be able to display the documentation of
    macros if the `PythonOptimize` option is enabled for mod_python!
    """

    def expand_macro(self, formatter, name, content):
        from trac.wiki.formatter import system_message

        def get_macro_descr():
            for macro_provider in formatter.wiki.macro_providers:
                for macro_name in macro_provider.get_macros():
                    if content and macro_name != content:
                        continue
                    try:
                        descr = macro_provider.get_macro_description(macro_name)
                        descr = format_to_html(self.env, formatter.context,
                                               to_unicode(descr) or '')
                    except Exception, e:
                        descr = system_message(_("Error: Can't get description "
                                                 "for macro %(name)s",
                                                 name=macro_name), e)
                    yield (macro_name, descr)

        return tag.dl([(tag.dt(tag.code('[[',macro_name,']]'),
                               id='%s-macro' % macro_name),
                        tag.dd(description))
                       for macro_name, description in get_macro_descr()])


class TracIniMacro(WikiMacroBase):
    """Produce documentation for Trac configuration file.

    Typically, this will be used in the TracIni page.
    Optional arguments are a configuration section filter,
    and a configuration option name filter: only the configuration
    options whose section and name start with the filters are output.
    """

    def expand_macro(self, formatter, name, args):
        from trac.config import Option
        section_filter = key_filter = ''
        args, kw = parse_args(args)
        if args:
            section_filter = args.pop(0).strip()
        if args:
            key_filter = args.pop(0).strip()

        sections = set([section for section, option in Option.registry.keys()
                        if section.startswith(section_filter)])

        return tag.div(class_='tracini')(
            [(tag.h2('[%s]' % section, id='%s-section' % section),
              tag.table(class_='wiki')(
            tag.tbody([tag.tr(tag.td(tag.tt(option.name)),
                              tag.td(format_to_oneliner(
                                            self.env, formatter.context,
                                            to_unicode(option.__doc__))))
                       for option in sorted(Option.registry.values(),
                                            key=lambda o: o.name)
                       if option.section == section and
                           option.name.startswith(key_filter)])))
             for section in sorted(sections)])



class TracGuideTocMacro(WikiMacroBase):
    """
    This macro shows a quick and dirty way to make a table-of-contents
    for a set of wiki pages.
    """

    TOC = [('TracGuide',                    'Index'),
           ('TracInstall',                  'Installation'),
           ('TracInterfaceCustomization',   'Customization'),
           ('TracPlugins',                  'Plugins'),
           ('TracUpgrade',                  'Upgrading'),
           ('TracIni',                      'Configuration'),
           ('TracAdmin',                    'Administration'),
           ('TracBackup',                   'Backup'),
           ('TracLogging',                  'Logging'),
           ('TracPermissions' ,             'Permissions'),
           ('TracWiki',                     'The Wiki'),
           ('WikiFormatting',               'Wiki Formatting'),
           ('TracTimeline',                 'Timeline'),
           ('TracBrowser',                  'Repository Browser'),
           ('TracRevisionLog',              'Revision Log'),
           ('TracChangeset',                'Changesets'),
           ('TracTickets',                  'Tickets'),
           ('TracWorkflow',                 'Workflow'),
           ('TracRoadmap',                  'Roadmap'),
           ('TracQuery',                    'Ticket Queries'),
           ('TracReports',                  'Reports'),
           ('TracRss',                      'RSS Support'),
           ('TracNotification',             'Notification'),
          ]

    def expand_macro(self, formatter, name, args):
        curpage = formatter.resource.id

        # scoped TOC (e.g. TranslateRu/TracGuide or 0.11/TracGuide ...)
        prefix = ''
        idx = curpage.find('/')
        if idx > 0:
            prefix = curpage[:idx+1]
            
        ws = WikiSystem(self.env)
        return tag.div(
            tag.h4(_('Table of Contents')),
            tag.ul([tag.li(tag.a(title, href=formatter.href.wiki(prefix+ref),
                                 class_=(not ws.has_page(prefix+ref) and
                                         "missing")),
                           class_=(prefix+ref == curpage and "active"))
                    for ref, title in self.TOC]),
            class_="wiki-toc")
