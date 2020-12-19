# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2020 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

from configparser import RawConfigParser
from glob import glob
from subprocess import PIPE, Popen
import inspect
import io
import os
import sys
import textwrap
import unittest

from trac import db_default
from trac.admin.console import TracAdmin
from trac.admin.test import TracAdminTestCaseBase
from trac.api import IEnvironmentSetupParticipant, ISystemInfoProvider
from trac.attachment import Attachment
from trac.config import ConfigurationError, Option
from trac.core import Component, TracError, implements
from trac.db.api import DatabaseManager, get_column_names
from trac.env import Environment, EnvironmentAdmin, open_environment
from trac.test import EnvironmentStub, get_dburi, mkdtemp, rmtree
from trac.util import create_file, extract_zipfile, hex_entropy, read_file
from trac.util.compat import close_fds
from trac.util import create_file


class EnvironmentWithoutDataTestCase(unittest.TestCase):

    def setUp(self):
        self.env_path = mkdtemp()
        self.env = self._create_env(self.env_path)

    def tearDown(self):
        self.env.shutdown() # really closes the db connections
        rmtree(self.env.path)

    def _create_env(self, env_path):
        return Environment(env_path, create=True, default_data=False)

    def test_database_version(self):
        self.assertEqual(db_default.db_version,
                         self.env.database_version)
        self.assertEqual(db_default.db_version,
                         self.env.database_initial_version)

    def test_environment_data(self):
        with self.env.db_query as db:
            for table, columns, default_data in db_default.get_data(db):
                table_data = db("SELECT * FROM %s" % db.quote(table))
                self.assertEqual([], table_data)

    def test_create_nonexistent_parent_directory(self):
        """TracError raised creating Environment at non-existent path."""
        base_dir = os.path.join(self.env_path, 'non-existent')
        env_path = os.path.join(base_dir, 'non-existent')
        with self.assertRaises(TracError) as cm:
            self._create_env(env_path)
        self.assertEqual("Base directory '%s' does not exist. Please create "
                         "it and retry." % base_dir, str(cm.exception))

    def test_create_in_existing_environment(self):
        """TracError raised creating Environment in existing Environment."""
        with self.assertRaises(TracError) as cm:
            self._create_env(self.env_path)
        self.assertEqual("Directory exists and is not empty.",
                         str(cm.exception))


class EnvironmentTestCase(unittest.TestCase):

    stdout = None
    stderr = None
    devnull = None

    @classmethod
    def setUpClass(cls):
        cls.stdout = sys.stdout
        cls.stderr = sys.stderr
        cls.devnull = io.open(os.devnull, 'w', encoding='utf-8')
        sys.stdout = sys.stderr = cls.devnull

    @classmethod
    def tearDownClass(cls):
        cls.devnull.close()
        sys.stdout = cls.stdout
        sys.stderr = cls.stderr

    def setUp(self):
        self.env_path = mkdtemp()
        self.env = Environment(self.env_path, create=True)

    def tearDown(self):
        self.env.shutdown() # really closes the db connections
        rmtree(self.env.path)

    def test_invalid_version_raises_trac_error(self):
        """TracError raised when environment version is invalid."""
        version = 'Trac Environment Version 0'
        create_file(os.path.join(self.env.path, 'VERSION'), version + '\n')

        with self.assertRaises(TracError) as cm:
            Environment(self.env.path)
        self.assertEqual(
            "Unknown Trac environment type 'Trac Environment Version 0'",
            str(cm.exception))

    def test_version_file_empty(self):
        """TracError raised when environment version is empty."""
        create_file(os.path.join(self.env.path, 'VERSION'), '')
        with self.assertRaises(TracError) as cm:
            Environment(self.env.path)
        self.assertEqual("Unknown Trac environment type ''", str(cm.exception))

    def test_version_file_not_found(self):
        """TracError raised when environment version file not found."""
        version_file = os.path.join(self.env.path, 'VERSION')
        os.remove(version_file)
        with self.assertRaises(TracError) as cm:
            Environment(self.env.path)
        self.assertEqual(
            "No Trac environment found at %s\n"
            "FileNotFoundError: [Errno 2] No such file or directory: '%s'"
            % (self.env.path, version_file),
            str(cm.exception))

    def test_missing_config_file_raises_trac_error(self):
        """TracError is raised when config file is missing."""
        os.remove(self.env.config_file_path)
        self.assertRaises(TracError, Environment, self.env.path)

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

        with open(self.env.log_file_path, encoding='utf-8') as f:
            log = f.readlines()
        self.assertEqual("Trac[env] My Project: The warning message\n",
                         log[-1])

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


