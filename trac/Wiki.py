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
from Href import href
from Module import Module
from db import get_connection
from util import *


class Formatter:
    """
    A simple Wiki formatter
    """
    _url_re = r'([a-z]+://[^ ]+)'
#    _url_re = r'(((new|file|(ht|f)tp)s?://))([a-z0-9_-]+:[a-z0-9_-]+\@)?([a-z0-9]+(\-*[a-z0-9]+)*\.)+[a-z]{2,7}(/~?[a-z0-9_\.%\-]+)?(/[a-z0-9_\.%\-]+)*(/?[a-z0-9_\%\-]*(\.[a-z0-9]+)?(\#[a-zA-Z0-9_\.]+)?)(\?([a-z0-9_\.\%\-]+)\=[a-z0-9_\.\%\/\-]*)?(&([a-z0-9_\.\%\-]+)\=[a-z0-9_\.\%\/\-]*)?(#[a-z0-9]+)?'



    _rules = r"""(?:(?P<bold>''')""" \
             r"""|(?P<tickethref> #[0-9]+)""" \
             r"""|(?P<changesethref>\[[0-9]+\])""" \
             r"""|(?P<reporthref>\{[0-9]+\})""" \
             r"""|(?P<italic>'')""" \
             r"""|(?P<beginpre>\{\{\{$)""" \
             r"""|(?P<endpre>\}\}\}$)""" \
             r"""|(?P<begintt>\{\{\{)""" \
             r"""|(?P<endtt>\}\}\})""" \
             r"""|(?P<hr>-{5,})""" \
             r"""|(?P<heading>^\s*(?P<hdepth>=+)\s.*\s(?P=hdepth)$)""" \
             r"""|(?P<listitem>^(?P<ldepth>\s+)(?:\*|[0-9]+\.) )""" \
             r"""|(?P<wikilink>(^|(?<=[^A-Za-z]))[A-Z][a-z]*(?:[A-Z][a-z]+)+)""" \
             r"""|(?P<indent>^(?P<idepth>\s+)(?=[^\s]))""" \
             r"""|(?P<imgurl>%(url_re)s(\.png|\.jpg|\.jpeg|\.gif))""" \
             r"""|(?P<url>%(url_re)s)""" \
             r"""|(?P<fancylink>\[(?P<fancyurl>%(url_re)s) (?P<linkname>.*?)\])""" \
             r"""|(?P<underline>__))""" % { 'url_re': _url_re}
    
    # RE patterns used by other patterna
    _helper_patterns = ('idepth', 'ldepth', 'hdepth', 'fancyurl', 'linkname')

    def _bold_formatter(self, match, fullmatch):
        self._is_bold = not self._is_bold
        return ['</strong>', '<strong>'][self._is_bold]

    def _beginpre_formatter(self, match, fullmatch):
        self._in_pre = 1
        return '<pre>'

    def _endpre_formatter(self, match, fullmatch):
        in_pre = self._in_pre
        self._in_pre = 0
        return ['</tt>', '</pre>'][in_pre]

    def _begintt_formatter(self, match, fullmatch):
        return ['<tt>', ''][self._in_pre]

    def _endtt_formatter(self, match, fullmatch):
        return ['</tt>', ''][self._in_pre]

    def _tickethref_formatter(self, match, fullmatch):
        number = int(match[2:])
        return '<a href="%s">#%d</a>' % (href.ticket(number), number)

    def _changesethref_formatter(self, match, fullmatch):
        number = int(match[1:-1])
        return '[<a href="%s">%d</a>]' % (href.changeset(number), number)

    def _reporthref_formatter(self, match, fullmatch):
        number = int(match[1:-1])
        return '{<a href="%s">%d</a>}' % (href.report(number), number)

    def _italic_formatter(self, match, fullmatch):
        self._is_italic = not self._is_italic
        return ['</i>', '<i>'][self._is_italic]

    def _hr_formatter(self, match, fullmatch):
        return '<hr />'

    def _underline_formatter(self, match, fullmatch):
        self._is_underline = not self._is_underline
        return ['</u>', '<u>'][self._is_underline]

    def _heading_formatter(self, match, fullmatch):
        depth = min(len(fullmatch.group('hdepth')), 5)
        self.is_heading = 1
        return '<h%d>%s</h%d>' % (depth, match[depth + 1:len(match) - depth - 1], depth)

    def _wikilink_formatter(self, match, fullmatch):
        return '<a href="%s">%s</a>' % (href.wiki(match), match)

    def _imgurl_formatter(self, match, fullmatch):
        return '<img src="%s" />' % match

    def _url_formatter(self, match, fullmatch):
        return '<a href="%s">%s</a>' % (match, match)

    def _fancylink_formatter(self, match, fullmatch):
        link = fullmatch.group('fancyurl')
        name = fullmatch.group('linkname')
        return '<a href="%s">%s</a>' % (link, name)

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
        depth = int((len(fullmatch.group('ldepth')) + 1) / 2)
        #self.out.write('depth:%d' % depth)
        type = ['ol', 'ul'][match[depth * 2 - 1] == '*']
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
        
    def replace(self, fullmatch):
        for type, match in fullmatch.groupdict().items():
            if match and not type in Formatter._helper_patterns:
                return getattr(self, '_' + type + '_formatter')(match, fullmatch)
    
    def format(self, text, out):
        self.out = out
        rules = re.compile(Formatter._rules)
        p_open = 0
        self.is_heading = 0
        self._li_open = 0
        self._list_stack = []
        self._in_pre = 0
        for line in text.splitlines():
            self._is_bold = 0
            self._is_italic = 0
            self._is_underline = 0
            self._in_list = 0
            line = escape(line)
            result = re.sub(rules, self.replace, line)
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
        self.render_history(out)
        perm.assert_permission (perm.WIKI_VIEW)
        out.write ('<div class="wikipage">')
        #format_wiki(self.text, out)
        Formatter().format(self.text, out)
        out.write ('</div><br>')
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
        out.write ('<a name="preview" /><h3>preview</h3>')
        self.render_view (out, hdf, edit_button=0)
        
    def render_history (self, out):
        cnx = get_connection ()
        cursor = cnx.cursor ()
        
        cursor.execute ('SELECT version, time, author, ipnr FROM wiki '
                        'WHERE name=%s ORDER BY version DESC', self.name)

        out.write ('<div class="wiki-history" align="right">'
                   '<a href=\"javascript:view_history()\">show/hide history</a>'
                   '</div>')
        out.write ('<table class="wiki-history" id="history">')
        out.write ('<tr class="wiki-history-header"><th>version</th>'
                   '<th>time</th><th>author</th><th>ipnr</th></tr>')
	while 1:
	    row = cursor.fetchone()
	    if row == None:
		break
		   #        for row in cursor:
            t = int(row[1])
            if t:
                time_str = time.strftime('%F', time.localtime(t))
            else:
                time_str = ''
            out.write ('<tr><td><a href="%s">%s</a></td><td>%s</td>'
                       '<td>%s</td><td>%s</td></tr>'
                       % (href.wiki(self.name, row[0]), row[0], time_str,
                          row[2], row[3]))
        out.write ('</table>')


class Wiki(Module):
    template_name = 'wiki.cs'

    def render(self):
        name = dict_get_with_default(self.args, 'page', 'WikiStart')
        action = dict_get_with_default(self.args, 'action', 'view')
        version = dict_get_with_default(self.args, 'version', 0)
            
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
'''
test_out = ''' <ul><li>Foo</li> <ul><li>Foo 2</li> </ul></ul><ol><li>Foo 3</li> </ol><h3>FooBar</h3> <ul> Hoj  Hoj2 </ul><p>Hoj3 </p>'''

def test():
    result = StringIO.StringIO()
    Formatter().format(test_in, result)
    if result.getvalue() != test_out:
        print 'now:', result.getvalue()
        print 'correct:', test_out

if __name__ == '__main__':
    test()
