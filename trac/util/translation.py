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

import pkg_resources
try:
    import threading
except ImportError:
    import dummy_threading as threading

__all__ = ['gettext', 'ngettext', 'gettext_noop', 'ngettext_noop']


def gettext_noop(string, **kwargs):
    retval = string
    if kwargs:
        retval %= kwargs
    return retval
N_ = gettext_noop

def ngettext_noop(singular, plural, num, **kwargs):
    if num == 1:
        retval = singular
    else:
        retval = plural
    if kwargs:
        retval %= kwargs
    return retval


try:
    from babel.support import LazyProxy, Translations
    from gettext import NullTranslations

    _current = threading.local()

    def gettext(string, **kwargs):
        def _gettext():
            trans = get_translations().ugettext(string)
            if kwargs:
                trans %= kwargs
            return trans
        if not hasattr(_current, 'translations'):
            return LazyProxy(_gettext)
        return _gettext()
    _ = gettext

    def ngettext(singular, plural, num, **kwargs):
        def _ngettext():
            trans = get_translations().ungettext(singular, plural, num)
            if kwargs:
                trans %= kwargs
            return trans
        if not hasattr(_current, 'translations'):
            return LazyProxy(_ngettext)
        return _ngettext()

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

except ImportError: # fall back on 0.11 behavior
    gettext = _ = gettext_noop
    ngettext = ngettext_noop

    def activate(locale):
        pass

    def deactivate():
        pass

    def get_translations():
        return []

    def get_available_locales():
        return []
