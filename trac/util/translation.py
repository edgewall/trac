# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2008 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

"""Utilities for text translation with gettext."""

import re
try:
    import threading
except ImportError:
    import dummy_threading as threading

import pkg_resources

from genshi.builder import tag


__all__ = ['gettext', 'ngettext', 'gettext_noop', 'ngettext_noop', 
           'tgettext', 'tgettext_noop', 'tngettext', 'tngettext_noop']


def gettext_noop(string, **kwargs):
    return kwargs and string % kwargs or string
N_ = gettext_noop

def ngettext_noop(singular, plural, num, **kwargs):
    string = (plural, singular)[num == 1]
    kwargs.setdefault('num', num)
    return string % kwargs

_param_re = re.compile(r"%\((\w+)\)(?:s|[\d]*d|\d*.?\d*[fg])")
def _tag_kwargs(trans, kwargs):
    trans_elts = _param_re.split(trans)
    for i in xrange(1, len(trans_elts), 2):
        trans_elts[i] = kwargs.get(trans_elts[i], '???')
    return tag(*trans_elts)

def tgettext_noop(string, **kwargs):
    return kwargs and _tag_kwargs(string, kwargs) or string

def tngettext_noop(singular, plural, num, **kwargs):
    string = (plural, singular)[num == 1]
    kwargs.setdefault('num', num)
    return _tag_kwargs(string, kwargs)


try:
    from babel.support import LazyProxy, Translations
    from gettext import NullTranslations

    _current = threading.local()

    def gettext(string, **kwargs):
        def _gettext():
            trans = get_translations().ugettext(string)
            return kwargs and trans % kwargs or trans
        if not hasattr(_current, 'translations'):
            return LazyProxy(_gettext)
        return _gettext()
    _ = gettext

    def ngettext(singular, plural, num, **kwargs):
        kwargs = kwargs.copy()
        kwargs.setdefault('num', num)
        def _ngettext():
            trans = get_translations().ungettext(singular, plural, num)
            return trans % kwargs
        if not hasattr(_current, 'translations'):
            return LazyProxy(_ngettext)
        return _ngettext()

    def tgettext(string, **kwargs):
        def _tgettext():
            trans = get_translations().ugettext(string)
            return kwargs and _tag_kwargs(trans, kwargs) or trans
        if not hasattr(_current, 'translations'):
            return LazyProxy(_tgettext)
        return _tgettext()
    tag_ = tgettext

    def tngettext(singular, plural, num, **kwargs):
        kwargs = kwargs.copy()
        kwargs.setdefault('num', num)
        def _tngettext():
            trans = get_translations().ungettext(singular, plural, num)
            return _tag_kwargs(trans, kwargs)
        if not hasattr(_current, 'translations'):
            return LazyProxy(_tngettext)
        return _tngettext()

    def activate(locale):
        locale_dir = pkg_resources.resource_filename(__name__, '../locale')
        _current.translations = Translations.load(locale_dir, locale)

    _null_translations = NullTranslations()

    def get_translations():
        return getattr(_current, 'translations', _null_translations)

    def deactivate():
        del _current.translations

    def get_available_locales():
        """Return a list of locale identifiers of the locales for which
        translations are available.
        """
        return [dirname for dirname
                in pkg_resources.resource_listdir(__name__, '../locale')
                if '.' not in dirname]

except ImportError: # fall back on 0.11 behavior, i18n functions are no-ops
    gettext = _ = gettext_noop
    ngettext = ngettext_noop
    tgettext = tag_ = tgettext_noop
    tngettext = tngettext_noop

    def activate(locale):
        pass

    def deactivate():
        pass

    def get_translations():
        return []

    def get_available_locales():
        return []
