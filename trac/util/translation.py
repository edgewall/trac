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

"""Utilities for text translation with gettext."""

import pkg_resources
import re

from genshi.builder import tag

from trac.util.concurrency import ThreadLocal, threading


__all__ = ['gettext', 'ngettext', 'gettext_noop', 'ngettext_noop', 
           'tgettext', 'tgettext_noop', 'tngettext', 'tngettext_noop']

def safefmt(string, kwargs):
    if kwargs:
        try:
            return string % kwargs
        except KeyError:
            pass
    return string


def gettext_noop(string, **kwargs):
    return safefmt(string, kwargs)

def dgettext_noop(domain, string, **kwargs):
    return gettext_noop(string, **kwargs)

N_ = _noop = lambda string: string

def ngettext_noop(singular, plural, num, **kwargs):
    string = (plural, singular)[num == 1]
    kwargs.setdefault('num', num)
    return safefmt(string, kwargs)

def dngettext_noop(domain, singular, plural, num, **kwargs):
    return ngettext_noop(singular, plural, num, **kwargs)

_param_re = re.compile(r"%\((\w+)\)(?:s|[\d]*d|\d*.?\d*[fg])")
def _tag_kwargs(trans, kwargs):
    trans_elts = _param_re.split(trans)
    for i in xrange(1, len(trans_elts), 2):
        trans_elts[i] = kwargs.get(trans_elts[i], '???')
    return tag(*trans_elts)

def tgettext_noop(string, **kwargs):
    return kwargs and _tag_kwargs(string, kwargs) or string

def dtgettext_noop(domain, string, **kwargs):
    return tgettext_noop(string, **kwargs)

def tngettext_noop(singular, plural, num, **kwargs):
    string = (plural, singular)[num == 1]
    kwargs.setdefault('num', num)
    return _tag_kwargs(string, kwargs)

def dtngettext_noop(domain, singular, plural, num, **kwargs):
    return tngettext_noop(singular, plural, num, **kwargs)

def add_domain(domain, env_path, locale_dir):
    pass

def domain_functions(domain, *symbols):
    if symbols and not isinstance(symbols[0], basestring):
        symbols = symbols[0]
    _functions = {
      'gettext': gettext_noop,
      '_': gettext_noop,
      'N_': _noop,
      'ngettext': ngettext_noop,
      'tgettext': tgettext_noop,
      'tag_': tgettext_noop,
      'tngettext': tngettext_noop,
      'tagn_': tngettext_noop,
      'add_domain': lambda env_path, locale_dir: None,
      }
    return [_functions[s] for s in symbols]


from gettext import NullTranslations

class NullTranslationsBabel(NullTranslations):
    """NullTranslations doesn't have the domain related methods."""

    def dugettext(self, domain, string):
        return self.ugettext(string)

    def dungettext(self, domain, singular, plural, num):
        return self.ungettext(singular, plural, num)

has_babel = False

