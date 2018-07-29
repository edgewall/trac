#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2018 Edgewall Software
# Copyright (C) 2005 Matthew Good <trac@matt-good.net>
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
# Author: Matthew Good <trac@matt-good.net>

import os
import pkg_resources
import urllib

from trac import __version__ as VERSION
from trac.web.main import dispatch_request

use_flup = os.environ.get('TRAC_USE_FLUP', False)
if use_flup in ('0', 'no', 'off'):
    use_flup = False


class FlupMiddleware(object):
    """Flup doesn't URL unquote the PATH_INFO, so we need to do it."""
    def __init__(self, application):
        self.application = application

    def __call__(self, environ, start_response):
        environ['PATH_INFO'] = urllib.unquote(environ.get('PATH_INFO', ''))
        return self.application(environ, start_response)

params = {}

if use_flup:
    try:
        from flup.server.fcgi import WSGIServer
        params['maxThreads'] = 15
        dispatch_request = FlupMiddleware(dispatch_request)
    except ImportError:
        use_flup = False

if not use_flup:
    from _fcgi import WSGIServer

def run():
    WSGIServer(dispatch_request, **params).run()

if __name__ == '__main__':
    pkg_resources.require('Trac==%s' % VERSION)
    run()
