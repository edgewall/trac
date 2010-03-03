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
import shutil
import os.path


class EnvironmentsTestCase(unittest.TestCase):

    def setUp(self):
        self.parent_dir = tempfile.mkdtemp(prefix='trac-')
        for dname in ('mydir1', 'mydir2', '.hidden_dir'):
            os.mkdir(os.path.join(self.parent_dir, dname))
        for fname in ('myfile1', 'myfile2', '.dot_file'):
            create_file(os.path.join(self.parent_dir, fname))
        self.environ = {
           'trac.env_paths': [],
           'trac.env_parent_dir': self.parent_dir,
        }

    def tearDown(self):
        shutil.rmtree(self.parent_dir)

    def make_tracignore(self, patterns):
        create_file(os.path.join(self.parent_dir, '.tracignore'),
                    '\n'.join(patterns) + '\n')
        
    def env_paths(self, projects):
        return dict((project, os.path.normpath(os.path.join(self.parent_dir,
                                                            project)))
                    for project in projects)

    def test_default_tracignore(self):
        self.assertEquals(self.env_paths(['mydir1', 'mydir2']),
                          get_environments(self.environ))

    def test_empty_tracignore(self):
        self.make_tracignore([])
        self.assertEquals(self.env_paths(['mydir1', 'mydir2', '.hidden_dir']),
                          get_environments(self.environ))

    def test_qmark_pattern_tracignore(self):
        self.make_tracignore(['mydir?'])
        self.assertEquals(self.env_paths(['.hidden_dir']),
                          get_environments(self.environ))

    def test_star_pattern_tracignore(self):
        self.make_tracignore(['my*', '.hidden_dir'])
        self.assertEquals({}, get_environments(self.environ))
    
    def test_combined_tracignore(self):
        self.make_tracignore(['my*i?1', '', '#mydir2'])
        self.assertEquals(self.env_paths(['mydir2', '.hidden_dir']),
                          get_environments(self.environ))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(EnvironmentsTestCase, 'test'))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