try:
    from babel import Locale
    from babel.support import LazyProxy, Translations

    class TranslationsProxy(object):
        """Delegate Translations calls to the currently active Translations.

        If there's none, wrap those calls in LazyProxy objects.

        Activation is controlled by `activate` and `deactivate` methods.
        However, if retrieving the locale information is costly, it's also
        possible to enable activation on demand only, by providing a callable
        to `make_activable`.
        """

        def __init__(self):
            self._current = ThreadLocal(args=None, translations=None)
            self._null_translations = NullTranslationsBabel()
            self._plugin_domains = {}
            self._plugin_domains_lock = threading.RLock()
            self._activate_failed = False

        # Public API

        def add_domain(self, domain, env_path, locales_dir):
            self._plugin_domains_lock.acquire()
            try:
                domains = self._plugin_domains.setdefault(env_path, {})
                domains[domain] = locales_dir
            finally:
                self._plugin_domains_lock.release()

        def make_activable(self, get_locale, env_path=None):
            self._current.args = (get_locale, env_path)

        def activate(self, locale, env_path=None):
            try:
                locale_dir = pkg_resources.resource_filename('trac', 'locale')
            except Exception:
                self._activate_failed = True
                return
            t = Translations.load(locale_dir, locale or 'en_US')
            if not t or t.__class__ is NullTranslations:
                t = self._null_translations
            elif env_path:
                self._plugin_domains_lock.acquire()
                try:
                    domains = self._plugin_domains.get(env_path, {}).items()
                finally:
                    self._plugin_domains_lock.release()
                for domain, dirname in domains:
                    t.add(Translations.load(dirname, locale, domain))
            self._current.translations = t
            self._activate_failed = False
         
        def deactivate(self):
            self._current.args = None
            t, self._current.translations = self._current.translations, None
            return t
         
        def reactivate(self, t):
            if t:
                self._current.translations = t
    
        @property
        def active(self):
            return self._current.translations or self._null_translations

        @property
        def isactive(self):
            if self._current.args is not None:
                get_locale, env_path = self._current.args
                self._current.args = None
                self.activate(get_locale(), env_path)
            # FIXME: The following always returns True: either a translation is
            # active, or activation has failed.
            return self._current.translations is not None \
                   or self._activate_failed

        # Delegated methods

        def __getattr__(self, name):
            return getattr(self.active, name)

        def gettext(self, string, **kwargs):
            def _gettext():
                return safefmt(self.active.ugettext(string), kwargs)
            if not self.isactive:
                return LazyProxy(_gettext)
            return _gettext()

        def dgettext(self, domain, string, **kwargs):
            def _dgettext():
                return safefmt(self.active.dugettext(domain, string), kwargs)
            if not self.isactive:
                return LazyProxy(_dgettext)
            return _dgettext()

        def ngettext(self, singular, plural, num, **kwargs):
            kwargs = kwargs.copy()
            kwargs.setdefault('num', num)
            def _ngettext():
                trans = self.active.ungettext(singular, plural, num)
                return safefmt(trans, kwargs)
            if not self.isactive:
                return LazyProxy(_ngettext)
            return _ngettext()

        def dngettext(self, domain, singular, plural, num, **kwargs):
            kwargs = kwargs.copy()
            kwargs.setdefault('num', num)
            def _dngettext():
                trans = self.active.dungettext(domain, singular, plural, num)
                return safefmt(trans, kwargs)
            if not self.isactive:
                return LazyProxy(_dngettext)
            return _dngettext()

        def tgettext(self, string, **kwargs):
            def _tgettext():
                trans = self.active.ugettext(string)
                return kwargs and _tag_kwargs(trans, kwargs) or trans
            if not self.isactive:
                return LazyProxy(_tgettext)
            return _tgettext()

        def dtgettext(self, domain, string, **kwargs):
            def _dtgettext():
                trans = self.active.dugettext(domain, string)
                return kwargs and _tag_kwargs(trans, kwargs) or trans
            if not self.isactive:
                return LazyProxy(_dtgettext)
            return _dtgettext()

        def tngettext(self, singular, plural, num, **kwargs):
            kwargs = kwargs.copy()
            kwargs.setdefault('num', num)
            def _tngettext():
                trans = self.active.ungettext(singular, plural, num)
                return _tag_kwargs(trans, kwargs)
            if not self.isactive:
                return LazyProxy(_tngettext)
            return _tngettext()

        def dtngettext(self, domain, singular, plural, num, **kwargs):
            kwargs = kwargs.copy()
            def _dtngettext():
                trans = self.active.dungettext(domain, singular, plural, num)
                if '%(num)' in trans:
                    kwargs.update(num=num)
                return kwargs and _tag_kwargs(trans, kwargs) or trans
            if not self.isactive:
                return LazyProxy(_dtngettext)
            return _dtngettext()

    
    translations = TranslationsProxy()

    def domain_functions(domain, *symbols):
        """Prepare partial instantiations of domain translation functions.

        :param domain: domain used for partial instantiation
        :param symbols: remaining parameters are the name of commonly used
                        translation function which will be bound to the domain
                        
        Note: the symbols can also be given as an iterable in the 2nd argument.
        """
        if symbols and not isinstance(symbols[0], basestring):
            symbols = symbols[0]
        _functions = {
          'gettext': translations.dgettext,
          '_': translations.dgettext,
          'ngettext': translations.dngettext,
          'tgettext': translations.dtgettext,
          'tag_': translations.dtgettext,
          'tngettext': translations.dtngettext,
          'tagn_': translations.dtngettext,
          'add_domain': translations.add_domain,
          }
        def wrapdomain(symbol):
            if symbol == 'N_':
                return _noop
            return lambda *args, **kw: _functions[symbol](domain, *args, **kw)
        return [wrapdomain(s) for s in symbols]

    gettext = translations.gettext 
    _ = gettext 
    dgettext = translations.dgettext 
    ngettext = translations.ngettext 
    dngettext = translations.dngettext 
    tgettext = translations.tgettext 
    tag_ = tgettext 
    dtgettext = translations.dtgettext 
    tngettext = translations.tngettext 
    tagn_ = tngettext 
    dtngettext = translations.dtngettext 
    
    def deactivate():
        """Deactivate translations.
        :return: the current Translations, if any
        """
        return translations.deactivate()

    def reactivate(t):
        """Reactivate previously deactivated translations.
        :param t: the Translations, as returned by `deactivate`
        """
        return translations.reactivate(t)

    def make_activable(get_locale, env_path=None):
        """Defer activation of translations.
        :param get_locale: a callable returning a Babel Locale object
        :param env_path: the environment to use for looking up catalogs
        """
        translations.make_activable(get_locale, env_path)

    def activate(locale, env_path=None):
        translations.activate(locale, env_path)

    def add_domain(domain, env_path, locale_dir):
        translations.add_domain(domain, env_path, locale_dir)

    def get_translations():
        return translations

    def get_available_locales():
        """Return a list of locale identifiers of the locales for which
        translations are available.
        """
        try:
            return [dirname for dirname
                    in pkg_resources.resource_listdir('trac', 'locale')
                    if '.' not in dirname]
        except Exception:
            return []

    def get_negotiated_locale(preferred_locales):
        def normalize(locale_ids):
            return [id.replace('_', '-') for id in locale_ids if id]
        return Locale.negotiate(normalize(preferred_locales),
                                normalize(get_available_locales()), sep='-')
        
    has_babel = True

except ImportError: # fall back on 0.11 behavior, i18n functions are no-ops
    gettext = _ = gettext_noop
    dgettext = dgettext_noop
    ngettext = ngettext_noop
    dngettext = dngettext_noop
    tgettext = tag_ = tgettext_noop
    dtgettext = dtgettext_noop
    tngettext = tagn_ = tngettext_noop
    dtngettext = dtngettext_noop

    translations = NullTranslationsBabel()
    
    def activate(locale, env_path=None):
        pass

    def deactivate():
        pass

    def reactivate(t):
        pass

    def make_activable(get_locale, env_path=None):
        pass

    def get_translations():
        return translations

    def get_available_locales():
        return []

    def get_negotiated_locale(preferred=None, default=None):
        return None
