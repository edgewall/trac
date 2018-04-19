# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Edgewall Software
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

from trac.core import TracError
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

        req = MockRequest(self.env, method='POST',
                          args={'name': ' component3 ', 'owner': owner,
                                'add': True})
        try:
            cap.render_admin_panel(req, 'ticket', 'component', None)
            self.fail('TracError not raised')
        except TracError as e:
            self.assertIn('Component "component3" already exists', unicode(e))

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
        try:
            cap.render_admin_panel(req, 'ticket', 'component', None)
            self.fail('TracError not raised')
        except TracError as e:
            self.assertIn('Component "comp on ent 4" already exists',
                          unicode(e))

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
        try:
            cap.render_admin_panel(req, 'ticket', 'component', old_name)
            self.fail('TracError not raised')
        except TracError as e:
            self.assertIn('Component "component1" already exists', unicode(e))

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

        try:
            map.render_admin_panel(req, 'ticket', 'milestone', None)
            self.fail('TracError not raised')
        except TracError as e:
            self.assertIn('Milestone "mile stone 5" already exists',
                          unicode(e))

    def test_save_milestone(self):
        map = MilestoneAdminPanel(self.env)
        old_name = 'milestone2'
        new_name = 'mile stone 6'
        milestone = Milestone(self.env, old_name)
        self.assertEqual(old_name, milestone.name)

        req = MockRequest(self.env, method='POST',
                          args={'name': ' milestone1 ', 'save': True})
        try:
            map.render_admin_panel(req, 'ticket', 'milestone', old_name)
            self.fail('TracError not raised')
        except TracError as e:
            self.assertIn('Milestone "milestone1" already exists', unicode(e))

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
        name = 'milestone2'
        config_key = 'default_milestone'
        map = MilestoneAdminPanel(self.env)
        req = MockRequest(self.env, method='POST',
                          args={'ticket_default': name, 'apply': True})

        self.assertRaises(RequestDone, map.render_admin_panel, req,
                          'ticket', 'milestone', None)
        self.assertIn('Your changes have been saved.', req.chrome['notices'])
        self.assertEqual([], req.chrome['warnings'])
        self.assertEqual(name, self.env.config.get('ticket', config_key))

    def test_set_default_retarget_to(self):
        name = 'milestone2'
        config_key = 'default_retarget_to'
        map = MilestoneAdminPanel(self.env)
        req = MockRequest(self.env, method='POST',
                          args={'retarget_default': name, 'apply': True})

        self.assertRaises(RequestDone, map.render_admin_panel, req,
                          'ticket', 'milestone', None)
        self.assertIn('Your changes have been saved.', req.chrome['notices'])
        self.assertEqual([], req.chrome['warnings'])
        self.assertEqual(name, self.env.config.get('milestone', config_key))

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


