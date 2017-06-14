# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2012 Edgewall Software
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

from __future__ import with_statement

from fnmatch import fnmatchcase
from itertools import groupby
import inspect
import os
import re
from StringIO import StringIO

from genshi.builder import tag
from genshi.core import Markup

from trac.core import *
from trac.resource import (
    Resource, ResourceNotFound, get_resource_name, get_resource_summary,
    get_resource_url
)
from trac.util import as_int
from trac.util.datefmt import format_date, from_utimestamp, user_time
from trac.util.html import escape, find_element
from trac.util.presentation import separated
from trac.util.text import unicode_quote, to_unicode, stripws
from trac.util.translation import _, dgettext, cleandoc_, tag_
from trac.web.chrome import chrome_resource_path
from trac.wiki.api import IWikiMacroProvider, WikiSystem, parse_args
from trac.wiki.formatter import (
    MacroError, OutlineFormatter, extract_link, format_to_html,
    format_to_oneliner, system_message
)


class WikiMacroBase(Component):
    """Abstract base class for wiki macros."""

    implements(IWikiMacroProvider)
    abstract = True

    #: A gettext domain to translate the macro description
    _domain = None

    #: A macro description
    _description = None

    def get_macros(self):
        """Yield the name of the macro based on the class name."""
        name = self.__class__.__name__
        if name.endswith('Macro'):
            name = name[:-5]
        yield name

    def get_macro_description(self, name):
        """Return the subclass's gettext domain and macro description"""
        domain, description = self._domain, self._description
        if description:
            return (domain, description) if domain else description
        # For pre-0.12 compatibility
        doc = inspect.getdoc(self.__class__)
        return to_unicode(doc) if doc else ''

    def parse_macro(self, parser, name, content):
        raise NotImplementedError

    def expand_macro(self, formatter, name, content, args=None):
        raise NotImplementedError(
            "pre-0.11 Wiki macro %s by provider %s no longer supported" %
            (name, self.__class__))


