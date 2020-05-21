# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2020 Edgewall Software
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

from trac.admin.web_ui import AdminModule
from trac.perm import PermissionError, PermissionSystem
from trac.resource import ResourceExistsError, ResourceNotFound
from trac.test import EnvironmentStub, MockRequest
from trac.ticket.admin import ComponentAdminPanel, MilestoneAdminPanel, \
                              PriorityAdminPanel, ResolutionAdminPanel, \
                              SeverityAdminPanel, TicketTypeAdminPanel, \
                              VersionAdminPanel
from trac.ticket.model import Component, Milestone, Priority, Resolution,\
                              Severity, Ticket, Type, Version
from trac.ticket.test import insert_ticket
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

        req = MockRequest(self.env, method='POST',
                          args={'name': ' component3 ', 'owner': owner,
                                'add': True})
        with self.assertRaises(ResourceExistsError) as cm:
            cap.render_admin_panel(req, 'ticket', 'component', None)
        self.assertIn('Component "component3" already exists',
                      unicode(cm.exception))

    def test_add_component_with_spaces(self):
        cap = ComponentAdminPanel(self.env)
        name = 'comp on ent 4'
        self.assertRaises(ResourceNotFound, Component, self.env, name)
        req = MockRequest(self.env, method='POST',
                          args={'name': ' comp \t on \t ent \t 4 ',
                                'owner': 'user4', 'add': True})
        self.assertRaises(RequestDone, cap.render_admin_panel, req,
                          'ticket', 'component', None)
        self.assertIn('The component "comp on ent 4" has been added.',
                      req.chrome['notices'])
        component = Component(self.env, name)
        self.assertEqual(name, component.name)
        with self.assertRaises(ResourceExistsError) as cm:
            cap.render_admin_panel(req, 'ticket', 'component', None)
        self.assertIn('Component "comp on ent 4" already exists',
                      unicode(cm.exception))

    def test_save_component(self):
        cap = ComponentAdminPanel(self.env)
        old_name = 'component2'
        old_owner = 'somebody'
        new_name = 'comp on ent 2'
        new_owner = 'user2'
        component = Component(self.env, old_name)
        self.assertEqual(old_name, component.name)
        self.assertEqual(old_owner, component.owner)

        req = MockRequest(self.env, method='POST',
                          args={'name': ' component1 ', 'owner': 'somebody',
                                'save': True})
        with self.assertRaises(ResourceExistsError) as cm:
            cap.render_admin_panel(req, 'ticket', 'component', old_name)
        self.assertIn('Component "component1" already exists',
                      unicode(cm.exception))

        req = MockRequest(self.env, method='POST',
                          args={'name': ' comp \t on \t ent \t 2 ',
                                'owner': new_owner, 'save': True})
        self.assertRaises(RequestDone, cap.render_admin_panel, req,
                          'ticket', 'component', old_name)
        self.assertIn('Your changes have been saved.', req.chrome['notices'])

        component = Component(self.env, new_name)
        self.assertEqual(new_name, component.name)
        self.assertEqual(new_owner, component.owner)
        self.assertRaises(ResourceNotFound, cap.render_admin_panel, req,
                          'ticket', 'component', old_name)
        self.assertRaises(ResourceNotFound, Component, self.env, old_name)

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
        self.assertIn('Your changes have been saved.', req.chrome['notices'])
        self.assertEqual([], req.chrome['warnings'])
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
        self.assertIn('Your changes have been saved.', req.chrome['notices'])
        self.assertEqual([], req.chrome['warnings'])
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

    def test_add_milestone_with_spaces(self):
        name = 'mile stone 5'
        map = MilestoneAdminPanel(self.env)
        req = MockRequest(self.env, method='POST',
                          args={'name': ' mile \t stone \t 5 ', 'add': True})

        self.assertRaises(ResourceNotFound, Milestone, self.env, name)
        self.assertRaises(RequestDone, map.render_admin_panel, req,
                          'ticket', 'milestone', None)
        self.assertIn('The milestone "mile stone 5" has been added.',
                      req.chrome['notices'])
        milestone = Milestone(self.env, name)
        self.assertEqual(name, milestone.name)

        with self.assertRaises(ResourceExistsError) as cm:
            map.render_admin_panel(req, 'ticket', 'milestone', None)
        self.assertIn('Milestone "mile stone 5" already exists',
                      unicode(cm.exception))

    def test_save_milestone(self):
        map = MilestoneAdminPanel(self.env)
        old_name = 'milestone2'
        new_name = 'mile stone 6'
        milestone = Milestone(self.env, old_name)
        self.assertEqual(old_name, milestone.name)

        req = MockRequest(self.env, method='POST',
                          args={'name': ' milestone1 ', 'save': True})
        with self.assertRaises(ResourceExistsError) as cm:
            map.render_admin_panel(req, 'ticket', 'milestone', old_name)
        self.assertIn('Milestone "milestone1" already exists',
                unicode(cm.exception))

        req = MockRequest(self.env, method='POST',
                          args={'name': ' mile \t stone \t 6 ', 'save': True})
        self.assertRaises(RequestDone, map.render_admin_panel, req,
                          'ticket', 'milestone', old_name)
        self.assertIn('Your changes have been saved.', req.chrome['notices'])

        milestone = Milestone(self.env, new_name)
        self.assertEqual(new_name, milestone.name)
        self.assertRaises(ResourceNotFound, map.render_admin_panel, req,
                          'ticket', 'milestone', old_name)
        self.assertRaises(ResourceNotFound, Milestone, self.env, old_name)

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
        self.assertIn('Your changes have been saved.', req.chrome['notices'])
        self.assertEqual([], req.chrome['warnings'])
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
        self.assertIn('Your changes have been saved.', req.chrome['notices'])
        self.assertEqual([], req.chrome['warnings'])
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

        self.assertIn('Your changes have been saved.', req.chrome['notices'])
        self.assertEqual([], req.chrome['warnings'])
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

    def test_complete_milestone_no_retarget(self):
        name = 'milestone1'
        insert_ticket(self.env, summary='Ticket 1', milestone=name)
        insert_ticket(self.env, summary='Ticket 2', milestone=name)
        ps = PermissionSystem(self.env)
        ps.grant_permission('user1', 'TICKET_ADMIN')
        ps.grant_permission('user1', 'MILESTONE_MODIFY')
        req = MockRequest(self.env, authname='user1', method='POST',
            path_info='/admin/ticket/milestones/%s' % name,
            args=dict(action='edit', save='Submit changes', name=name,
                      description='', comment='', completed='on',
                      completeddate='May 20, 2020, 9:07:52 PM'))

        mod = AdminModule(self.env)
        self.assertTrue(mod.match_request(req))
        with self.assertRaises(RequestDone):
            mod.process_request(req)

        self.assertEqual(1, len(req.chrome['notices']))
        self.assertEqual('Your changes have been saved.',
                         req.chrome['notices'][0])
        self.assertEqual([], req.chrome['warnings'])
        self.assertEqual(['303 See Other'], req.status_sent)
        self.assertEqual('http://example.org/trac.cgi/admin/ticket/milestones',
                         req.headers_sent['Location'])
        self.assertTrue(Milestone(self.env, name).is_completed)
        self.assertEqual(name, Ticket(self.env, 1)['milestone'])
        self.assertEqual(name, Ticket(self.env, 2)['milestone'])

    def test_complete_milestone_retarget_tickets(self):
        name = 'milestone1'
        target = 'milestone2'
        insert_ticket(self.env, summary='Ticket 1', milestone=name)
        insert_ticket(self.env, summary='Ticket 2', milestone=name)
        ps = PermissionSystem(self.env)
        ps.grant_permission('user1', 'TICKET_ADMIN')
        ps.grant_permission('user1', 'MILESTONE_MODIFY')
        req = MockRequest(self.env, authname='user1', method='POST',
            path_info='/admin/ticket/milestones/%s' % name,
            args=dict(action='edit', save='Submit changes', name=name,
                      description='', retarget='on', target=target,
                      comment='', completed='on',
                      completeddate='May 20, 2020, 9:07:52 PM'))

        mod = AdminModule(self.env)
        self.assertTrue(mod.match_request(req))
        with self.assertRaises(RequestDone):
            mod.process_request(req)

        self.assertEqual(2, len(req.chrome['notices']))
        self.assertEqual(
            'The open tickets associated with milestone "milestone1" '
            'have been retargeted to milestone "milestone2".',
            req.chrome['notices'][0])
        self.assertEqual('Your changes have been saved.',
                         req.chrome['notices'][1])
        self.assertEqual([], req.chrome['warnings'])
        self.assertEqual(['303 See Other'], req.status_sent)
        self.assertEqual('http://example.org/trac.cgi/admin/ticket/milestones',
                         req.headers_sent['Location'])
        self.assertTrue(Milestone(self.env, name).is_completed)
        self.assertEqual(target, Ticket(self.env, 1)['milestone'])
        self.assertEqual(target, Ticket(self.env, 2)['milestone'])


