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

import unittest

from trac.upgrades import db44


class UpgradeTestCase(unittest.TestCase):

    def test_replace_sql_fragment(self):
        fragments = [(" description AS _description, ",
                      " t.description AS _description, "),
                     (" description AS _description_, ",
                      " t.description AS _description_, "),
                     (" t.description AS _description,",
                      None)]
        for query, expected in fragments:
            self.assertEqual(expected, db44.replace_sql_fragment(query))


def test_suite():
    return unittest.makeSuite(UpgradeTestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