class TitleIndexMacro(WikiMacroBase):
    _domain = 'messages'
    _description = cleandoc_(
    """Insert an alphabetic list of all wiki pages into the output.

    Accepts a prefix string as parameter: if provided, only pages with names
    that start with the prefix are included in the resulting list. If this
    parameter is omitted, all pages are listed.
    If the prefix is specified, a second argument of value `hideprefix`
    can be given as well, in order to remove that prefix from the output.

    Alternate `format` and `depth` named parameters can be specified:
     - `format=compact`: The pages are displayed as comma-separated links.
     - `format=group`: The list of pages will be structured in groups
       according to common prefix. This format also supports a `min=n`
       argument, where `n` is the minimal number of pages for a group.
     - `format=hierarchy`: The list of pages will be structured according
       to the page name path hierarchy. This format also supports a `min=n`
       argument, where higher `n` flatten the display hierarchy
     - `depth=n`: limit the depth of the pages to list. If set to 0,
       only toplevel pages will be shown, if set to 1, only immediate
       children pages will be shown, etc. If not set, or set to -1,
       all pages in the hierarchy will be shown.
     - `include=page1:page*2`: include only pages that match an item in the
       colon-separated list of pages. If the list is empty, or if no `include`
       argument is given, include all pages.
     - `exclude=page1:page*2`: exclude pages that match an item in the colon-
       separated list of pages.

    The `include` and `exclude` lists accept shell-style patterns.
    """)

    SPLIT_RE = re.compile(r"(/| )")
    NUM_SPLIT_RE = re.compile(r"([0-9.]+)")

    def expand_macro(self, formatter, name, content):
        args, kw = parse_args(content)
        prefix = args[0].strip() if args else None
        hideprefix = args and len(args) > 1 and args[1].strip() == 'hideprefix'
        minsize = _arg_as_int(kw.get('min', 1), 'min', min=1)
        minsize_group = max(minsize, 2)
        depth = _arg_as_int(kw.get('depth', -1), 'depth', min=-1)
        start = prefix.count('/') if prefix else 0
        format = kw.get('format', '')

        def parse_list(name):
            return [inc.strip() for inc in kw.get(name, '').split(':')
                    if inc.strip()]

        includes = parse_list('include') or ['*']
        excludes = parse_list('exclude')

        if hideprefix:
            omitprefix = lambda page: page[len(prefix):]
        else:
            omitprefix = lambda page: page

        wiki = formatter.wiki

        pages = sorted(page for page in wiki.get_pages(prefix)
                       if (depth < 0 or depth >= page.count('/') - start)
                       and 'WIKI_VIEW' in formatter.perm('wiki', page)
                       and any(fnmatchcase(page, inc) for inc in includes)
                       and not any(fnmatchcase(page, exc) for exc in excludes))

        if format == 'compact':
            return tag(
                separated((tag.a(wiki.format_page_name(omitprefix(p)),
                                 href=formatter.href.wiki(p)) for p in pages),
                          ', '))

        # the function definitions for the different format styles

        # the different page split formats, each corresponding to its rendering
        def split_pages_group(pages):
            """Return a list of (path elements, page_name) pairs,
            where path elements correspond to the page name (without prefix)
            splitted at Camel Case word boundaries, numbers and '/'.
            """
            page_paths = []
            for page in pages:
                path = [elt.strip() for elt in self.SPLIT_RE.split(
                        self.NUM_SPLIT_RE.sub(r" \1 ",
                        wiki.format_page_name(omitprefix(page), split=True)))]
                page_paths.append(([elt for elt in path if elt], page))
            return page_paths

        def split_pages_hierarchy(pages):
            """Return a list of (path elements, page_name) pairs,
            where path elements correspond to the page name (without prefix)
            splitted according to the '/' hierarchy.
            """
            return [(wiki.format_page_name(omitprefix(page)).split("/"), page)
                    for page in pages]

        # the different tree structures, each corresponding to its rendering
        def tree_group(entries):
            """Transform a flat list of entries into a tree structure.

            `entries` is a list of `(path_elements, page_name)` pairs

            Return a list organized in a tree structure, in which:
              - a leaf is a page name
              - a node is a `(key, nodes)` pairs, where:
                - `key` is the leftmost of the path elements, common to the
                  grouped (path element, page_name) entries
                - `nodes` is a list of nodes or leaves
            """
            groups = []

            for key, grouper in groupby(entries, lambda (elts, name):
                                                    elts[0] if elts else ''):
                # remove key from path_elements in grouped entries for further
                # grouping
                grouped_entries = [(path_elements[1:], page_name)
                                   for path_elements, page_name in grouper]

                if key and len(grouped_entries) >= minsize_group:
                    subnodes = tree_group(sorted(grouped_entries))
                    if len(subnodes) == 1:
                        subkey, subnodes = subnodes[0]
                        node = (key + subkey, subnodes)
                        groups.append(node)
                    elif self.SPLIT_RE.match(key):
                        for elt in subnodes:
                            if isinstance(elt, tuple):
                                subkey, subnodes = elt
                                elt = (key + subkey, subnodes)
                            groups.append(elt)
                    else:
                        node = (key, subnodes)
                        groups.append(node)
                else:
                    for path_elements, page_name in grouped_entries:
                        groups.append(page_name)
            return groups

        def tree_hierarchy(entries):
            """Transform a flat list of entries into a tree structure.

            `entries` is a list of `(path_elements, page_name)` pairs

            Return a list organized in a tree structure, in which:
              - a leaf is a `(rest, page)` pair, where:
                - `rest` is the rest of the path to be shown
                - `page` is a page name
              - a node is a `(key, nodes, page)` pair, where:
                - `key` is the leftmost of the path elements, common to the
                  grouped (path element, page_name) entries
                - `page` is a page name (if one exists for that node)
                - `nodes` is a list of nodes or leaves
            """
            groups = []

            for key, grouper in groupby(entries, lambda (elts, name):
                                                    elts[0] if elts else ''):
                grouped_entries = [e for e in grouper]
                sub_entries = [e for e in grouped_entries if len(e[0]) > 1]
                key_entries = [e for e in grouped_entries if len(e[0]) == 1]
                key_entry = key_entries[0] if key_entries else None
                key_page = key_entry[1] if key_entries else None

                if key and len(sub_entries) >= minsize:
                    # remove key from path_elements in grouped entries for
                    # further grouping
                    sub_entries = [(path_elements[1:], page)
                                   for path_elements, page in sub_entries]

                    subnodes = tree_hierarchy(sorted(sub_entries))
                    node = (key, key_page, subnodes)
                    groups.append(node)
                else:
                    if key_entry:
                        groups.append(key_entry)
                    groups.extend(sub_entries)
            return groups

        # the different rendering formats
        def render_group(group):
            return tag.ul(
                tag.li(tag(tag.strong(elt[0].strip('/')), render_group(elt[1]))
                       if isinstance(elt, tuple) else
                       tag.a(wiki.format_page_name(omitprefix(elt)),
                             href=formatter.href.wiki(elt)))
                for elt in group)

        def render_hierarchy(group):
            return tag.ul(
                tag.li(tag(tag.a(elt[0], href=formatter.href.wiki(elt[1]))
                           if elt[1] else tag(elt[0]),
                           render_hierarchy(elt[2]))
                       if len(elt) == 3 else
                       tag.a('/'.join(elt[0]),
                             href=formatter.href.wiki(elt[1])))
                for elt in group)

        transform = {
            'group': lambda p: render_group(tree_group(split_pages_group(p))),
            'hierarchy': lambda p: render_hierarchy(
                                    tree_hierarchy(split_pages_hierarchy(p))),
            }.get(format, None)

        if transform:
            titleindex = transform(pages)
        else:
            titleindex = tag.ul(
                tag.li(tag.a(wiki.format_page_name(omitprefix(page)),
                             href=formatter.href.wiki(page)))
                for page in pages)

        return tag.div(titleindex, class_='titleindex')


