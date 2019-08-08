# -*- coding: utf-8 -*-
#
# Copyright (C) 2016-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.

import copy
import unittest

from trac.db.api import DatabaseManager
from trac.db.schema import Column, Index, Table
from trac.test import EnvironmentStub, mkdtemp
from trac.upgrades import db42
from trac.util.datefmt import datetime_now, to_utimestamp, utc

VERSION = 42

old_attachment_schema = \
    Table('attachment', key=('type', 'id', 'filename'))[
        Column('type'),
        Column('id'),
        Column('filename'),
        Column('size', type='int'),
        Column('time', type='int64'),
        Column('description'),
        Column('author'),
        Column('ipnr')]

old_wiki_schema = \
    Table('wiki', key=('name', 'version'))[
        Column('name'),
        Column('version', type='int'),
        Column('time', type='int64'),
        Column('author'),
        Column('ipnr'),
        Column('text'),
        Column('comment'),
        Column('readonly', type='int'),
        Index(['time'])]
old_schema = (old_attachment_schema, old_wiki_schema)

new_attachment_schema = copy.deepcopy(old_attachment_schema)
new_attachment_schema.remove_columns(('ipnr',))
new_wiki_schema = copy.deepcopy(old_wiki_schema)
new_wiki_schema.remove_columns(('ipnr',))
new_schema = (new_attachment_schema, new_wiki_schema)


class UpgradeTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(path=mkdtemp())
        self.dbm = DatabaseManager(self.env)
        with self.env.db_transaction:
            self.dbm.drop_tables(new_schema)
            self.dbm.create_tables(old_schema)
            self.dbm.set_database_version(VERSION - 1)

    def tearDown(self):
        self.env.reset_db_and_disk()

    def test_attachment_table_upgraded(self):
        """The ipnr column is removed from the attachment table."""
        db42.do_upgrade(self.env, VERSION, None)

        column_names = [col.name for col in new_attachment_schema.columns]
        self.assertEqual(column_names, self.dbm.get_column_names('attachment'))

    def test_wiki_table_upgraded(self):
        """The ipnr column is removed from the wiki table."""
        db42.do_upgrade(self.env, VERSION, None)

        column_names = [col.name for col in new_wiki_schema.columns]
        self.assertEqual(column_names, self.dbm.get_column_names('wiki'))

    def test_attachments_data_migrated(self):
        """Attachment data is migrated on table upgrade."""
        now = to_utimestamp(datetime_now(utc))
        attachment_column_names = \
            [col.name for col in old_attachment_schema.columns]
        attachment_data = (
            ('ticket', '1', 'file1', 10, now, 'desc1', 'user1', '::1'),
            ('wiki', 'WikiStart', 'file2', 20, now, 'desc2', 'user2', '::2'))
        self.dbm.insert_into_tables((('attachment', attachment_column_names,
                                      attachment_data),))

        db42.do_upgrade(self.env, VERSION, None)

        ipnr_col = attachment_column_names.index('ipnr')
        i = 0
        for i, data in enumerate(self.env.db_query("""
                SELECT * FROM attachment ORDER BY type
                """)):
            self.assertEqual(attachment_data[i][:ipnr_col] +
                             attachment_data[i][ipnr_col+1:], data)
        self.assertEqual(len(attachment_data), i+1)

    def test_wiki_data_migrated(self):
        """Wiki data is migrated on table upgrade."""
        now = to_utimestamp(datetime_now(utc))
        wiki_column_names = \
            [col.name for col in old_wiki_schema.columns]
        wiki_data = (
            ('TracGuide', 2, now, 'user2', '::4', 'The guide', 'Edit', 0),
            ('WikiStart', 1, now, 'user1', '::3', 'The page', 'Init', 1))
        self.dbm.insert_into_tables((('wiki', wiki_column_names, wiki_data),))

        db42.do_upgrade(self.env, VERSION, None)

        ipnr_col = wiki_column_names.index('ipnr')
        i = 0
        for i, data in enumerate(self.env.db_query("""
                SELECT * FROM wiki ORDER BY name
                """)):
            self.assertEqual(wiki_data[i][:ipnr_col] +
                             wiki_data[i][ipnr_col+1:], data)
        self.assertEqual(len(wiki_data), i+1)


def test_suite():
    return unittest.makeSuite(UpgradeTestCase)

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
