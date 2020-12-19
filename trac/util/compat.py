# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2020 Edgewall Software
# Copyright (C) 2006 Matthew Good <trac@matt-good.net>
# Copyright (C) 2006 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import errno
import os
import subprocess
import time


# Windows doesn't have a crypt module by default.
try:
    from crypt import crypt
except ImportError:
    try:
        from passlib.hash import des_crypt
    except ImportError:
        crypt = None
    else:
        def crypt(secret, salt):
            # encrypt method deprecated in favor of hash in passlib 1.7
            if hasattr(des_crypt, 'hash'):
                return des_crypt.using(salt=salt).hash(secret)
            else:
                return des_crypt.encrypt(secret, salt=salt)


def rpartition(s, sep):
    return s.rpartition(sep)

# An error is raised by subprocess if we ever pass close_fds=True on Windows.
# We want it to be True on all other platforms to not leak file descriptors.
close_fds = os.name != 'nt'


def wait_for_file_mtime_change(filename):
    """This function is typically called before a file save operation,
    waiting if necessary for the file modification time to change. The
    purpose is to avoid successive file updates going undetected by the
    caching mechanism that depends on a change in the file modification
    time to know when the file should be reparsed."""

    from trac.util import touch_file
    try:
        mtime = os.stat(filename).st_mtime
        touch_file(filename)
        while mtime == os.stat(filename).st_mtime:
            time.sleep(1e-3)
            touch_file(filename)
    except OSError as e:
        if e.errno == errno.ENOENT:
            pass
        else:
            raise
