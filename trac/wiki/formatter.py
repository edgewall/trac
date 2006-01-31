# -*- coding: iso-8859-1 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005-2006 Christian Boos <cboos@neuf.fr>
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
# Author: Jonas Borgström <jonas@edgewall.com>
#         Christopher Lenz <cmlenz@gmx.de>

import re
import os
import urllib

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from trac import util
from trac.core import *
from trac.mimeview import *
from trac.wiki.api import WikiSystem, IWikiChangeListener, IWikiMacroProvider

__all__ = ['wiki_to_html', 'wiki_to_oneliner', 'wiki_to_outline', 'Formatter' ]


def system_message(msg, text):
    return """<div class="system-message">
 <strong>%s</strong>
 <pre>%s</pre>
</div>
""" % (util.escape(msg), util.escape(text))


class WikiProcessor(object):

    def __init__(self, env, name):
        self.env = env
        self.name = name
        self.error = None

        builtin_processors = {'html': self._html_processor,
                              'default': self._default_processor,
                              'comment': self._comment_processor}
        self.processor = builtin_processors.get(name)
        if not self.processor:
            # Find a matching wiki macro
            from trac.wiki import WikiSystem
            wiki = WikiSystem(self.env)
            for macro_provider in wiki.macro_providers:
                if self.name in list(macro_provider.get_macros()):
                    self.processor = self._macro_processor
                    break
        if not self.processor:
            # Find a matching mimeview renderer
            from trac.mimeview.api import MIME_MAP
            if MIME_MAP.has_key(self.name):
                self.name = MIME_MAP[self.name]
                self.processor = self._mimeview_processor
            elif self.name in MIME_MAP.values():
                self.processor = self._mimeview_processor
            else:
                self.processor = self._default_processor
                self.error = 'No macro named [[%s]] found' % name

    def _comment_processor(self, req, text):
        return ''

    def _default_processor(self, req, text):
        return '<pre class="wiki">' + util.escape(text) + '</pre>\n'

    def _html_processor(self, req, text):
        from HTMLParser import HTMLParseError
        try:
            return util.Markup(text).sanitize()
        except HTMLParseError, e:
            self.env.log.warn(e)
            return system_message('HTML parsing error: %s' % util.escape(e.msg),
                                  text.splitlines()[e.lineno - 1].strip())

    def _macro_processor(self, req, text):
        from trac.wiki import WikiSystem
        wiki = WikiSystem(self.env)
        for macro_provider in wiki.macro_providers:
            if self.name in list(macro_provider.get_macros()):
                self.env.log.debug('Executing Wiki macro %s by provider %s'
                                   % (self.name, macro_provider))
                return macro_provider.render_macro(req, self.name, text)

    def _mimeview_processor(self, req, text):
        return Mimeview(self.env).render(req, self.name, text)

    def process(self, req, text, inline=False):
        if self.error:
            return system_message(util.Markup('Error: Failed to load processor '
                                              '<code>%s</code>', self.name),
                                  self.error)
        text = self.processor(req, text)
        if inline:
            code_block_start = re.compile('^<div class="code-block">')
            code_block_end = re.compile('</div>$')
            text, nr = code_block_start.subn('<span class="code-block">', text, 1 )
            if nr:
                text, nr = code_block_end.subn('</span>', text, 1 )
            return text
        else:
            return text


