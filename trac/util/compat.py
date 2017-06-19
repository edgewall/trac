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
previous versions of Python from 2.6 onward.
"""

import errno
import math
import os
import time

from trac.util.text import cleandoc

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
            hash_method = des_crypt.hash if hasattr(des_crypt, 'hash') \
                                         else des_crypt.encrypt
            return hash_method(secret, salt=salt)

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
    """Use in templates as an alternative to `itertools.groupby`,
    which leaks memory for Python < 2.5.3.

    This class will be removed in Trac 1.3.1.
    """
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
        return self.currkey, self._grouper(self.tgtkey)
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


try:
    from collections import OrderedDict
except ImportError:

    try:
        from thread import get_ident as _get_ident
    except ImportError:
        from dummy_thread import get_ident as _get_ident

    class OrderedDict(dict):
        'Dictionary that remembers insertion order'
        # An inherited dict maps keys to values.
        # The inherited dict provides __getitem__, __len__,
        # __contains__, and get.
        # The remaining methods are order-aware.
        # Big-O running times for all methods are the same as for
        # regular dictionaries.

        # The internal self.__map dictionary maps keys to links in a
        # doubly linked list.
        # The circular doubly linked list starts and ends with a
        # sentinel element.
        # The sentinel element never gets deleted (this simplifies
        # the algorithm).
        # Each link is stored as a list of length three:
        # [PREV, NEXT, KEY].

        def __init__(self, *args, **kwds):
            """Initialize an ordered dictionary.  Signature is the same
            as for regular dictionaries, but keyword arguments are not
            recommended because their insertion order is arbitrary.
            """
            if len(args) > 1:
                raise TypeError('expected at most 1 arguments, got %d'
                                % len(args))
            try:
                self.__root
            except AttributeError:
                self.__root = root = []  # sentinel node
                root[:] = [root, root, None]
                self.__map = {}
            self.__update(*args, **kwds)

        def __setitem__(self, key, value, dict_setitem=dict.__setitem__):
            'od.__setitem__(i, y) <==> od[i]=y'
            # Setting a new item creates a new link which goes at the
            # end of the linked
            # list, and the inherited dictionary is updated with the
            # new key/value pair.
            if key not in self:
                root = self.__root
                last = root[0]
                last[1] = root[0] = self.__map[key] = [last, root, key]
            dict_setitem(self, key, value)

        def __delitem__(self, key, dict_delitem=dict.__delitem__):
            """od.__delitem__(y) <==> del od[y]"""
            # Deleting an existing item uses self.__map to find the
            # link which is then removed by updating the links in the
            # predecessor and successor nodes.
            dict_delitem(self, key)
            link_prev, link_next, key = self.__map.pop(key)
            link_prev[1] = link_next
            link_next[0] = link_prev

        def __iter__(self):
            """od.__iter__() <==> iter(od)"""
            root = self.__root
            curr = root[1]
            while curr is not root:
                yield curr[2]
                curr = curr[1]

        def __reversed__(self):
            """od.__reversed__() <==> reversed(od)"""
            root = self.__root
            curr = root[0]
            while curr is not root:
                yield curr[2]
                curr = curr[0]

        def clear(self):
            """od.clear() -> None.  Remove all items from od."""
            try:
                for node in self.__map.itervalues():
                    del node[:]
                root = self.__root
                root[:] = [root, root, None]
                self.__map.clear()
            except AttributeError:
                pass
            dict.clear(self)

        def popitem(self, last=True):
            """od.popitem() -> (k, v), return and remove a (key, value)
            pair. Pairs are returned in LIFO order if last is true or
            FIFO order if false.
            """
            if not self:
                raise KeyError('dictionary is empty')
            root = self.__root
            if last:
                link = root[0]
                link_prev = link[0]
                link_prev[1] = root
                root[0] = link_prev
            else:
                link = root[1]
                link_next = link[1]
                root[1] = link_next
                link_next[0] = root
            key = link[2]
            del self.__map[key]
            value = dict.pop(self, key)
            return key, value

        # -- the following methods do not depend on the internal structure --

        def keys(self):
            """od.keys() -> list of keys in od"""
            return list(self)

        def values(self):
            """od.values() -> list of values in od"""
            return [self[key] for key in self]

        def items(self):
            """od.items() -> list of (key, value) pairs in od"""
            return [(key, self[key]) for key in self]

        def iterkeys(self):
            """od.iterkeys() -> an iterator over the keys in od"""
            return iter(self)

        def itervalues(self):
            """od.itervalues -> an iterator over the values in od"""
            for k in self:
                yield self[k]

        def iteritems(self):
            """od.iteritems -> an iterator over the (key, value) items
            in od
            """
            for k in self:
                yield (k, self[k])

        def update(*args, **kwds):
            """od.update(E, **F) -> None.  Update od from dict/iterable
            E and F.

            If E is a dict instance, does:
                for k in E: od[k] = E[k]
            If E has a .keys() method, does:
                for k in E.keys(): od[k] = E[k]
            Or if E is an iterable of items, does:
                for k, v in E: od[k] = v
            In either case, this is followed by:
                for k, v in F.items(): od[k] = v
            """
            if len(args) > 2:
                raise TypeError('update() takes at most 2 positional '
                                'arguments (%d given)' % (len(args),))
            elif not args:
                raise TypeError('update() takes at least 1 argument (0 given)')
            self = args[0]
            # Make progressively weaker assumptions about "other"
            other = ()
            if len(args) == 2:
                other = args[1]
            if isinstance(other, dict):
                for key in other:
                    self[key] = other[key]
            elif hasattr(other, 'keys'):
                for key in other.keys():
                    self[key] = other[key]
            else:
                for key, value in other:
                    self[key] = value
            for key, value in kwds.items():
                self[key] = value

        # let subclasses override update without breaking __init__
        __update = update

        __marker = object()

        def pop(self, key, default=__marker):
            """od.pop(k[,d]) -> v, remove specified key and return the
            corresponding value. If key is not found, d is returned if
            given, otherwise KeyError is raised.
            """
            if key in self:
                result = self[key]
                del self[key]
                return result
            if default is self.__marker:
                raise KeyError(key)
            return default

        def setdefault(self, key, default=None):
            """od.setdefault(k[,d]) -> od.get(k,d), also set od[k]=d if
            k not in od
            """
            if key in self:
                return self[key]
            self[key] = default
            return default

        def __repr__(self, _repr_running={}):
            """od.__repr__() <==> repr(od)"""
            call_key = id(self), _get_ident()
            if call_key in _repr_running:
                return '...'
            _repr_running[call_key] = 1
            try:
                if not self:
                    return '%s()' % (self.__class__.__name__,)
                return '%s(%r)' % (self.__class__.__name__, self.items())
            finally:
                del _repr_running[call_key]

        def __reduce__(self):
            """Return state information for pickling"""
            items = [[k, self[k]] for k in self]
            inst_dict = vars(self).copy()
            for k in vars(OrderedDict()):
                inst_dict.pop(k, None)
            if inst_dict:
                return (self.__class__, (items,), inst_dict)
            return self.__class__, (items,)

        def copy(self):
            """od.copy() -> a shallow copy of od"""
            return self.__class__(self)

        @classmethod
        def fromkeys(cls, iterable, value=None):
            """OD.fromkeys(S[, v]) -> New ordered dictionary with keys
            from S and values equal to v (which defaults to None).
            """
            d = cls()
            for key in iterable:
                d[key] = value
            return d

        def __eq__(self, other):
            """od.__eq__(y) <==> od==y.  Comparison to another OD is
            order-sensitive while comparison to a regular mapping is
            order-insensitive.
            """
            if isinstance(other, OrderedDict):
                return len(self)==len(other) and self.items() == other.items()
            return dict.__eq__(self, other)

        def __ne__(self, other):
            return not self == other
