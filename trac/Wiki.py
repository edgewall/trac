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
import time
import os
import StringIO
import auth
import perm
import string
from Href import href
from Module import Module
from db import get_connection
from util import *

page_dict = None

def populate_page_dict():
    """Extract wiki page names. This is used to detect broken wiki-links"""
    global page_dict
    page_dict = {'TitleIndex': 1}
    cnx = get_connection()
    cursor = cnx.cursor()
    cursor.execute('SELECT DISTINCT name FROM wiki')
    while 1:
        row = cursor.fetchone()
        if not row:
            break
        page_dict[row[0]] = 1

class CommonFormatter:
    """This class contains the patterns common to both Formatter and
    OneLinerFormatter"""
    
    _rules = [r"""(?P<bold>''')""",
              r"""(?P<italic>'')""",
              r"""(?P<underline>__)""",
              r"""(?P<htmlescapeentity>&#[0-9]+;)""",
              r"""(?P<tickethref>#[0-9]+)""",
              r"""(?P<changesethref>\[[0-9]+\])""",
              r"""(?P<reporthref>\{[0-9]+\})""",
              r"""(?P<svnhref>(svn:[^ ]+[^\.,]))""",
              r"""(?P<wikilink>(^|(?<=[^A-Za-z]))[A-Z][a-z/]*(?:[A-Z][a-z/]+)+)""",
              r"""(?P<fancylink>\[(?P<fancyurl>([a-z]+:[^ ]+)) (?P<linkname>.*?)\])"""]


    def compile_rules(self, rules):
        return re.compile('(?:' + string.join(rules, '|') + ')')

    def replace(self, fullmatch):
        for type, match in fullmatch.groupdict().items():
            if match and not type in Formatter._helper_patterns:
                return getattr(self, '_' + type + '_formatter')(match, fullmatch)
    
    def _bold_formatter(self, match, fullmatch):
        self._is_bold = not self._is_bold
        return ['</strong>', '<strong>'][self._is_bold]

    def _italic_formatter(self, match, fullmatch):
        self._is_italic = not self._is_italic
        return ['</i>', '<i>'][self._is_italic]

    def _underline_formatter(self, match, fullmatch):
        self._is_underline = not self._is_underline
        return ['</u>', '<u>'][self._is_underline]

    def _htmlescapeentity_formatter(self, match, fullmatch):
        #dummy function that match html escape entities in the format:
        # &#[0-9]+;
        # This function is used to avoid these being matched by
        # the tickethref regexp
        return match
    
    def _tickethref_formatter(self, match, fullmatch):
        number = int(match[1:])
        return '<a href="%s">#%d</a>' % (href.ticket(number), number)

    def _changesethref_formatter(self, match, fullmatch):
        number = int(match[1:-1])
        return '[<a href="%s">%d</a>]' % (href.changeset(number), number)

    def _reporthref_formatter(self, match, fullmatch):
        number = int(match[1:-1])
        return '{<a href="%s">%d</a>}' % (href.report(number), number)

    def _svnhref_formatter(self, match, fullmatch):
        return '<a href="%s">%s</a>' % (href.log(match[4:]), match[4:])

    def _wikilink_formatter(self, match, fullmatch):
        global page_dict
        if page_dict and not page_dict.has_key(match):
            return '<a class="wiki-missing-page" href="%s">%s?</a>' % (href.wiki(match), match)
        else:
            return '<a href="%s">%s</a>' % (href.wiki(match), match)

    def _url_formatter(self, match, fullmatch):
        return '<a href="%s">%s</a>' % (match, match)

    def _fancylink_formatter(self, match, fullmatch):
        link = fullmatch.group('fancyurl')
        name = fullmatch.group('linkname')
        if link[0:5] == 'wiki:':
            link = href.wiki(link[5:])
        if link[0:4] == 'svn:':
            link = href.file(link[4:])
        return '<a href="%s">%s</a>' % (link, name)


class OneLinerFormatter(CommonFormatter):
    """
    A special version of the wiki formatter that only implement a
    subset of the wiki formatting functions. This version is useful
    for rendering short wiki-formatted messages on a single line
    """
    
    _rules = CommonFormatter._rules + \
             [r"""(?P<url>([a-z]+://[^ ]+))"""]

    def format(self, text, out):
        self.out = out
        rules = self.compile_rules(self._rules)
        p_open = 0
        self._is_bold = 0
        self._is_italic = 0
        self._is_underline = 0
        text = escape(text)
        result = re.sub(rules, self.replace, text)
        out.write(result)