class AbstractEnumTestCase(BaseTestCase):

    admin = None
    type = None
    type_name = None
    cls = None

    def _test_add(self, name, norm_name=None):
        if norm_name is None:
            norm_name = name
        req = MockRequest(self.env, method='POST',
                          args={'name': name, 'add': True})

        self.assertRaises(ResourceNotFound, self.cls, self.env, norm_name)
        self.assertRaises(RequestDone, self.admin.render_admin_panel, req,
                          'ticket', self.type, None)
        self.assertIn('The %s value "%s" has been added.' %
                      (self.type_name, norm_name), req.chrome['notices'])
        item = self.cls(self.env, norm_name)
        self.assertEqual(norm_name, item.name)

    def _test_add_non_unique(self, name, norm_name=None):
        if norm_name is None:
            norm_name = name
        req = MockRequest(self.env, method='POST',
                          args={'name': name, 'add': True})

        with self.assertRaises(ResourceExistsError) as cm:
            self.admin.render_admin_panel(req, 'ticket', self.type, None)
        self.assertIn('%s value "%s" already exists' %
                      (self.type_name, norm_name), unicode(cm.exception))

    def _test_save(self, old_name, name, norm_name=None):
        if norm_name is None:
            norm_name = name
        req = MockRequest(self.env, method='POST',
                          args={'name': name, 'save': True})

        self.assertRaises(RequestDone, self.admin.render_admin_panel, req,
                          'ticket', self.type, old_name)
        item = self.cls(self.env, norm_name)
        self.assertEqual(norm_name, item.name)

    def _test_save_non_unique(self, old_name, name, norm_name=None):
        if norm_name is None:
            norm_name = name
        req = MockRequest(self.env, method='POST',
                          args={'name': name, 'save': True})
        with self.assertRaises(ResourceExistsError) as cm:
            self.admin.render_admin_panel(req, 'ticket', self.type, old_name)
        self.assertIn('value "%s" already exists' % norm_name,
                      unicode(cm.exception))

    def _test_set_default(self, name):
        config_key = 'default_' + self.type
        req = MockRequest(self.env, method='POST',
                          args={'default': name, 'apply': True})
        for item in self.cls.select(self.env):
            req.args.update({'value_' + str(item.value): str(item.value)})

        self.assertRaises(RequestDone, self.admin.render_admin_panel, req,
                          'ticket', self.type, None)
        self.assertIn('Your changes have been saved.', req.chrome['notices'])
        self.assertEqual([], req.chrome['warnings'])
        self.assertEqual(name, self.env.config.get('ticket', config_key))

    def _test_remove_default(self, name):
        config_key = 'default_' + self.type
        self.env.config.set('ticket', config_key, name)

        req = MockRequest(self.env, method='POST',
                          args={'sel': name, 'remove': True})

        self.assertRaises(RequestDone, self.admin.render_admin_panel, req,
                          'ticket', self.type, None)
        self.assertIn('The selected %s values have been removed.' %
                      self.type_name, req.chrome['notices'])
        self.assertEqual([], req.chrome['warnings'])
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
    type_name = 'Priority'
    cls = Priority

    def setUp(self):
        super(PriorityAdminPanelTestCase, self).setUp()
        self.admin = PriorityAdminPanel(self.env)

    def test_add_priority(self):
        self._test_add('priority 1')
        self._test_add(' prio \t rity \t 2 ', 'prio rity 2')
        self._test_add_non_unique('critical')
        self._test_add_non_unique(' priority \t 1 ', 'priority 1')

    def test_save_priority(self):
        self._test_save('critical', 'critical!!')
        self._test_save('critical!!', ' crit \t ical ', 'crit ical')
        self._test_save_non_unique('crit ical', 'blocker')
        self._test_save_non_unique('blocker', ' crit \t ical ', 'crit ical')

    def test_set_default_priority(self):
        self._test_set_default('critical')

    def test_remove_default_priority(self):
        self._test_remove_default('critical')

    def test_edit_description(self):
        self._test_edit_description('critical')


