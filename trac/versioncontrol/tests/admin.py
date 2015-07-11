# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Edgewall Software
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

from trac.test import EnvironmentStub, Mock, MockPerm
from trac.util.datefmt import utc
from trac.versioncontrol.api import DbRepositoryProvider
from trac.versioncontrol.admin import RepositoryAdminPanel
from trac.web.href import Href


class VersionControlAdminTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def test_render_admin_with_alias_to_default_repos(self):
        db_provider = DbRepositoryProvider(self.env)
        db_provider.add_alias('', '')
        db_provider.add_alias('blah', '')
        panel = RepositoryAdminPanel(self.env)
        req = Mock(method='GET', chrome={}, args={}, session={},
                   abs_href=Href('/'), href=Href('/'), locale=None,
                   perm=MockPerm(), authname='anonymous', tz=utc)
        template, data = panel.render_admin_panel(req, 'versioncontrol',
                                                  'repository', '')
        repositories = data['repositories']
        self.assertEqual('', repositories['']['name'])
        self.assertEqual('', repositories['']['alias'])
        self.assertEqual('blah', repositories['blah']['name'])
        self.assertEqual('', repositories['blah']['alias'])


def suite():
    return unittest.makeSuite(VersionControlAdminTestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
