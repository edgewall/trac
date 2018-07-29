# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

# Workaround for http://bugs.python.org/issue6763 and
# http://bugs.python.org/issue5853 thread issues
import mimetypes
mimetypes.init()

# With mod_python we'll have to delay importing trac.web.api until
# modpython_frontend.handler() has been called since the
# PYTHON_EGG_CACHE variable is set from there
#
# TODO: Remove this once the Genshi zip_safe issue has been resolved.

import os
from pkg_resources import get_distribution
if not os.path.isdir(get_distribution('genshi').location):
    try:
        import mod_python.apache
        import sys
        if 'trac.web.modpython_frontend' in sys.modules:
            from trac.web.api import *
    except ImportError:
        from trac.web.api import *
else:
    from trac.web.api import *