class EnvironmentDataTestCase(unittest.TestCase):
    """Tests for environment data.

    The test cases don't modify the environment so the Environment can
    be reused to make the tests run faster.
    """

    env = None
    stdout = None
    stderr = None
    devnull = None

    @classmethod
    def setUpClass(cls):
        cls.stdout = sys.stdout
        cls.stderr = sys.stderr
        cls.devnull = io.open(os.devnull, 'w', encoding='utf-8')
        sys.stdout = sys.stderr = cls.devnull
        cls.env = Environment(mkdtemp(), create=True)

    @classmethod
    def tearDownClass(cls):
        cls.env.shutdown()
        rmtree(cls.env.path)
        cls.devnull.close()
        sys.stdout = cls.stdout
        sys.stderr = cls.stderr

    def test_database_version(self):
        self.assertEqual(db_default.db_version,
                         self.env.database_version)
        self.assertEqual(db_default.db_version,
                         self.env.database_initial_version)

    def test_environment_data(self):
        with self.env.db_query as db:
            for table, columns, default_data in db_default.get_data(db):
                table_data = db("""
                    SELECT %s FROM %s
                    """ % (','.join(columns), db.quote(table)))
                self.assertEqual(list(default_data), table_data)

    def test_is_component_enabled(self):
        self.assertTrue(Environment.required)
        self.assertTrue(self.env.is_component_enabled(Environment))

    def test_dumped_values_in_tracini(self):
        parser = RawConfigParser()
        filename = self.env.config.filename
        self.assertEqual([filename], parser.read(filename, 'utf-8'))
        self.assertEqual('#cc0,#0c0,#0cc,#00c,#c0c,#c00',
                         parser.get('revisionlog', 'graph_colors'))
        self.assertEqual('disabled', parser.get('trac', 'secure_cookies'))

    def test_dumped_values_in_tracini_sample(self):
        parser = RawConfigParser()
        filename = self.env.config.filename + '.sample'
        self.assertEqual([filename], parser.read(filename, 'utf-8'))
        self.assertEqual('#cc0,#0c0,#0cc,#00c,#c0c,#c00',
                         parser.get('revisionlog', 'graph_colors'))
        self.assertEqual('disabled', parser.get('trac', 'secure_cookies'))
        self.assertTrue(parser.has_option('logging', 'log_format'))
        self.assertEqual('', parser.get('logging', 'log_format'))

    def test_tracguide_is_readonly(self):
        from trac.wiki.model import WikiPage
        for name in ('TracGuide', 'TracInstall', 'TracUpgrade'):
            self.assertTrue(WikiPage(self.env, name).readonly)
        for name in ('SandBox', 'WikiStart', 'InterMapTxt'):
            self.assertFalse(WikiPage(self.env, name).readonly)