class Formatter(CommonFormatter):
    """
    A simple Wiki formatter
    """
    _rules = [r"""(?P<svnimg>svn:([^ ]+)(\.png|\.jpg|\.jpeg|\.gif))"""] + \
             CommonFormatter._rules + \
             [r"""(?P<fancysvnhref>\[(?P<fancysvnfile>svn:[^ ]+) (?P<svnlinkname>.*?)\])""",
              r"""(?P<begintt>\{\{\{)""",
              r"""(?P<endtt>\}\}\})""",
              r"""(?P<br>\[\[(br|BR)\]\])""",
              r"""(?P<hr>-{4,})""",
              r"""(?P<heading>^\s*(?P<hdepth>=+)\s.*\s(?P=hdepth)$)""",
              r"""(?P<listitem>^(?P<ldepth>\s+)(?:\*|[0-9]+\.) )""",
              r"""(?P<indent>^(?P<idepth>\s+)(?=[^\s]))""",
              r"""(?P<imgurl>([a-z]+://[^ ]+)(\.png|\.jpg|\.jpeg|\.gif))""",
              r"""(?P<url>([a-z]+://[^ ]+))"""]
    
    # RE patterns used by other patterna
    _helper_patterns = ('idepth', 'ldepth', 'hdepth', 'fancyurl',
                        'linkname', 'fancysvnfile', 'svnlinkname')

    def _begintt_formatter(self, match, fullmatch):
        return '<tt>'

    def _endtt_formatter(self, match, fullmatch):
        return '</tt>'

    def _fancysvnhref_formatter(self, match, fullmatch):
        path = fullmatch.group('fancysvnfile')
        name = fullmatch.group('svnlinkname')
        return '<a href="%s">%s</a>' % (href.log(path[4:]), name)

    def _hr_formatter(self, match, fullmatch):
        return '<hr />'

    def _br_formatter(self, match, fullmatch):
        return '<br />'

    def _heading_formatter(self, match, fullmatch):
        depth = min(len(fullmatch.group('hdepth')), 5)
        self.is_heading = 1
        return '<h%d>%s</h%d>' % (depth, match[depth + 1:len(match) - depth - 1], depth)

    def _svnimg_formatter(self, match, fullmatch):
        return '<img src="%s" />' % href.file(match[4:])

    def _imgurl_formatter(self, match, fullmatch):
        return '<img src="%s" />' % match

    def _set_list_depth(self, depth, type):
        self._in_list = depth > 0
        current_depth = len(self._list_stack)
        diff = depth - current_depth
        if diff > 0:
            for i in range(diff):
                self.out.write('<%s>' % type)
                self._list_stack.append('</%s>' % type)
        elif diff < 0:
            for i in range(-diff):
                self.out.write(self._list_stack.pop())
            # If the list type changes...
            if self._list_stack != [] and self._list_stack[0][2:4] != type:
                self.out.write(self._list_stack.pop())
                self.out.write('<%s>' % type)
                self._list_stack.append('</%s>' % type)
        # If the list type changes...
        elif self._list_stack != [] and self._list_stack[0][2:4] != type:
            self.out.write(self._list_stack.pop())
            self.out.write('<%s>' % type)
            self._list_stack.append('</%s>' % type)
        
    def _listitem_formatter(self, match, fullmatch):
        ldepth = len(fullmatch.group('ldepth'))
        depth = int((ldepth + 1) / 2)
        #self.out.write('depth:%d' % depth)
        type = ['ol', 'ul'][match[ldepth] == '*']
        self._li_open = 1
        self._set_list_depth(depth, type)
        return '<li>'
        #return '<li>%s</li>' % match[depth * 2 + 1:]

    def _indent_formatter(self, match, fullmatch):
        depth = int((len(fullmatch.group('idepth')) + 1) / 2)
        #self.out.write('depth:%d' % depth)
        self._set_list_depth(depth, 'ul')
        return ' '
        #return '<li>%s</li>' % match[depth * 2 + 1:]
        
    def format(self, text, out):
        self.out = out
        rules = self.compile_rules(self._rules)
        p_open = 0
        self.is_heading = 0
        self._li_open = 0
        self._list_stack = []
        self._in_pre = 0
        for line in text.splitlines():
            # In a PRE-block no other formatting commands apply
            if not self._in_pre and re.search('^\{\{\{$', line.strip()):
                self._in_pre = 1
                out.write('<pre>')
                continue
            if self._in_pre:
                if re.search('^\}\}\}$', line.strip()):
                    self._in_pre = 0
                    out.write('</pre>')
                    continue
                else:
                    out.write(escape(line) + '\n')
                    continue
                    
            self._is_bold = 0
            self._is_italic = 0
            self._is_underline = 0
            self._in_list = 0
            result = re.sub(rules, self.replace, escape(line))
            # close any open list item
            if self._li_open:
                self._li_open = 0
                result = result + '</li>'
            # close the paragraph when a heading starts
            # or on an empty line
            if p_open and self._list_stack != []:
                out.write ('</p>')
                p_open = 0

            if not self._in_list:
                self._set_list_depth(0, None)
            if p_open and (self.is_heading or result == ''):
                out.write ('</p>')
                p_open = 0
            elif not p_open and not self.is_heading and not \
                     self._in_list and result != '':
                p_open = 1
                out.write ('<p>')
                
            out.write(result)
            self.is_heading = 0
            out.write([' ', '\n'][self._in_pre])
        # clean up before we are done
        self._set_list_depth(0, None)
        if p_open:
            out.write('</p>')


