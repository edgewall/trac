 # -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004 Edgewall Software
# Copyright (C) 2003, 2004 Jonas Borgström <jonas@edgewall.com>
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

import re
import os
import time
import string
import StringIO

import util

__all__ = ['Formatter', 'OneLinerFormatter', 'wiki_to_html', 'wiki_to_oneliner']


class CommonFormatter:
    """This class contains the patterns common to both Formatter and
    OneLinerFormatter"""

    _rules = [r"""(?P<bold>''')""",
              r"""(?P<italic>'')""",
              r"""(?P<underline>__)""",
              r"""(?P<inlinecode>\{\{\{(?P<inline>.*?)\}\}\})""",
              r"""(?P<htmlescapeentity>&#\d+;)""",
              r"""(?P<tickethref>#\d+)""",
              r"""(?P<changesethref>\[\d+\])""",
              r"""(?P<reporthref>\{\d+\})""",
              r"""(?P<modulehref>((?P<modulename>bug|ticket|browser|source|repos|report|changeset|wiki|search):(?P<moduleargs>(&#34;(.*?)&#34;|'(.*?)')|([^ ]*[^\., \)]))))""",
              r"""(?P<wikilink>(^|(?<=[^A-Za-z]))[!]?[A-Z][a-z0-9/.]+(?:[A-Z][a-z0-9/.]*[a-z0-9/])+(?=\Z|\s|,|\.|:))""",
              r"""(?P<fancylink>\[(?P<fancyurl>([a-z]+:[^ ]+)) (?P<linkname>.*?)\])"""]

    _open_tags = []
    hdf = None
    env = None

    def __init__(self, hdf, env):
        self.hdf = hdf
        self.env = env

    def replace(self, fullmatch):
        for itype, match in fullmatch.groupdict().items():
            if match and not itype in Formatter._helper_patterns:
                return getattr(self, '_' + itype + '_formatter')(match, fullmatch)

    def tag_open_p(self, tag):
        """Do we currently have any open tag with @tag as end-tag"""
        return tag in self._open_tags

    def close_tag(self, tag):
        tmp = s = ''
        while self._open_tags != [] and tag != tmp:
            tmp = self._open_tags.pop()
            s += tmp
        return s

    def open_tag(self, tag):
        self._open_tags.append(tag)

    def simple_tag_handler(self, open_tag, close_tag):
        """Generic handler for simple binary style tags"""
        if self.tag_open_p(close_tag):
            return self.close_tag(close_tag)
        else:
            self.open_tag(close_tag)
            return open_tag

    def _bold_formatter(self, match, fullmatch):
        return self.simple_tag_handler('<strong>', '</strong>')

    def _italic_formatter(self, match, fullmatch):
        return self.simple_tag_handler('<i>', '</i>')

    def _underline_formatter(self, match, fullmatch):
        return self.simple_tag_handler('<span class="underline">', '</span>')

    def _inlinecode_formatter(self, match, fullmatch):
        return '<tt>%s</tt>' % fullmatch.group('inline')

    def _htmlescapeentity_formatter(self, match, fullmatch):
        #dummy function that match html escape entities in the format:
        # &#[0-9]+;
        # This function is used to avoid these being matched by
        # the tickethref regexp
        return match

    def _tickethref_formatter(self, match, fullmatch):
        number = int(match[1:])
        return '<a href="%s">#%d</a>' % (self.env.href.ticket(number), number)

    def _changesethref_formatter(self, match, fullmatch):
        number = int(match[1:-1])
        return '[<a href="%s">%d</a>]' % (self.env.href.changeset(number), number)

    def _reporthref_formatter(self, match, fullmatch):
        number = int(match[1:-1])
        return '{<a href="%s">%d</a>}' % (self.env.href.report(number), number)

    def _expand_module_link(self, text):
        sep = text.find(':')
        if sep == -1:
            return None, None
        module = text[:sep]
        args = text[sep+1:]
        if module in ['bug', 'ticket']:
            return self.env.href.ticket(args), '%s:%s' % (module, args), 0
        elif module == 'wiki':
            if not self.env._wiki_pages.has_key(args):
                return self.env.href.wiki(args), '%s:%s' % (module, args), 1
            else:
                return self.env.href.wiki(args), '%s:%s' % (module, args), 0
        elif module == 'report':
            return self.env.href.report(args), '%s:%s' % (module, args), 0
        elif module == 'changeset':
            return self.env.href.changeset(args), '%s:%s' % (module, args), 0
        elif module == 'search':
            return self.env.href.search(args), '%s:%s' % (module, args), 0
        elif module in ['source', 'repos', 'browser']:
            rev = None
            match = re.search('([^#]+)#(.+)', args)
            if match:
                args = match.group(1)
                rev = match.group(2)
            if rev:
                return self.env.href.browser(args, rev), \
                       '%s:%s#%s' % (module, args, rev), 0
            else:
                return self.env.href.browser(args), '%s:%s' % (module, args), 0
        else:
            return None, None, 0

    def _modulehref_formatter(self, match, fullmatch):
        link, text, missing = self._expand_module_link(match)
        if link and missing:
            return '<a class="missing" href="%s">%s?</a>' % (link, text)
        elif link:
            return '<a href="%s">%s</a>' % (link, text)
        else:
            return match

    def _wikilink_formatter(self, match, fullmatch):
        if match[0] == '!':
            return match[1:]
        if not self.env._wiki_pages.has_key(match):
            return '<a class="missing" href="%s">%s?</a>' % \
                   (self.env.href.wiki(match), match)
        else:
            return '<a href="%s">%s</a>' % (self.env.href.wiki(match), match)

    def _url_formatter(self, match, fullmatch):
        return '<a href="%s">%s</a>' % (match, match)

    def _fancylink_formatter(self, match, fullmatch):
        link = fullmatch.group('fancyurl')
        name = fullmatch.group('linkname')

        module_link, t, missing = self._expand_module_link(link)
        if module_link and missing:
            return '<a class="missing" href="%s">%s?</a>' % (module_link, name)
        elif module_link:
            return '<a href="%s">%s</a>' % (module_link, name)
        else:
            return '<a href="%s">%s</a>' % (link, name)


