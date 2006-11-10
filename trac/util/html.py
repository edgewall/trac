# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import re

from genshi.core import Markup, escape, unescape
from genshi.builder import Element, ElementFactory, Fragment
from genshi.path import Path

__all__ = ['escape', 'unescape', 'html', 'plaintext']


class Deuglifier(object):

    def __new__(cls):
        self = object.__new__(cls)
        if not hasattr(cls, '_compiled_rules'):
            cls._compiled_rules = re.compile('(?:' + '|'.join(cls.rules()) + ')')
        self._compiled_rules = cls._compiled_rules
        return self
    
    def format(self, indata):
        return re.sub(self._compiled_rules, self.replace, indata)

    def replace(self, fullmatch):
        for mtype, match in fullmatch.groupdict().items():
            if match:
                if mtype == 'font':
                    return '<span>'
                elif mtype == 'endfont':
                    return '</span>'
                return '<span class="code-%s">' % mtype


class TransposingElementFactory(ElementFactory):

    def __init__(self, func, namespace=None):
        ElementFactory.__init__(self, namespace=namespace)
        self.func = func

    def __getattr__(self, name):
        return ElementFactory.__getattr__(self, self.func(name))


TEXT_XPATH = Path('text()')

def plaintext(text, keeplinebreaks=True):
    if isinstance(text, Fragment):
        return TEXT_XPATH.select(text)
    else:
        from genshi import core
        return core.plaintext(text)
    
html = TransposingElementFactory(str.lower)
