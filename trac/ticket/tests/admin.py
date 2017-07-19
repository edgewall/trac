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

from trac.perm import PermissionError, PermissionSystem
from trac.resource import ResourceNotFound
from trac.test import EnvironmentStub, MockRequest
from trac.ticket.admin import ComponentAdminPanel, MilestoneAdminPanel, \
                              PriorityAdminPanel, ResolutionAdminPanel, \
                              SeverityAdminPanel, TicketTypeAdminPanel, \
                              VersionAdminPanel
from trac.ticket.model import Component, Milestone, Priority, Resolution,\
                              Severity, Type, Version
from trac.web.api import RequestDone


class BaseTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)

    def tearDown(self):
        self.env.reset_db()


class ComponentAdminPanelTestCase(BaseTestCase):

    def test_add_component(self):
        cap = ComponentAdminPanel(self.env)
        name, owner = 'component3', 'user3'
        req = MockRequest(self.env, method='POST',
                          args={'name': name, 'owner': owner, 'add': True})

        self.assertRaises(ResourceNotFound, Component, self.env, name)
        self.assertRaises(RequestDone, cap.render_admin_panel, req,
                          'ticket', 'component', None)
        component = Component(self.env, name)
        self.assertEqual(name, component.name)
        self.assertEqual(owner, component.owner)

    def test_remove_component(self):
        cap = ComponentAdminPanel(self.env)
        name = 'component2'
        req = MockRequest(self.env, method='POST',
                          args={'sel': name, 'remove': True})

        component = Component(self.env, name)
        self.assertEqual(name, component.name)
        self.assertEqual('somebody', component.owner)
        self.assertRaises(RequestDone, cap.render_admin_panel, req,
                          'ticket', 'component', None)
        self.assertRaises(ResourceNotFound, Component, self.env, name)

    def test_remove_multiple_components(self):
        cap = ComponentAdminPanel(self.env)
        names = ['component1', 'component2']
        req = MockRequest(self.env, method='POST',
                          args={'sel': names, 'remove': True})

        for name in names:
            component = Component(self.env, name)
            self.assertEqual(name, component.name)
            self.assertEqual('somebody', component.owner)
        self.assertRaises(RequestDone, cap.render_admin_panel, req,
                          'ticket', 'component', None)
        for name in names:
            self.assertRaises(ResourceNotFound, Component, self.env, name)

    def test_set_default_component(self):
        name = 'component2'
        config_key = 'default_component'
        cap = ComponentAdminPanel(self.env)

        req = MockRequest(self.env, method='POST',
                          args={'default': name, 'apply': True})
        self.assertRaises(RequestDone, cap.render_admin_panel, req,
                          'ticket', 'component', None)
        self.assertEqual(name, self.env.config.get('ticket', config_key))

    def test_remove_default_component(self):
        name = 'component2'
        cap = ComponentAdminPanel(self.env)
        config_key = 'default_component'
        self.env.config.set('ticket', config_key, name)

        req = MockRequest(self.env, method='POST',
                          args={'sel': name, 'remove': True})
        self.assertRaises(RequestDone, cap.render_admin_panel, req,
                          'ticket', 'component', None)
        self.assertEqual('', self.env.config.get('ticket', config_key))


