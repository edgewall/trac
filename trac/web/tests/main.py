# -*- coding: utf-8 -*-
#
# Copyright (C) 2010 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from trac.util import create_file
from trac.web.main import get_environments

import tempfile
import unittest
import os.path


class EnvironmentsTestCase(unittest.TestCase):

    dirs = ('mydir1', 'mydir2', '.hidden_dir')
    files = ('myfile1', 'myfile2', '.dot_file')

    def setUp(self):
        self.parent_dir = tempfile.mkdtemp(prefix='trac-')
        self.tracignore = os.path.join(self.parent_dir, '.tracignore')
        for dname in self.dirs:
            os.mkdir(os.path.join(self.parent_dir, dname))
        for fname in self.files:
            create_file(os.path.join(self.parent_dir, fname))
        self.environ = {
           'trac.env_paths': [],
           'trac.env_parent_dir': self.parent_dir,
        }

    def tearDown(self):
        for fname in self.files:
            os.unlink(os.path.join(self.parent_dir, fname))
        for dname in self.dirs:
            os.rmdir(os.path.join(self.parent_dir, dname))
        if os.path.exists(self.tracignore):
            os.unlink(self.tracignore)
        os.rmdir(self.parent_dir)

    def env_paths(self, projects):
        return dict((project, os.path.normpath(os.path.join(self.parent_dir,
                                                            project)))
                    for project in projects)

    def test_default_tracignore(self):
        self.assertEquals(self.env_paths(['mydir1', 'mydir2']),
                          get_environments(self.environ))

    def test_empty_tracignore(self):
        create_file(self.tracignore)
        self.assertEquals(self.env_paths(['mydir1', 'mydir2', '.hidden_dir']),
                          get_environments(self.environ))

    def test_qmark_pattern_tracignore(self):
        create_file(self.tracignore, 'mydir?')
        self.assertEquals(self.env_paths(['.hidden_dir']),
                          get_environments(self.environ))

    def test_star_pattern_tracignore(self):
        create_file(self.tracignore, 'my*\n.hidden_dir')
        self.assertEquals({}, get_environments(self.environ))
    
    def test_combined_tracignore(self):
        create_file(self.tracignore, 'my*i?1\n\n#mydir2')
        self.assertEquals(self.env_paths(['mydir2', '.hidden_dir']),
                          get_environments(self.environ))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(EnvironmentsTestCase, 'test'))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
