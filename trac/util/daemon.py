# -*- coding: utf-8 -*-
#
# Copyright (C) 2006 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.

import os
import sys

def daemonize(stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
    """Fork a daemon process (taken from the Python Cookbook)."""

    # Perform first fork
    pid = os.fork()
    if pid > 0:
        sys.exit(0) # exit first parent

    # Decouple from parent environment
    os.chdir('/')
    os.umask(0)
    os.setsid()

    # Perform second fork
    pid = os.fork()
    if pid > 0:
        sys.exit(0) # exit first parent

    # The process is now daemonized, redirect standard file descriptors
    for fileobj in sys.stdout, sys.stderr:
        fileobj.flush()
    stdin = file(stdin, 'r')
    stdout = file(stdout, 'a+')
    stderr = file(stderr, 'a+', 0)
    os.dup2(stdin.fileno(), sys.stdin.fileno())
    os.dup2(stdout.fileno(), sys.stdout.fileno())
    os.dup2(stderr.fileno(), sys.stderr.fileno())
