supported_types = [
    (8, 'image/gif'),
    (8, 'image/jpeg'),
    (8, 'image/png'),
    (8, 'image/x-ms-bmp'),
    ]


def display(data, mimetype, filename, env):
    html = '<div class="image-file">' \
           '<div class="image-file-frame">' \
           '<img alt="%s" src="?format=raw" />' \
           '</div></div><br style="clear: both" />' % filename
    return html
