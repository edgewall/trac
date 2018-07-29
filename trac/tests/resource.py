# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import doctest
import unittest

from genshi.builder import tag
from trac import resource
from trac.core import Component, implements
from trac.test import EnvironmentStub, MockRequest
from trac.web.chrome import web_context


class ResourceTestCase(unittest.TestCase):

    def test_equals(self):
        # Plain equalities
        self.assertEqual(resource.Resource(), resource.Resource())
        self.assertEqual(resource.Resource(None), resource.Resource())
        self.assertEqual(resource.Resource('wiki'), resource.Resource('wiki'))
        self.assertEqual(resource.Resource('wiki', 'WikiStart'),
                         resource.Resource('wiki', 'WikiStart'))
        self.assertEqual(resource.Resource('wiki', 'WikiStart', 42),
                         resource.Resource('wiki', 'WikiStart', 42))
        # Inequalities
        self.assertNotEqual(resource.Resource('wiki', 'WikiStart', 42),
                            resource.Resource('wiki', 'WikiStart', 43))
        self.assertNotEqual(resource.Resource('wiki', 'WikiStart', 0),
                            resource.Resource('wiki', 'WikiStart', None))
        # Resource hierarchy
        r1 = resource.Resource('attachment', 'file.txt')
        r1.parent = resource.Resource('wiki', 'WikiStart')
        r2 = resource.Resource('attachment', 'file.txt')
        r2.parent = resource.Resource('wiki', 'WikiStart')
        self.assertEqual(r1, r2)
        r2.parent = r2.parent(version=42)
        self.assertNotEqual(r1, r2)


class RenderResourceLinkTestCase(unittest.TestCase):

    class FakeResourceManager(Component):
        implements(resource.IResourceManager)

        def get_resource_realms(self):
            yield 'fake'

        def resource_exists(self, resource):
            return False if resource.id == 'missing' else True

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.env.enable_component(self.FakeResourceManager)
        self.req = MockRequest(self.env)
        self.context = web_context(self.req)

    def tearDown(self):
        self.env.reset_db()

    def test_resource_exists_default_format(self):
        res = resource.Resource('fake', 'exists', version=1)
        link = resource.render_resource_link(self.env, self.context, res)
        html = tag.a('fake:exists',  class_='fake',
                     href='/trac.cgi/fake/exists?version=1')
        self.assertEqual(unicode(html), unicode(link))

    def test_resource_exists_summary_format(self):
        res = resource.Resource('fake', 'exists', version=1)
        link = resource.render_resource_link(self.env, self.context,
                                             res, 'summary')
        html = tag.a('fake:exists at version 1', class_='fake',
                     href='/trac.cgi/fake/exists?version=1')
        self.assertEqual(unicode(html), unicode(link))

    def test_resource_missing_default_format(self):
        res = resource.Resource('fake', 'missing', version=1)
        link = resource.render_resource_link(self.env, self.context, res)
        html = tag.a('fake:missing', class_='fake missing',
                     rel='nofollow', href='/trac.cgi/fake/missing?version=1')
        self.assertEqual(unicode(html), unicode(link))

    def test_resource_missing_summary_format(self):
        res = resource.Resource('fake', 'missing', version=1)
        link = resource.render_resource_link(self.env, self.context,
                                             res, 'summary')
        html = tag.a('fake:missing at version 1', class_='fake missing',
                     rel='nofollow', href='/trac.cgi/fake/missing?version=1')
        self.assertEqual(unicode(html), unicode(link))

    def test_resource_has_no_manager_default_format(self):
        res = resource.Resource('unmanaged', 'exists', version=1)
        link = resource.render_resource_link(self.env, self.context, res)
        html = tag.a('unmanaged:exists', class_='unmanaged',
                     href='/trac.cgi/unmanaged/exists?version=1')
        self.assertEqual(unicode(html), unicode(link))

    def test_resource_has_no_manager_summary_format(self):
        res = resource.Resource('unmanaged', 'exists', version=1)
        link = resource.render_resource_link(self.env, self.context,
                                             res, 'summary')
        html = tag.a('unmanaged:exists at version 1', class_='unmanaged',
                     href='/trac.cgi/unmanaged/exists?version=1')
        self.assertEqual(unicode(html), unicode(link))

def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(doctest.DocTestSuite(resource))
    suite.addTest(unittest.makeSuite(ResourceTestCase))
    suite.addTest(unittest.makeSuite(RenderResourceLinkTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
