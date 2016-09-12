# -*- coding: utf-8 -*-
#
# Copyright (C) 2016 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import unittest

from trac.db.schema import Column, Table


class TableTestCase(unittest.TestCase):

    def test_remove_columns(self):
        """Method removes columns and key entries from Table object."""
        table = Table('table1', key=['col1', 'col2'])[
            Column('col1'),
            Column('col2'),
            Column('col3'),
            Column('col4'),
        ]

        table.remove_columns(('col2', 'col3'))

        self.assertEqual(2, len(table.columns))
        self.assertEqual('col1', table.columns[0].name)
        self.assertEqual('col4', table.columns[1].name)
        self.assertEqual([], table.key)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TableTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
