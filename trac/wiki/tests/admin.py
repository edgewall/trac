# -*- coding: utf-8 -*-
#
# Copyright (C) 2018-2023 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import os.path
import sys
import tempfile
import unittest

from trac.admin.api import console_datetime_format
from trac.admin.console import TracAdmin
from trac.admin.test import TracAdminTestCaseBase
from trac.test import EnvironmentStub, makeSuite, mkdtemp
from trac.tests.contentgen import random_unique_camel, random_paragraph
from trac.util import create_file
from trac.util.datefmt import format_datetime
from trac.wiki.admin import WikiAdmin
from trac.wiki.model import WikiPage


class WikiAdminTestCase(unittest.TestCase):

    page_text = 'Link to WikiStart'

    def setUp(self):
        self.env = EnvironmentStub()
        self.env.path = mkdtemp()
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
        with open(os.devnull, 'w', encoding='utf-8') as devnull:
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

    def test_import_page_replace(self):
        page = WikiPage(self.env, 'WritablePage')
        self.assertEqual(3, page.version)
        self.assertEqual(0, page.readonly)
        self.assertNotEqual(self.page_text, page.text)
        self._import_page(self.filename, 'WritablePage', replace=True)
        page = WikiPage(self.env, 'WritablePage')
        self.assertEqual(3, page.version)
        self.assertEqual(0, page.readonly)
        self.assertEqual(self.page_text, page.text)