class EnvironmentAttributesTestCase(unittest.TestCase):
    """Tests for attributes which don't require a real environment
    on disk, and therefore can be executed against an `EnvironmentStub`
    object (faster execution).
    """

    def setUp(self):
        self.env = EnvironmentStub()
        self.env.config.set('trac', 'base_url',
                            'https://trac.edgewall.org/some/path')

    def test_is_component_enabled(self):
        self.assertFalse(EnvironmentStub.required)
        self.assertIsNone(self.env.is_component_enabled(EnvironmentStub))

    def test_db_exc(self):
        db_exc = self.env.db_exc
        self.assertTrue(hasattr(db_exc, 'IntegrityError'))
        self.assertIs(db_exc, self.env.db_exc)

    def test_abs_href(self):
        abs_href = self.env.abs_href
        self.assertEqual('https://trac.edgewall.org/some/path', abs_href())
        self.assertIs(abs_href, self.env.abs_href)

    def test_href(self):
        href = self.env.href
        self.assertEqual('/some/path', href())
        self.assertIs(href, self.env.href)

    def test_log_file_path_is_relative_path(self):
        log_file_path = self.env.log_file_path
        self.assertEqual(os.path.join(self.env.path, 'log', 'trac.log'),
                         log_file_path)
        self.assertIs(log_file_path, self.env.log_file_path)

    def test_log_file_path_is_absolute_path(self):
        log_file = os.path.join(self.env.path, 'trac.log')
        self.env.config.set('logging', 'log_file', log_file)
        self.assertEqual(log_file, self.env.log_file_path)

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
            def environment_needs_upgrade(self):
                return True
            def upgrade_environment(self):
                insert_value('value1', 1)

        class Participant2(Component):
            implements(IEnvironmentSetupParticipant)
            def environment_created(self):
                pass
            def environment_needs_upgrade(self):
                return True
            def upgrade_environment(self):
                insert_value('value2', 2)

        def insert_value(name, value):
            with self.env.db_transaction as db:
                db("""
                    INSERT INTO {0} (name, value) VALUES (%s, %s)
                    """.format(db.quote('system')), (name, value))

        def select_value(name):
            with self.env.db_query as db:
                for value, in db("""
                        SELECT value FROM {0} WHERE name=%s
                        """.format(db.quote('system')), (name,)):
                    return value

        self.env.enable_component(Participant1)
        self.env.enable_component(Participant2)

        self.assertTrue(self.env.needs_upgrade())
        self.assertTrue(self.env.upgrade())
        self.assertEqual('1', select_value('value1'))
        self.assertEqual('2', select_value('value2'))

    def test_upgrade_environment(self):
        """EnvironmentSetupParticipants are called only if
        environment_needs_upgrade returns True for the participant.
        """

        class SetupParticipantA(Component):
            implements(IEnvironmentSetupParticipant)

            called = False

            def environment_created(self):
                pass

            def environment_needs_upgrade(self):
                return True

            def upgrade_environment(self):
                self.called = True

        class SetupParticipantB(Component):
            implements(IEnvironmentSetupParticipant)

            called = False

            def environment_created(self):
                pass

            def environment_needs_upgrade(self):
                return False

            def upgrade_environment(self):
                self.called = True

        self.env.enable_component(SetupParticipantA)
        self.env.enable_component(SetupParticipantB)
        participant_a = SetupParticipantA(self.env)
        participant_b = SetupParticipantB(self.env)

        self.assertTrue(self.env.needs_upgrade())
        self.env.upgrade()
        self.assertTrue(participant_a.called)
        self.assertFalse(participant_b.called)


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


class SystemInfoTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def tearDown(self):
        self.env.reset_db()

    def test_database_backend_version(self):
        """Database backend is returned in system_info."""
        # closes the pooled connections to use `DatabaseManager.shutdown()`
        # instead of `env.shutdown()` to avoid `log.shutdown()`
        DatabaseManager(self.env).shutdown()
        info_before = self.env.system_info
        self.env.db_query("SELECT 42")  # just connects database
        info_after = self.env.system_info

        def get_info(system_info, name):
            for info in system_info:
                if info[0] == name:
                    return info[1]
            self.fail('Missing %r' % name)

        if self.env.dburi.startswith('mysql'):
            self.assertRegex(get_info(info_before, 'MySQL'),
                             r'^server: \(not-connected\), '
                             r'client: "\d+(\.\d+)+([-.].+)?", '
                             r'thread-safe: True$')
            self.assertRegex(get_info(info_after, 'MySQL'),
                             r'^server: "\d+(\.\d+)+([-.].+)?", '
                             r'client: "\d+(\.\d+)+([-.].+)?", '
                             r'thread-safe: True$')
            self.assertRegex(get_info(info_before, 'pymysql'),
                             r'^\d+(\.\d+)+$')
            self.assertRegex(get_info(info_after, 'pymysql'),
                             r'^\d+(\.\d+)+$')
        elif self.env.dburi.startswith('postgres'):
            self.assertRegex(get_info(info_before, 'PostgreSQL'),
                             r'^server: \(not-connected\), '
                             r'client: (\d+(\.\d+)+|\(unknown\))$')
            self.assertRegex(get_info(info_after, 'PostgreSQL'),
                             r'^server: \d+(\.\d+)+, '
                             r'client: (\d+(\.\d+)+|\(unknown\))$')
            self.assertRegex(get_info(info_before, 'psycopg2'),
                             r'^\d+(\.\d+)+$')
            self.assertRegex(get_info(info_after, 'psycopg2'),
                             r'^\d+(\.\d+)+$')
        elif self.env.dburi.startswith('sqlite'):
            self.assertEqual(info_before, info_after)
            self.assertRegex(get_info(info_before, 'SQLite'),
                             r'^\d+(\.\d+)+$')
            self.assertRegex(get_info(info_before, 'pysqlite'),
                             r'^\d+(\.\d+)+$')
        else:
            self.fail("Unknown value for dburi %s" % self.env.dburi)