class MilestoneAdminPanelTestCase(BaseTestCase):

    def test_add_milestone(self):
        name = 'milestone5'
        map = MilestoneAdminPanel(self.env)
        req = MockRequest(self.env, method='POST',
                          args={'name': name, 'add': True})

        self.assertRaises(ResourceNotFound, Milestone, self.env, name)
        self.assertRaises(RequestDone, map.render_admin_panel, req,
                          'ticket', 'milestone', None)
        milestone = Milestone(self.env, name)
        self.assertEqual(name, milestone.name)

    def test_set_default_milestone(self):
        """Set default milestone."""
        name = 'milestone2'
        config_key = 'default_milestone'
        PermissionSystem(self.env).grant_permission('user1', 'TICKET_ADMIN')
        req = MockRequest(self.env, authname='user1', method='POST',
                          args={'ticket_default': name, 'apply': True})

        self.assertEqual('', self.env.config.get('ticket', config_key))
        with self.assertRaises(RequestDone):
            MilestoneAdminPanel(self.env).render_admin_panel(
                req, 'ticket', 'milestone', None)
        self.assertEqual(name, self.env.config.get('ticket', config_key))

    def test_set_default_milestone_requires_ticket_admin(self):
        """Setting default milestone requires TICKET_ADMIN."""
        PermissionSystem(self.env).grant_permission('user1', 'MILESTONE_ADMIN')
        req = MockRequest(self.env, authname='user1', method='POST',
                          args={'ticket_default': 'milestone1', 'apply': True})

        self.assertNotIn('TICKET_ADMIN', req.perm)
        with self.assertRaises(PermissionError):
            MilestoneAdminPanel(self.env).render_admin_panel(
                req, 'ticket', 'milestone', None)

    def test_set_default_retarget_to(self):
        """Set default retarget milestone."""
        name = 'milestone2'
        config_key = 'default_retarget_to'
        PermissionSystem(self.env).grant_permission('user1', 'TICKET_ADMIN')
        req = MockRequest(self.env, authname='user1', method='POST',
                          args={'retarget_default': name, 'apply': True})

        self.assertEqual('', self.env.config.get('ticket', config_key))
        with self.assertRaises(RequestDone):
            MilestoneAdminPanel(self.env).render_admin_panel(
                req, 'ticket', 'milestone', None)
        self.assertEqual(name, self.env.config.get('milestone', config_key))

    def test_set_default_retarget_to_requires_ticket_admin(self):
        """Setting default retarget milestone requires TICKET_ADMIN."""
        PermissionSystem(self.env).grant_permission('user1', 'MILESTONE_ADMIN')
        req = MockRequest(self.env, authname='user1', method='POST',
                          args={'retarget_to': 'milestone1', 'apply': True})

        self.assertNotIn('TICKET_ADMIN', req.perm)
        with self.assertRaises(PermissionError):
            MilestoneAdminPanel(self.env).render_admin_panel(
                req, 'ticket', 'milestone', None)

    def test_remove_default_milestone(self):
        name = 'milestone2'
        map = MilestoneAdminPanel(self.env)
        self.env.config.set('ticket', 'default_milestone', 'milestone2')
        self.env.config.set('milestone', 'default_retarget_to', 'milestone2')

        req = MockRequest(self.env, method='POST',
                          args={'sel': name, 'remove': True})
        self.assertRaises(RequestDone, map.render_admin_panel, req,
                          'ticket', 'milestone', None)

        self.assertEqual('', self.env.config.get('ticket',
                                                 'default_milestone'))
        self.assertEqual('', self.env.config.get('milestone',
                                                 'default_retarget_to'))

    def test_default_view(self):
        panel = MilestoneAdminPanel(self.env)
        req = MockRequest(self.env)
        template, data = panel.render_admin_panel(req, 'ticket', 'milestone',
                                                  None)
        self.assertEqual('admin_milestones.html', template)
        self.assertEqual('list', data['view'])
        self.assertEqual('/trac.cgi/query?group=status&milestone=blah',
                         data['query_href']('blah'))

    def test_user_with_milestone_admin_can_view(self):
        """User with MILESTONE_ADMIN can view."""
        PermissionSystem(self.env).grant_permission('user1', 'MILESTONE_ADMIN')
        req = MockRequest(self.env, authname='user1')
        rv = MilestoneAdminPanel(self.env).get_admin_panels(req)
        self.assertEqual([('ticket', "Ticket System", 'milestones',
                           "Milestones")], list(rv))

    def test_user_with_ticket_admin_can_view(self):
        """User with MILESTONE_VIEW and TICKET_ADMIN can view."""
        PermissionSystem(self.env).grant_permission('user1', 'TICKET_ADMIN')
        req = MockRequest(self.env, authname='user1')
        rv = MilestoneAdminPanel(self.env).get_admin_panels(req)
        self.assertEqual([('ticket', "Ticket System", 'milestones',
                           "Milestones")], list(rv))

    def test_user_without_milestone_or_ticket_admin_cannot_view(self):
        """User without MILESTONE_ADMIN or TICKET_ADMIN cannot view."""
        req = MockRequest(self.env, authname='user1')
        rv = MilestoneAdminPanel(self.env).get_admin_panels(req)
        self.assertEqual([], list(rv))


class AbstractEnumTestCase(BaseTestCase):

    admin = None
    type = None
    cls = None

    def _test_add(self, name):
        req = MockRequest(self.env, method='POST',
                          args={'name': name, 'add': True})

        self.assertRaises(ResourceNotFound, self.cls, self.env, name)
        self.assertRaises(RequestDone, self.admin.render_admin_panel, req,
                          'ticket', self.type, None)
        item = self.cls(self.env, name)
        self.assertEqual(name, item.name)

    def _test_set_default(self, name):
        config_key = 'default_' + self.type
        req = MockRequest(self.env, method='POST',
                          args={'default': name, 'apply': True})
        for item in self.cls.select(self.env):
            req.args.update({'value_' + str(item.value): str(item.value)})

        self.assertRaises(RequestDone, self.admin.render_admin_panel, req,
                          'ticket', self.type, None)
        self.assertEqual(name, self.env.config.get('ticket', config_key))

    def _test_remove_default(self, name):
        config_key = 'default_' + self.type
        self.env.config.set('ticket', config_key, name)

        req = MockRequest(self.env, method='POST',
                          args={'sel': name, 'remove': True})

        self.assertRaises(RequestDone, self.admin.render_admin_panel, req,
                          'ticket', self.type, None)
        self.assertEqual('', self.env.config.get('ticket', config_key))

    def _test_edit_description(self, name):
        description = 'the edit'
        req = MockRequest(self.env, method='POST',
                          path_info='/admin/ticket/%s/%s' % (self.type, name),
                          args={'name': name, 'description': description,
                                'save': True})

        self.assertEqual(1, len(list(self.admin.get_admin_panels(req))))
        with self.assertRaises(RequestDone):
            self.admin.render_admin_panel(req, 'ticket', self.type, name)

        self.assertIn("Your changes have been saved",
                      unicode(req.chrome['notices']))
        self.assertEqual(description, self.cls(self.env, name).description)


