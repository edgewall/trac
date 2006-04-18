"""Example macro."""
from trac.util import escape

def execute(hdf, txt, env):
    # Currently hdf is set only when the macro is called
    # From a wiki page
    if hdf:
        hdf['wiki.macro.greeting'] = 'Hello World'
        
    # args will be `None` if the macro is called without parenthesis.
    args = txt or 'No arguments'

    # then, as `txt` comes from the user, it's important to guard against
    # the possibility to inject malicious HTML/Javascript, by using `escape()`:
    return 'Hello World, args = ' + escape(args)
