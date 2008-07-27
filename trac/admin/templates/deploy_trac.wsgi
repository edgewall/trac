#!${executable}
# -*- coding: utf-8 -*-
#
# Copyright (C) 2008 Edgewall Software
# Copyright (C) 2008 Noah Kantrowitz <noah@coderanger.net>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Noah Kantrowitz <noah@coderanger.net>
import os
import pkg_resources

def application(environ, start_request):
    environ['trac.env_path'] = '${env.path}'
    if 'PYTHON_EGG_CACHE' not in os.environ:
        egg_cache = os.path.join('${env.path}', 'egg-cache')
        pkg_resources.set_extraction_path(egg_cache)
    from trac.web.main import dispatch_request
    return dispatch_request(environ, start_request)