class AbstractEnumTestCase(BaseTestCase):

    type = None
    type_name = None
    cls = None

    def _test_add(self, panel, name, norm_name=None):
        if norm_name is None:
            norm_name = name
        req = MockRequest(self.env, method='POST',
                          args={'name': name, 'add': True})

        self.assertRaises(ResourceNotFound, self.cls, self.env, norm_name)
        self.assertRaises(RequestDone, panel.render_admin_panel, req,
                          'ticket', self.type, None)
        self.assertIn('The %s value "%s" has been added.' %
                      (self.type_name, norm_name), req.chrome['notices'])
        item = self.cls(self.env, norm_name)
        self.assertEqual(norm_name, item.name)

    def _test_add_non_unique(self, panel, name, norm_name=None):
        if norm_name is None:
            norm_name = name
        req = MockRequest(self.env, method='POST',
                          args={'name': name, 'add': True})

        try:
            panel.render_admin_panel(req, 'ticket', self.type, None)
            self.fail('TracError not raised')
        except TracError as e:
            self.assertIn('%s value "%s" already exists' %
                          (self.type_name, norm_name), unicode(e))

    def _test_save(self, panel, old_name, name, norm_name=None):
        if norm_name is None:
            norm_name = name
        req = MockRequest(self.env, method='POST',
                          args={'name': name, 'save': True})

        self.assertRaises(RequestDone, panel.render_admin_panel, req,
                          'ticket', self.type, old_name)
        item = self.cls(self.env, norm_name)
        self.assertEqual(norm_name, item.name)

    def _test_save_non_unique(self, panel, old_name, name, norm_name=None):
        if norm_name is None:
            norm_name = name
        req = MockRequest(self.env, method='POST',
                          args={'name': name, 'save': True})
        try:
            panel.render_admin_panel(req, 'ticket', self.type, old_name)
            self.fail('TracError not raised')
        except TracError as e:
            self.assertIn('value "%s" already exists' % norm_name, unicode(e))

    def _test_set_default(self, panel, name):
        config_key = 'default_' + self.type
        req = MockRequest(self.env, method='POST',
                          args={'default': name, 'apply': True})
        for item in self.cls.select(self.env):
            req.args.update({'value_' + str(item.value): str(item.value)})

        self.assertRaises(RequestDone, panel.render_admin_panel, req,
                          'ticket', self.type, None)
        self.assertIn('Your changes have been saved.', req.chrome['notices'])
        self.assertEqual([], req.chrome['warnings'])
        self.assertEqual(name, self.env.config.get('ticket', config_key))

    def _test_remove_default(self, panel, name):
        config_key = 'default_' + self.type
        self.env.config.set('ticket', config_key, name)

        req = MockRequest(self.env, method='POST',
                          args={'sel': name, 'remove': True})

        self.assertRaises(RequestDone, panel.render_admin_panel, req,
                          'ticket', self.type, None)
        self.assertIn('The selected %s values have been removed.' %
                      self.type_name, req.chrome['notices'])
        self.assertEqual([], req.chrome['warnings'])
        self.assertEqual('', self.env.config.get('ticket', config_key))


class PriorityAdminPanelTestCase(AbstractEnumTestCase):

    type = 'priority'
    type_name = 'Priority'
    cls = Priority

    def test_add_priority(self):
        ap = PriorityAdminPanel(self.env)
        self._test_add(ap, 'priority 1')
        self._test_add(ap, ' prio \t rity \t 2 ', 'prio rity 2')
        self._test_add_non_unique(ap, 'critical')
        self._test_add_non_unique(ap, ' priority \t 1 ', 'priority 1')

    def test_save_priority(self):
        ap = PriorityAdminPanel(self.env)
        self._test_save(ap, 'critical', 'critical!!')
        self._test_save(ap, 'critical!!', ' crit \t ical ', 'crit ical')
        self._test_save_non_unique(ap, 'crit ical', 'blocker')
        self._test_save_non_unique(ap, 'blocker',
                                   ' crit \t ical ', 'crit ical')

    def test_set_default_priority(self):
        ap = PriorityAdminPanel(self.env)
        self._test_set_default(ap, 'critical')

    def test_remove_default_priority(self):
        ap = PriorityAdminPanel(self.env)
        self._test_remove_default(ap, 'critical')


class ResolutionAdminPanelTestCase(AbstractEnumTestCase):

    type = 'resolution'
    type_name = 'Resolution'
    cls = Resolution

    def test_add_resolution(self):
        ap = ResolutionAdminPanel(self.env)
        self._test_add(ap, 'resolution 1')
        self._test_add(ap, ' resol \t ution 2 ', 'resol ution 2')
        self._test_add_non_unique(ap, 'fixed')
        self._test_add_non_unique(ap, ' resolution \t 1 ', 'resolution 1')

    def test_save_resolution(self):
        ap = ResolutionAdminPanel(self.env)
        self._test_save(ap, 'invalid', 'invalid!!')
        self._test_save(ap, 'invalid!!', ' in \t valid ', 'in valid')
        self._test_save_non_unique(ap, 'wontfix', 'fixed')
        self._test_save_non_unique(ap, 'wontfix', ' in \t valid ', 'in valid')

    def test_set_default_resolution(self):
        ap = ResolutionAdminPanel(self.env)
        self._test_set_default(ap, 'invalid')

    def test_remove_default_resolution(self):
        ap = ResolutionAdminPanel(self.env)
        self._test_remove_default(ap, 'invalid')