class Formatter(object):
    flavor = 'default'

    # Some constants used for clarifying the Wiki regexps:

    BOLDITALIC_TOKEN = "'''''"
    BOLD_TOKEN = "'''"
    ITALIC_TOKEN = "''"
    UNDERLINE_TOKEN = "__"
    STRIKE_TOKEN = "~~"
    SUBSCRIPT_TOKEN = ",,"
    SUPERSCRIPT_TOKEN = r"\^"
    INLINE_TOKEN = "`"

    LINK_SCHEME = r"[\w.+-]+" # as per RFC 2396
    INTERTRAC_SCHEME = r"[a-zA-Z.+-]+?" # no digits (support for shorthand links)

    QUOTED_STRING = r"'[^']+'|\"[^\"]+\""

    SHREF_TARGET_FIRST = r"[\w/?!#@]"
    SHREF_TARGET_MIDDLE = r"(?:\|(?=[^|\s])|[^|<>\s])"
    SHREF_TARGET_LAST = r"[a-zA-Z0-9/=]" # we don't want "_"

    LHREF_RELATIVE_TARGET = r"[/.][^\s[\]]*"


    # Rules provided by IWikiSyntaxProviders will be inserted,
    # between _pre_rules and _post_rules

    _pre_rules = [
        # Font styles
        r"(?P<bolditalic>%s)" % BOLDITALIC_TOKEN,
        r"(?P<bold>%s)" % BOLD_TOKEN,
        r"(?P<italic>%s)" % ITALIC_TOKEN,
        r"(?P<underline>!?%s)" % UNDERLINE_TOKEN,
        r"(?P<strike>!?%s)" % STRIKE_TOKEN,
        r"(?P<subscript>!?%s)" % SUBSCRIPT_TOKEN,
        r"(?P<superscript>!?%s)" % SUPERSCRIPT_TOKEN,
        r"(?P<inlinecode>!?\{\{\{(?P<inline>.*?)\}\}\})",
        r"(?P<inlinecode2>!?%s(?P<inline2>.*?)%s)" \
        % (INLINE_TOKEN, INLINE_TOKEN)]

    _post_rules = [
        r"(?P<htmlescape>[&<>])",
        # shref corresponds to short TracLinks, i.e. sns:stgt
        r"(?P<shref>!?((?P<sns>%s):(?P<stgt>%s|%s(?:%s*%s)?)))" \
        % (LINK_SCHEME, QUOTED_STRING,
           SHREF_TARGET_FIRST, SHREF_TARGET_MIDDLE, SHREF_TARGET_LAST),
        # lhref corresponds to long TracLinks, i.e. [lns:ltgt label?]
        r"(?P<lhref>!?\[(?:(?P<lns>%s):(?P<ltgt>%s|[^\]\s]*)|(?P<rel>%s))"
        r"(?:\s+(?P<label>%s|[^\]]+))?\])" \
        % (LINK_SCHEME, QUOTED_STRING, LHREF_RELATIVE_TARGET, QUOTED_STRING),
        # macro call
        (r"(?P<macro>!?\[\[(?P<macroname>[\w/+-]+)"
         r"(\]\]|\((?P<macroargs>.*?)\)\]\]))"),
        # heading, list, definition, indent, table...
        r"(?P<heading>^\s*(?P<hdepth>=+)\s.*\s(?P=hdepth)\s*$)",
        r"(?P<list>^(?P<ldepth>\s+)(?:\*|\d+\.) )",
        r"(?P<definition>^\s+(.+)::)\s*",
        r"(?P<indent>^(?P<idepth>\s+)(?=\S))",
        r"(?P<last_table_cell>\|\|\s*$)",
        r"(?P<table_cell>\|\|)"]

    _processor_re = re.compile('#\!([\w+-][\w+-/]*)')
    _anchor_re = re.compile('[^\w\d\.-:]+', re.UNICODE)
    
    img_re = re.compile(r"\.(gif|jpg|jpeg|png)(\?.*)?$", re.IGNORECASE)

    def __init__(self, env, req=None, absurls=0, db=None):
        self.env = env
        self.req = req
        self._db = db
        self._absurls = absurls
        self._anchors = []
        self._open_tags = []
        self.href = absurls and env.abs_href or env.href
        self._local = env.config.get('project', 'url', '') or env.abs_href.base

    def _get_db(self):
        if not self._db:
            self._db = self.env.get_db_cnx()
        return self._db
    db = property(fget=_get_db)

    def _get_rules(self):
        return WikiSystem(self.env).rules
    rules = property(_get_rules)

    def _get_link_resolvers(self):
        return WikiSystem(self.env).link_resolvers
    link_resolvers = property(_get_link_resolvers)

    def replace(self, fullmatch):
        wiki = WikiSystem(self.env)        
        for itype, match in fullmatch.groupdict().items():
            if match and not itype in wiki.helper_patterns:
                # Check for preceding escape character '!'
                if match[0] == '!':
                    return match[1:]
                if itype in wiki.external_handlers:
                    return wiki.external_handlers[itype](self, match, fullmatch)
                else:
                    return getattr(self, '_' + itype + '_formatter')(match, fullmatch)

    def tag_open_p(self, tag):
        """Do we currently have any open tag with @tag as end-tag"""
        return tag in self._open_tags

    def close_tag(self, tag):
        tmp =  ''
        for i in xrange(len(self._open_tags)-1, -1, -1):
            tmp += self._open_tags[i][1]
            if self._open_tags[i][1] == tag:
                del self._open_tags[i]
                for j in xrange(i, len(self._open_tags)):
                    tmp += self._open_tags[j][0]
                break
        return tmp

    def open_tag(self, open, close):
        self._open_tags.append((open, close))

    def simple_tag_handler(self, open_tag, close_tag):
        """Generic handler for simple binary style tags"""
        if self.tag_open_p((open_tag, close_tag)):
            return self.close_tag(close_tag)
        else:
            self.open_tag(open_tag, close_tag)
        return open_tag

    def _bolditalic_formatter(self, match, fullmatch):
        italic = ('<i>', '</i>')
        italic_open = self.tag_open_p(italic)
        tmp = ''
        if italic_open:
            tmp += italic[1]
            self.close_tag(italic[1])
        tmp += self._bold_formatter(match, fullmatch)
        if not italic_open:
            tmp += italic[0]
            self.open_tag(*italic)
        return tmp

    def _unquote(self, text):
        if text and text[0] in "'\"" and text[0] == text[-1]:
            return text[1:-1]
        else:
            return text

    def _shref_formatter(self, match, fullmatch):
        ns = fullmatch.group('sns')
        target = self._unquote(fullmatch.group('stgt'))
        return self._make_link(ns, target, match, match)

    def _lhref_formatter(self, match, fullmatch):
        ns = fullmatch.group('lns')
        target = self._unquote(fullmatch.group('ltgt'))
        label = fullmatch.group('label')
        if not label: # e.g. `[http://target]` or `[wiki:target]`
            if target:
                if target.startswith('//'): # for `[http://target]`
                    label = ns+':'+target   # use `http://target`
                else:                       # for `wiki:target`
                    label = target          # use only `target`
            else: # e.g. `[search:]` 
                label = ns
        label = self._unquote(label)
        rel = fullmatch.group('rel')
        if rel:
            return self._make_relative_link(rel, label or rel)
        else:
            return self._make_link(ns, target, match, label)

    def _make_link(self, ns, target, match, label):
        # check first for an alias defined in trac.ini
        ns = self.env.config.get('intertrac', ns.upper(), ns)
        if ns in self.link_resolvers:
            return self.link_resolvers[ns](self, ns, target,
                                           util.escape(label, False))
        elif target.startswith('//') or ns == "mailto":
            return self._make_ext_link(ns+':'+target, label)
        else:
            return self._make_intertrac_link(ns, target, label) or \
                   self._make_interwiki_link(ns, target, label) or \
                   match

    def _make_intertrac_link(self, ns, target, label):
        if self.env.siblings.has_key(ns):
            sibling = self.env.siblings[ns]
            # The following is currently needed because env.href is set
            # in trac.web.main.dispatch_request: for an environment which
            # has not yet been queried by a client, .href is not defined.
            if not hasattr(sibling, 'href'):
                from trac.web.href import Href
                def xchg_base(base):
                    return '/'.join(base.split('/')[:-1] + [ns])
                sibling.href = Href(xchg_base(self.env.href.base))
                sibling.abs_href = Href(xchg_base(self.env.abs_href.base))
            # EOKludge
            ref = wiki_to_oneliner(target, sibling)
            return ref.replace('>%s' % target, '>%s' % label)
        url = self.env.config.get('intertrac', ns.upper()+'.url')
        if url:
            name = self.env.config.get('intertrac', ns.upper()+'.title',
                                       'Trac project %s' % ns)
            sep = target.find(':')
            if sep != -1:
                url = '%s/%s/%s' % (url, target[:sep], target[sep+1:])
            else: 
                url = '%s/search?q=%s' % (url, urllib.quote_plus(target))
            return self._make_ext_link(url, label, '%s in %s' % (target, name))
        else:
            return None

    def shorthand_intertrac_helper(self, ns, target, label, fullmatch):
        if fullmatch: # short form
            it_group = fullmatch.group('it_%s' % ns)
            if it_group:
                alias = it_group.strip()
                intertrac = self.env.config.get('intertrac', alias.upper(),
                                                alias)
                target = '%s:%s' % (ns, target[len(it_group):])
                return self._make_intertrac_link(intertrac, target, label) or \
                       label
        return None

    def _make_interwiki_link(self, ns, target, label):
        interwiki = InterWikiMap(self.env)
        if interwiki.has_key(ns):
            url, title = interwiki.url(ns, target)
            return self._make_ext_link(url, label, title)
        else:
            return None

    def _make_ext_link(self, url, text, title=''):
        url = util.escape(url)
        text, title = util.escape(text), util.escape(title)
        title_attr = title and ' title="%s"' % title or ''
        if Formatter.img_re.search(url) and self.flavor != 'oneliner':
            return '<img src="%s" alt="%s" />' % (url, title or text)
        if not url.startswith(self._local):
            return '<a class="ext-link" href="%s"%s><span class="icon">' \
                   '</span>%s</a>' % (url, title_attr, text)
        else:
            return '<a href="%s"%s>%s</a>' % (url, title_attr, text)

    def _make_relative_link(self, url, text):
        url, text = util.escape(url), util.escape(text)
        if Formatter.img_re.search(url) and self.flavor != 'oneliner':
            return '<img src="%s" alt="%s" />' % (url, text)
        if url.startswith('//'): # only the protocol will be kept
            return '<a class="ext-link" href="%s">%s</a>' % (url, text)
        else:
            return '<a href="%s">%s</a>' % (url, text)

    def _bold_formatter(self, match, fullmatch):
        return self.simple_tag_handler('<strong>', '</strong>')

    def _italic_formatter(self, match, fullmatch):
        return self.simple_tag_handler('<i>', '</i>')

    def _underline_formatter(self, match, fullmatch):
        if match[0] == '!':
            return match[1:]
        else:
            return self.simple_tag_handler('<span class="underline">',
                                           '</span>')

    def _strike_formatter(self, match, fullmatch):
        if match[0] == '!':
            return match[1:]
        else:
            return self.simple_tag_handler('<del>', '</del>')

    def _subscript_formatter(self, match, fullmatch):
        if match[0] == '!':
            return match[1:]
        else:
            return self.simple_tag_handler('<sub>', '</sub>')

    def _superscript_formatter(self, match, fullmatch):
        if match[0] == '!':
            return match[1:]
        else:
            return self.simple_tag_handler('<sup>', '</sup>')

    def _inlinecode_formatter(self, match, fullmatch):
        return '<tt>%s</tt>' % util.escape(fullmatch.group('inline'))

    def _inlinecode2_formatter(self, match, fullmatch):
        return '<tt>%s</tt>' % util.escape(fullmatch.group('inline2'))

    def _htmlescape_formatter(self, match, fullmatch):
        return match == "&" and "&amp;" or match == "<" and "&lt;" or "&gt;"

    def _macro_formatter(self, match, fullmatch):
        name = fullmatch.group('macroname')
        if name in ['br', 'BR']:
            return '<br />'
        args = fullmatch.group('macroargs')
        try:
            macro = WikiProcessor(self.env, name)
            return macro.process(self.req, args, 1)
        except Exception, e:
            self.env.log.error('Macro %s(%s) failed' % (name, args),
                               exc_info=True)
            return system_message('Error: Macro %s(%s) failed' % (name, args), e)

    def _heading_formatter(self, match, fullmatch):
        match = match.strip()
        self.close_table()
        self.close_paragraph()
        self.close_indentation()
        self.close_list()
        self.close_def_list()

        depth = min(len(fullmatch.group('hdepth')), 5)
        heading = match[depth + 1:len(match) - depth - 1]

        text = wiki_to_oneliner(heading, self.env, self.db, self._absurls)
        sans_markup = re.sub(r'</?\w+(?: .*?)?>', '', text)

        anchor = self._anchor_re.sub('', sans_markup.decode('utf-8'))
        if not anchor or not anchor[0].isalpha():
            # an ID must start with a letter in HTML
            anchor = 'a' + anchor
        i = 1
        anchor = anchor_base = anchor.encode('utf-8')
        while anchor in self._anchors:
            anchor = anchor_base + str(i)
            i += 1
        self._anchors.append(anchor)
        self.out.write('<h%d id="%s">%s</h%d>' % (depth, anchor, text, depth))

    def _indent_formatter(self, match, fullmatch):
        depth = int((len(fullmatch.group('idepth')) + 1) / 2)
        list_depth = len(self._list_stack)
        if list_depth > 0 and depth == list_depth + 1:
            self.in_list_item = 1
        else:
            self.open_indentation(depth)
        return ''

    def _last_table_cell_formatter(self, match, fullmatch):
        return ''

    def _table_cell_formatter(self, match, fullmatch):
        self.open_table()
        self.open_table_row()
        if self.in_table_cell:
            return '</td><td>'
        else:
            self.in_table_cell = 1
            return '<td>'

    def close_indentation(self):
        self.out.write(('</blockquote>' + os.linesep) * self.indent_level)
        self.indent_level = 0

    def open_indentation(self, depth):
        if self.in_def_list:
            return
        diff = depth - self.indent_level
        if diff != 0:
            self.close_paragraph()
            self.close_indentation()
            self.close_list()
            self.indent_level = depth
            self.out.write(('<blockquote>' + os.linesep) * depth)

    def _list_formatter(self, match, fullmatch):
        ldepth = len(fullmatch.group('ldepth'))
        depth = int((len(fullmatch.group('ldepth')) + 1) / 2)
        self.in_list_item = depth > 0
        type_ = ['ol', 'ul'][match[ldepth] == '*']
        self._set_list_depth(depth, type_)
        return ''

    def _definition_formatter(self, match, fullmatch):
        tmp = self.in_def_list and '</dd>' or '<dl>'
        tmp += '<dt>%s</dt><dd>' % wiki_to_oneliner(match[:-2], self.env,
                                                    self.db)
        self.in_def_list = True
        return tmp

    def close_def_list(self):
        if self.in_def_list:
            self.out.write('</dd></dl>\n')
        self.in_def_list = False

    def _set_list_depth(self, depth, type_):
        current_depth = len(self._list_stack)
        diff = depth - current_depth
        self.close_table()
        self.close_paragraph()
        self.close_indentation()
        if diff > 0:
            for i in range(diff):
                self._list_stack.append(type_)
                self.out.write('<%s><li>' % type_)
        elif diff < 0:
            for i in range(-diff):
                tmp = self._list_stack.pop()
                self.out.write('</li></%s>' % tmp)
            if self._list_stack != [] and type_ != self._list_stack[-1]:
                tmp = self._list_stack.pop()
                self._list_stack.append(type_)
                self.out.write('</li></%s><%s><li>' % (tmp, type_))
            if depth > 0:
                self.out.write('</li><li>')
        # diff == 0
        elif self._list_stack != [] and type_ != self._list_stack[-1]:
            tmp = self._list_stack.pop()
            self._list_stack.append(type_)
            self.out.write('</li></%s><%s><li>' % (tmp, type_))
        elif depth > 0:
            self.out.write('</li><li>')

    def close_list(self):
        if self._list_stack != []:
            self._set_list_depth(0, None)

    def open_paragraph(self):
        if not self.paragraph_open:
            self.out.write('<p>' + os.linesep)
            self.paragraph_open = 1

    def close_paragraph(self):
        if self.paragraph_open:
            while self._open_tags != []:
                self.out.write(self._open_tags.pop()[1])
            self.out.write('</p>' + os.linesep)
            self.paragraph_open = 0

    def open_table(self):
        if not self.in_table:
            self.close_paragraph()
            self.close_indentation()
            self.close_list()
            self.close_def_list()
            self.in_table = 1
            self.out.write('<table class="wiki">' + os.linesep)

    def open_table_row(self):
        if not self.in_table_row:
            self.open_table()
            self.in_table_row = 1
            self.out.write('<tr>')

    def close_table_row(self):
        if self.in_table_row:
            self.in_table_row = 0
            if self.in_table_cell:
                self.in_table_cell = 0
                self.out.write('</td>')

            self.out.write('</tr>')

    def close_table(self):
        if self.in_table:
            self.close_table_row()
            self.out.write('</table>' + os.linesep)
            self.in_table = 0

    def handle_code_block(self, line):
        if line.strip() == '{{{':
            self.in_code_block += 1
            if self.in_code_block == 1:
                self.code_processor = None
                self.code_text = ''
            else:
                self.code_text += line + os.linesep
                if not self.code_processor:
                    self.code_processor = WikiProcessor(self.env, 'default')
        elif line.strip() == '}}}':
            self.in_code_block -= 1
            if self.in_code_block == 0 and self.code_processor:
                self.close_paragraph()
                self.close_table()
                self.out.write(self.code_processor.process(self.req, self.code_text))
            else:
                self.code_text += line + os.linesep
        elif not self.code_processor:
            match = Formatter._processor_re.search(line)
            if match:
                name = match.group(1)
                self.code_processor = WikiProcessor(self.env, name)
            else:
                self.code_text += line + os.linesep 
                self.code_processor = WikiProcessor(self.env, 'default')
        else:
            self.code_text += line + os.linesep

    def format(self, text, out, escape_newlines=False):
        self.out = out
        self._open_tags = []
        self._list_stack = []

        self.in_code_block = 0
        self.in_table = 0
        self.in_def_list = 0
        self.in_table_row = 0
        self.in_table_cell = 0
        self.indent_level = 0
        self.paragraph_open = 0

        for line in text.splitlines():
            # Handle code block
            if self.in_code_block or line.strip() == '{{{':
                self.handle_code_block(line)
                continue
            # Handle Horizontal ruler
            elif line[0:4] == '----':
                self.close_paragraph()
                self.close_indentation()
                self.close_list()
                self.close_def_list()
                self.close_table()
                self.out.write('<hr />' + os.linesep)
                continue
            # Handle new paragraph
            elif line == '':
                self.close_paragraph()
                self.close_indentation()
                self.close_list()
                self.close_def_list()
                continue

            if escape_newlines:
                line += ' [[BR]]'
            self.in_list_item = False
            # Throw a bunch of regexps on the problem
            result = re.sub(self.rules, self.replace, line)

            if not self.in_list_item:
                self.close_list()

            if self.in_def_list and not line.startswith(' '):
                self.close_def_list()

            if self.in_table and line[0:2] != '||':
                self.close_table()

            if len(result) and not self.in_list_item and not self.in_def_list \
                    and not self.in_table:
                self.open_paragraph()
            out.write(result + os.linesep)
            self.close_table_row()

        self.close_table()
        self.close_paragraph()
        self.close_indentation()
        self.close_list()
        self.close_def_list()


