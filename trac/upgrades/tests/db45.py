# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import os
import unittest

from trac.config import UnicodeConfigParser
from trac.test import EnvironmentStub, mkdtemp
from trac.upgrades import db45


class UpgradeTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(path=mkdtemp())
        self.env.config.filename = os.path.join(self.env.path, 'trac.ini')

    def tearDown(self):
        self.env.reset_db_and_disk()

    def _backup_file_exists(self):
        return os.path.exists(os.path.join(self.env.path, 'trac.ini.db45.bak'))

    def test_templates_need_update_true(self):
        """Templates need to be updated."""
        self.env.config.set('notification', 'ticket_subject_template',
                            '$prefix #$ticket.id: $summary')
        self.env.config.set('notification', 'batch_subject_template',
                            '$prefix Batch modify: $tickets_descr')
        self.env.config.save()

        db45.do_upgrade(self.env, None, None)

        self.assertIn(('INFO',
                       'Replaced value of [notification] '
                       'ticket_subject_template: $prefix #$ticket.id: '
                       '$summary -> ${prefix} #${ticket.id}: ${summary}'),
                      self.env.log_messages)
        self.assertIn(('INFO',
                       'Replaced value of [notification] '
                       'batch_subject_template: $prefix Batch modify: '
                       '$tickets_descr -> ${prefix} Batch modify: '
                       '${tickets_descr}'),
                      self.env.log_messages)
        parser = UnicodeConfigParser()
        parser.read(self.env.config.filename)
        self.assertEqual('${prefix} #${ticket.id}: ${summary}',
                         parser.get('notification', 'ticket_subject_template'))
        self.assertEqual('${prefix} Batch modify: ${tickets_descr}',
                         parser.get('notification', 'batch_subject_template'))
        self.assertTrue(self._backup_file_exists())

    def test_templates_need_update_false(self):
        """Templates don't need to be updated."""
        self.env.config.set('notification', 'ticket_subject_template',
                            '${prefix} #${ticket.id}: ${summary}')
        self.env.config.set('notification', 'batch_subject_template',
                            '${prefix} Batch modify: ${tickets_descr}')
        self.env.config.save()

        db45.do_upgrade(self.env, None, None)

        self.assertEqual([], self.env.log_messages)
        self.assertFalse(self._backup_file_exists())


def test_suite():
    return unittest.makeSuite(UpgradeTestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
