#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C)2005-2009 Edgewall Software
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

import pkg_resources

from trac import __version__ as VERSION
from trac.web.main import dispatch_request

import _fcgi

def run():
    _fcgi.WSGIServer(dispatch_request).run()

if __name__ == '__main__':
    pkg_resources.require('Trac==%s' % VERSION)
    run()