class OneLinerFormatter(Formatter):
    """
    A special version of the wiki formatter that only implement a
    subset of the wiki formatting functions. This version is useful
    for rendering short wiki-formatted messages on a single line
    """
    flavor = 'oneliner'

    def __init__(self, env, absurls=0, db=None):
        Formatter.__init__(self, env, None, absurls, db)

    # Override a few formatters to disable some wiki syntax in "oneliner"-mode
    def _list_formatter(self, match, fullmatch): return match
    def _indent_formatter(self, match, fullmatch): return match
    def _heading_formatter(self, match, fullmatch):
        return util.escape(match, False)
    def _definition_formatter(self, match, fullmatch):
        return util.escape(match, False)
    def _table_cell_formatter(self, match, fullmatch): return match
    def _last_table_cell_formatter(self, match, fullmatch): return match

    def _macro_formatter(self, match, fullmatch):
        name = fullmatch.group('macroname')
        if name.lower() == 'br':
            return ' '
        elif name == 'comment':
            return ''
        else:
            args = fullmatch.group('macroargs')
            return '[[%s%s]]' % (name,  args and '(...)' or '')

    def format(self, text, out, shorten=False):
        if not text:
            return
        self.out = out
        self._open_tags = []

        # Simplify code blocks
        in_code_block = 0
        processor = None
        buf = StringIO()
        for line in text.strip().splitlines():
            if line.strip() == '{{{':
                in_code_block += 1
            elif line.strip() == '}}}':
                if in_code_block:
                    in_code_block -= 1
                    if in_code_block == 0:
                        if processor != 'comment':
                            print>>buf, ' ![...]'
                        processor = None
            elif in_code_block:
                if not processor:
                    if line.startswith('#!'):
                        processor = line[2:].strip()
            else:
                print>>buf, line
        result = buf.getvalue()[:-1]

        if shorten:
            result = util.shorten_line(result)

        result = re.sub(self.rules, self.replace, result)
        result = result.replace('[...]', '[&hellip;]')
        if result.endswith('...'):
            result = result[:-3] + '&hellip;'

        # Close all open 'one line'-tags
        result += self.close_tag(None)
        out.write(result)