class SeverityAdminPanelTestCase(AbstractEnumTestCase):

    type = 'severity'
    type_name = 'Severity'
    cls = Severity

    def test_add_severity(self):
        ap = SeverityAdminPanel(self.env)
        self._test_add(ap, 'severity 1')
        self._test_add(ap, ' seve  rity  2 ', 'seve rity 2')
        self._test_add_non_unique(ap, 'severity 1')
        self._test_add_non_unique(ap, ' seve \t rity \t 2 ', 'seve rity 2')

    def test_save_severity(self):
        self.env.db_transaction.executemany("""
            INSERT INTO enum (type, name, value) VALUES ('severity',%s,%s)
            """, [('severity 1', 1), ('severity 2', 2),
                  ('severity 3', 3), ('severity 4', 4)])
        ap = SeverityAdminPanel(self.env)
        self._test_save(ap, 'severity 1', 'severity 42')
        self._test_save(ap, 'severity 2', ' severity \t z ', 'severity z')
        self._test_save_non_unique(ap, 'severity 3', 'severity 4')
        self._test_save_non_unique(ap, 'severity 4', ' severity \t 3 ',
                                   'severity 3')

    def test_set_default_severity(self):
        s = Severity(self.env)
        s.name = 'severity 1'
        s.insert()
        ap = SeverityAdminPanel(self.env)
        self._test_set_default(ap, 'severity 1')

    def test_remove_default_severity(self):
        s = Severity(self.env)
        s.name = 'severity 1'
        s.insert()
        ap = SeverityAdminPanel(self.env)
        self._test_remove_default(ap, 'severity 1')


class TicketTypeAdminPanelTestCase(AbstractEnumTestCase):

    type = 'type'
    type_name = 'Ticket Type'
    cls = Type

    def test_add_type(self):
        ap = TicketTypeAdminPanel(self.env)
        self._test_add(ap, 'improvement')
        self._test_add(ap, ' new \t feature ', 'new feature')
        self._test_add_non_unique(ap, 'task')
        self._test_add_non_unique(ap, ' new \t feature ', 'new feature')

    def test_save_severity(self):
        ap = TicketTypeAdminPanel(self.env)
        self._test_save(ap, 'defect', 'bug')
        self._test_save(ap, 'task', ' new \t task ', 'new task')
        self._test_save_non_unique(ap, 'bug', 'enhancement')
        self._test_save_non_unique(ap, 'bug', ' new \t task ', 'new task')

    def test_set_default_type(self):
        ap = TicketTypeAdminPanel(self.env)
        self._test_set_default(ap, 'task')

    def test_remove_default_type(self):
        ap = TicketTypeAdminPanel(self.env)
        self._test_remove_default(ap, 'task')


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

        try:
            ap.render_admin_panel(req, 'ticket', 'version', None)
            self.fail('TracError not raised')
        except TracError as e:
            self.assertIn('Version "4.0 dev" already exists', unicode(e))

    def test_save_version(self):
        ap = VersionAdminPanel(self.env)
        old_name = '2.0'
        new_name = '4.0 dev'
        version = Version(self.env, old_name)
        self.assertEqual(old_name, version.name)

        req = MockRequest(self.env, method='POST',
                          args={'name': ' 1.0 ', 'save': True})
        try:
            ap.render_admin_panel(req, 'ticket', 'version', old_name)
            self.fail('TracError not raised')
        except TracError as e:
            self.assertIn('Version "1.0" already exists', unicode(e))

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
