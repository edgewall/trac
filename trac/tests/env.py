# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from ConfigParser import RawConfigParser
import os
import tempfile
import unittest

from trac import db_default
from trac.config import ConfigurationError
from trac.core import Component, ComponentManager, TracError, implements
from trac.env import Environment, IEnvironmentSetupParticipant, \
                     ISystemInfoProvider, open_environment
from trac.test import EnvironmentStub, rmtree


class EnvironmentCreatedWithoutData(Environment):
    def __init__(self, path, create=False, options=[]):
        ComponentManager.__init__(self)

        self.path = path
        self.systeminfo = []
        self.href = self.abs_href = None

        if create:
            self.create(options)
        else:
            self.verify()
            self.setup_config()


class EmptyEnvironmentTestCase(unittest.TestCase):

    def setUp(self):
        env_path = tempfile.mkdtemp(prefix='trac-tempenv-')
        self.env = EnvironmentCreatedWithoutData(env_path, create=True)

    def tearDown(self):
        self.env.shutdown() # really closes the db connections
        rmtree(self.env.path)

    def test_get_version(self):
        """Testing env.get_version"""
        self.assertFalse(self.env.get_version())


class EnvironmentTestCase(unittest.TestCase):

    def setUp(self):
        self.env_path = tempfile.mkdtemp(prefix='trac-tempenv-')
        self.env = Environment(self.env_path, create=True)
        self.env.config.set('trac', 'base_url',
                            'http://trac.edgewall.org/some/path')
        self.env.config.save()

    def tearDown(self):
        self.env.shutdown() # really closes the db connections
        rmtree(self.env.path)

    def test_missing_config_file_raises_trac_error(self):
        """TracError is raised when config file is missing."""
        os.remove(self.env.config_file_path)
        self.assertRaises(TracError, Environment, self.env.path)

    def test_db_exc(self):
        db_exc = self.env.db_exc
        self.assertTrue(hasattr(db_exc, 'IntegrityError'))
        self.assertIs(db_exc, self.env.db_exc)

    def test_abs_href(self):
        abs_href = self.env.abs_href
        self.assertEqual('http://trac.edgewall.org/some/path', abs_href())
        self.assertIs(abs_href, self.env.abs_href)

    def test_href(self):
        href = self.env.href
        self.assertEqual('/some/path', href())
        self.assertIs(href, self.env.href)

    def test_get_version(self):
        """Testing env.get_version"""
        self.assertEqual(db_default.db_version, self.env.get_version())
        self.assertEqual(db_default.db_version, self.env.database_version)
        self.assertEqual(db_default.db_version, self.env.database_initial_version)

    def test_is_component_enabled(self):
        self.assertEqual(True, Environment.required)
        self.assertEqual(True, self.env.is_component_enabled(Environment))
        self.assertEqual(False, EnvironmentStub.required)
        self.assertEqual(None, self.env.is_component_enabled(EnvironmentStub))

    def test_log_format(self):
        """Configure the log_format and log to a file at WARNING level."""
        self.env.config.set('logging', 'log_type', 'file')
        self.env.config.set('logging', 'log_level', 'WARNING')
        self.env.config.set('logging', 'log_format',
                            'Trac[$(module)s] $(project)s: $(message)s')
        self.env.config.save()
        self.env.shutdown()
        self.env = Environment(self.env_path)  # Reload environment

        self.env.log.warning("The warning message")

        with open(os.path.join(self.env.log_dir, self.env.log_file)) as f:
            log = f.readlines()
        self.assertEqual("Trac[env] My Project: The warning message\n",
                         log[-1])

    def test_dumped_values_in_tracini(self):
        parser = RawConfigParser()
        filename = self.env.config.filename
        self.assertEqual([filename], parser.read(filename))
        self.assertEqual('#cc0,#0c0,#0cc,#00c,#c0c,#c00',
                         parser.get('revisionlog', 'graph_colors'))
        self.assertEqual('disabled', parser.get('trac', 'secure_cookies'))

    def test_dumped_values_in_tracini_sample(self):
        parser = RawConfigParser()
        filename = self.env.config.filename + '.sample'
        self.assertEqual([filename], parser.read(filename))
        self.assertEqual('#cc0,#0c0,#0cc,#00c,#c0c,#c00',
                         parser.get('revisionlog', 'graph_colors'))
        self.assertEqual('disabled', parser.get('trac', 'secure_cookies'))
        self.assertTrue(parser.has_option('logging', 'log_format'))
        self.assertEqual('', parser.get('logging', 'log_format'))

    def test_invalid_log_level_raises_exception(self):
        self.env.config.set('logging', 'log_level', 'invalid')
        self.env.config.save()

        self.assertEqual('invalid',
                         self.env.config.get('logging', 'log_level'))
        self.assertRaises(ConfigurationError, open_environment,
                          self.env.path, True)

    def test_invalid_log_type_raises_exception(self):
        self.env.config.set('logging', 'log_type', 'invalid')
        self.env.config.save()

        self.assertEqual('invalid',
                         self.env.config.get('logging', 'log_type'))
        self.assertRaises(ConfigurationError, open_environment,
                          self.env.path, True)

    def test_log_level_not_case_sensitive(self):
        """[logging] log_level is not case-sensitive."""
        self.env.config.set('logging', 'log_level', 'warning')
        self.env.config.save()

        self.assertEqual('warning',
                         self.env.config.get('logging', 'log_level'))
        self.assertEqual('WARNING', self.env.log_level)

    def test_log_type_not_case_sensitive(self):
        """[logging] log_type is not case-sensitive."""
        self.env.config.set('logging', 'log_type', 'File')
        self.env.config.save()

        self.assertEqual('File',
                         self.env.config.get('logging', 'log_type'))
        self.assertEqual('file', self.env.log_type)


class EnvironmentUpgradeTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def tearDown(self):
        self.env.reset_db()

    def test_multiple_upgrade_participants(self):

        class Participant1(Component):
            implements(IEnvironmentSetupParticipant)
            def environment_created(self):
                pass
            def environment_needs_upgrade(self, db):
                return True
            def upgrade_environment(self, db):
                insert_value('value1', 1)

        class Participant2(Component):
            implements(IEnvironmentSetupParticipant)
            def environment_created(self):
                pass
            def environment_needs_upgrade(self, db):
                return True
            def upgrade_environment(self, db):
                insert_value('value2', 2)

        def insert_value(name, value):
            self.env.db_transaction("""
                INSERT INTO system (name, value) VALUES (%s, %s)
                """, (name, value))

        def select_value(name):
            for value, in self.env.db_query("""
                    SELECT value FROM system WHERE name=%s
                    """, (name,)):
                return value

        self.env.enable_component(Participant1)
        self.env.enable_component(Participant2)

        self.assertTrue(self.env.needs_upgrade())
        self.assertTrue(self.env.upgrade())
        self.assertEqual('1', select_value('value1'))
        self.assertEqual('2', select_value('value2'))

    def test_needs_upgrade_legacy_participant(self):
        """For backward compatibility with plugin, environment_needs_upgrade
        with a `db` argument is deprecated but still allowed."""
        participants = self.env.setup_participants
        needs_upgrade = self.env.needs_upgrade()

        class LegacyParticipant(Component):
            implements(IEnvironmentSetupParticipant)
            def environment_created(self):
                pass
            def environment_needs_upgrade(self, db):
                return True
            def upgrade_environment(self, db):
                pass

        self.env.enable_component(LegacyParticipant)

        self.assertFalse(needs_upgrade)
        self.assertEqual(len(participants) + 1,
                         len(self.env.setup_participants))
        self.assertTrue(self.env.needs_upgrade())

    def test_upgrade_legacy_participant(self):
        """For backward compatibility with plugin, upgrade with a `db`
        argument is deprecated but still allowed."""
        participants = self.env.setup_participants

        class LegacyParticipant(Component):
            implements(IEnvironmentSetupParticipant)
            def environment_created(self):
                pass
            def environment_needs_upgrade(self, db):
                return True
            def upgrade_environment(self, db):
                pass

        self.env.enable_component(LegacyParticipant)

        self.assertEqual(len(participants) + 1,
                         len(self.env.setup_participants))
        self.assertTrue(self.env.needs_upgrade())
        self.assertTrue(self.env.upgrade())


class KnownUsersTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        users = [
            ('123', None, 'a@example.com', 0),
            ('jane', 'Jane', None, 1),
            ('joe', None, 'joe@example.com', 1),
            ('tom', 'Tom', 'tom@example.com', 1)
        ]
        self.env.insert_users(users)
        self.expected = [user[:3] for user in users if user[3] == 1]

    def tearDown(self):
        self.env.reset_db()

    def test_get_known_users_as_list_of_tuples(self):
        users = list(self.env.get_known_users())

        i = 0
        for i, user in enumerate(users):
            self.assertEqual(self.expected[i], user)
        else:
            self.assertEqual(2, i)

    def test_get_known_users_as_dict(self):
        users = self.env.get_known_users(as_dict=True)

        self.assertEqual(3, len(users))
        for exp in self.expected:
            self.assertEqual(exp[1:], users[exp[0]])

    def test_get_known_users_is_cached(self):
        self.env.get_known_users()
        self.env.get_known_users(as_dict=True)
        self.env.insert_users([('user4', None, None)])

        users_list = list(self.env.get_known_users())
        users_dict = self.env.get_known_users(as_dict=True)

        i = 0
        for i, user in enumerate(users_list):
            self.assertEqual(self.expected[i], user)
            self.assertIn(self.expected[i][0], users_dict)
        else:
            self.assertEqual(2, i)
            self.assertEqual(3, len(users_dict))

    def test_invalidate_known_users_cache(self):
        self.env.get_known_users()
        self.env.get_known_users(as_dict=True)
        user = ('user4', 'User Four', 'user4@example.net')
        self.env.insert_users([user])
        self.expected.append(user[:3])

        self.env.invalidate_known_users_cache()
        users_list = self.env.get_known_users()
        users_dict = self.env.get_known_users(as_dict=True)

        i = 0
        for i, user in enumerate(users_list):
            self.assertEqual(self.expected[i], user)
            self.assertIn(self.expected[i][0], users_dict)
        else:
            self.assertEqual(3, i)
            self.assertEqual(4, len(users_dict))


class SystemInfoProviderTestCase(unittest.TestCase):

    def setUp(self):
        class SystemInfoProvider1(Component):
            implements(ISystemInfoProvider)

            def get_system_info(self):
                yield 'pkg1', 1.0

        class SystemInfoProvider2(Component):
            implements(ISystemInfoProvider)

            def get_system_info(self):
                yield 'pkg1', 1.0

        self.env = EnvironmentStub(enable=(SystemInfoProvider1,
                                           SystemInfoProvider2))

    def test_duplicate_entries_are_removed(self):
        """Duplicate entries are removed."""
        system_info = list(self.env.get_systeminfo())
        self.assertIn(('pkg1', 1.0), system_info)
        self.assertEqual(len(system_info), len(set(system_info)))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(EnvironmentTestCase))
    suite.addTest(unittest.makeSuite(EnvironmentUpgradeTestCase))
    suite.addTest(unittest.makeSuite(EmptyEnvironmentTestCase))
    suite.addTest(unittest.makeSuite(KnownUsersTestCase))
    suite.addTest(unittest.makeSuite(SystemInfoProviderTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
