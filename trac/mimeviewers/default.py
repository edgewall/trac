from trac.util import escape

supported_types = [(9, None)]

def display(data, mimetype, filename, env):
    env.log.debug("Using default mimeviewer")
    return '<pre class="code-block">' + escape(data) + '</pre>'
