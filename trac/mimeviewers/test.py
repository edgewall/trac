supported_types = [(2, 'application/x-test')]

def display(data, mimetype, filename, env):
    return '<pre>' + '\nTESTING: '.join(data.splitlines()) + '</pre>'