class OutlineFormatter(Formatter):
    """Special formatter that generates an outline of all the headings in wiki
    text."""
    flavor = 'outline'
    
    def __init__(self, env, absurls=0, db=None):
        Formatter.__init__(self, env, None, absurls, db)

    # Override a few formatters to disable some wiki syntax in "outline"-mode
    def _macro_formatter(self, match, fullmatch):
        return match

    def format(self, text, out, max_depth=6, min_depth=1):
        self.outline = []
        class NullOut(object):
            def write(self, data): pass
        Formatter.format(self, text, NullOut())

        if min_depth > max_depth:
            min_depth, max_depth = max_depth, min_depth
        max_depth = min(6, max_depth)
        min_depth = max(1, min_depth)

        curr_depth = min_depth - 1
        for depth, link in self.outline:
            if depth < min_depth or depth > max_depth:
                continue
            if depth < curr_depth:
                out.write('</li></ol><li>' * (curr_depth - depth))
            elif depth > curr_depth:
                out.write('<ol><li>' * (depth - curr_depth))
            else:
                out.write("</li><li>\n")
            curr_depth = depth
            out.write(link)
        out.write('</li></ol>' * curr_depth)

    def _heading_formatter(self, match, fullmatch):
        Formatter._heading_formatter(self, match, fullmatch)
        depth = min(len(fullmatch.group('hdepth')), 5)
        heading = match[depth + 1:len(match) - depth - 1]
        anchor = self._anchors[-1]
        text = wiki_to_oneliner(heading, self.env, self.db, self._absurls)
        text = re.sub(r'</?a(?: .*?)?>', '', text) # Strip out link tags
        self.outline.append((depth, '<a href="#%s">%s</a>' % (anchor, text)))


