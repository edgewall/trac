# svntrac
#
# Copyright (C) 2003 Xyche Software
#
# svntrac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# svntrac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Jonas Borgström <jonas@xyche.com>

import re
import time
import os
import StringIO
import auth
import perm
from Module import Module
from db import get_connection
from util import *
from xml.sax.saxutils import quoteattr, escape


h1_re = re.compile ('!!!(.*)!!!')
h2_re = re.compile ('!!(.*)!!')
h3_re = re.compile ('!(.*)!')
url_re = re.compile ('((((new|(ht|f)tp)s?://))([a-z0-9_-]+:[a-z0-9_-]+\@)?([a-z0-9]+(\-*[a-z0-9]+)*\.)+[a-z]{2,7}(/~?[a-z0-9_\.%\-]+)?(/[a-z0-9_\.%\-]+)*(/?[a-z0-9_\%\-]+(\.[a-z0-9]+)?(\#[a-zA-Z0-9_\.]+)?)(\?([a-z0-9_\.\%\-]+)\=[a-z0-9_\.\%\/\-]*)?(&([a-z0-9_\.\%\-]+)\=[a-z0-9_\.\%\/\-]*)?(#[a-z0-9]+)?)')
oldstylelink_re = re.compile ('([[A-Z][a-z]*(?:[A-Z][a-z]+)+)')
newstylelink_re = re.compile ('\[([^]*])\]')
list_re = re.compile ('^(([\*#])\\2*) (.*)$')
newline_re = re.compile ('(%%%)')
strong_re = re.compile ('\__([^ ]+)\__')
emph_re = re.compile ("''([^ ]+)''")
empty_line_re = re.compile ("^[ 	]*$")
indented_re = re.compile ("^[ 	]")

def format_wiki (text, out):
    """
    some basic wiki style text formatting
    """
    def set_list_depth (stack, type, depth):
        listdepth = len(stack)
        diff = depth - listdepth
        if diff > 0:
            for i in range (diff):
                out.write ('<%s>' % type)
                stack.append('</%s>' % type)
        elif diff < 0:
            for i in range (-diff):
                out.write (stack.pop())
        if depth > 0 and stack[0][2:4] != type:
            out.write (stack.pop())
            out.write ('<%s>' % type)
            stack.append('</%s>' % type)
            
    def handle_links (line):
        line = oldstylelink_re.sub('<a href="?mode=wiki&page=\\1">\\1</a>', line)
        line = url_re.sub('<a href="\\1">\\1</a>', line)
        return line
            
    newp = 1
    inverb = 0
    liststack = []

    for line in text.splitlines():
        line = escape(line)
        if empty_line_re.match(line):
            if not newp:
                newp = 1
                set_list_depth (liststack, None, 0)
                if inverb:
                    inverb = 0
                    out.write ('</pre>\n')
                out.write ('<p>\n')
            continue
        if newp and indented_re.match(line):
            out.write('<pre>\n')
            inverb = 1
        newp = 0
        
        match = list_re.match(line)
        if match:
            depth = len(match.group(1))
            if match.group(2) == '#':
                type = 'ol'
            else:
                type = 'ul'
            set_list_depth(liststack, type, depth)
            line = list_re.sub('<li>\\3', line)

        line = newline_re.sub('<br>', line)
        line = handle_links(line)
        line = h1_re.sub('<h1>\\1</h1>', line)
        line = h2_re.sub('<h2>\\1</h2>', line)
        line = h3_re.sub('<h3>\\1</h3>', line)
        line = strong_re.sub('<strong>\\1</strong>', line)
        line = emph_re.sub('<em>\\1</em>', line)
        out.write(line + '\n')
    if inverb:
        out.write ('</pre>\n')


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

    def render_edit(self, out):
        perm.assert_permission (perm.WIKI_MODIFY)
        out.write ('<h3>source</h3>')
        out.write ('<form action="svntrac.cgi" method="POST">')
        out.write ('<input type="hidden" name="page" value="%s">' % self.name)
        out.write ('<input type="hidden" name="mode" value="wiki">')
        out.write ('<textarea name="text" rows="15" cols="80">')
        out.write(escape(self.text))
        out.write ('</textarea><p>')
        out.write ('<input type="submit" name="action" value="preview">&nbsp;')
        out.write ('<input type="submit" name="action" value="commit">')
        out.write ('</form>')

    def render_view(self, out, edit_button=1):
        self.render_history(out)
        perm.assert_permission (perm.WIKI_VIEW)
        out.write ('<div class="wikipage">')
        format_wiki(self.text, out)
        out.write ('</div>')
        if edit_button and perm.has_permission (perm.WIKI_MODIFY):
            out.write ('<form action="svntrac.cgi" method="POST">')
            out.write ('<input type="hidden" name="mode" value="wiki">')
            out.write ('<input type="hidden" name="page" value="%s">' % self.name)
            out.write ('<input type="submit" name="action" value=" edit ">')
            out.write ('</form>')
        
    def render_preview (self, out):
        perm.assert_permission (perm.WIKI_MODIFY)
        
        out.write ('<h3>preview</h3>')
        self.render_view (out, edit_button=0)
        self.render_edit (out)
        
    def render_history (self, out):
        cnx = get_connection ()
        cursor = cnx.cursor ()
        
        cursor.execute ('SELECT version, time, author, ipnr FROM wiki '
                        'WHERE name=%s ORDER BY version DESC', self.name)

        out.write ('<div align="right">'
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
                       % (wiki_href(self.name, row[0]), row[0], time_str,
                          row[2], row[3]))
        out.write ('</table>')

class Wiki (Module):
    template_key = 'wiki_template'

    def render(self):
        if self.args.has_key('page'):
            name = self.args['page']
        else:
            name = 'WikiStart'
        if self.args.has_key('version'):
            version = self.args['version']
        else:
            version = 0
            
        if self.args.has_key('action'):
            action = self.args['action']
        else:
            action = 'view'
            
        page = Page(name, version)

        if self.args.has_key('text'):
            page.set_content (self.args['text'])
            
        out = StringIO.StringIO()
        if action == 'commit':
            page.commit ()
            redirect (wiki_href (page.name))
        elif action == ' edit ':
            out.write ('<h2>edit <a href="%s">%s</a></h2>' %
                       (wiki_href(page.name), page.name))
            page.render_edit (out)
            self.namespace['title'] = 'wiki - edit'
        elif action == 'preview':
            out.write ('<h2>edit <a href="%s">%s</a></h2>' %
                       (wiki_href(page.name), page.name))
            page.render_preview (out)
            self.namespace['title'] = 'wiki - preview'
        else:
            out.write ('<h2><a href="%s">%s</a></h2>' %
                       (wiki_href(page.name), page.name))
            page.render_view (out)
            self.namespace['title'] = 'wiki - view'
        self.namespace['content'] = out.getvalue()