def wiki_to_html(wikitext):
    out = StringIO.StringIO()
    Formatter().format(wikitext, out)
    return out.getvalue()

def wiki_to_oneliner(wikitext):
    out = StringIO.StringIO()
    OneLinerFormatter().format(wikitext, out)
    return out.getvalue()


class Page:
    def __init__(self, name, version):
        
        self.name = name
        cnx = get_connection ()
        cursor = cnx.cursor ()
        if version:
            cursor.execute ('SELECT version, text FROM wiki '
                            'WHERE name=%s AND version=%s',
                            name, version)
        else:
            cursor.execute ('SELECT version, text FROM wiki '
                            'WHERE name=%s ORDER BY version DESC LIMIT 1', name)
        row = cursor.fetchone()
        if row:
            self.new = 0
            self.version = int(row[0])
            self.text = row[1]
        else:
            self.version = 0
            self.text = 'describe %s here' % name
            self.new = 1
            
    def set_content (self, text):
        self.text = text
        self.version = self.version + 1

    def commit (self):
        if self.new:
            perm.assert_permission (perm.WIKI_CREATE)
        else:
            perm.assert_permission (perm.WIKI_MODIFY)
        cnx = get_connection ()
        cursor = cnx.cursor ()
        cursor.execute ('SELECT MAX(version)+1 FROM '
                        '(SELECT version FROM wiki WHERE name=%s '
                        'UNION ALL SELECT 0 as version)', self.name)
        row = cursor.fetchone()
        new_version = int(row[0])
        
        cursor.execute ('INSERT INTO WIKI '
                        '(name, version, time, author, ipnr, locked, text) '
                        'VALUES (%s, %s, %s, %s, %s, %s, %s)',
                        self.name, new_version, int(time.time()),
                        auth.get_authname(), os.getenv('REMOTE_ADDR'),
                        0, self.text)
        cnx.commit ()

    def render_edit(self, out, hdf):
        perm.assert_permission (perm.WIKI_MODIFY)
        out.write ('<h3>source</h3>')
        out.write ('<form action="%s" method="POST">' %
                   hdf.getValue('cgi_location', ''))
        out.write ('<input type="hidden" name="page" value="%s">' % self.name)
        out.write ('<input type="hidden" name="mode" value="wiki">')
        out.write ('<textarea name="text" rows="15" cols="80">')
        out.write(escape(self.text))
        out.write ('</textarea><p>')
        out.write ('<input type="submit" name="action" value="preview">&nbsp;')
        out.write ('<input type="submit" name="action" value="save changes">')
        out.write ('</form>')

    def render_view(self, out, hdf, edit_button=1):
        perm.assert_permission (perm.WIKI_VIEW)
        out.write ('<div class="wikipage">')
        #format_wiki(self.text, out)
        Formatter().format(self.text, out)
        out.write ('</div><br />')
        if edit_button and perm.has_permission (perm.WIKI_MODIFY):
            out.write ('<form action="%s" method="POST">' %
                       hdf.getValue('cgi_location', ''))
            out.write ('<input type="hidden" name="mode" value="wiki">')
            out.write ('<input type="hidden" name="page" value="%s">' % self.name)
            out.write ('<input type="submit" name="action" value=" edit page ">')
            out.write ('</form>')
        
    def render_preview (self, out, hdf):
        perm.assert_permission (perm.WIKI_MODIFY)
        
        self.render_edit (out, hdf)
        out.write ('<a name="preview"></a><h3>preview</h3>')
        self.render_view (out, hdf, edit_button=0)
        

