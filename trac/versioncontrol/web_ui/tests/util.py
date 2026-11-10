# -*- coding: utf-8 -*-
#
# Copyright (C) 2014-2026 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.

from datetime import datetime
import io
import unittest
import zipfile

from trac.test import EnvironmentStub, Mock, MockRequest, makeSuite
from trac.util.datefmt import utc
from trac.versioncontrol.api import EmptyChangeset, NoSuchChangeset
from trac.versioncontrol.web_ui import util
from trac.web.api import RequestDone


class UtilTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def test_get_changes_raises_nosuchchangeset(self):
        def get_changeset(rev):
            raise NoSuchChangeset(rev)
        repos = Mock(get_changeset=lambda rev: get_changeset(rev))

        rev = 1
        changes = util.get_changes(repos, (rev, ))

        self.assertEqual(1, len(changes))
        self.assertIsInstance(changes[rev], EmptyChangeset)
        self.assertEqual(rev, changes[rev].rev)
        self.assertEqual(repos, changes[rev].repos)

    def test_render_zip(self):

        def get_content(content):
            content = io.BytesIO(content)
            return lambda **kwargs: content

        def get_properties(props):
            return lambda: props

        def mock_dir(path, mtime, props=None):
            return Mock(path=path, last_modified=mtime, isfile=False,
                        isdir=True, get_properties=get_properties(props or {}))

        def mock_file(path, mtime, content, props=None):
            return Mock(path=path, last_modified=mtime, isfile=True,
                        isdir=False,
                        get_processed_content=get_content(content),
                        get_properties=get_properties(props or {}))

        def iter_nodes(root_node):
            yield mock_dir('/trunk', mtime)
            yield mock_file('/trunk/file.sh', mtime, b'#!/bin/sh\n',
                            {'svn:executable': b'*'})
            yield mock_file('/trunk/Résumé.txt', mtime,
                            'link ../Résumé.txt'.encode('utf-8'),
                            {'svn:special': b''})

        mtime = datetime(2026, 11, 6, 2, 42, 24, 0, utc)
        req = MockRequest(self.env)
        try:
            util.render_zip(req, 'file.zip', None, None, iter_nodes)
        except RequestDone:
            pass
        else:
            self.fail('RequestDone not raised')
        with zipfile.ZipFile(io.BytesIO(req.response_sent.getvalue())) as z:
            self.assertEqual(['trunk/', 'trunk/file.sh', 'trunk/Résumé.txt'],
                             z.namelist())
            trunk = z.getinfo('trunk/')
            self.assertEqual(0o40755, (trunk.external_attr >> 16) & 0xffff)
            shell = z.getinfo('trunk/file.sh')
            self.assertEqual(0o755, (shell.external_attr >> 16) & 0xffff)
            symlink = z.getinfo('trunk/Résumé.txt')
            self.assertEqual(0o120644, (symlink.external_attr >> 16) & 0xffff)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(makeSuite(UtilTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
