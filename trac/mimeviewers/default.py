from trac.util import escape

supported_types = [(9, None)]

def display(data, mimetype, filename, env):
    return '<pre class="code-block">' + escape(data) + '</pre>'