class RecentChangesMacro(WikiMacroBase):
    _domain = 'messages'
    _description = cleandoc_(
    """List all pages that have recently been modified, ordered by the
    time they were last modified.

    This macro accepts two ordered arguments and a named argument. The named
    argument can be placed in any position within the argument list.

    The first parameter is a prefix string: if provided, only pages with names
    that start with the prefix are included in the resulting list. If this
    parameter is omitted, all pages are included in the list.

    The second parameter is the maximum number of pages to include in the
    list.

    The `group` parameter determines how the list is presented:
      `group=date` :: The pages are presented in bulleted lists that are
        grouped by date (default).
      `group=none` :: The pages are presented in a single bulleted list.

    Tip: if you only want to specify a maximum number of entries and
    don't want to filter by prefix, specify an empty first parameter,
    e.g. `[[RecentChanges(,10,group=none)]]`.
    """)

    def expand_macro(self, formatter, name, content):
        args, kw = parse_args(content)
        prefix = args[0].strip() if args else None
        limit = _arg_as_int(args[1].strip(), min=1) if len(args) > 1 else None
        group = kw.get('group', 'date')

        sql = """SELECT name, max(version) AS max_version,
                        max(time) AS max_time FROM wiki"""
        args = []
        if prefix:
            with self.env.db_query as db:
                sql += " WHERE name %s" % db.prefix_match()
                args.append(db.prefix_match_value(prefix))
        sql += " GROUP BY name ORDER BY max_time DESC"
        if limit:
            sql += " LIMIT %s"
            args.append(limit)

        entries_per_date = []
        prevdate = None
        for name, version, ts in self.env.db_query(sql, args):
            if not 'WIKI_VIEW' in formatter.perm('wiki', name, version):
                continue
            req = formatter.req
            date = user_time(req, format_date, from_utimestamp(ts))
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

        items_per_date = (
            (date, (tag.li(tag.a(page, href=formatter.href.wiki(name)),
                           tag.small(' (', tag.a(_("diff"), href=diff_href),
                                     ')') if diff_href else None,
                           '\n')
                    for page, name, version, diff_href in entries))
            for date, entries in entries_per_date)

        if group == 'date':
            out = ((tag.h3(date), tag.ul(entries))
                   for date, entries in items_per_date)
        else:
            out = tag.ul(entries for date, entries in items_per_date)
        return tag.div(out)


