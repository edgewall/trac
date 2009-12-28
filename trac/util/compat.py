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
previous versions of Python from 2.4 onward.
"""

import os

# Import symbols previously defined here for Python 2.3 compatibility from
# __builtin__ so that plugins importing them don't suddenly stop working
set = set
frozenset = frozenset
reversed = reversed
sorted = sorted
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

try:
    all = all
    any = any
except NameError:
    def any(S):
        for x in S:
            if x:
                return True
        return False

    def all(S):
        for x in S:
            if not x:
                return False
        return True

if hasattr('', 'rpartition'):
    def rpartition(s, sep):
        return s.rpartition(sep)
else:
    def rpartition(s, sep):
        idx = s.rfind(sep)
        if idx < 0:
            return ('', '', s)
        else:
            return (s[:idx], sep, s[idx+len(sep):])

try:
    from functools import partial
except ImportError:
    def partial(func_, *args, **kwargs):
        def newfunc(*fargs, **fkwargs):
            return func_(*(args + fargs), **dict(kwargs, **fkwargs))
        newfunc.func = func_
        newfunc.args = args
        newfunc.keywords = kwargs
        try:
            newfunc.__name__ = func_.__name__
        except TypeError: # python 2.3
            pass
        return newfunc


# The md5 and sha modules are deprecated in Python 2.5
try:
    from hashlib import md5, sha1
except ImportError:
    from md5 import md5
    from sha import new as sha1

# An error is raised by subprocess if we ever pass close_fds=True on Windows.
# We want it to be True on all other platforms to not leak file descriptors.
close_fds = True
if os.name == 'nt':
    close_fds = False

