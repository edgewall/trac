# -*- coding: utf-8 -*-
#
# Copyright (C)2006-2009 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os
import sys
import threading
import time
import traceback

_SLEEP_TIME = 1

def _reloader_thread(modification_callback, loop_callback):
    """When this function is run from the main thread, it will force other
    threads to exit when any modules currently loaded change.

    @param modification_callback: a function taking a single argument, the
        modified file, which is called every time a modification is detected
    @param loop_callback: a function taking no arguments, which is called
        after every modification check
    """
    mtimes = {}
    while True:
        for filename in filter(None, [getattr(module, '__file__', None)
                                      for module in sys.modules.values()]):
            while not os.path.isfile(filename): # Probably in an egg or zip file
                filename = os.path.dirname(filename)
                if not filename:
                    break
            if not filename: # Couldn't map to physical file, so just ignore
                continue

            if filename.endswith(('.pyc', '.pyo')):
                filename = filename[:-1]

            if not os.path.isfile(filename):
                # Compiled file for non-existant source
                continue

            mtime = os.stat(filename).st_mtime
            if filename not in mtimes:
                mtimes[filename] = mtime
                continue
            if mtime != mtimes[filename]:
                modification_callback(filename)
                sys.exit(3)
        loop_callback()
        time.sleep(_SLEEP_TIME)

def _restart_with_reloader():
    while True:
        args = [sys.executable] + sys.argv
        if sys.platform == 'win32':
            args = ['"%s"' % arg for arg in args]
        new_environ = os.environ.copy()
        new_environ['RUN_MAIN'] = 'true'

        # This call reinvokes ourself and goes into the other branch of main as
        # a new process.
        exit_code = os.spawnve(os.P_WAIT, sys.executable,
                               args, new_environ)
        if exit_code != 3:
            return exit_code

def main(func, modification_callback, *args, **kwargs):
    """Run the given function and restart any time modules are changed."""
    if os.environ.get('RUN_MAIN'):
        exit_code = []
        def main_thread():
            try:
                func(*args, **kwargs)
                exit_code.append(None)
            except SystemExit, e:
                exit_code.append(e.code)
            except:
                traceback.print_exception(*sys.exc_info())
                exit_code.append(1)
        def check_exit():
            if exit_code:
                sys.exit(exit_code[0])
        # Lanch the actual program as a child thread
        thread = threading.Thread(target=main_thread, name='Main thread')
        thread.setDaemon(True)
        thread.start()
        try:
            # Now wait for a file modification and quit
            _reloader_thread(modification_callback, check_exit)
        except KeyboardInterrupt:
            pass
    else:
        # Initial invocation just waits around restarting this executable
        try:
            sys.exit(_restart_with_reloader())
        except KeyboardInterrupt:
            pass