class ConvertDatabaseTestCase(unittest.TestCase):

    stdout = None
    stderr = None

    @classmethod
    def setUpClass(cls):
        cls.stdout = sys.stdout
        cls.stderr = sys.stderr
        cls.devnull = io.open(os.devnull, 'w', encoding='utf-8')
        sys.stdout = sys.stderr = cls.devnull

    @classmethod
    def tearDownClass(cls):
        cls.devnull.close()
        sys.stdout = cls.stdout
        sys.stderr = cls.stderr

    def setUp(self):
        self.path = mkdtemp()
        self.src_path = os.path.join(self.path, 'src')
        self.dst_path = os.path.join(self.path, 'dst')
        self.src_env = None
        self.dst_env = None
        self._destroy_db()

    def tearDown(self):
        if self.src_env:
            self.src_env.shutdown()
        if self.dst_env:
            self.dst_env.shutdown()
        rmtree(self.path)

    def _create_env(self, path, dburi):
        env = Environment(path, True,
                          [('trac', 'database', dburi),
                           ('trac', 'base_url', 'http://localhost/'),
                           ('project', 'name', 'Pŕójéćŧ Ńáḿé')])
        dbm = DatabaseManager(env)
        dbm.set_database_version(21, 'initial_database_version')
        att = Attachment(env, 'wiki', 'WikiStart')
        att.insert('filename.txt', io.BytesIO(b'test'), 4)
        env.shutdown()

    if 'destroying' in inspect.signature(EnvironmentStub.__init__).parameters:
        def _destroy_db(self):
            EnvironmentStub(path=self.path, destroying=True).destroy_db()
    else:
        def _destroy_db(self):
            EnvironmentStub(path=self.path).destroy_db()

    def _get_all_records(self, env):
        def primary(row, columns):
            if len(columns) == 1:
                return row[columns[0]]
            else:
                return tuple(row[col] for col in columns)

        records = {}
        with env.db_query as db:
            cursor = db.cursor()
            for table in db_default.schema:
                primary_cols = ','.join(db.quote(col) for col in table.key)
                query = "SELECT * FROM %s ORDER BY %s" \
                        % (db.quote(table.name), primary_cols)
                cursor.execute(query)
                columns = get_column_names(cursor)
                rows = {}
                for row in cursor:
                    row = dict(zip(columns, row))
                    rows[primary(row, table.key)] = row
                records[table.name] = rows
        return records

    def _generate_module_name(self):
        return 'trac_convert_db_' + hex_entropy(16)

    def _build_egg_file(self):
        module_name = self._generate_module_name()
        plugin_src = os.path.join(self.path, 'plugin_src')
        os.mkdir(plugin_src)
        os.mkdir(os.path.join(plugin_src, module_name))
        create_file(os.path.join(plugin_src, 'setup.py'),
                    _setup_py % {'name': module_name})
        create_file(os.path.join(plugin_src, module_name, '__init__.py'),
                    _plugin_py)
        proc = Popen((sys.executable, 'setup.py', 'bdist_egg'), cwd=plugin_src,
                     stdin=PIPE, stdout=PIPE, stderr=PIPE, close_fds=close_fds)
        proc.communicate(input='')
        for f in (proc.stdin, proc.stdout, proc.stderr):
            f.close()
        for filename in glob(os.path.join(plugin_src, 'dist', '*-*.egg')):
            return filename

    def _convert_db(self, env, dburi, path):
        EnvironmentAdmin(env)._do_convert_db(dburi, path)

    def _convert_db_inplace(self, env, dburi):
        self._convert_db(env, dburi, None)

    def _compare_records(self, expected, actual):
        self.assertEqual(list(expected), list(actual))
        for table in db_default.schema:
            name = table.name
            if name == 'report':
                self.assertEqual(list(expected[name]), list(actual[name]))
            else:
                self.assertEqual(expected[name], actual[name])

    def _get_options(self, env):
        config = env.config
        return [(section, name, self._option_dumps(section, name, value))
                for section in sorted(config.sections())
                for name, value in sorted(config.options(section))
                if (section, name) != ('trac', 'database')]

    def _option_dumps(self, section, name, value):
        try:
            option = Option.registry[(section, name)]
        except KeyError:
            pass
        else:
            value = option.dumps(value)
        return value

    def test_convert_from_sqlite_to_env(self):
        self._create_env(self.src_path, 'sqlite:db/trac.db')
        dburi = get_dburi()
        if dburi == 'sqlite::memory:':
            dburi = 'sqlite:db/trac.db'

        self.src_env = Environment(self.src_path)
        src_options = self._get_options(self.src_env)
        src_records = self._get_all_records(self.src_env)
        self._convert_db(self.src_env, dburi, self.dst_path)
        self.dst_env = Environment(self.dst_path)
        dst_options = self._get_options(self.dst_env)
        dst_records = self._get_all_records(self.dst_env)
        self.assertEqual({'name': 'initial_database_version', 'value': '21'},
                         dst_records['system']['initial_database_version'])
        self._compare_records(src_records, dst_records)
        self.assertEqual(src_options, dst_options)
        att = Attachment(self.dst_env, 'wiki', 'WikiStart', 'filename.txt')
        self.assertEqual('test', read_file(att.path))

    def test_convert_from_sqlite_inplace(self):
        self._create_env(self.src_path, 'sqlite:db/trac.db')
        dburi = get_dburi()
        if dburi in ('sqlite::memory:', 'sqlite:db/trac.db'):
            dburi = 'sqlite:db/trac-convert.db'

        self.src_env = Environment(self.src_path)
        src_options = self._get_options(self.src_env)
        src_records = self._get_all_records(self.src_env)
        self._convert_db_inplace(self.src_env, dburi)
        self.src_env.shutdown()
        self.src_env = Environment(self.src_path)
        dst_options = self._get_options(self.src_env)
        dst_records = self._get_all_records(self.src_env)
        self.assertEqual({'name': 'initial_database_version', 'value': '21'},
                         dst_records['system']['initial_database_version'])
        self._compare_records(src_records, dst_records)
        self.assertEqual(src_options, dst_options)

    def test_convert_to_sqlite_env(self):
        dburi = get_dburi()
        if dburi == 'sqlite::memory:':
            dburi = 'sqlite:db/trac.db'
        self._create_env(self.src_path, dburi)

        self.src_env = Environment(self.src_path)
        src_options = self._get_options(self.src_env)
        src_records = self._get_all_records(self.src_env)
        self._convert_db(self.src_env, 'sqlite:db/trac.db', self.dst_path)
        self.dst_env = Environment(self.dst_path)
        dst_options = self._get_options(self.dst_env)
        dst_records = self._get_all_records(self.dst_env)
        self.assertEqual({'name': 'initial_database_version', 'value': '21'},
                         dst_records['system']['initial_database_version'])
        self._compare_records(src_records, dst_records)
        self.assertEqual(src_options, dst_options)
        att = Attachment(self.dst_env, 'wiki', 'WikiStart', 'filename.txt')
        self.assertEqual('test', read_file(att.path))

    def test_convert_to_sqlite_inplace(self):
        dburi = get_dburi()
        if dburi in ('sqlite::memory:', 'sqlite:db/trac.db'):
            dburi = 'sqlite:db/trac-convert.db'
        self._create_env(self.src_path, dburi)

        self.src_env = Environment(self.src_path)
        src_options = self._get_options(self.src_env)
        src_records = self._get_all_records(self.src_env)
        self._convert_db_inplace(self.src_env, 'sqlite:db/trac.db')
        self.src_env.shutdown()
        self.src_env = Environment(self.src_path)
        dst_options = self._get_options(self.src_env)
        dst_records = self._get_all_records(self.src_env)
        self.assertEqual({'name': 'initial_database_version', 'value': '21'},
                         dst_records['system']['initial_database_version'])
        self._compare_records(src_records, dst_records)
        self.assertEqual(src_options, dst_options)

    def _test_convert_with_plugin_to_sqlite_env(self):
        self.src_env = Environment(self.src_path)
        self.assertTrue(self.src_env.needs_upgrade())
        self.src_env.upgrade()
        self.assertFalse(self.src_env.needs_upgrade())
        src_options = self._get_options(self.src_env)
        src_records = self._get_all_records(self.src_env)

        self._convert_db(self.src_env, 'sqlite:db/trac.db', self.dst_path)
        self.dst_env = Environment(self.dst_path)
        self.assertFalse(self.dst_env.needs_upgrade())
        self.assertFalse(os.path.exists(os.path.join(self.dst_env.log_dir,
                                                     'created')))
        self.assertTrue(os.path.exists(os.path.join(self.dst_env.log_dir,
                                                    'upgraded')))
        dst_options = self._get_options(self.dst_env)
        dst_records = self._get_all_records(self.dst_env)
        self.assertEqual({'name': 'initial_database_version', 'value': '21'},
                         dst_records['system']['initial_database_version'])
        self._compare_records(src_records, dst_records)
        self.assertEqual(src_options, dst_options)
        att = Attachment(self.dst_env, 'wiki', 'WikiStart', 'filename.txt')
        self.assertEqual('test', read_file(att.path))

    def test_convert_with_plugin_py_to_sqlite_env(self):
        dburi = get_dburi()
        if dburi == 'sqlite::memory:':
            dburi = 'sqlite:db/trac.db'
        self._create_env(self.src_path, dburi)
        plugin_name = self._generate_module_name() + '.py'
        create_file(os.path.join(self.src_path, 'plugins', plugin_name),
                    _plugin_py)
        self._test_convert_with_plugin_to_sqlite_env()

    def test_convert_with_plugin_egg_to_sqlite_env(self):
        dburi = get_dburi()
        if dburi == 'sqlite::memory:':
            dburi = 'sqlite:db/trac.db'
        self._create_env(self.src_path, dburi)
        extract_zipfile(self._build_egg_file(),
                        os.path.join(self.src_path, 'plugins',
                                     'trac_convert_db_test.egg'))
        self._test_convert_with_plugin_to_sqlite_env()


