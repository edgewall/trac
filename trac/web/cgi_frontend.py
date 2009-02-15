#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C)2005-2009 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
# Author: Christopher Lenz <cmlenz@gmx.de>
#         Matthew Good <trac@matt-good.net>

import os
import pkg_resources
import sys

from trac import __version__ as VERSION
from trac.web.main import dispatch_request
from trac.web.wsgi import WSGIGateway


class CGIGateway(WSGIGateway):

    wsgi_multithread = False
    wsgi_multiprocess = False
    wsgi_run_once = True

    def __init__(self):
        WSGIGateway.__init__(self, dict(os.environ))

    def _write(self, data):
        assert self.headers_set, 'Response not started'

        if not self.headers_sent:
            status, headers = self.headers_sent = self.headers_set
            sys.stdout.write('Status: %s\r\n' % status)
            for header in headers:
                sys.stdout.write('%s: %s\r\n' % header)
            sys.stdout.write('\r\n')
            sys.stdout.flush()

        sys.stdout.write(data)
        sys.stdout.flush()


def run():
    try: # Make FreeBSD use blocking I/O like other platforms
        import fcntl
        for stream in [sys.stdin, sys.stdout]:
            fd = stream.fileno()
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)
    except (ImportError, AttributeError):
        pass

    try: # Use binary I/O on Windows
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    except ImportError:
        pass

    gateway = CGIGateway()
    gateway.run(dispatch_request)

if __name__ == '__main__':
    pkg_resources.require('Trac==%s' % VERSION)
    run()