class Wiki(Module):
    template_name = 'wiki.cs'

    def generate_title_index(self):
        cnx = get_connection ()
        cursor = cnx.cursor ()
        
        cursor.execute ('SELECT DISTINCT name FROM wiki ORDER BY name')
        i = 0
	while 1:
	    row = cursor.fetchone()
	    if row == None:
		break
            self.cgi.hdf.setValue('wiki.title_index.%d.title' % i, row[0])
            self.cgi.hdf.setValue('wiki.title_index.%d.href' % i,
                                  href.wiki(row[0]))
            i = i + 1

    def generate_history(self,pagename):
        cnx = get_connection ()
        cursor = cnx.cursor ()
        cursor.execute ('SELECT version, time, author, ipnr FROM wiki '
                        'WHERE name=%s ORDER BY version DESC', pagename)
        i = 0
	while 1:
	    row = cursor.fetchone()
	    if not row:
		break
		   #        for row in cursor:
            t = int(row[1])
            if t:
                time_str = time.strftime('%F', time.localtime(t))
            else:
                time_str = ''
            n = 'wiki.history.%d' % i
            self.cgi.hdf.setValue(n, str(i))
            self.cgi.hdf.setValue(n+'.url', href.wiki(pagename, str(row[0])))
            self.cgi.hdf.setValue(n+'.version', str(row[0]))
            self.cgi.hdf.setValue(n+'.time', time_str)
            self.cgi.hdf.setValue(n+'.author', str(row[2]))
            self.cgi.hdf.setValue(n+'.ipnr', str(row[3]))
            i = i + 1

    def render(self):
        name = dict_get_with_default(self.args, 'page', 'WikiStart')
        action = dict_get_with_default(self.args, 'action', 'view')
        version = dict_get_with_default(self.args, 'version', 0)

        self.generate_history(name)

        if name == 'TitleIndex':
            self.generate_title_index()
            return
            
        page = Page(name, version)

        if self.args.has_key('text'):
            page.set_content (self.args['text'])
            
        out = StringIO.StringIO()
        if action == 'save changes':
            page.commit ()
            redirect (href.wiki(page.name))
        elif action == ' edit page ':
            out.write ('<h2>edit <a href="%s">%s</a></h2>' %
                       (href.wiki(page.name), page.name))
            page.render_edit (out, self.cgi.hdf)
            self.cgi.hdf.setValue('title', 'wiki - edit')
        elif action == 'preview':
            out.write ('<h2>edit <a href="%s">%s</a></h2>' %
                       (href.wiki(page.name), page.name))
            page.render_preview (out, self.cgi.hdf)
            self.cgi.hdf.setValue('title', 'wiki - preview')
        else:
            page.render_view (out, self.cgi.hdf)
            self.cgi.hdf.setValue('title', 'wiki - view')
        self.cgi.hdf.setValue('content', out.getvalue())


###
### A simple unit test
###

test_in = '''
 * Foo
   * Foo 2
 1. Foo 3
=== FooBar ===
  Hoj
  Hoj2
Hoj3
Line1[[br]]Line2
'''
test_out = ''' <ul><li>Foo</li> <ul><li>Foo 2</li> </ul></ul><ol><li>Foo 3</li> </ol><h3>FooBar</h3> <ul> Hoj  Hoj2 </ul><p>Hoj3 Line1<br />Line2 </p>'''

def test():
    result = StringIO.StringIO()
    Formatter().format(test_in, result)
    if result.getvalue() != test_out:
        print 'now:', result.getvalue()
        print 'correct:', test_out

if __name__ == '__main__':
    test()
