# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os.path
import sys
import tempfile
import unittest

from trac.test import EnvironmentStub
from trac.util import create_file
from trac.wiki.model import WikiPage
from trac.wiki.admin import WikiAdmin


class WikiAdminTestCase(unittest.TestCase):

    page_text = 'Link to WikiStart'

    def setUp(self):
        self.env = EnvironmentStub()
        self.env.path = tempfile.mkdtemp(prefix='trac-tempenv-')
        self.tmpdir = os.path.join(self.env.path, 'tmp')
        os.mkdir(self.tmpdir)
        self.filename = os.path.join(self.tmpdir, 'file.txt')
        create_file(self.filename, self.page_text)
        self.admin = WikiAdmin(self.env)
        with self.env.db_transaction:
            for name, readonly in (('WritablePage', [0, 1, 0]),
                                   ('ReadOnlyPage', [1, 0, 1, 0, 1])):
                for r in readonly:
                    page = WikiPage(self.env, name)
                    page.text = '[wiki:%s@%d]' % (name, page.version + 1)
                    page.readonly = r
                    page.save('trac', '')

    def tearDown(self):
        self.env.reset_db_and_disk()

    def _import_page(self, *args, **kwargs):
        with open(os.devnull, 'wb') as devnull:
            stdout = sys.stdout
            try:
                sys.stdout = devnull
                self.admin.import_page(*args, **kwargs)
            finally:
                sys.stdout = stdout

    def test_import_page_new(self):
        self._import_page(self.filename, 'NewPage')
        page = WikiPage(self.env, 'NewPage')
        self.assertEqual('NewPage', page.name)
        self.assertEqual(1, page.version)
        self.assertEqual(self.page_text, page.text)
        self.assertEqual(0, page.readonly)

    def test_import_page_readonly(self):
        page = WikiPage(self.env, 'ReadOnlyPage')
        self.assertEqual(5, page.version)
        self.assertEqual(1, page.readonly)
        self.assertNotEqual(self.page_text, page.text)
        self._import_page(self.filename, 'ReadOnlyPage')
        page = WikiPage(self.env, 'ReadOnlyPage')
        self.assertEqual(6, page.version)
        self.assertEqual(1, page.readonly)
        self.assertEqual(self.page_text, page.text)

    def test_import_page_not_readonly(self):
        page = WikiPage(self.env, 'WritablePage')
        self.assertEqual(3, page.version)
        self.assertEqual(0, page.readonly)
        self.assertNotEqual(self.page_text, page.text)
        self._import_page(self.filename, 'WritablePage')
        page = WikiPage(self.env, 'WritablePage')
        self.assertEqual(4, page.version)
        self.assertEqual(0, page.readonly)
        self.assertEqual(self.page_text, page.text)

    def test_import_page_uptodate(self):
        page = WikiPage(self.env, 'WritablePage')
        self.assertEqual(3, page.version)
        self.assertEqual(0, page.readonly)
        create_file(self.filename, page.text)
        page_text = page.text
        self._import_page(self.filename, 'WritablePage')
        page = WikiPage(self.env, 'WritablePage')
        self.assertEqual(3, page.version)
        self.assertEqual(0, page.readonly)
        self.assertEqual(page_text, page.text)


def test_suite():
    return unittest.makeSuite(WikiAdminTestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
