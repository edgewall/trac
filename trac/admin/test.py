# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2020 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import difflib
import inspect
import io
import os
import re
import sys
import unittest

from trac.admin.console import AdminCommandManager, TracAdmin, _run

STRIP_TRAILING_SPACE = re.compile(r'( +)$', re.MULTILINE)


def load_expected_results(file, pattern):
    """Reads the file, named file, which contains test results separated
    by the regular expression pattern.

    The test results are returned as a dictionary.
    """
    expected = {}
    compiled_pattern = re.compile(pattern)
    with open(file, encoding='utf-8') as f:
        test = None
        for line in f:
            line = line.rstrip()
            match = compiled_pattern.search(line)
            if match:
                test = match.groups()[0]
                expected[test] = ''
            else:
                expected[test] += line + '\n'
    return expected


def _execute(func, strip_trailing_space=True, input=None):
    if isinstance(input, str):
        input = input.encode('utf-8')
    elif input is None:
        input = b''
    elif not isinstance(input, bytes):
        raise ValueError('input must be str, bytes or None, not %s' %
                         type(input))

    with io.BytesIO(input) as rbuf, io.BytesIO() as wbuf:
        stdin = io.TextIOWrapper(rbuf, encoding='utf-8', newline='\n')
        stdout = io.TextIOWrapper(wbuf, encoding='utf-8', newline='\n',
                                  write_through=True)
        _files = sys.stdin, sys.stdout, sys.stderr
        try:
            sys.stdin = stdin
            sys.stderr = sys.stdout = stdout
            return_val = func()
        finally:
            sys.stdin, sys.stdout, sys.stderr = _files
        value = wbuf.getvalue()

    value = str(value, 'utf-8')
    if strip_trailing_space:
        return return_val, STRIP_TRAILING_SPACE.sub('', value)
    else:
        return return_val, value


def execute_cmd(tracadmin, cmd, strip_trailing_space=True, input=None):
    def func():
        try:
            return tracadmin.onecmd(cmd)
        except SystemExit:
            return None
    return _execute(func, strip_trailing_space, input)


class TracAdminTestCaseBase(unittest.TestCase):

    expected_results_filename = 'console-tests.txt'

    @classmethod
    def setUpClass(cls):
        cls.environ = os.environ.copy()

    @classmethod
    def tearDownClass(cls):
        for name in set(os.environ) - set(cls.environ):
            del os.environ[name]
        os.environ.update(cls.environ)

    @property
    def expected_results_file(self):
        results_file = sys.modules[self.__class__.__module__].__file__
        return os.path.join(os.path.dirname(results_file),
                            self.expected_results_filename)

    @property
    def expected_results(self):
        return load_expected_results(self.expected_results_file,
                                     '===== (test_[^ ]+) =====')

    def execute(self, cmd, strip_trailing_space=True, input=None):
        if hasattr(self, 'admin'):
            admin = self.admin
        else:
            admin = TracAdmin()
        return execute_cmd(admin, cmd,
                           strip_trailing_space=strip_trailing_space,
                           input=input)

    def assertExpectedResult(self, output, args=None, suffix=None):
        test_name = inspect.stack()[1][3]
        if suffix:
            test_name += suffix
        expected_result = self.expected_results[test_name]
        if args is not None:
            expected_result %= args

        def diff():
            # Create a useful delta between the output and the expected output
            output_lines = ['%s\n' % x for x in output.split('\n')]
            expected_lines = ['%s\n' % x for x in expected_result.split('\n')]
            return ''.join(difflib.unified_diff(expected_lines, output_lines,
                                                'expected', 'actual'))

        msg = "%r != %r\n%s" % (expected_result, output, diff())
        if '[...]' in expected_result:
            m = re.match('.*'.join(map(re.escape,
                                       expected_result.split('[...]'))) +
                         '\Z',
                         output, re.DOTALL)
            self.assertTrue(m, msg)
        else:
            self.assertEqual(expected_result, output, msg)

    @classmethod
    def execute_run(cls, args):
        def func():
            try:
                return _run(args)
            except SystemExit:
                return None
        return _execute(func)

    def get_command_help(self, *args):
        docs = AdminCommandManager(self.env).get_command_help(list(args))
        self.assertEqual(1, len(docs))
        return docs[0][2]

    def complete_command(self, *args):
        return AdminCommandManager(self.env).complete_command(list(args))
