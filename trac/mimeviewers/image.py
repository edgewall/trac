supported_types = [
    (8, 'image/gif'),
    (8, 'image/x-icon'),
    (8, 'image/jpeg'),
    (8, 'image/png'),
    (8, 'image/x-ms-bmp'),
    ]


def display(data, mimetype, filename, rev, env):
    src_href = '?'
    if rev:
        src_href += 'rev=%d&' % rev
    src_href += 'format=raw'
    html = '<div class="image-file">' \
           '<img alt="%s" src="%s" />' \
           '</div>' % (filename, src_href)
    return html