_setup_py = """\
from setuptools import setup, find_packages

setup(
    name = '%(name)s',
    version = '0.1.0',
    description = '',
    license = '',
    install_requires = ['Trac'],
    packages = find_packages(exclude=['*.tests*']),
    entry_points = {'trac.plugins': ['%(name)s = %(name)s']})
"""


_plugin_py = """\
import os.path
from trac.core import Component, implements
from trac.env import IEnvironmentSetupParticipant
from trac.util import create_file

class Setup(Component):

    implements(IEnvironmentSetupParticipant)

    def __init__(self):
        self._created_file = os.path.join(self.env.path, 'log', 'created')
        self._upgraded_file = os.path.join(self.env.path, 'log', 'upgraded')

    def environment_created(self):
        create_file(self._created_file)

    def environment_needs_upgrade(self):
        return not os.path.exists(self._upgraded_file)

    def upgrade_environment(self):
        create_file(self._upgraded_file)
"""


class SystemInfoProviderTestCase(unittest.TestCase):

    system_info_providers = []

    @classmethod
    def setUpClass(cls):
        class SystemInfoProvider1(Component):
            implements(ISystemInfoProvider)

            def get_system_info(self):
                yield 'pkg1', 1.0
                yield 'pkg2', 2.0

        class SystemInfoProvider2(Component):
            implements(ISystemInfoProvider)

            def get_system_info(self):
                yield 'pkg1', 1.0

        cls.system_info_providers = [SystemInfoProvider1, SystemInfoProvider2]

    @classmethod
    def tearDownClass(cls):
        from trac.core import ComponentMeta
        for component in cls.system_info_providers:
            ComponentMeta.deregister(component)

    def setUp(self):
        self.env = EnvironmentStub(enable=self.system_info_providers)

    def test_system_info_property(self):
        """The system_info property returns a list of all tuples
        generated by ISystemInfoProvider implementations.
        """
        system_info = self.env.system_info
        self.assertIn(('pkg1', 1.0), system_info)
        self.assertIn(('pkg2', 2.0), system_info)

    def test_duplicate_entries_are_removed(self):
        """Duplicate entries are removed."""
        system_info = self.env.system_info
        self.assertIn(('pkg1', 1.0), system_info)
        self.assertEqual(len(system_info), len(set(system_info)))