class ResolutionAdminPanelTestCase(AbstractEnumTestCase):

    type = 'resolution'
    type_name = 'Resolution'
    cls = Resolution

    def setUp(self):
        super(ResolutionAdminPanelTestCase, self).setUp()
        self.admin = ResolutionAdminPanel(self.env)

    def test_add_resolution(self):
        self._test_add('resolution 1')
        self._test_add(' resol \t ution 2 ', 'resol ution 2')
        self._test_add_non_unique('fixed')
        self._test_add_non_unique(' resolution \t 1 ', 'resolution 1')

    def test_save_resolution(self):
        ap = ResolutionAdminPanel(self.env)
        self._test_save('invalid', 'invalid!!')
        self._test_save('invalid!!', ' in \t valid ', 'in valid')
        self._test_save_non_unique('wontfix', 'fixed')
        self._test_save_non_unique('wontfix', ' in \t valid ', 'in valid')

    def test_set_default_resolution(self):
        self._test_set_default('invalid')

    def test_remove_default_resolution(self):
        self._test_remove_default('invalid')

    def test_edit_description(self):
        self._test_edit_description('invalid')


class SeverityAdminPanelTestCase(AbstractEnumTestCase):

    type = 'severity'
    type_name = 'Severity'
    cls = Severity

    def setUp(self):
        super(SeverityAdminPanelTestCase, self).setUp()
        self.admin = SeverityAdminPanel(self.env)

    def test_add_severity(self):
        self._test_add('severity 1')
        self._test_add(' seve  rity  2 ', 'seve rity 2')
        self._test_add_non_unique('severity 1')
        self._test_add_non_unique(' seve \t rity \t 2 ', 'seve rity 2')

    def test_save_severity(self):
        with self.env.db_transaction:
            self._insert_severity('severity 1')
            self._insert_severity('severity 2')
            self._insert_severity('severity 3')
            self._insert_severity('severity 4')
        self._test_save('severity 1', 'severity 42')
        self._test_save('severity 2', ' severity \t z ', 'severity z')
        self._test_save_non_unique('severity 3', 'severity 4')
        self._test_save_non_unique('severity 4', ' severity \t 3 ',
                                   'severity 3')

    def _insert_severity(self, name):
        s = Severity(self.env)
        s.name = name
        s.insert()

    def test_add_severity(self):
        self._test_add('severity 1')

    def test_set_default_severity(self):
        self._insert_severity('severity 1')
        self._test_set_default('severity 1')

    def test_remove_default_severity(self):
        self._insert_severity('severity 1')
        self._test_remove_default('severity 1')

    def test_edit_description(self):
        self._insert_severity('severity 1')
        self._test_edit_description('severity 1')


