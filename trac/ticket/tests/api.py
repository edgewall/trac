# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from datetime import timedelta

from trac.perm import PermissionCache, PermissionSystem
from trac.resource import Resource
from trac.test import EnvironmentStub, MockRequest
from trac.ticket import model
from trac.ticket.api import TicketSystem
from trac.ticket.model import Milestone, Ticket, Version
from trac.util.datefmt import datetime_now, utc

import unittest


class TicketSystemTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.perm = PermissionSystem(self.env)
        self.ticket_system = TicketSystem(self.env)
        self.req = MockRequest(self.env)

    def tearDown(self):
        self.env.reset_db()

    def _get_actions(self, ticket_dict):
        ts = TicketSystem(self.env)
        ticket = Ticket(self.env)
        ticket.populate(ticket_dict)
        id = ticket.insert()
        return ts.get_available_actions(self.req, Ticket(self.env, id))

    def _get_ticket_field(self, field_name):
        fields = TicketSystem(self.env).get_ticket_fields()
        return (i for i in fields if i['name'] == field_name).next()

    def test_custom_field_text(self):
        self.env.config.set('ticket-custom', 'test', 'text')
        self.env.config.set('ticket-custom', 'test.label', 'Test')
        self.env.config.set('ticket-custom', 'test.value', 'Foo bar')
        self.env.config.set('ticket-custom', 'test.format', 'wiki')
        fields = TicketSystem(self.env).get_custom_fields()
        self.assertEqual({'name': 'test', 'type': 'text', 'label': 'Test',
                          'value': 'Foo bar', 'order': 0, 'format': 'wiki',
                          'custom': True},
                         fields[0])

    def test_custom_field_select(self):
        self.env.config.set('ticket-custom', 'test', 'select')
        self.env.config.set('ticket-custom', 'test.label', 'Test')
        self.env.config.set('ticket-custom', 'test.value', '1')
        self.env.config.set('ticket-custom', 'test.options', 'option1|option2')
        fields = TicketSystem(self.env).get_custom_fields()
        self.assertEqual({'name': 'test', 'type': 'select', 'label': 'Test',
                          'value': '1', 'options': ['option1', 'option2'],
                          'order': 0, 'custom': True},
                         fields[0])

    def test_custom_field_optional_select(self):
        self.env.config.set('ticket-custom', 'test', 'select')
        self.env.config.set('ticket-custom', 'test.label', 'Test')
        self.env.config.set('ticket-custom', 'test.value', '1')
        self.env.config.set('ticket-custom', 'test.options', '|option1|option2')
        fields = TicketSystem(self.env).get_custom_fields()
        self.assertEqual({'name': 'test', 'type': 'select', 'label': 'Test',
                          'value': '1', 'options': ['option1', 'option2'],
                          'order': 0, 'optional': True, 'custom': True},
                         fields[0])

    def test_custom_field_textarea(self):
        self.env.config.set('ticket-custom', 'test', 'textarea')
        self.env.config.set('ticket-custom', 'test.label', 'Test')
        self.env.config.set('ticket-custom', 'test.value', 'Foo bar')
        self.env.config.set('ticket-custom', 'test.rows', '4')
        self.env.config.set('ticket-custom', 'test.format', 'wiki')
        fields = TicketSystem(self.env).get_custom_fields()
        self.assertEqual({'name': 'test', 'type': 'textarea', 'label': 'Test',
                          'value': 'Foo bar', 'height': 4, 'order': 0,
                          'format': 'wiki', 'custom': True},
                         fields[0])

    def test_description_field(self):
        field = self._get_ticket_field('description')
        self.assertEqual({'name': 'description', 'label': 'Description',
                          'type': 'textarea', 'format': 'wiki'},
                          field)

    def test_custom_field_checkbox(self):
        def add_checkbox(name, value):
            self.env.config.set('ticket-custom', name, 'checkbox')
            self.env.config.set('ticket-custom', '%s.value' % name, value)

        add_checkbox('checkbox0', 'true')
        add_checkbox('checkbox1', 1)
        add_checkbox('checkbox2', 'enabled')
        add_checkbox('checkbox3', 0)
        add_checkbox('checkbox4', 'tru')
        add_checkbox('checkbox5', 'off')

        fields = TicketSystem(self.env).get_custom_fields()
        self.assertEqual({'name': 'checkbox0', 'type': 'checkbox',
                          'label': 'Checkbox0', 'value': '1',
                          'order': 0, 'custom': True},
                         fields[0])
        self.assertEqual('1', fields[1]['value'])
        self.assertEqual('1', fields[2]['value'])
        self.assertEqual('0', fields[3]['value'])
        self.assertEqual('0', fields[4]['value'])
        self.assertEqual('0', fields[5]['value'])

    def test_custom_field_time(self):
        self.env.config.set('ticket-custom', 'test', 'time')
        self.env.config.set('ticket-custom', 'test.label', 'Test')
        self.env.config.set('ticket-custom', 'test.value', '')
        fields = TicketSystem(self.env).get_custom_fields()
        self.assertEqual({'name': 'test', 'type': 'time', 'label': 'Test',
                          'value': '', 'order': 0, 'format': 'datetime',
                          'custom': True},
                         fields[0])

    def test_custom_field_with_invalid_name(self):
        ticket_custom = self.env.config['ticket-custom']
        ticket_custom.set('_field1', 'text')
        ticket_custom.set('2field', 'text')
        ticket_custom.set('f3%^&*', 'text')
        ticket_custom.set('field4', 'text')
        ticket_custom.set('FiEld5', 'text')

        ts = TicketSystem(self.env)

        self.assertEqual(2, len(ts.custom_fields))
        self.assertIsNotNone(ts.custom_fields.by_name('field4'))
        self.assertIsNotNone(ts.custom_fields.by_name('field5'))
        self.assertIsNotNone(ts.fields.by_name('field4'))
        self.assertIsNotNone(ts.fields.by_name('field5'))

    def test_custom_field_with_reserved_name(self):
        ticket_custom = self.env.config['ticket-custom']
        ticket_custom.set('owner', 'select')
        ticket_custom.set('description', 'text')

        ts = TicketSystem(self.env)

        self.assertEqual({'name': 'owner', 'label': 'Owner', 'type': 'text'},
                         ts.fields.by_name('owner'))
        self.assertEqual({'name': 'description', 'label': 'Description',
                          'type': 'textarea', 'format': 'wiki'},
                         ts.fields.by_name('description'))
        self.assertIsNone(ts.custom_fields.by_name('owner'))
        self.assertIsNone(ts.custom_fields.by_name('description'))

    def test_custom_field_order(self):
        self.env.config.set('ticket-custom', 'test1', 'text')
        self.env.config.set('ticket-custom', 'test1.order', '2')
        self.env.config.set('ticket-custom', 'test2', 'text')
        self.env.config.set('ticket-custom', 'test2.order', '1')
        fields = TicketSystem(self.env).get_custom_fields()
        self.assertEqual('test2', fields[0]['name'])
        self.assertEqual('test1', fields[1]['name'])

    def test_custom_field_label(self):
        self.env.config.set('ticket-custom', 'test_one', 'text')
        self.env.config.set('ticket-custom', 'test_two', 'text')
        self.env.config.set('ticket-custom', 'test_two.label', 'test_2')
        fields = TicketSystem(self.env).get_custom_fields()
        self.assertEqual('Test one', fields[0]['label'])
        self.assertEqual('test_2', fields[1]['label'])

    def _test_custom_field_with_enum(self, name, cls):
        tktsys = TicketSystem(self.env)
        instance = cls(self.env)
        instance.name = '%s 42' % name
        instance.insert()
        self.env.config.set('ticket-custom', name, 'text')
        field = self._get_ticket_field(name)
        self.assertFalse(field.get('custom'))

        with self.env.db_transaction:
            instances = list(cls.select(self.env))
            if issubclass(cls, model.AbstractEnum):
                # delete from highest to lowest to avoid re-ordering enums
                instances.sort(reverse=True, key=lambda v: int(v.value))
            for instance in instances:
                instance.delete()
        field = self._get_ticket_field(name)
        self.assertTrue(field.get('custom'))

    def test_custom_field_type(self):
        self._test_custom_field_with_enum('type', model.Type)

    def test_custom_field_priority(self):
        self._test_custom_field_with_enum('priority', model.Priority)

    def test_custom_field_milestone(self):
        self._test_custom_field_with_enum('milestone', Milestone)

    def test_custom_field_component(self):
        self._test_custom_field_with_enum('component', model.Component)

    def test_custom_field_version(self):
        self._test_custom_field_with_enum('version', Version)

    def test_custom_field_severity(self):
        self._test_custom_field_with_enum('severity', model.Severity)

    def test_custom_field_resolution(self):
        self._test_custom_field_with_enum('resolution', model.Resolution)

    def test_available_actions_full_perms(self):
        self.perm.grant_permission('anonymous', 'TICKET_CREATE')
        self.perm.grant_permission('anonymous', 'TICKET_MODIFY')
        self.req.perm = PermissionCache(self.env)
        self.assertEqual(['leave', 'resolve', 'reassign', 'accept'],
                         self._get_actions({'status': 'new'}))
        self.assertEqual(['leave', 'resolve', 'reassign', 'accept'],
                         self._get_actions({'status': 'assigned'}))
        self.assertEqual(['leave', 'resolve', 'reassign', 'accept'],
                         self._get_actions({'status': 'accepted'}))
        self.assertEqual(['leave', 'resolve', 'reassign', 'accept'],
                         self._get_actions({'status': 'reopened'}))
        self.assertEqual(['leave', 'reopen'],
                         self._get_actions({'status': 'closed'}))

    def test_available_actions_no_perms(self):
        self.req.perm = PermissionCache(self.env)
        self.assertEqual(['leave'], self._get_actions({'status': 'new'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'assigned'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'accepted'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'reopened'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'closed'}))

    def test_available_actions_create_only(self):
        self.perm.grant_permission('anonymous', 'TICKET_CREATE')
        self.req.perm = PermissionCache(self.env)
        self.assertEqual(['leave'], self._get_actions({'status': 'new'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'assigned'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'accepted'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'reopened'}))
        self.assertEqual(['leave', 'reopen'],
                         self._get_actions({'status': 'closed'}))

    def test_available_actions_chgprop_only(self):
        # CHGPROP is not enough for changing a ticket's state (#3289)
        self.perm.grant_permission('anonymous', 'TICKET_CHGPROP')
        self.req.perm = PermissionCache(self.env)
        self.assertEqual(['leave'], self._get_actions({'status': 'new'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'assigned'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'accepted'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'reopened'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'closed'}))

    def test_get_allowed_owners_restrict_owner_false(self):
        self.env.config.set('ticket', 'restrict_owner', False)
        self.assertIsNone(self.ticket_system.get_allowed_owners())

    def test_get_allowed_owners_restrict_owner_true(self):
        self.env.config.set('ticket', 'restrict_owner', True)
        self.env.insert_users([('user3', None, None),
                               ('user1', None, None)])
        self.perm.grant_permission('user4', 'TICKET_MODIFY')
        self.perm.grant_permission('user3', 'TICKET_MODIFY')
        self.perm.grant_permission('user2', 'TICKET_VIEW')
        self.perm.grant_permission('user1', 'TICKET_MODIFY')
        self.assertEqual(['user1', 'user3'],
                         self.ticket_system.get_allowed_owners())

    def test_get_ticket_fields_version_rename(self):
        """Cached ticket fields are updated when version is renamed."""
        fields = self.ticket_system.get_ticket_fields()
        version_field = self._get_ticket_field('version')
        v2 = Version(self.env, '2.0')
        v2.name = '0.0'
        v2.update()
        updated_fields = self.ticket_system.get_ticket_fields()
        updated_version_field = self._get_ticket_field('version')

        self.assertNotEqual(fields, updated_fields)
        self.assertEqual(['2.0', '1.0'], version_field['options'])
        self.assertEqual(['1.0', '0.0'], updated_version_field['options'])

    def test_get_ticket_fields_version_update_time(self):
        """Cached ticket fields are updated when version release time
        is changed.
        """
        fields = self.ticket_system.get_ticket_fields()
        version_field = self._get_ticket_field('version')
        v1 = Version(self.env, '1.0')
        v1.time = datetime_now(utc)
        v2 = Version(self.env, '2.0')
        v2.time = v1.time - timedelta(seconds=1)

        v1.update()
        v2.update()
        updated_fields = self.ticket_system.get_ticket_fields()
        updated_version_field = self._get_ticket_field('version')

        self.assertNotEqual(fields, updated_fields)
        self.assertEqual(['2.0', '1.0'], version_field['options'])
        self.assertEqual(['1.0', '2.0'], updated_version_field['options'])

    def test_get_ticket_fields_milestone_rename(self):
        """Cached ticket fields are updated when milestone is renamed."""
        fields = self.ticket_system.get_ticket_fields()
        milestone_field = self._get_ticket_field('milestone')
        m2 = Milestone(self.env, 'milestone2')
        m2.name = 'milestone5'

        m2.update()
        updated_fields = self.ticket_system.get_ticket_fields()
        updated_milestone_field = self._get_ticket_field('milestone')

        self.assertNotEqual(fields, updated_fields)
        self.assertEqual(['milestone1', 'milestone2',
                          'milestone3', 'milestone4'],
                         milestone_field['options'])
        self.assertEqual(['milestone1', 'milestone3',
                          'milestone4', 'milestone5'],
                         updated_milestone_field['options'])

    def test_get_ticket_fields_milestone_update_completed(self):
        """Cached ticket fields are updated when milestone is completed
        date is changed.
        """
        fields = self.ticket_system.get_ticket_fields()
        milestone_field = self._get_ticket_field('milestone')
        m2 = Milestone(self.env, 'milestone2')
        m2.completed = datetime_now(utc)

        m2.update()
        updated_fields = self.ticket_system.get_ticket_fields()
        updated_milestone_field = self._get_ticket_field('milestone')

        self.assertNotEqual(fields, updated_fields)
        self.assertEqual(['milestone1', 'milestone2',
                          'milestone3', 'milestone4'],
                         milestone_field['options'])
        self.assertEqual(['milestone2', 'milestone1',
                          'milestone3', 'milestone4'],
                         updated_milestone_field['options'])

    def test_get_ticket_fields_milestone_update_due(self):
        """Cached ticket fields are updated when milestone due date is
        changed.
        """
        fields = self.ticket_system.get_ticket_fields()
        milestone_field = self._get_ticket_field('milestone')
        m2 = Milestone(self.env, 'milestone2')
        m2.due = datetime_now(utc)

        m2.update()
        updated_fields = self.ticket_system.get_ticket_fields()
        updated_milestone_field = self._get_ticket_field('milestone')

        self.assertNotEqual(fields, updated_fields)
        self.assertEqual(['milestone1', 'milestone2',
                          'milestone3', 'milestone4'],
                         milestone_field['options'])
        self.assertEqual(['milestone2', 'milestone1',
                          'milestone3', 'milestone4'],
                         updated_milestone_field['options'])

    def test_resource_exists_valid_resource_id(self):
        Ticket(self.env).insert()
        r1 = Resource('ticket', 1)
        r2 = Resource('ticket', 2)

        self.assertTrue(self.ticket_system.resource_exists(r1))
        self.assertFalse(self.ticket_system.resource_exists(r2))

    def test_resource_exists_invalid_resource_id(self):
        """Exception is trapped from resource with invalid id."""
        r1 = Resource('ticket', None)
        r2 = Resource('ticket', 'abc')
        r3 = Resource('ticket', '2.')
        r4 = Resource('ticket', r2)

        self.assertFalse(self.ticket_system.resource_exists(r1))
        self.assertFalse(self.ticket_system.resource_exists(r2))
        self.assertFalse(self.ticket_system.resource_exists(r3))
        self.assertFalse(self.ticket_system.resource_exists(r4))


def test_suite():
    return unittest.makeSuite(TicketSystemTestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