class TracAdminDeployTestCase(TracAdminTestCaseBase):
    """Tests for the trac-admin deploy command."""

    stdout = None
    stderr = None
    devnull = None

    @classmethod
    def setUpClass(cls):
        cls.stdout = sys.stdout
        cls.stderr = sys.stderr
        cls.devnull = io.open(os.devnull, 'w', encoding='utf-8')
        sys.stdout = sys.stderr = cls.devnull

    @classmethod
    def tearDownClass(cls):
        cls.devnull.close()
        sys.stdout = cls.stdout
        sys.stderr = cls.stderr

    def setUp(self):
        self.env = Environment(path=mkdtemp(), create=True)
        self.admin = TracAdmin(self.env.path)
        self.admin.env_set('', self.env)

    def tearDown(self):
        self.env.shutdown()
        rmtree(self.env.path)

    def test_deploy(self):
        target = os.path.join(self.env.path, 'www')
        shebang = ('#!' + sys.executable).encode('utf-8')
        rv, output = self.execute('deploy %s' % target)
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)
        self.assertTrue(os.path.exists(os.path.join(target, 'cgi-bin')))
        self.assertTrue(os.path.exists(os.path.join(target, 'htdocs')))
        self.assertTrue(os.path.exists(os.path.join(target, 'htdocs',
                                                    'common')))
        self.assertTrue(os.path.exists(os.path.join(target, 'htdocs',
                                                    'site')))
        self.assertTrue(os.path.isfile(os.path.join(
            target, 'htdocs', 'common', 'js', 'trac.js')))
        self.assertTrue(os.path.isfile(os.path.join(
            target, 'htdocs', 'common', 'css', 'trac.css')))
        for ext in ('cgi', 'fcgi', 'wsgi'):
            content = read_file(os.path.join(target, 'cgi-bin',
                                             'trac.%s' % ext), 'rb')
            self.assertIn(shebang, content)
            self.assertEqual(0, content.index(shebang))
            self.assertIn(repr(self.env.path).encode('ascii'), content)

    def test_deploy_to_invalid_target_raises_error(self):
        """Running deploy with target directory equal to or below the source
        directory raises AdminCommandError.
        """
        rv, output = self.execute('deploy %s' % self.env.htdocs_dir)

        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)