class PageOutlineMacro(WikiMacroBase):
    _domain = 'messages'
    _description = cleandoc_(
    """Display a structural outline of the current wiki page, each item in the
    outline being a link to the corresponding heading.

    This macro accepts four optional parameters:

     * The first is a number or range that allows configuring the minimum and
       maximum level of headings that should be included in the outline. For
       example, specifying "1" here will result in only the top-level headings
       being included in the outline. Specifying "2-3" will make the outline
       include all headings of level 2 and 3, as a nested list. The default is
       to include all heading levels.
     * The second parameter can be used to specify a custom title (the default
       is no title).
     * The third parameter selects the style of the outline. This can be
       either `inline` or `pullout` (the latter being the default). The
       `inline` style renders the outline as normal part of the content, while
       `pullout` causes the outline to be rendered in a box that is by default
       floated to the right side of the other content.
     * The fourth parameter specifies whether the outline is numbered or not.
       It can be either `numbered` or `unnumbered` (the former being the
       default). This parameter only has an effect in `inline` style.
    """)

    def expand_macro(self, formatter, name, content):
        min_depth, max_depth = 1, 6
        title = None
        inline = False
        numbered = True
        if content:
            argv = [arg.strip() for arg in content.split(',')]
            if len(argv) > 0:
                depth = argv[0]
                if '-' in depth:
                    min_depth, max_depth = \
                        [_arg_as_int(d, min=min_depth, max=max_depth)
                         for d in depth.split('-', 1)]
                else:
                    min_depth = max_depth = \
                        _arg_as_int(depth, min=min_depth, max=max_depth)
                if len(argv) > 1:
                    title = argv[1].strip()
                    for arg in argv[2:]:
                        arg = arg.strip().lower()
                        if arg == 'inline':
                            inline = True
                        elif arg == 'unnumbered':
                            numbered = False

        # TODO: - integrate the rest of the OutlineFormatter directly here
        #       - use formatter.wikidom instead of formatter.source
        out = StringIO()
        oformatter = OutlineFormatter(self.env, formatter.context)
        oformatter.format(formatter.source, out, max_depth, min_depth,
                          shorten=not inline)
        outline = Markup(out.getvalue())

        if title:
            outline = tag.h4(title) + outline
        if not inline:
            outline = tag.div(outline, class_='wiki-toc')
        elif not numbered:
            outline = tag.div(outline, class_='wiki-toc-un')
        return outline


