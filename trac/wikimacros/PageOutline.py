# -*- coding: iso8859-1 -*-
"""
Displays a structural outline of the current wiki page, each item in the outline
being a link to the corresponding heading.

This macro accepts three optional parameters: The first must be a number between
1 and 6 that specifies the maximum depth of the outline (the default is 6). The
second can be used to specify a custom title (the default is no title). The
third parameter selects the style of the outline. This can be either 'inline' or
'pullout' (default is 'pullout'). The 'inline' style renders the outline as
normal part of the content, while 'pullout' causes the outline to be rendered
in a box that is by default floated to the right side of the other content.
"""

import re
from StringIO import StringIO

from trac.util import escape


rules_re = re.compile(r'(?P<heading>^\s*(?P<hdepth>=+)\s(?P<header>.*)\s(?P=hdepth)\s*$)')
anchor_re = re.compile('[^\w\d\.-:]+', re.UNICODE)

def execute(hdf, args, env):

    def make_outline(wikitext, out, max_depth):
        seen_anchors = []
        current_depth = 0
        in_pre = 0
        for line in wikitext.splitlines():
            line = escape(line)
    
            if in_pre:
                if line == '}}}':
                    in_pre = 0
                else:
                    continue
            elif line == '{{{':
                in_pre = 1
                continue    
    
            match = rules_re.match(line)
            if match:
                header = match.group('header')
                new_depth = len(match.group('hdepth'))
                if new_depth > max_depth:
                    continue
                if new_depth < current_depth:
                    out.write('</li></ol><li>' * (current_depth - new_depth))
                elif new_depth > current_depth:
                    out.write('<ol><li>' * (new_depth - current_depth))
                else:
                    out.write("</li><li>\n")
                current_depth = new_depth

                anchor = anchor_base = anchor_re.sub('', header.decode('utf-8'))
                if not anchor or not anchor[0].isalpha():
                    # an ID must start with a letter in HTML
                    anchor = 'a' + anchor
                i = 1
                while anchor in seen_anchors:
                    anchor = anchor_base + str(i)
                    i += 1
                seen_anchors.append(anchor)
                out.write('<a href="#%s">%s</a>' % (anchor, header))

        out.write('</li></ol>' * current_depth)

    max_depth = 6
    title = None
    inline = 0
    if args:
        argv = [arg.strip() for arg in args.split(',')]
        if len(argv) > 0:
            max_depth = int(argv[0])
            if len(argv) > 1:
                title = escape(argv[1]).strip()
                if len(argv) > 2:
                    inline = argv[2].strip().lower() == 'inline'

    db = env.get_db_cnx()
    cursor = db.cursor()
    pagename = hdf.get('wiki.page_name', 'WikiStart')
    cursor.execute("SELECT text FROM wiki WHERE name=%s "
                   "ORDER BY version DESC LIMIT 1", (pagename,))
    row = cursor.fetchone()
    if not row:
        return

    buf = StringIO()
    if not inline:
        buf.write('<div class="wiki-toc">')
    if title:
        buf.write('<h4>%s</h4>' % title)
    make_outline(row[0], buf, max_depth)
    if not inline:
        buf.write('</div>')
    return buf.getvalue()
