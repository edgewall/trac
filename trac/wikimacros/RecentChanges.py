"""
Lists all pages that have recently been modified, grouping them by the
day they were last modified.

This macro accepts two parameters. The first is a prefix string: if provided,
only pages with names that start with the prefix are included in the resulting
list. If this parameter is omitted, all pages are listed.

The second parameter is a number for limiting the number of pages returned. For
example, specifying a limit of 5 will result in only the five most recently
changed pages to be included in the list.
"""

import time
from StringIO import StringIO

def execute(hdf, args, env):
    db = env.get_db_cnx()
    cursor = db.cursor()

    prefix = limit = None
    if args:
        argv = [arg.strip() for arg in args.split(',')]
        if len(argv) > 0:
            prefix = argv[0].replace('\'', '\'\'')
            if len(argv) > 1:
                limit = int(argv[1])

    sql = 'SELECT name, max(time) FROM wiki '
    if prefix:
        sql += 'WHERE name LIKE \'%s%%\' ' % prefix
    sql += 'GROUP BY name ORDER BY max(time) DESC'
    if limit:
        sql += ' LIMIT %d' % limit
    cursor.execute(sql)

    buf = StringIO()
    prevtime = None
    while 1:
        row = cursor.fetchone()
        if row == None:
            break
        t = time.strftime('%x', time.localtime(int(row[1])))
        if not t == prevtime:
            if prevtime:
                buf.write('</ul>')
            buf.write('<h3>%s</h3><ul>' % t)
            prevtime = t
        buf.write('<li><a href="%s">%s</a></li>\n' % (env.href.wiki(row[0]),
                                                      row[0]))
    if prevtime:
        buf.write('</ul>')

    return buf.getvalue()
