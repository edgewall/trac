from trac.util import escape

supported_types = [(9, None)]

def display(data, mimetype, filename, env):
    env.log.debug("Mimetype: %s   filename: %s" % (mimetype, filename))
    if not mimetype or not mimetype[:5] == 'text/':
        env.log.debug("Binary data. Displaying summary.")
        return ''
    env.log.debug("Using default mimeviewer")
    return '<pre class="code-block">' + escape(data) + '</pre>'