def wiki_to_html(wikitext, env, req, db=None, absurls=0, escape_newlines=False):
    out = StringIO()
    Formatter(env, req, absurls, db).format(wikitext, out, escape_newlines)
    return util.Markup(out.getvalue())

def wiki_to_oneliner(wikitext, env, db=None, shorten=False, absurls=0):
    out = StringIO()
    OneLinerFormatter(env, absurls, db).format(wikitext, out, shorten)
    return util.Markup(out.getvalue())

def wiki_to_outline(wikitext, env, db=None, absurls=0, max_depth=None,
                    min_depth=None):
    out = StringIO()
    OutlineFormatter(env, absurls, db).format(wikitext, out, max_depth,
                                              min_depth)
    return util.Markup(out.getvalue())


# -- InterWiki support

class InterWikiMap(Component):

    implements(IWikiChangeListener, IWikiMacroProvider)

    _page_name = 'InterMapTxt'
    _interwiki_re = re.compile(r"(%s)[ \t]+([^ \t]+)(?:[ \t]+#(.*))?" %
                               Formatter.LINK_SCHEME, re.UNICODE)
    _argspec_re = re.compile(r"\$\d")

    def __init__(self):
        self._interwiki_map = None
        # This dictionary maps upper-cased namespaces
        # to (namespace, prefix, title) values

    def _expand(self, txt, args):
        def setarg(match):
            num = int(match.group()[1:])
            return 0 < num <= len(args) and args[num-1] or ''
        return re.sub(InterWikiMap._argspec_re, setarg, txt)

    def _expand_or_append(self, txt, args):
        if not args:
            return txt
        expanded = self._expand(txt, args)
        return expanded == txt and txt + args[0] or expanded

    def has_key(self, ns):
        if not self._interwiki_map:
            self._update()
        return self._interwiki_map.has_key(ns.upper())

    def url(self, ns, target):
        ns, url, title = self._interwiki_map[ns.upper()]
        args = target.split(':')
        expanded_url = self._expand_or_append(url, args)
        expanded_title = self._expand(title, args)
        if expanded_title == title:
            expanded_title = target+' in '+title
        return expanded_url, expanded_title

    # IWikiChangeListener methods

    def wiki_page_added(self, page):
        if page.name == InterWikiMap._page_name:
            self._update()

    def wiki_page_changed(self, page, version, t, comment, author, ipnr):
        if page.name == InterWikiMap._page_name:
            self._update()

    def wiki_page_deleted(self, page):
        if page.name == InterWikiMap._page_name:
            self._interwiki_map.clear()

    def _update(self):
        from trac.wiki.model import WikiPage
        self._interwiki_map = {}
        content = WikiPage(self.env, InterWikiMap._page_name).text
        in_map = False
        for line in content.split('\n'):
            if in_map:
                if line.startswith('----'):
                    in_map = False
                else:
                    m = re.match(InterWikiMap._interwiki_re, line)
                    if m:
                        prefix, url, title = m.groups()
                        url = url.strip()
                        title = title and title.strip() or prefix
                        self._interwiki_map[prefix.upper()] = (prefix, url,
                                                               title)
            elif line.startswith('----'):
                in_map = True

    # IWikiMacroProvider

    def get_macros(self):
        yield 'InterWiki'

    def get_macro_description(self, name): 
        return "Provide a description list for the known InterWiki prefixes."

    def render_macro(self, req, name, content):
        if not self._interwiki_map:
            self._update()
        keys = self._interwiki_map.keys()
        keys.sort()
        buf = StringIO()
        buf.write('<table><tr><th>Prefix</th><td>Site</td></tr>\n')
        for k in keys:
            prefix, url, title = self._interwiki_map[k]
            rc_url = self._expand_or_append(url, ['RecentChanges'])
            description = title == prefix and url or title
            buf.write('<tr>\n' +
                      '<td><a href="%s">%s</a></td>' % (rc_url, prefix) +
                      '<td><a href="%s">%s</a></td>\n' % (url, description) +
                      '</tr>\n')
        buf.write('</table>\n')
        return buf.getvalue()
