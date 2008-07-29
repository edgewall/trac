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
    # main_server is only available in mod_python >= 3.3
    from mod_python.apache import main_server
    egg_cache = main_server.get_options().get('PYTHON_EGG_CACHE')
    if egg_cache:
        import pkg_resources
        pkg_resources.set_extraction_path(egg_cache)
except ImportError:
    pass
    
from trac.web.api import *
