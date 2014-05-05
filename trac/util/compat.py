# -*- coding: utf-8 -*-
#
# Copyright (C)2006-2009 Edgewall Software
# Copyright (C) 2006 Matthew Good <trac@matt-good.net>
# Copyright (C) 2006 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

"""Various classes and functions to provide some backwards-compatibility with
previous versions of Python from 2.5 onward.
"""

import math
import os
import time
from inspect import cleandoc

# Import symbols previously defined here, kept around so that plugins importing
# them don't suddenly stop working
all = all
any = any
frozenset = frozenset
reversed = reversed
set = set
sorted = sorted
from functools import partial
from hashlib import md5, sha1
from itertools import groupby, tee

class py_groupby(object):
    def __init__(self, iterable, key=None):
        if key is None:
            key = lambda x: x
        self.keyfunc = key
        self.it = iter(iterable)
        self.tgtkey = self.currkey = self.currvalue = xrange(0)
    def __iter__(self):
        return self
    def next(self):
        while self.currkey == self.tgtkey:
            self.currvalue = self.it.next() # Exit on StopIteration
            self.currkey = self.keyfunc(self.currvalue)
        self.tgtkey = self.currkey
        return (self.currkey, self._grouper(self.tgtkey))
    def _grouper(self, tgtkey):
        while self.currkey == tgtkey:
            yield self.currvalue
            self.currvalue = self.it.next() # Exit on StopIteration
            self.currkey = self.keyfunc(self.currvalue)

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
    try:
        mtime = os.stat(filename).st_mtime
        os.utime(filename, None)
        while mtime == os.stat(filename).st_mtime:
            time.sleep(1e-3)
            os.utime(filename, None)
    except OSError:
        pass  # file doesn't exist (yet)
