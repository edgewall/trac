"""
Inserts an alphabetic list of all wiki pages into the output.

Accepts a prefix string as parameter: if provided, only pages with names that
start with the prefix are included in the resulting list. If this parameter is
omitted, all pages are listed.
"""

from StringIO import StringIO

def execute(hdf, args, env):
    db = env.get_db_cnx()
    cursor = db.cursor()

    prefix = None
    if args:
        prefix = args.replace('\'', '\'\'')

    sql = 'SELECT DISTINCT name FROM wiki '
    if prefix:
        sql += 'WHERE name LIKE \'%s%%\' ' % prefix
    sql += 'ORDER BY name'
    cursor.execute(sql)

    buf = StringIO()
    buf.write('<ul>')
    while 1:
        row = cursor.fetchone()
        if row == None:
            break
        buf.write('<li><a href="%s">' % env.href.wiki(row[0]))
        buf.write(row[0])
        buf.write('</a></li>\n')
    buf.write('</ul>')

    return buf.getvalue()
