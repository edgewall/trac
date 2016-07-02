# -*- coding: utf-8 -*-
#
# Copyright (C) 2013 Edgewall Software
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
import shutil
import sys
import time
import unittest


def rmtree(path):
    import errno
    def onerror(function, path, excinfo, retry=1):
        # `os.remove` fails for a readonly file on Windows.
        # Then, it attempts to be writable and remove.
        if function != os.remove:
            raise
        e = excinfo[1]
        if isinstance(e, OSError) and e.errno == errno.EACCES:
            mode = os.stat(path).st_mode
            os.chmod(path, mode | 0666)
            try:
                function(path)
            except Exception:
                # print "%d: %s %o" % (retry, path, os.stat(path).st_mode)
                if retry > 10:
                    raise
                time.sleep(0.1)
                onerror(function, path, excinfo, retry + 1)
        else:
            raise
    if os.name == 'nt' and isinstance(path, str):
        # Use unicode characters in order to allow non-ansi characters
        # on Windows.
        path = unicode(path, sys.getfilesystemencoding())
    shutil.rmtree(path, onerror=onerror)