class PriorityAdminPanelTestCase(AbstractEnumTestCase):

    type = 'priority'
    cls = Priority

    def setUp(self):
        super(PriorityAdminPanelTestCase, self).setUp()
        self.admin = PriorityAdminPanel(self.env)

    def test_add_priority(self):
        self._test_add('priority 1')

    def test_set_default_priority(self):
        self._test_set_default('critical')

    def test_remove_default_priority(self):
        self._test_remove_default('critical')

    def test_edit_description(self):
        self._test_edit_description('critical')


class ResolutionAdminPanelTestCase(AbstractEnumTestCase):

    type = 'resolution'
    cls = Resolution

    def setUp(self):
        super(ResolutionAdminPanelTestCase, self).setUp()
        self.admin = ResolutionAdminPanel(self.env)

    def test_add_resolution(self):
        self._test_add('resolution 1')

    def test_set_default_resolution(self):
        self._test_set_default('invalid')

    def test_remove_default_resolution(self):
        self._test_remove_default('invalid')

    def test_edit_description(self):
        self._test_edit_description('invalid')


class SeverityAdminPanelTestCase(AbstractEnumTestCase):

    type = 'severity'
    cls = Severity

    def setUp(self):
        super(SeverityAdminPanelTestCase, self).setUp()
        self.admin = SeverityAdminPanel(self.env)

    def _insert_severity(self):
        s = Severity(self.env)
        s.name = 'severity 1'
        s.insert()

    def test_add_severity(self):
        self._test_add('severity 1')

    def test_set_default_severity(self):
        self._insert_severity()
        self._test_set_default('severity 1')

    def test_remove_default_severity(self):
        self._insert_severity()
        self._test_remove_default('severity 1')

    def test_edit_description(self):
        self._insert_severity()
        self._test_edit_description('severity 1')


class TicketTypeAdminPanelTestCase(AbstractEnumTestCase):

    type = 'type'
    cls = Type

    def setUp(self):
        super(TicketTypeAdminPanelTestCase, self).setUp()
        self.admin = TicketTypeAdminPanel(self.env)

    def test_add_type(self):
        self._test_add('improvement')

    def test_set_default_type(self):
        self._test_set_default('task')

    def test_remove_default_type(self):
        self._test_remove_default('task')

    def test_edit_description(self):
        self._test_edit_description('task')


class VersionAdminPanelTestCase(BaseTestCase):

    def test_add_version(self):
        name = '3.0'
        ap = VersionAdminPanel(self.env)
        req = MockRequest(self.env, method='POST',
                          args={'name': name, 'add': True})

        self.assertRaises(ResourceNotFound, Version, self.env, name)
        self.assertRaises(RequestDone, ap.render_admin_panel, req,
                          'ticket', 'version', None)
        version = Version(self.env, name)
        self.assertEqual(name, version.name)

    def test_set_default_version(self):
        name = '1.0'
        ap = VersionAdminPanel(self.env)
        config_key = 'default_version'
        req = MockRequest(self.env, method='POST',
                          args={'default': name, 'apply': True})

        self.assertRaises(RequestDone, ap.render_admin_panel, req,
                          'ticket', 'version', None)
        self.assertEqual(name, self.env.config.get('ticket', config_key))

    def test_remove_default_version(self):
        name = '1.0'
        ap = VersionAdminPanel(self.env)
        config_key = 'default_version'
        self.env.config.set('ticket', config_key, name)

        req = MockRequest(self.env, method='POST',
                          args={'sel': name, 'remove': True})
        self.assertRaises(RequestDone, ap.render_admin_panel, req,
                          'ticket', 'version', None)
        self.assertEqual(self.env.config.get('ticket', config_key), '')


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ComponentAdminPanelTestCase))
    suite.addTest(unittest.makeSuite(MilestoneAdminPanelTestCase))
    suite.addTest(unittest.makeSuite(PriorityAdminPanelTestCase))
    suite.addTest(unittest.makeSuite(ResolutionAdminPanelTestCase))
    suite.addTest(unittest.makeSuite(SeverityAdminPanelTestCase))
    suite.addTest(unittest.makeSuite(TicketTypeAdminPanelTestCase))
    suite.addTest(unittest.makeSuite(VersionAdminPanelTestCase))

    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
