# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2009 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

"""Utilities for text translation with gettext.

Currently (for version 0.11) the functions here are noops, and only used to
flag localizable strings as such.
"""

__all__ = ['gettext', 'ngettext', 'gettext_noop', 'ngettext_noop']

def gettext_noop(string, **kwargs):
    retval = string
    if kwargs:
        retval %= kwargs
    return retval
N_ = gettext_noop
gettext = _ = gettext_noop

def ngettext_noop(singular, plural, num, **kwargs):
    if num == 1:
        retval = singular
    else:
        retval = plural
    kwargs.setdefault('num', num)
    return retval % kwargs
ngettext = ngettext_noop
