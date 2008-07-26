# mod_python specific code that needs to be here in order to
# to be executed before anything is imported.
# 
# Make it possible to set PYTHON_EGG_CACHE from the apache config like this:
#
# PythonOption PYTHON_EGG_CACHE /some/path
#
# Important: This option must be placed outside any Virtualhost 
# and Location sections.
#
try:
    from mod_python import apache
    import os
    options = apache.main_server.get_options()
    egg_cache = options.get('PYTHON_EGG_CACHE')
    if egg_cache:
        os.environ['PYTHON_EGG_CACHE'] = egg_cache
except ImportError:
    pass
    
from trac.web.api import *
