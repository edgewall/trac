# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2008 Edgewall Software
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


# The md5 module is deprecated in Python 2.5
try:
    from hashlib import md5
except ImportError:
    from md5 import md5
