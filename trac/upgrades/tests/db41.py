# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

import os
import tempfile
import unittest

from trac.test import EnvironmentStub
from trac.upgrades import db41

VERSION = 41


class UpgradeTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True, path=tempfile.mkdtemp())
        self.env.config.filename = os.path.join(self.env.path, 'trac.ini')

    def tearDown(self):
        self.env.reset_db_and_disk()

    def test_saves_backup(self):
        config = self.env.config
        db41.do_upgrade(self.env, VERSION, None)

        self.assertTrue(os.path.exists(config.filename + '.db41.bak'))

    def test_default_ordering(self):
        config = self.env.config
        db41.do_upgrade(self.env, VERSION, None)

        self.assertEqual(1.0, config.getfloat('mainnav', 'wiki.order'))
        self.assertEqual(2.0, config.getfloat('mainnav', 'timeline.order'))
        self.assertEqual(3.0, config.getfloat('mainnav', 'roadmap.order'))
        self.assertEqual(4.0, config.getfloat('mainnav', 'browser.order'))
        self.assertEqual(5.0, config.getfloat('mainnav', 'tickets.order'))
        self.assertEqual(6.0, config.getfloat('mainnav', 'newticket.order'))
        self.assertEqual(7.0, config.getfloat('mainnav', 'search.order'))
        self.assertEqual(8.0, config.getfloat('mainnav', 'admin.order'))
        self.assertEqual(1.0, config.getfloat('metanav', 'login.order'))
        self.assertEqual(2.0, config.getfloat('metanav', 'logout.order'))
        self.assertEqual(3.0, config.getfloat('metanav', 'prefs.order'))
        self.assertEqual(4.0, config.getfloat('metanav', 'help.order'))
        self.assertEqual(5.0, config.getfloat('metanav', 'about.order'))
        self.assertIsNone(config.get('trac', 'mainnav', None))
        self.assertIsNone(config.get('trac', 'metanav', None))

    def test_nondefault_ordering(self):
        config = self.env.config
        config.set('trac', 'mainnav', 'search, newticket, tickets, browser, '
                                      'roadmap, timeline, wiki')
        config.set('trac', 'metanav', 'about, help, prefs, logout, login')
        db41.do_upgrade(self.env, VERSION, None)

        self.assertEqual(1.0, config.getfloat('mainnav', 'search.order'))
        self.assertEqual(2.0, config.getfloat('mainnav', 'newticket.order'))
        self.assertEqual(3.0, config.getfloat('mainnav', 'tickets.order'))
        self.assertEqual(4.0, config.getfloat('mainnav', 'browser.order'))
        self.assertEqual(5.0, config.getfloat('mainnav', 'roadmap.order'))
        self.assertEqual(6.0, config.getfloat('mainnav', 'timeline.order'))
        self.assertEqual(7.0, config.getfloat('mainnav', 'wiki.order'))
        self.assertEqual(-1, config.getfloat('mainnav', 'admin.order', -1))
        self.assertEqual(1.0, config.getfloat('metanav', 'about.order'))
        self.assertEqual(2.0, config.getfloat('metanav', 'help.order'))
        self.assertEqual(3.0, config.getfloat('metanav', 'prefs.order'))
        self.assertEqual(4.0, config.getfloat('metanav', 'logout.order'))
        self.assertEqual(5.0, config.getfloat('metanav', 'login.order'))
        self.assertIsNone(config.get('trac', 'mainnav', None))
        self.assertIsNone(config.get('trac', 'metanav', None))


def test_suite():
    return unittest.makeSuite(UpgradeTestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
