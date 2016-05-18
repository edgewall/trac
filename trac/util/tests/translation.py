# -*- coding: utf-8 -*-
#
# Copyright (C) 2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import tempfile
import unittest
from pkg_resources import resource_exists, resource_filename
try:
    import babel
except ImportError:
    babel = None
    locale_identifiers = lambda: ()
else:
    try:
        from babel.localedata import locale_identifiers
    except ImportError:
        from babel.localedata import list as locale_identifiers

from trac.test import EnvironmentStub
from trac.util import translation


class TranslationsProxyTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.env.path = tempfile.mkdtemp(prefix='trac-tempenv-')

    def tearDown(self):
        translation.deactivate()
        self.env.reset_db_and_disk()

    def _get_locale_dir(self):
        return resource_filename('trac', 'locale')

    def _get_available_locales(self):
        return sorted(locale
                      for locale in translation.get_available_locales()
                      if resource_exists('trac',
                                         'locale/%s/LC_MESSAGES/messages.mo'
                                         % locale))

    def test_activate(self):
        locales = self._get_available_locales()
        if locales:
            translation.activate(locales[0], self.env.path)

    def test_activate_unavailable_locale(self):
        unavailables = sorted(set(locale_identifiers()) -
                              set(translation.get_available_locales())) or \
                       ('en_US',)
        locale_dir = self._get_locale_dir()
        translation.add_domain('catalog1', self.env.path, locale_dir)
        translation.add_domain('catalog2', self.env.path, locale_dir)
        translation.activate(unavailables[0], self.env.path)

    def test_activate_with_non_existent_catalogs(self):
        locales = self._get_available_locales()
        if locales:
            locale_dir = self._get_locale_dir()
            translation.add_domain('catalog1', self.env.path, locale_dir)
            translation.add_domain('catalog2', self.env.path, locale_dir)
            translation.activate(locales[0], self.env.path)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TranslationsProxyTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