class ImageMacro(WikiMacroBase):
    _domain = 'messages'
    _description = cleandoc_(
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
    for absolute location of the file. The
    [http://tools.ietf.org/html/rfc2397 rfc2397] `data` URL scheme is also
    supported if the URL is enclosed in quotes.

    The remaining arguments are optional and allow configuring the attributes
    and style of the rendered `<img>` element:
     * digits and unit are interpreted as the size (ex. 120px, 25%)
       for the image
     * `right`, `left`, `center`, `top`, `bottom` and `middle` are interpreted
       as the alignment for the image (alternatively, the first three can be
       specified using `align=...` and the last three using `valign=...`)
     * `link=some TracLinks...` replaces the link to the image source by the
       one specified using a TracLinks. If no value is specified, the link is
       simply removed.
     * `inline` specifies that the content generated be an inline XHTML
       element. By default, inline content is not generated, therefore images
       won't be rendered in section headings and other one-line content.
     * `nolink` means without link to image source (deprecated, use `link=`)
     * `key=value` style are interpreted as HTML attributes or CSS style
       indications for the image. Valid keys are:
        * align, valign, border, width, height, alt, title, longdesc, class,
          margin, margin-(left,right,top,bottom), id and usemap
        * `border`, `margin`, and `margin-`* can only be a single number
          (units are pixels).
        * `margin` is superseded by `center` which uses auto margins

    Examples:
    {{{
    [[Image(photo.jpg)]]               # simplest
    [[Image(photo.jpg, 120px)]]        # with image width size
    [[Image(photo.jpg, right)]]        # aligned by keyword
    [[Image(photo.jpg, nolink)]]       # without link to source
    [[Image(photo.jpg, align=right)]]  # aligned by attribute
    }}}

    You can use an image from a wiki page, ticket or other module.
    {{{
    [[Image(OtherPage:foo.bmp)]]    # from a wiki page
    [[Image(base/sub:bar.bmp)]]     # from hierarchical wiki page
    [[Image(#3:baz.bmp)]]           # from another ticket
    [[Image(ticket:36:boo.jpg)]]    # from another ticket (long form)
    [[Image(source:/img/bee.jpg)]]  # from the repository
    [[Image(htdocs:foo/bar.png)]]   # from project htdocs dir
    [[Image(shared:foo/bar.png)]]   # from shared htdocs dir (since 1.0.2)
    }}}

    ''Adapted from the Image.py macro created by Shun-ichi Goto
    <gotoh@taiyo.co.jp>''
    """)

    def is_inline(self, content):
        args = [stripws(arg) for arg
                             in self._split_args_re.split(content or '')[1::2]]
        return 'inline' in args

    _split_re = r'''((?:[^%s"']|"[^"]*"|'[^']*')+)'''
    _split_args_re = re.compile(_split_re % ',')
    _split_filespec_re = re.compile(_split_re % ':')
    _size_re = re.compile('[0-9]+(%|px)?$')
    _attr_re = re.compile('(align|valign|border|width|height|alt'
                          '|margin(?:-(?:left|right|top|bottom))?'
                          '|title|longdesc|class|id|usemap)=(.+)')
    _quoted_re = re.compile("(?:[\"'])(.*)(?:[\"'])$")

    def expand_macro(self, formatter, name, content):
        if content:
            content = stripws(content)
        if not content:
            return ''
        # parse arguments
        # we expect the 1st argument to be a filename (filespec)
        args = [stripws(arg) for arg
                             in self._split_args_re.split(content)[1::2]]
        # strip unicode white-spaces and ZWSPs are copied from attachments
        # section (#10668)
        filespec = args.pop(0)

        # style information
        attr = {}
        style = {}
        link = ''
        # helper for the special case `source:`
        #
        from trac.versioncontrol.web_ui import BrowserModule
        # FIXME: somehow use ResourceSystem.get_known_realms()
        #        ... or directly trac.wiki.extract_link
        try:
            browser_links = [res[0] for res in
                             BrowserModule(self.env).get_link_resolvers()]
        except Exception:
            browser_links = []
        while args:
            arg = args.pop(0)
            if self._size_re.match(arg):
                # 'width' keyword
                attr['width'] = arg
            elif arg == 'nolink':
                link = None
            elif arg.startswith('link='):
                val = arg.split('=', 1)[1]
                elt = extract_link(self.env, formatter.context, val.strip())
                elt = find_element(elt, 'href')
                link = None
                if elt is not None:
                    link = elt.attrib.get('href')
            elif arg in ('left', 'right'):
                style['float'] = arg
            elif arg == 'center':
                style['margin-left'] = style['margin-right'] = 'auto'
                style['display'] = 'block'
                style.pop('margin', '')
            elif arg in ('top', 'bottom', 'middle'):
                style['vertical-align'] = arg
            else:
                match = self._attr_re.match(arg)
                if match:
                    key, val = match.groups()
                    if (key == 'align' and
                            val in ('left', 'right', 'center')) or \
                        (key == 'valign' and
                            val in ('top', 'middle', 'bottom')):
                        args.append(val)
                    elif key in ('margin-top', 'margin-bottom'):
                        style[key] = ' %dpx' % _arg_as_int(val, key, min=1)
                    elif key in ('margin', 'margin-left', 'margin-right') \
                             and 'display' not in style:
                        style[key] = ' %dpx' % _arg_as_int(val, key, min=1)
                    elif key == 'border':
                        style['border'] = ' %dpx solid' % _arg_as_int(val, key)
                    else:
                        m = self._quoted_re.search(val)  # unquote "..." and '...'
                        if m:
                            val = m.group(1)
                        attr[str(key)] = val  # will be used as a __call__ kwd

        if self._quoted_re.match(filespec):
            filespec = filespec.strip('\'"')
        # parse filespec argument to get realm and id if contained.
        parts = [i.strip('''['"]''')
                 for i in self._split_filespec_re.split(filespec)[1::2]]
        url = raw_url = desc = None
        attachment = None
        if parts and parts[0] in ('http', 'https', 'ftp', 'data'):  # absolute
            raw_url = url = filespec
            desc = url.rsplit('?')[0]
        elif filespec.startswith('//'):       # server-relative
            raw_url = url = filespec[1:]
            desc = url.rsplit('?')[0]
        elif filespec.startswith('/'):        # project-relative
            params = ''
            if '?' in filespec:
                filespec, params = filespec.rsplit('?', 1)
            url = formatter.href(filespec)
            if params:
                url += '?' + params
            raw_url, desc = url, filespec
        elif len(parts) == 3:                 # realm:id:attachment-filename
            #                                 # or intertrac:realm:id
            realm, id, filename = parts
            intertrac_target = "%s:%s" % (id, filename)
            it = formatter.get_intertrac_url(realm, intertrac_target)
            if it:
                url, desc = it
                raw_url = url + unicode_quote('?format=raw')
            else:
                attachment = Resource(realm, id).child('attachment', filename)
        elif len(parts) == 2:
            realm, filename = parts
            if realm in browser_links:  # source:path
                # TODO: use context here as well
                rev = None
                if '@' in filename:
                    filename, rev = filename.rsplit('@', 1)
                url = formatter.href.browser(filename, rev=rev)
                raw_url = formatter.href.browser(filename, rev=rev,
                                                 format='raw')
                desc = filespec
            else:  # #ticket:attachment or WikiPage:attachment
                # FIXME: do something generic about shorthand forms...
                realm = None
                id, filename = parts
                if id and id[0] == '#':
                    realm = 'ticket'
                    id = id[1:]
                elif id == 'htdocs':
                    raw_url = url = formatter.href.chrome('site', filename)
                    desc = os.path.basename(filename)
                elif id == 'shared':
                    raw_url = url = formatter.href.chrome('shared', filename)
                    desc = os.path.basename(filename)
                else:
                    realm = 'wiki'
                if realm:
                    attachment = Resource(realm, id).child('attachment',
                                                           filename)
        elif len(parts) == 1:  # it's an attachment of the current resource
            attachment = formatter.resource.child('attachment', filespec)
        else:
            return system_message(_("No filespec given"))
        if attachment:
            try:
                desc = get_resource_summary(self.env, attachment)
            except ResourceNotFound:
                link = None
                raw_url = chrome_resource_path(formatter.context.req,
                                               'common/attachment.png')
                desc = _('No image "%(id)s" attached to %(parent)s',
                         id=attachment.id,
                         parent=get_resource_name(self.env, attachment.parent))
            else:
                if 'ATTACHMENT_VIEW' in formatter.perm(attachment):
                    url = get_resource_url(self.env, attachment,
                                           formatter.href)
                    raw_url = get_resource_url(self.env, attachment,
                                               formatter.href, format='raw')

        for key in ('title', 'alt'):
            if desc and key not in attr:
                attr[key] = desc
        if style:
            attr['style'] = '; '.join('%s:%s' % (k, escape(v))
                                      for k, v in style.iteritems())
        if not WikiSystem(self.env).is_safe_origin(raw_url,
                                                   formatter.context.req):
            attr['crossorigin'] = 'anonymous'  # avoid password prompt
        result = tag.img(src=raw_url, **attr)
        if link is not None:
            result = tag.a(result, href=link or url,
                           style='padding:0; border:none')
        return result


class MacroListMacro(WikiMacroBase):
    _domain = 'messages'
    _description = cleandoc_(
    """Display a list of all installed Wiki macros, including documentation if
    available.

    Optionally, the name of a specific macro can be provided as an argument. In
    that case, only the documentation for that macro will be rendered.

    Note that this macro will not be able to display the documentation of
    macros if the `PythonOptimize` option is enabled for mod_python!
    """)

    def expand_macro(self, formatter, name, content):
        from trac.wiki.formatter import system_message

        content = content.strip() if content else ''
        name_filter = content.strip('*')

        def get_macro_descr():
            for macro_provider in formatter.wiki.macro_providers:
                names = list(macro_provider.get_macros() or [])
                if name_filter and not any(name.startswith(name_filter)
                                           for name in names):
                    continue
                try:
                    name_descriptions = [
                        (name, macro_provider.get_macro_description(name))
                        for name in names]
                except Exception, e:
                    yield system_message(
                        _("Error: Can't get description for macro %(name)s",
                          name=names[0]), e), names
                else:
                    for descr, pairs in groupby(name_descriptions,
                                                key=lambda p: p[1]):
                        if descr:
                            if isinstance(descr, (tuple, list)):
                                descr = dgettext(descr[0],
                                                 to_unicode(descr[1])) \
                                        if descr[1] else ''
                            else:
                                descr = to_unicode(descr) or ''
                            if content == '*':
                                descr = format_to_oneliner(
                                    self.env, formatter.context, descr,
                                    shorten=True)
                            else:
                                descr = format_to_html(
                                    self.env, formatter.context, descr)
                        yield descr, [name for name, descr in pairs]

        return tag.div(class_='trac-macrolist')(
            (tag.h3(tag.code('[[', names[0], ']]'), id='%s-macro' % names[0]),
             len(names) > 1 and tag.p(tag.strong(_("Aliases:")),
                                      [tag.code(' [[', alias, ']]')
                                       for alias in names[1:]]) or None,
             description or tag.em(_("Sorry, no documentation found")))
            for description, names in sorted(get_macro_descr(),
                                             key=lambda item: item[1][0]))


class TracIniMacro(WikiMacroBase):
    _domain = 'messages'
    _description = cleandoc_(
    """Produce documentation for the Trac configuration file.

    Typically, this will be used in the TracIni page.
    Optional arguments are a configuration section filter,
    and a configuration option name filter: only the configuration
    options whose section and name start with the filters are output.
    """)

    def expand_macro(self, formatter, name, content):
        from trac.config import ConfigSection, Option
        section_filter = key_filter = ''
        args, kw = parse_args(content)
        if args:
            section_filter = args.pop(0).strip()
        if args:
            key_filter = args.pop(0).strip()

        def getdoc(option_or_section):
            doc = to_unicode(option_or_section.__doc__)
            if doc:
                doc = dgettext(option_or_section.doc_domain, doc)
            return doc

        registry = ConfigSection.get_registry(self.compmgr)
        sections = dict((name, getdoc(section))
                        for name, section in registry.iteritems()
                        if name.startswith(section_filter))

        registry = Option.get_registry(self.compmgr)
        options = {}
        for (section, key), option in registry.iteritems():
            if section.startswith(section_filter):
                options.setdefault(section, {})[key] = option
                sections.setdefault(section, '')

        def default_cell(option):
            default = option.default
            if default is not None and default != '':
                return tag.td(tag.code(option.dumps(default)),
                              class_='default')
            else:
                return tag.td(_("(no default)"), class_='nodefault')

        return tag.div(class_='tracini')(
            (tag.h3(tag.code('[%s]' % section), id='%s-section' % section),
             format_to_html(self.env, formatter.context, section_doc),
             tag.table(class_='wiki')(tag.tbody(
                 tag.tr(tag.td(tag.tt(option.name)),
                        tag.td(format_to_html(self.env, formatter.context,
                                              getdoc(option))),
                        default_cell(option),
                        class_='odd' if idx % 2 else 'even')
                 for idx, option in
                    enumerate(sorted(options.get(section, {}).itervalues(),
                                     key=lambda o: o.name))
                 if option.name.startswith(key_filter))))
            for section, section_doc in sorted(sections.iteritems()))


class KnownMimeTypesMacro(WikiMacroBase):
    _domain = 'messages'
    _description = cleandoc_(
    """List all known mime-types which can be used as WikiProcessors.

    Can be given an optional argument which is interpreted as mime-type filter.
    """)

    def expand_macro(self, formatter, name, content):
        from trac.mimeview.api import Mimeview
        mime_map = Mimeview(self.env).mime_map
        mime_type_filter = ''
        args, kw = parse_args(content)
        if args:
            mime_type_filter = args.pop(0).strip().rstrip('*')

        mime_types = {}
        for key, mime_type in mime_map.iteritems():
            if (not mime_type_filter or
                mime_type.startswith(mime_type_filter)) and key != mime_type:
                mime_types.setdefault(mime_type, []).append(key)

        return tag.div(class_='mimetypes')(
            tag.table(class_='wiki')(
                tag.thead(tag.tr(
                    tag.th(_("MIME Types")),  # always use plural
                    tag.th(tag.a("WikiProcessors",
                                 href=formatter.context.href.wiki(
                                     'WikiProcessors'))))),
                tag.tbody(
                    tag.tr(tag.th(tag.tt(mime_type),
                                  style="text-align: left"),
                           tag.td(tag.code(
                               ' '.join(sorted(mime_types[mime_type])))))
                    for mime_type in sorted(mime_types.keys()))))


class TracGuideTocMacro(WikiMacroBase):
    _domain = 'messages'
    _description = cleandoc_(
    """Display a table of content for the Trac guide.

    This macro shows a quick and dirty way to make a table-of-contents
    for the !Help/Guide. The table of contents will contain the Trac* and
    WikiFormatting pages, and can't be customized. See the
    [https://trac-hacks.org/wiki/TocMacro TocMacro] for a more customizable
    table of contents.
    """)

    TOC = [('TracGuide',                    'Index'),
           ('TracInstall',                  'Installation'),
           ('TracInterfaceCustomization',   'Customization'),
           ('TracPlugins',                  'Plugins'),
           ('TracUpgrade',                  'Upgrading'),
           ('TracIni',                      'Configuration'),
           ('TracAdmin',                    'Administration'),
           ('TracBackup',                   'Backup'),
           ('TracLogging',                  'Logging'),
           ('TracPermissions',              'Permissions'),
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
           ('TracBatchModify',              'Batch Modify'),
           ('TracReports',                  'Reports'),
           ('TracRss',                      'RSS Support'),
           ('TracNotification',             'Notification'),
          ]

    def expand_macro(self, formatter, name, content):
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
                                         'missing')),
                           class_=(prefix+ref == curpage and 'active'))
                    for ref, title in self.TOC]),
            class_='wiki-toc')


def _arg_as_int(val, key=None, min=None, max=None):
    int_val = as_int(val, None, min=min, max=max)
    if int_val is None:
        raise MacroError(tag_("Invalid macro argument %(expr)s",
                              expr=tag.tt("%s=%s" % (key, val))
                                   if key else tag.tt(val)))
    return int_val