class TracAdminTestCase(TracAdminTestCaseBase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True, enable=('trac.*',),
                                   disable=('trac.tests.*',))
        self.admin = TracAdmin()
        self.admin.env_set('', self.env)
        self.tempdir = mkdtemp()

    def tearDown(self):
        self.env = None

    def _insert_page(self, name=None):
        page = WikiPage(self.env)
        if name is None:
            name = random_unique_camel()
        page.name = name
        page.text = random_paragraph()
        page.save('user1', 'Page created.')
        return name

    def _insert_pages(self, int_or_names):
        if isinstance(int_or_names, int):
            names = sorted(random_unique_camel()
                           for _ in range(0, int_or_names))
        else:
            names = sorted(int_or_names)
        return [self._insert_page(n) for n in names]

    def _change_page(self, name):
        page = WikiPage(self.env, name)
        page.text = random_paragraph()
        page.save('user2', 'Page changed.')

    def _file_content(self, dir_or_path, name=None):
        path = dir_or_path if name is None else os.path.join(dir_or_path, name)
        with open(path, 'r') as f:
            return f.read()

    def _write_file(self, path, content=None):
        if content is None:
            content = random_paragraph()
        with open(path, 'w') as f:
            f.write(content)
        return content

    def execute(self, cmd, *args):
        argstr = ' '.join('"%s"' % a for a in args)
        return super().execute('wiki {} {}'.format(cmd, argstr))

    def assertFileContentMatchesPage(self, names):
        for n in names:
            self.assertEqual(WikiPage(self.env, n).text,
                             self._file_content(self.tempdir, n))

    def test_wiki_dump(self):
        names = self._insert_pages(2)
        rv, output = self.execute('dump', self.tempdir, *names)
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'name1': names[0],
            'name2': names[1],
            'path1': os.path.join(self.tempdir, names[0]),
            'path2': os.path.join(self.tempdir, names[1]),
        })
        self.assertFileContentMatchesPage(names)

    def test_wiki_dump_all(self):
        names = self._insert_pages(2)
        rv, output = self.execute('dump', self.tempdir)
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'name1': names[0],
            'name2': names[1],
            'path1': os.path.join(self.tempdir, names[0]),
            'path2': os.path.join(self.tempdir, names[1]),
        })
        self.assertEqual(names, sorted(os.listdir(self.tempdir)))
        self.assertFileContentMatchesPage(names)

    def test_wiki_dump_all_create_dst_dir(self):
        names = self._insert_pages(2)
        dstdir = os.path.join(self.tempdir, 'subdir')
        rv, output = self.execute('dump', dstdir)
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'name1': names[0],
            'name2': names[1],
            'path1': os.path.join(dstdir, names[0]),
            'path2': os.path.join(dstdir, names[1]),
        })
        self.assertEqual(names, sorted(os.listdir(dstdir)))

    def test_wiki_dump_all_glob(self):
        names = self._insert_pages(['PageOne', 'PageTwo', 'ThreePage'])
        rv, output = self.execute('dump', self.tempdir, 'Page*')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'name1': names[0],
            'name2': names[1],
            'path1': os.path.join(self.tempdir, names[0]),
            'path2': os.path.join(self.tempdir, names[1]),
        })
        self.assertEqual(names[0:2], sorted(os.listdir(self.tempdir)))
        self.assertFileContentMatchesPage(names[0:2])

    def test_wiki_dump_all_dst_is_file(self):
        tempdir = os.path.join(self.tempdir, 'dst')
        create_file(tempdir)
        rv, output = self.execute('dump', tempdir)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'dstdir': tempdir,
        })

    def test_wiki_export(self):
        name = self._insert_page()
        export_path = os.path.join(self.tempdir, name)
        rv, output = self.execute('export', name, export_path)
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'name': name,
            'path': export_path,
        })
        self.assertFileContentMatchesPage([name])

    def test_wiki_export_page_not_found(self):
        name = random_unique_camel()
        export_path = os.path.join(self.tempdir, name)
        rv, output = self.execute('export', name, export_path)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'name': name,
        })

    def test_wiki_export_file_exists(self):
        name = self._insert_page()
        export_path = os.path.join(self.tempdir, name)
        create_file(export_path)
        rv, output = self.execute('export', name, export_path)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'export_path': export_path,
        })

    def test_wiki_export_print_to_stdout(self):
        name = self._insert_page()
        rv, output = self.execute('export', name)
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'content': WikiPage(self.env, name).text,
        })

    def test_wiki_import(self):
        name = random_unique_camel()
        import_path = os.path.join(self.tempdir, name)
        content = self._write_file(import_path)
        rv, output = self.execute('import', name, import_path)
        page = WikiPage(self.env, name)
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'name': name,
            'path': import_path,
        })
        self.assertIn(('INFO', '%s imported from %s' % (name, import_path)),
                      self.env.log_messages)
        self.assertEqual(content, page.text)

    def test_wiki_import_page_exists(self):
        name = self._insert_page()
        import_path = os.path.join(self.tempdir, name)
        self._write_file(import_path)
        rv, output = self.execute('import', name, import_path)
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'name': name,
            'path': import_path,
        })
        self.assertEqual(2, WikiPage(self.env, name).version)

    def test_wiki_import_page_up_to_date(self):
        name = self._insert_page()
        import_path = os.path.join(self.tempdir, name)
        self._write_file(import_path, WikiPage(self.env, name).text)
        rv, output = self.execute('import', name, import_path)
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'tempdir': self.tempdir,
            'name': name,
        })
        self.assertIn(('INFO', '%s is already up to date' % name),
                      self.env.log_messages)
        self.assertEqual(1, WikiPage(self.env, name).version)

    def test_wiki_import_page_name_invalid(self):
        name = 'PageOne/../PageTwo'
        import_path = os.path.join(self.tempdir, 'PageOne')
        self._write_file(import_path)
        rv, output = self.execute('import', name, import_path)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'tempdir': self.tempdir,
            'name': name
        })
        self.assertFalse(WikiPage(self.env, name).exists)

    def test_wiki_import_file_not_found(self):
        name = random_unique_camel()
        import_path = os.path.join(self.tempdir, name)
        rv, output = self.execute('import', name, import_path)
        page = WikiPage(self.env, name)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'import_path': import_path,
        })

    def test_wiki_list(self):
        name1 = self._insert_page('PageOne')
        name2 = self._insert_page('PageTwo')
        self._change_page(name2)
        rv, output = self.execute('list')
        self.assertEqual(0, rv, output)
        fmt = lambda m: format_datetime(m, console_datetime_format)
        self.assertExpectedResult(output, {
            'page1_modified': fmt(WikiPage(self.env, name1).time),
            'page2_modified': fmt(WikiPage(self.env, name2).time),
        })

    def test_wiki_list_no_pages(self):
        rv, output = self.execute('list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_wiki_load(self):
        name1 = 'PageOne'
        name2 = 'PageTwo'
        path1 = os.path.join(self.tempdir, name1)
        path2 = os.path.join(self.tempdir, name2)
        content1 = random_paragraph()
        content2 = random_paragraph()
        with open(path1, 'w') as f:
            f.write(content1)
        with open(path2, 'w') as f:
            f.write(content2)
        rv, output = self.execute('load', path1, path2)
        page1 = WikiPage(self.env, name1)
        page2 = WikiPage(self.env, name2)
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'name1': name1,
            'name2': name2,
            'path1': path1,
            'path2': path2,
        })
        self.assertIn(('INFO', '%s imported from %s' % (name1, path1)),
                      self.env.log_messages)
        self.assertIn(('INFO', '%s imported from %s' % (name2, path2)),
                      self.env.log_messages)
        self.assertEqual(content1, page1.text)
        self.assertEqual(content2, page2.text)
        self.assertEqual(1, page1.version)
        self.assertEqual(1, page2.version)

    def test_wiki_load_page_exists(self):
        name = self._insert_page()
        path = os.path.join(self.tempdir, name)
        content = self._write_file(path)
        rv, output = self.execute('load', path)
        page = WikiPage(self.env, name)
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'name': name,
            'path': path,
        })
        self.assertEqual(content, page.text)
        self.assertEqual(2, page.version)

    def test_wiki_load_pages_from_dir(self):
        name1 = 'PageOne'
        name2 = 'PageTwo'
        path1 = os.path.join(self.tempdir, name1)
        path2 = os.path.join(self.tempdir, name2)
        content1 = random_paragraph()
        content2 = random_paragraph()
        with open(path1, 'w') as f:
            f.write(content1)
        with open(path2, 'w') as f:
            f.write(content2)
        os.mkdir(os.path.join(self.tempdir, 'subdir'))
        rv, output = self.execute('load', self.tempdir)
        page1 = WikiPage(self.env, name1)
        page2 = WikiPage(self.env, name2)
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'name1': name1,
            'name2': name2,
            'path1': path1,
            'path2': path2,
        })
        self.assertEqual(content1, page1.text)
        self.assertEqual(content2, page2.text)
        self.assertEqual(1, page1.version)
        self.assertEqual(1, page2.version)

    def test_wiki_load_from_invalid_path(self):
        name = random_unique_camel()
        path = os.path.join(self.tempdir, name)
        rv, output = self.execute('load', path)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'path': path,
        })
        self.assertFalse(WikiPage(self.env, name).exists)

    def test_wiki_remove(self):
        name = self._insert_page()

        rv, output = self.execute('remove', name)
        self.assertIn(('INFO', 'Deleted page %s' % name),
                      self.env.log_messages)
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'name': name,
        })
        self.assertFalse(WikiPage(self.env, name).exists)

    def test_wiki_remove_glob(self):
        names = self._insert_pages(['PageOne', 'PageTwo', 'PageThree'])

        rv, output = self.execute('remove', 'Page*')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)
        for n in names:
            self.assertIn(('INFO', 'Deleted page %s' % n),
                          self.env.log_messages)
            self.assertFalse(WikiPage(self.env, n).exists)

    def test_wiki_rename(self):
        name1 = self._insert_page()
        name2 = random_unique_camel()

        rv, output = self.execute('rename', name1, name2)
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'name1': name1,
            'name2': name2,
        })
        self.assertIn(('INFO', 'Renamed page %s to %s' % (name1, name2)),
                      self.env.log_messages)
        self.assertFalse(WikiPage(self.env, name1).exists)
        self.assertTrue(WikiPage(self.env, name2).exists)

    def test_wiki_rename_name_unchanged(self):
        name = self._insert_page()

        rv, output = self.execute('rename', name, name)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)
        self.assertTrue(WikiPage(self.env, name).exists)

    def test_wiki_rename_name_not_specified(self):
        name = self._insert_page()

        rv, output = self.execute('rename', name)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_wiki_rename_new_name_invalid(self):
        name = self._insert_page()
        new_name = 'PageOne/../PageTwo'

        rv, output = self.execute('rename', name, new_name)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'name': new_name,
        })
        self.assertTrue(WikiPage(self.env, name).exists)

    def test_wiki_rename_new_page_exists(self):
        names = self._insert_pages(['PageOne', 'PageTwo'])
        page1_content = WikiPage(self.env, names[0]).text
        page2_content = WikiPage(self.env, names[1]).text

        rv, output = self.execute('rename', *names)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)
        page1 = WikiPage(self.env, names[0])
        page2 = WikiPage(self.env, names[1])
        self.assertTrue(page1.exists)
        self.assertTrue(page2.exists)
        self.assertEqual(page1_content, page1.text)
        self.assertEqual(page2_content, page2.text)

    def test_wiki_replace(self):
        name1 = random_unique_camel()
        name2 = random_unique_camel()
        path1 = os.path.join(self.tempdir, name1)
        path2 = os.path.join(self.tempdir, name2)
        content1 = random_paragraph()
        content2 = random_paragraph()
        self._insert_page(name1)
        self._insert_page(name2)
        with open(path1, 'w') as f:
            f.write(content1)
        with open(path2, 'w') as f:
            f.write(content2)
        rv, output = self.execute('replace', path1, path2)
        page1 = WikiPage(self.env, name1)
        page2 = WikiPage(self.env, name2)
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'name1': name1,
            'name2': name2,
            'path1': path1,
            'path2': path2,
        })
        self.assertIn(('INFO', '%s imported from %s' % (name1, path1)),
                      self.env.log_messages)
        self.assertIn(('INFO', '%s imported from %s' % (name2, path2)),
                      self.env.log_messages)
        self.assertEqual(content1, page1.text)
        self.assertEqual(content2, page2.text)
        self.assertEqual(1, page1.version)
        self.assertEqual(1, page2.version)

    def test_wiki_replace_new_page(self):
        name = random_unique_camel()
        path = os.path.join(self.tempdir, name)
        content = self._write_file(path)
        rv, output = self.execute('replace', path)
        page = WikiPage(self.env, name)
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'name': name,
            'path': path,
        })
        self.assertEqual(1, page.version)
        self.assertEqual(content, page.text)

    def test_wiki_replace_pages_from_dir(self):
        names = self._insert_pages(2)
        path1 = os.path.join(self.tempdir, names[0])
        path2 = os.path.join(self.tempdir, names[1])
        content1 = random_paragraph()
        content2 = random_paragraph()
        with open(path1, 'w') as f:
            f.write(content1)
        with open(path2, 'w') as f:
            f.write(content2)
        os.mkdir(os.path.join(self.tempdir, 'subdir'))
        rv, output = self.execute('replace', self.tempdir)
        page1 = WikiPage(self.env, names[0])
        page2 = WikiPage(self.env, names[1])
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'name1': names[0],
            'name2': names[1],
            'path1': path1,
            'path2': path2,
        })
        self.assertEqual(content1, page1.text)
        self.assertEqual(content2, page2.text)
        self.assertEqual(1, page1.version)
        self.assertEqual(1, page2.version)

    def test_wiki_replace_from_invalid_path(self):
        name = random_unique_camel()
        path = os.path.join(self.tempdir, name)
        rv, output = self.execute('replace', path)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'path': path,
        })
        self.assertFalse(WikiPage(self.env, name).exists)

    def test_wiki_upgrade(self):
        rv, output = self.execute('upgrade')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_wiki_upgrade_up_to_date(self):
        self.execute('upgrade')
        rv, output = self.execute('upgrade')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(makeSuite(WikiAdminTestCase))
    suite.addTest(makeSuite(TracAdminTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