class TicketTypeAdminPanelTestCase(AbstractEnumTestCase):

    type = 'type'
    type_name = 'Ticket Type'
    cls = Type

    def setUp(self):
        super(TicketTypeAdminPanelTestCase, self).setUp()
        self.admin = TicketTypeAdminPanel(self.env)

    def test_add_type(self):
        self._test_add('improvement')
        self._test_add(' new \t feature ', 'new feature')
        self._test_add_non_unique('task')
        self._test_add_non_unique(' new \t feature ', 'new feature')

    def test_save_severity(self):
        self._test_save('defect', 'bug')
        self._test_save('task', ' new \t task ', 'new task')
        self._test_save_non_unique('bug', 'enhancement')
        self._test_save_non_unique('bug', ' new \t task ', 'new task')

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

    def test_add_version_with_spaces(self):
        name = '4.0 dev'
        ap = VersionAdminPanel(self.env)
        req = MockRequest(self.env, method='POST',
                          args={'name': ' 4.0 \t dev ', 'add': True})

        self.assertRaises(ResourceNotFound, Version, self.env, name)
        self.assertRaises(RequestDone, ap.render_admin_panel, req,
                          'ticket', 'version', None)
        self.assertIn('The version "4.0 dev" has been added.',
                      req.chrome['notices'])
        version = Version(self.env, name)
        self.assertEqual(name, version.name)

        with self.assertRaises(ResourceExistsError) as cm:
            ap.render_admin_panel(req, 'ticket', 'version', None)
        self.assertIn('Version "4.0 dev" already exists',
                      unicode(cm.exception))

    def test_save_version(self):
        ap = VersionAdminPanel(self.env)
        old_name = '2.0'
        new_name = '4.0 dev'
        version = Version(self.env, old_name)
        self.assertEqual(old_name, version.name)

        req = MockRequest(self.env, method='POST',
                          args={'name': ' 1.0 ', 'save': True})
        with self.assertRaises(ResourceExistsError) as cm:
            ap.render_admin_panel(req, 'ticket', 'version', old_name)
        self.assertIn('Version "1.0" already exists', unicode(cm.exception))

        req = MockRequest(self.env, method='POST',
                          args={'name': ' 4.0 \t dev ', 'save': True})
        self.assertRaises(RequestDone, ap.render_admin_panel, req,
                          'ticket', 'version', old_name)
        self.assertIn('Your changes have been saved.', req.chrome['notices'])

        version = Version(self.env, new_name)
        self.assertEqual(new_name, version.name)
        self.assertRaises(ResourceNotFound, ap.render_admin_panel, req,
                          'ticket', 'version', old_name)
        self.assertRaises(ResourceNotFound, Version, self.env, old_name)

    def test_set_default_version(self):
        name = '1.0'
        ap = VersionAdminPanel(self.env)
        config_key = 'default_version'
        req = MockRequest(self.env, method='POST',
                          args={'default': name, 'apply': True})

        self.assertRaises(RequestDone, ap.render_admin_panel, req,
                          'ticket', 'version', None)
        self.assertIn('Your changes have been saved.', req.chrome['notices'])
        self.assertEqual([], req.chrome['warnings'])
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
        self.assertIn('Your changes have been saved.', req.chrome['notices'])
        self.assertEqual([], req.chrome['warnings'])
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