class OneLinerFormatter(CommonFormatter):
    """
    A special version of the wiki formatter that only implement a
    subset of the wiki formatting functions. This version is useful
    for rendering short wiki-formatted messages on a single line
    """

    _rules = CommonFormatter._rules + \
             [r"""(?P<url>([a-z]+://[^ ]+[^\., ]))"""]

    _compiled_rules = re.compile('(?:' + string.join(_rules, '|') + ')')

    def format(self, text, out):
        if not text:
            return
        self.out = out
        self._open_tags = []

        rules = self._compiled_rules

        result = re.sub(rules, self.replace, util.escape(text.strip()))
        # Close all open 'one line'-tags
        result += self.close_tag(None)
        out.write(result)


class Formatter(CommonFormatter):
    """
    A simple Wiki formatter
    """
    _rules = [r"""(?P<svnimg>(source|repos):([^ ]+)\.(PNG|png|JPG|jpg|JPEG|jpeg|GIF|gif))"""] + \
             CommonFormatter._rules + \
             [r"""(?P<macro>\[\[(?P<macroname>[a-zA-Z]+)(\((?P<macroargs>[^\)]*)\))?\]\])""",
              r"""(?P<heading>^\s*(?P<hdepth>=+)\s.*\s(?P=hdepth)$)""",
              r"""(?P<list>^(?P<ldepth>\s+)(?:\*|[0-9]+\.) )""",
              r"""(?P<indent>^(?P<idepth>\s+)(?=\S))""",
              r"""(?P<imgurl>([a-z]+://[^ ]+)\.(PNG|png|JPG|jpg|JPEG|jpeg|GIF|gif)(\?\S+)?)""",
              r"""(?P<url>([a-z]+://[^ ]+[^\., \)\]\}]))""",
              r"""(?P<last_table_cell>\|\|$)""",
              r"""(?P<table_cell>\|\|)"""]

    _compiled_rules = re.compile('(?:' + string.join(_rules, '|') + ')')
    _processor_re = re.compile('#\!([a-zA-Z]+)')


    # RE patterns used by other patterna
    _helper_patterns = ('idepth', 'ldepth', 'hdepth', 'fancyurl',
                        'linkname', 'macroname', 'macroargs', 'inline',
                        'modulename', 'moduleargs')

    _htmlproc_disallow_rule = re.compile('(?i)<(script|noscript|embed|object|iframe|frame|frameset|link|style|meta|param|doctype)')

    def default_processor(hdf, text, env):
        return '<pre class="wiki">' + util.escape(text) + '</pre>'
    def asp_processor(hdf, text, env):
        return env.mimeview.display(text, 'text/x-asp')
    def c_processor(hdf, text, env):
        return env.mimeview.display(text, 'text/x-csrcl')
    def java_processor(hdf, text, env):
        return env.mimeview.display(text, 'text/x-java')
    def cpp_processor(hdf, text, env):
        return env.mimeview.display(text, 'text/x-c++src')
    def perl_processor(hdf, text, env):
        return env.mimeview.display(text, 'text/x-perl')
    def php_processor(hdf, text, env):
        return env.mimeview.display(text, 'text/x-php')
    def python_processor(hdf, text, env):
        return env.mimeview.display(text, 'text/x-python')
    def ruby_processor(hdf, text, env):
        return env.mimeview.display(text, 'text/x-ruby')
    def sql_processor(hdf, text, env):
        return env.mimeview.display(text, 'text/x-sql')
    def xml_processor(hdf, text, env):
        return env.mimeview.display(text, 'text/xml')

    def html_processor(hdf, text, env):
        if Formatter._htmlproc_disallow_rule.search(text):
            err = """\
<div class="error">Error: HTML block contains disallowed tags.
<pre>
%s</pre>
</div>""" % util.escape(text)
            env.log.error(err)
            return err
        return text

    builtin_processors = { 'html': html_processor,
                           'asp': asp_processor,
                           'c': c_processor,
                           'cpp': cpp_processor,
                           'java': java_processor,
                           'php': php_processor,
                           'perl': perl_processor,
                           'python': python_processor,
                           'ruby': ruby_processor,
                           'sql': sql_processor,
                           'xml': xml_processor,
                           'default': default_processor}

    def load_macro(self, name):
        macros = __import__('wikimacros.' + name, globals(),  locals(), [])
        module = getattr(macros, name)
        return module.execute

    def _macro_formatter(self, match, fullmatch):
        name = fullmatch.group('macroname')
        if name in ['br', 'BR']:
            return '<br />'
        args = fullmatch.group('macroargs')
        try:
            macro = self.load_macro(name)
            return macro(self.hdf, args, self.env)
        except Exception, e:
            return '<span class="error">Macro %s(%s) failed: %s</span' \
                   % (name, args, e)

    def _heading_formatter(self, match, fullmatch):
        depth = min(len(fullmatch.group('hdepth')), 5)
        self.close_table()
        self.close_paragraph()
        self.close_indentation()
        self.close_list()
        self.out.write('<h%d>%s</h%d>' % (depth, match[depth + 1:len(match) - depth - 1], depth))
        return ''

    def _svnimg_formatter(self, match, fullmatch):
        prefix_len = match.find(':') + 1
        return '<img src="%s" alt="%s" />' % \
               (self.env.href.file(match[prefix_len:], format='raw'),
                match[prefix_len:])

    def _imgurl_formatter(self, match, fullmatch):
        return '<img src="%s" alt="%s" />' % (match, match)

    def _indent_formatter(self, match, fullmatch):
        depth = int((len(fullmatch.group('idepth')) + 1) / 2)
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
            self.out.write('</p>' + os.linesep)
            self.paragraph_open = 0

    def open_table(self):
        if not self.in_table:
            self.close_paragraph()
            self.close_indentation()
            self.close_list()
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
                    self.code_processor = Formatter.builtin_processors['default']
        elif line.strip() == '}}}':
            self.in_code_block -= 1
            if self.in_code_block == 0 and self.code_processor:
                self.close_paragraph()
                self.close_table()
                self.out.write(self.code_processor(self.hdf, self.code_text, self.env))
            else:
                self.code_text += line + os.linesep
        elif not self.code_processor:
            match = Formatter._processor_re.search(line)
            if match:
                name = match.group(1)
                if  Formatter.builtin_processors.has_key(name):
                    self.code_processor = Formatter.builtin_processors[name]
                else:
                    try:
                        self.code_processor = self.load_macro(name)
                    except Exception, e:
                        self.code_text += line + os.linesep 
                        self.code_processor = Formatter.builtin_processors['default']
                        self.out.write('<div class="error">Failed to load processor macro %s: %s</div>' % (name, e))
            else:
                self.code_text += line + os.linesep 
                self.code_processor = Formatter.builtin_processors['default']
        else:
            self.code_text += line + os.linesep

    def format(self, text, out):
        self.out = out
        self._open_tags = []
        self._list_stack = []

        self.in_code_block = 0
        self.in_table = 0
        self.in_table_row = 0
        self.in_table_cell = 0
        self.indent_level = 0
        self.paragraph_open = 0

        rules = self._compiled_rules

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
                self.out.write('<hr />' + os.linesep)
                continue
            # Handle new paragraph
            elif line == '':
                self.close_paragraph()
                self.close_indentation()
                self.close_list()
                continue

            line = util.escape(line)
            self.in_list_item = 0
            # Throw a bunch of regexps on the problem
            result = re.sub(rules, self.replace, line)
            # Close all open 'one line'-tags
            result += self.close_tag(None)

            if not self.in_list_item:
                self.close_list()

            if self.in_table and line[0:2] != '||':
                self.close_table()

            if len(result) and not self.in_list_item and not self.in_table:
                self.open_paragraph()
            out.write(result + os.linesep)
            self.close_table_row()

        self.close_table()
        self.close_paragraph()
        self.close_indentation()
        self.close_list()

def wiki_to_html(wikitext, hdf, env):
    out = StringIO.StringIO()
    Formatter(hdf, env).format(wikitext, out)
    return out.getvalue()

def wiki_to_oneliner(wikitext, hdf, env):
    out = StringIO.StringIO()
    OneLinerFormatter(hdf, env).format(wikitext, out)
    return out.getvalue()
