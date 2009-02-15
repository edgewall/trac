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
previous of Python prior to 2.4.
"""

try:
    set = set
    frozenset = frozenset
except NameError:
    from sets import Set as set
    from sets import ImmutableSet as frozenset

try:
    reversed = reversed
except NameError:
    def reversed(x):
        if hasattr(x, 'keys'):
            raise ValueError('mappings do not support reverse iteration')
        i = len(x)
        while i > 0:
            i -= 1
            yield x[i]

try:
    sorted = sorted
except NameError:
    def sorted(iterable, cmp=None, key=None, reverse=False):
        """Partial implementation of the "sorted" function from Python 2.4"""
        if key is None:
            lst = list(iterable)
        else:
            lst = [(key(val), idx, val) for idx, val in enumerate(iterable)]
        lst.sort()
        if key is None:
            if reverse:
                return lst[::-1]
            return lst
        if reverse:
            lst = reversed(lst)
        return [i[-1] for i in lst]

# Note: not used, suggest to remove in 0.12
try:
    from operator import attrgetter, itemgetter
except ImportError:
    def attrgetter(name):
        def _getattr(obj):
            return getattr(obj, name)
        return _getattr
    def itemgetter(name):
        def _getitem(obj):
            return obj[name]
        return _getitem

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
    from itertools import groupby
except ImportError:
    groupby = py_groupby

# Note: only used by pairwise, which is now deprecated
#       (suggest to remove it from 0.12 as well)
try:
    from itertools import tee
except ImportError:
    from itertools import count
    def tee(iterable):
        def gen(next, data={}, cnt=[0]):
            for i in count():
                if i == cnt[0]:
                    item = data[i] = next()
                    cnt[0] += 1
                else:
                    item = data.pop(i)
                yield item
        it = iter(iterable)
        return (gen(it.next), gen(it.next))

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