class TracAdminInitenvTestCase(TracAdminTestCaseBase):

    def setUp(self):
        self.parent_dir = mkdtemp()
        self.env_path = os.path.join(self.parent_dir, 'trac')
        self.admin = TracAdmin(self.env_path)

    def tearDown(self):
        if os.path.isfile(os.path.join(self.env_path, 'VERSION')):
            self.admin.env.shutdown()
        rmtree(self.parent_dir)

    def test_default_values(self):
        tracini_path = os.path.join(self.env_path, 'conf', 'trac.ini')
        rv, output = self.execute('initenv project1 sqlite:db/sqlite.db')

        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'env_path': self.env_path,
            'tracini_path': tracini_path
        })

        rv, output = self.execute('component list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, suffix='_component_list')
        rv, output = self.execute('milestone list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, suffix='_milestone_list')
        rv, output = self.execute('version list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, suffix='_version_list')
        rv, output = self.execute('resolution list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, suffix='_resolution_list')
        rv, output = self.execute('priority list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, suffix='_priority_list')
        rv, output = self.execute('ticket_type list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, suffix='_ticket_type_list')
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, suffix='_permission_list')

    def test_no_default_data_argument(self):
        tracini_path = os.path.join(self.env_path, 'conf', 'trac.ini')
        rv, output = self.execute('initenv project1 sqlite:db/sqlite.db '
                                  '--no-default-data')

        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'env_path': self.env_path,
            'tracini_path': tracini_path
        })

        rv, output = self.execute('component list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, suffix='_component_list')
        rv, output = self.execute('milestone list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, suffix='_milestone_list')
        rv, output = self.execute('version list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, suffix='_version_list')
        rv, output = self.execute('resolution list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, suffix='_resolution_list')
        rv, output = self.execute('priority list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, suffix='_priority_list')
        rv, output = self.execute('ticket_type list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, suffix='_ticket_type_list')
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, suffix='_permission_list')

    def test_config_argument(self):
        """Options contained in file specified by the --config argument
        are written to trac.ini.
        """
        config_file = os.path.join(self.parent_dir, 'config.ini')
        create_file(config_file, textwrap.dedent("""\
            [the-plugin]
            option_a = 1
            option_b = 2
            [components]
            the_plugin.* = enabled
            [project]
            name = project2
            """))
        rv, output = self.execute('initenv project1 sqlite:db/sqlite.db '
                                   '--config=%s' % config_file)
        env = Environment(self.env_path)
        cfile = env.config.parser

        self.assertEqual(0, rv, output)
        self.assertEqual('1', cfile.get('the-plugin', 'option_a'))
        self.assertEqual('2', cfile.get('the-plugin', 'option_b'))
        self.assertEqual('enabled', cfile.get('components', 'the_plugin.*'))
        self.assertEqual('project1', cfile.get('project', 'name'))
        self.assertEqual('sqlite:db/sqlite.db', cfile.get('trac', 'database'))
        for (section, name), option in \
                Option.get_registry(env.compmgr).items():
            if (section, name) not in \
                    (('trac', 'database'), ('project', 'name')):
                self.assertEqual(option.default, cfile.get(section, name))

    def test_config_argument_has_invalid_path(self):
        """Exception is raised when --config argument is an invalid path."""
        config_file = os.path.join(self.parent_dir, 'config.ini')
        rv, output = self.execute('initenv project1 sqlite:db/sqlite.db '
                                   '--config=%s' % config_file)

        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'env_path': self.env_path,
            'config_file': config_file,
        })

    def test_config_argument_has_invalid_value(self):
        """Exception is raised when --config argument specifies a malformed
        configuration file.
        """
        config_file = os.path.join(self.parent_dir, 'config.ini')
        create_file(config_file, textwrap.dedent("""\
            [the-plugin]
            option_a = 1
            [components
            the_plugin.* = enabled
            """))
        rv, output = self.execute('initenv project1 sqlite:db/sqlite.db '
                                   '--config=%s' % config_file)

        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'env_path': self.env_path,
            'config_file': config_file,
        })


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(EnvironmentWithoutDataTestCase))
    suite.addTest(unittest.makeSuite(EnvironmentDataTestCase))
    suite.addTest(unittest.makeSuite(EnvironmentTestCase))
    suite.addTest(unittest.makeSuite(EnvironmentAttributesTestCase))
    suite.addTest(unittest.makeSuite(EnvironmentUpgradeTestCase))
    suite.addTest(unittest.makeSuite(KnownUsersTestCase))
    suite.addTest(unittest.makeSuite(SystemInfoTestCase))
    suite.addTest(unittest.makeSuite(ConvertDatabaseTestCase))
    suite.addTest(unittest.makeSuite(SystemInfoProviderTestCase))
    suite.addTest(unittest.makeSuite(TracAdminDeployTestCase))
    suite.addTest(unittest.makeSuite(TracAdminInitenvTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
