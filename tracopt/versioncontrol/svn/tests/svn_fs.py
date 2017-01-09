# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2013 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

from datetime import datetime
import locale
import new
import os.path
import tempfile
import unittest

from StringIO import StringIO

try:
    from svn import core, repos
    has_svn = True
except ImportError:
    has_svn = False

from genshi.core import Stream

import trac.tests.compat
from trac.test import EnvironmentStub, MockRequest, TestSetup
from trac.core import TracError
from trac.mimeview.api import RenderingContext
from trac.resource import Resource, resource_exists
from trac.util.concurrency import get_thread_id
from trac.util.datefmt import utc
from trac.versioncontrol.api import DbRepositoryProvider, Changeset, \
                                    InvalidRepository, Node, \
                                    NoSuchChangeset, RepositoryManager
from trac.web.chrome import web_context
from tracopt.versioncontrol.svn import svn_fs, svn_prop


REPOS_PATH = None
REPOS_NAME = 'repo'
URL = 'svn://test'

HEAD = 31
TETE = 26

NATIVE_EOL = '\r\n' if os.name == 'nt' else '\n'


def _create_context(env):
    req = MockRequest(env)
    return web_context(req)


def setlocale(*locales):
    """Decorator to call test method with each locale.
    """
    if os.name != 'nt':
        locales_map = {'de': 'de_DE.UTF8', 'fr': 'fr_FR.UTF8',
                       'pl': 'pl_PL.UTF8', 'ja': 'ja_JP.UTF8',
                       'zh_CN': 'zh_CN.UTF8'}
    else:
        locales_map = {'de': 'German_Germany', 'fr': 'French_France',
                       'pl': 'Polish_Poland', 'ja': 'Japanese_Japan',
                       'zh_CN': "Chinese_People's Republic of China"}
    locales_map['C'] = 'C'

    def getlocale():
        rv = locale.getlocale(locale.LC_ALL)
        return rv if rv[0] else 'C'

    def setlocale(locale_id):
        locale_id = locales_map[locale_id]
        try:
            locale.setlocale(locale.LC_ALL, locale_id)
            return True
        except locale.Error:
            return False

    def wrap(fn, locales):
        def wrapped(*args, **kwargs):
            saved_locale = getlocale()
            try:
                for locale_id in locales:
                    if setlocale(locale_id):
                        fn(*args, **kwargs)
            finally:
                locale.setlocale(locale.LC_ALL, saved_locale)
        return wrapped

    if len(locales) == 1 and hasattr(locales[0], '__call__'):
        return wrap(locales[0], sorted(locales_map))
    else:
        def decorator(fn):
            return wrap(fn, locales)
        return decorator


class SubversionRepositoryTestSetup(TestSetup):

    def setUp(self):
        dumpfile = open(os.path.join(os.path.split(__file__)[0],
                                     'svnrepos.dump'))

        svn_fs._import_svn()
        core.apr_initialize()
        pool = core.svn_pool_create(None)
        dumpstream = None
        try:
            r = repos.svn_repos_create(REPOS_PATH, '', '', None, None, pool)
            if hasattr(repos, 'svn_repos_load_fs2'):
                repos.svn_repos_load_fs2(r, dumpfile, StringIO(),
                                        repos.svn_repos_load_uuid_default, '',
                                        0, 0, None, pool)
            else:
                dumpstream = core.svn_stream_from_aprfile(dumpfile, pool)
                repos.svn_repos_load_fs(r, dumpstream, None,
                                        repos.svn_repos_load_uuid_default, '',
                                        None, None, pool)
        finally:
            if dumpstream:
                core.svn_stream_close(dumpstream)
            core.svn_pool_destroy(pool)
            core.apr_terminate()

    def tearDown(self):
        repos.svn_repos_delete(REPOS_PATH)


# -- Re-usable test mixins

class NormalTests(object):

    def test_invalid_path_raises(self):
        self.assertRaises(InvalidRepository, svn_fs.SubversionRepository,
                          '/the/invalid/path', [], self.env.log)

    def test_resource_exists(self):
        repos = Resource('repository', REPOS_NAME)
        self.assertTrue(resource_exists(self.env, repos))
        self.assertFalse(resource_exists(self.env, repos(id='xxx')))
        node = repos.child('source', u'tête')
        self.assertTrue(resource_exists(self.env, node))
        self.assertFalse(resource_exists(self.env, node(id='xxx')))
        cset = repos.child('changeset', HEAD)
        self.assertTrue(resource_exists(self.env, cset))
        self.assertFalse(resource_exists(self.env, cset(id=123456)))

    def test_repos_normalize_path(self):
        self.assertEqual('/', self.repos.normalize_path('/'))
        self.assertEqual('/', self.repos.normalize_path(''))
        self.assertEqual('/', self.repos.normalize_path(None))
        self.assertEqual(u'tête', self.repos.normalize_path(u'tête'))
        self.assertEqual(u'tête', self.repos.normalize_path(u'/tête'))
        self.assertEqual(u'tête', self.repos.normalize_path(u'tête/'))
        self.assertEqual(u'tête', self.repos.normalize_path(u'/tête/'))

    def test_repos_normalize_rev(self):
        self.assertEqual(HEAD, self.repos.normalize_rev('latest'))
        self.assertEqual(HEAD, self.repos.normalize_rev('head'))
        self.assertEqual(HEAD, self.repos.normalize_rev(''))
        self.assertRaises(NoSuchChangeset,
                          self.repos.normalize_rev, 'something else')
        self.assertEqual(HEAD, self.repos.normalize_rev(None))
        self.assertEqual(11, self.repos.normalize_rev('11'))
        self.assertEqual(11, self.repos.normalize_rev(11))
        self.assertRaises(NoSuchChangeset, self.repos.normalize_rev, -1)
        self.assertRaises(NoSuchChangeset, self.repos.normalize_rev, -42)

    def test_repos_display_rev(self):
        self.assertEqual(str(HEAD), self.repos.display_rev('latest'))
        self.assertEqual(str(HEAD), self.repos.display_rev('head'))
        self.assertEqual(str(HEAD), self.repos.display_rev(''))
        self.assertRaises(NoSuchChangeset,
                          self.repos.display_rev, 'something else')
        self.assertEqual(str(HEAD), self.repos.display_rev(None))
        self.assertEqual('11', self.repos.display_rev('11'))
        self.assertEqual('11', self.repos.display_rev(11))

    def test_repos_short_rev(self):
        self.assertEqual(str(HEAD), self.repos.short_rev('latest'))
        self.assertEqual(str(HEAD), self.repos.short_rev('head'))
        self.assertEqual(str(HEAD), self.repos.short_rev(''))
        self.assertRaises(NoSuchChangeset,
                          self.repos.short_rev, 'something else')
        self.assertEqual(str(HEAD), self.repos.short_rev(None))
        self.assertEqual('11', self.repos.short_rev('11'))
        self.assertEqual('11', self.repos.short_rev(11))

    def test_rev_navigation(self):
        self.assertEqual(1, self.repos.oldest_rev)
        self.assertIsNone(self.repos.previous_rev(0))
        self.assertIsNone(self.repos.previous_rev(1))
        self.assertEqual(HEAD, self.repos.youngest_rev)
        self.assertEqual(6, self.repos.next_rev(5))
        self.assertEqual(7, self.repos.next_rev(6))
        # ...
        self.assertIsNone(self.repos.next_rev(HEAD))
        self.assertRaises(NoSuchChangeset, self.repos.normalize_rev, HEAD + 1)

    def test_rev_path_navigation(self):
        self.assertEqual(1, self.repos.oldest_rev)
        self.assertIsNone(self.repos.previous_rev(0, u'tête'))
        self.assertIsNone(self.repos.previous_rev(1, u'tête'))
        self.assertEqual(HEAD, self.repos.youngest_rev)
        self.assertEqual(6, self.repos.next_rev(5, u'tête'))
        self.assertEqual(13, self.repos.next_rev(6, u'tête'))
        # ...
        self.assertIsNone(self.repos.next_rev(HEAD, u'tête'))
        # test accentuated characters
        self.assertIsNone(self.repos.previous_rev(17, u'tête/R\xe9sum\xe9.txt'))
        self.assertEqual(17, self.repos.next_rev(16, u'tête/R\xe9sum\xe9.txt'))

    def test_has_node(self):
        self.assertFalse(self.repos.has_node(u'/tête/dir1', 3))
        self.assertTrue(self.repos.has_node(u'/tête/dir1', 4))
        self.assertTrue(self.repos.has_node(u'/tête/dir1'))

    def test_get_node(self):
        node = self.repos.get_node(u'/')
        self.assertEqual(u'', node.name)
        self.assertEqual(u'/', node.path)
        self.assertEqual(Node.DIRECTORY, node.kind)
        self.assertEqual(HEAD, node.rev)
        self.assertEqual(HEAD, node.created_rev)
        self.assertEqual(datetime(2017, 1, 9, 6, 12, 33, 247657, utc),
                         node.last_modified)
        self.assertRaises(NoSuchChangeset, self.repos.get_node, u'/', -1)
        node = self.repos.get_node(u'/tête')
        self.assertEqual(u'tête', node.name)
        self.assertEqual(u'/tête', node.path)
        self.assertEqual(Node.DIRECTORY, node.kind)
        self.assertEqual(HEAD, node.rev)
        self.assertEqual(TETE, node.created_rev)
        self.assertEqual(datetime(2013, 4, 28, 5, 36, 6, 29637, utc),
                         node.last_modified)
        node = self.repos.get_node(u'/tête/README.txt')
        self.assertEqual('README.txt', node.name)
        self.assertEqual(u'/tête/README.txt', node.path)
        self.assertEqual(Node.FILE, node.kind)
        self.assertEqual(HEAD, node.rev)
        self.assertEqual(3, node.created_rev)
        self.assertEqual(datetime(2005, 4, 1, 13, 24, 58, 234643, utc),
                         node.last_modified)

    def test_get_node_specific_rev(self):
        node = self.repos.get_node(u'/tête', 1)
        self.assertEqual(u'tête', node.name)
        self.assertEqual(u'/tête', node.path)
        self.assertEqual(Node.DIRECTORY, node.kind)
        self.assertEqual(1, node.rev)
        self.assertEqual(datetime(2005, 4, 1, 10, 0, 52, 353248, utc),
                         node.last_modified)
        node = self.repos.get_node(u'/tête/README.txt', 2)
        self.assertEqual('README.txt', node.name)
        self.assertEqual(u'/tête/README.txt', node.path)
        self.assertEqual(Node.FILE, node.kind)
        self.assertEqual(2, node.rev)
        self.assertEqual(datetime(2005, 4, 1, 13, 12, 18, 216267, utc),
                         node.last_modified)

    def test_get_dir_entries(self):
        node = self.repos.get_node(u'/tête')
        entries = node.get_entries()
        self.assertEqual('dir1', entries.next().name)
        self.assertEqual('mpp_proc', entries.next().name)
        self.assertEqual('v2', entries.next().name)
        self.assertEqual('README3.txt', entries.next().name)
        self.assertEqual(u'R\xe9sum\xe9.txt', entries.next().name)
        self.assertEqual('README.txt', entries.next().name)
        self.assertRaises(StopIteration, entries.next)

    def test_get_file_entries(self):
        node = self.repos.get_node(u'/tête/README.txt')
        entries = node.get_entries()
        self.assertRaises(StopIteration, entries.next)

    def test_get_dir_content(self):
        node = self.repos.get_node(u'/tête')
        self.assertIsNone(node.content_length)
        self.assertIsNone(node.content_type)
        self.assertIsNone(node.get_content())

    def test_get_file_content(self):
        node = self.repos.get_node(u'/tête/README.txt')
        self.assertEqual(8, node.content_length)
        self.assertEqual('text/plain', node.content_type)
        self.assertEqual('A test.\n', node.get_content().read())

    def test_get_dir_properties(self):
        f = self.repos.get_node(u'/tête')
        props = f.get_properties()
        self.assertEqual(1, len(props))

    def test_get_file_properties(self):
        f = self.repos.get_node(u'/tête/README.txt')
        props = f.get_properties()
        self.assertEqual('native', props['svn:eol-style'])
        self.assertEqual('text/plain', props['svn:mime-type'])

    def test_get_file_content_without_native_eol_style(self):
        f = self.repos.get_node(u'/tête/README.txt', 2)
        props = f.get_properties()
        self.assertIsNone(props.get('svn:eol-style'))
        self.assertEqual('A text.\n', f.get_content().read())
        self.assertEqual('A text.\n', f.get_processed_content().read())

    def test_get_file_content_with_native_eol_style(self):
        f = self.repos.get_node(u'/tête/README.txt', 3)
        props = f.get_properties()
        self.assertEqual('native', props.get('svn:eol-style'))

        self.repos.params['eol_style'] = 'native'
        self.assertEqual('A test.\n', f.get_content().read())
        self.assertEqual('A test.' + NATIVE_EOL,
                         f.get_processed_content().read())

        self.repos.params['eol_style'] = 'LF'
        self.assertEqual('A test.\n', f.get_content().read())
        self.assertEqual('A test.\n', f.get_processed_content().read())

        self.repos.params['eol_style'] = 'CRLF'
        self.assertEqual('A test.\n', f.get_content().read())
        self.assertEqual('A test.\r\n', f.get_processed_content().read())

        self.repos.params['eol_style'] = 'CR'
        self.assertEqual('A test.\n', f.get_content().read())
        self.assertEqual('A test.\r', f.get_processed_content().read())
        # check that the hint is stronger than the repos default
        self.assertEqual('A test.\r\n',
                         f.get_processed_content(eol_hint='CRLF').read())

    def test_get_file_content_with_native_eol_style_and_no_keywords_28(self):
        f = self.repos.get_node(u'/branches/v4/README.txt', 28)
        props = f.get_properties()
        self.assertEqual('native', props.get('svn:eol-style'))
        self.assertIsNone(props.get('svn:keywords'))

        self.assertEqual(
            'A test.\n' +
            '# $Rev$ is not substituted with no svn:keywords.\n',
            f.get_content().read())
        self.assertEqual(
            'A test.\r\n' +
            '# $Rev$ is not substituted with no svn:keywords.\r\n',
            f.get_processed_content(eol_hint='CRLF').read())

    def test_get_file_content_with_keyword_substitution_23(self):
        f = self.repos.get_node(u'/tête/Résumé.txt', 23)
        props = f.get_properties()
        self.assertEqual('Revision Author URL', props['svn:keywords'])
        self.assertEqual('''\
# Simple test for svn:keywords property substitution (#717)
# $Rev: 23 $:     Revision of last commit
# $Author: cboos $:  Author of last commit
# $Date$:    Date of last commit (not substituted)

Now with fixed width fields:
# $URL:: svn://test/t%C3%AAte/R%C3%A9sum%C3%A9.txt    $ the configured URL
# $HeadURL:: svn://test/t%C3%AAte/R%C3%A9sum%C3%A9.tx#$ same
# $URL:: svn://test/t%C#$ same, but truncated

En r\xe9sum\xe9 ... \xe7a marche.
'''.splitlines(), f.get_processed_content().read().splitlines())
    # Note: "En résumé ... ça marche." in the content is really encoded in
    #       latin1 in the file, and our substitutions are UTF-8 encoded...
    #       This is expected.

    def test_get_file_content_with_keyword_substitution_24(self):
        f = self.repos.get_node(u'/tête/Résumé.txt', 24)
        props = f.get_properties()
        self.assertEqual('Revision Author URL Id', props['svn:keywords'])
        self.assertEqual('''\
# Simple test for svn:keywords property substitution (#717)
# $Rev: 24 $:     Revision of last commit
# $Author: cboos $:  Author of last commit
# $Date$:    Date of last commit (now substituted)
# $Id: Résumé.txt 24 2013-04-27 14:38:50Z cboos $:      Combination

Now with fixed width fields:
# $URL:: svn://test/t%C3%AAte/R%C3%A9sum%C3%A9.txt    $ the configured URL
# $HeadURL:: svn://test/t%C3%AAte/R%C3%A9sum%C3%A9.tx#$ same
# $URL:: svn://test/t%C#$ same, but truncated
# $Header::                                           $ combination with URL

En r\xe9sum\xe9 ... \xe7a marche.
'''.splitlines(), f.get_processed_content().read().splitlines())

    @setlocale
    def test_get_file_content_with_keyword_substitution_25(self):
        f = self.repos.get_node(u'/tête/Résumé.txt', 25)
        props = f.get_properties()
        self.assertEqual('Revision Author URL Date Id Header',
                         props['svn:keywords'])
        self.assertEqual('''\
# Simple test for svn:keywords property substitution (#717)
# $Rev: 25 $:     Revision of last commit
# $Author: cboos $:  Author of last commit
# $Date: 2013-04-27 14:43:15 +0000 (Sat, 27 Apr 2013) $:    Date of last commit (now really substituted)
# $Id: Résumé.txt 25 2013-04-27 14:43:15Z cboos $:      Combination

Now with fixed width fields:
# $URL:: svn://test/t%C3%AAte/R%C3%A9sum%C3%A9.txt    $ the configured URL
# $HeadURL:: svn://test/t%C3%AAte/R%C3%A9sum%C3%A9.tx#$ same
# $URL:: svn://test/t%C#$ same, but truncated
# $Header:: svn://test/t%C3%AAte/R%C3%A9sum%C3%A9.txt#$ combination with URL

En r\xe9sum\xe9 ... \xe7a marche.
'''.splitlines(), f.get_processed_content().read().splitlines())

    @setlocale
    def test_get_file_content_with_keyword_substitution_30(self):
        self.maxDiff = None
        f = self.repos.get_node(u'/branches/v4/Résumé.txt', 30)
        props = f.get_properties()
        expected = [
            '# Simple test for svn:keywords property substitution (#717)',
            '# $Rev: 30 $:     Revision of last commit',
            '# $Author: jomae $:  Author of last commit',
            '# $Date: 2015-06-15 14:09:13 +0000 (Mon, 15 Jun 2015) $:    ' \
                'Date of last commit (now really substituted)',
            '# $Id: Résumé.txt 30 2015-06-15 14:09:13Z jomae $:      ' \
                'Combination',
            '',
            'Now with fixed width fields:',
            '# $URL:: svn://test/branches/v4/R%C3%A9sum%C3%A9.txt  $ ' \
                'the configured URL',
            '# $HeadURL:: svn://test/branches/v4/R%C3%A9sum%C3%A9.#$ same',
            '# $URL:: svn://test/bra#$ same, but truncated',
            '# $Header:: svn://test/branches/v4/R%C3%A9sum%C3%A9.t#$ ' \
                'combination with URL',
            '',
            'Overlapped keywords:',
            '# $Xxx$Rev: 30 $Xxx$',
            '# $Rev: 30 $Xxx$Rev: 30 $',
            '# $Rev: 30 $Rev$Rev: 30 $',
            '',
            'Custom keyword definitions (#11364)',
            '# $_Author: jomae $:',
            '# $_Basename: R\xc3\xa9sum\xc3\xa9.txt $:',
            '# $_ShortDate: 2015-06-15 14:09:13Z $:',
            '# $_LongDate: 2015-06-15 14:09:13 +0000 (Mon, 15 Jun 2015) $:',
            '# $_Path: branches/v4/R\xc3\xa9sum\xc3\xa9.txt $:',
            '# $_Rev: 30 $:',
            '# $_RootURL: svn://test $:',
            '# $_URL: svn://test/branches/v4/R%C3%A9sum%C3%A9.txt $:',
            '# $_Header: branches/v4/R\xc3\xa9sum\xc3\xa9.txt 30 ' \
                '2015-06-15 14:09:13Z jomae $:',
            '# $_Id: R\xc3\xa9sum\xc3\xa9.txt 30 ' \
                '2015-06-15 14:09:13Z jomae $:',
            '# $_Header2: branches/v4/R\xc3\xa9sum\xc3\xa9.txt 30 ' \
                '2015-06-15 14:09:13Z jomae $:',
            '# $_Id2: R\xc3\xa9sum\xc3\xa9.txt 30 ' \
                '2015-06-15 14:09:13Z jomae $:',
            '# $_t\xc3\xa9t\xc3\xa9: jomae $:',
            '# $42: jomae $:',
            '# $123456789012345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '123456789012345678901234567890123456789: j $:',
            '# $123456789012345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '1234567890123456789012345678901234567890:  $:',
            '# $123456789012345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901$:',
            '# $_TooLong: branches/v4/R\xc3\xa9sum\xc3\xa9.txt' \
                'branches/v4/R\xc3\xa9sum\xc3\xa9.txt' \
                'branches/v4/R\xc3\xa9sum\xc3\xa9.txt' \
                'branches/v4/R\xc3\xa9sum\xc3\xa9.txt' \
                'branches/v4/R\xc3\xa9sum\xc3\xa9.txt' \
                'branches/v4/R\xc3\xa9sum\xc3\xa9.txt' \
                'branches/v4/R\xc3\xa9sum\xc3\xa9.txt' \
                'branches/v4/R\xc3\xa9sum\xc3\xa9.txt' \
                'branches/v4/R\xc3\xa9sum\xc3\xa9.txt' \
                'branches/v4/R\xc3\xa9sum\xc3\xa9.txt' \
                'br $:',
            '',
            'Custom keyword definitions with fixed width',
            '# $123456789012345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '1234567890123456789012345678901234:: jomae $',
            '# $123456789012345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '1234567890123456789012345678901234::        $',
            '# $123456789012345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678:: j#$',
            '# $123456789012345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678901234567890' \
                '12345678901234567890123456789012345678::    $',
        ]
        self.assertEqual(expected,
                         f.get_processed_content().read().splitlines())

    @setlocale
    def test_get_file_content_with_keyword_substitution_31(self):
        """$Author$ is is the last user to change this file in the repository.
        Regression test for #12655.
        """
        self.assertEqual('john', self.repos.get_changeset(31).author)
        self.assertEqual('jomae', self.repos.get_changeset(26).author)
        f = self.repos.get_node(u'/tête/Résumé.txt', 31)
        self.assertEqual(31, f.rev)
        self.assertEqual(26, f.created_rev)
        props = f.get_properties()
        self.assertEqual('Revision Author URL Date Id Header',
                         props['svn:keywords'])
        self.assertEqual('''\
# Simple test for svn:keywords property substitution (#717)
# $Rev: 26 $:     Revision of last commit
# $Author: jomae $:  Author of last commit
# $Date: 2013-04-28 05:36:06 +0000 (Sun, 28 Apr 2013) $:    Date of last commit (now really substituted)
# $Id: Résumé.txt 26 2013-04-28 05:36:06Z jomae $:      Combination

Now with fixed width fields:
# $URL:: svn://test/t%C3%AAte/R%C3%A9sum%C3%A9.txt    $ the configured URL
# $HeadURL:: svn://test/t%C3%AAte/R%C3%A9sum%C3%A9.tx#$ same
# $URL:: svn://test/t%C#$ same, but truncated
# $Header:: svn://test/t%C3%AAte/R%C3%A9sum%C3%A9.txt#$ combination with URL

Overlapped keywords:
# $Xxx$Rev: 26 $Xxx$
# $Rev: 26 $Xxx$Rev: 26 $
# $Rev: 26 $Rev$Rev: 26 $

En r\xe9sum\xe9 ... \xe7a marche.
'''.splitlines(), f.get_processed_content().read().splitlines())

    def test_created_path_rev(self):
        node = self.repos.get_node(u'/tête/README3.txt', 15)
        self.assertEqual(15, node.rev)
        self.assertEqual(u'/tête/README3.txt', node.path)
        self.assertEqual(14, node.created_rev)
        self.assertEqual(u'tête/README3.txt', node.created_path)

    def test_created_path_rev_parent_copy(self):
        node = self.repos.get_node('/tags/v1/README.txt', 15)
        self.assertEqual(15, node.rev)
        self.assertEqual('/tags/v1/README.txt', node.path)
        self.assertEqual(3, node.created_rev)
        self.assertEqual(u'tête/README.txt', node.created_path)

    def test_get_annotations(self):
        # svn_client_blame2() requires a canonical uri since Subversion 1.7.
        # If the uri is not canonical, assertion raises (#11167).
        node = self.repos.get_node(u'/tête/R\xe9sum\xe9.txt', 25)
        self.assertEqual([23, 23, 23, 25, 24, 23, 23, 23, 23, 23, 24, 23, 20],
                         node.get_annotations())

    def test_get_annotations_lower_drive_letter(self):
        # If the drive letter in the uri is lower case on Windows, a
        # SubversionException raises (#10514).
        drive, tail = os.path.splitdrive(REPOS_PATH)
        repos_path = drive.lower() + tail
        DbRepositoryProvider(self.env).add_repository('lowercase', repos_path,
                                                      'direct-svnfs')
        repos = self.env.get_repository('lowercase')
        node = repos.get_node(u'/tête/R\xe9sum\xe9.txt', 25)
        self.assertEqual([23, 23, 23, 25, 24, 23, 23, 23, 23, 23, 24, 23, 20],
                         node.get_annotations())

    if os.name != 'nt':
        del test_get_annotations_lower_drive_letter

    def test_get_annotations_with_urlencoded_percent_sign(self):
        node = self.repos.get_node(u'/branches/t10386/READ%25ME.txt')
        self.assertEqual([14], node.get_annotations())

    def test_get_path_url(self):
        self.assertEqual('svn://test', self.repos.get_path_url('', 42))
        self.assertEqual('svn://test', self.repos.get_path_url('/', 42))
        self.assertEqual('svn://test/path/to/file.txt',
                         self.repos.get_path_url('path/to/file.txt', 42))
        self.assertEqual('svn://test/path/to/file.txt',
                         self.repos.get_path_url('/path/to/file.txt', 42))
        self.assertEqual('svn://test/trunk%25/Resume%25.txt',
                         self.repos.get_path_url('trunk%/Resume%.txt', 42))
        self.assertEqual('svn://test/trunk%23/Resume%23.txt',
                         self.repos.get_path_url('trunk#/Resume#.txt', 42))
        self.assertEqual('svn://test/trunk%3F/Resume%3F.txt',
                         self.repos.get_path_url('trunk?/Resume?.txt', 42))
        self.assertEqual('svn://test/trunk%40/Resume.txt%4042',
                         self.repos.get_path_url('trunk@/Resume.txt@42', 42))
        self.assertEqual('svn://test/tr%C3%BCnk/R%C3%A9sum%C3%A9.txt',
                         self.repos.get_path_url(u'trünk/Résumé.txt', 42))

    # Revision Log / node history

    def test_get_node_history(self):
        node = self.repos.get_node(u'/tête/README3.txt')
        history = node.get_history()
        self.assertEqual((u'tête/README3.txt', 14, 'copy'), history.next())
        self.assertEqual((u'tête/README2.txt', 6, 'copy'), history.next())
        self.assertEqual((u'tête/README.txt', 3, 'edit'), history.next())
        self.assertEqual((u'tête/README.txt', 2, 'add'), history.next())
        self.assertRaises(StopIteration, history.next)

    def test_get_node_history_limit(self):
        node = self.repos.get_node(u'/tête/README3.txt')
        history = node.get_history(2)
        self.assertEqual((u'tête/README3.txt', 14, 'copy'), history.next())
        self.assertEqual((u'tête/README2.txt', 6, 'copy'), history.next())
        self.assertRaises(StopIteration, history.next)

    def test_get_node_history_follow_copy(self):
        node = self.repos.get_node('/tags/v1/README.txt')
        history = node.get_history()
        self.assertEqual(('tags/v1/README.txt', 7, 'copy'), history.next())
        self.assertEqual((u'tête/README.txt', 3, 'edit'), history.next())
        self.assertEqual((u'tête/README.txt', 2, 'add'), history.next())
        self.assertRaises(StopIteration, history.next)

    def test_get_copy_ancestry(self):
        node = self.repos.get_node('/tags/v1/README.txt')
        ancestry = node.get_copy_ancestry()
        self.assertEqual([(u'tête/README.txt', 6)], ancestry)
        for path, rev in ancestry:
            self.repos.get_node(path, rev) # shouldn't raise NoSuchNode

        node = self.repos.get_node(u'/tête/README3.txt')
        ancestry = node.get_copy_ancestry()
        self.assertEqual([(u'tête/README2.txt', 13),
                          (u'tête/README.txt', 3)], ancestry)
        for path, rev in ancestry:
            self.repos.get_node(path, rev) # shouldn't raise NoSuchNode

        node = self.repos.get_node('/branches/v1x')
        ancestry = node.get_copy_ancestry()
        self.assertEqual([(u'tags/v1.1', 11),
                          (u'branches/v1x', 9),
                          (u'tags/v1', 7),
                          (u'tête', 6)], ancestry)
        for path, rev in ancestry:
            self.repos.get_node(path, rev) # shouldn't raise NoSuchNode

    def test_get_copy_ancestry_for_move(self):
        node = self.repos.get_node(u'/tête/dir1/dir2', 5)
        ancestry = node.get_copy_ancestry()
        self.assertEqual([(u'tête/dir2', 4)], ancestry)
        for path, rev in ancestry:
            self.repos.get_node(path, rev) # shouldn't raise NoSuchNode

    def test_get_branch_origin(self):
        node = self.repos.get_node('/tags/v1/README.txt')
        self.assertEqual(7, node.get_branch_origin())
        node = self.repos.get_node(u'/tête/README3.txt')
        self.assertEqual(14, node.get_branch_origin())
        node = self.repos.get_node('/branches/v1x')
        self.assertEqual(12, node.get_branch_origin())
        node = self.repos.get_node(u'/tête/dir1/dir2', 5)
        self.assertEqual(5, node.get_branch_origin())

    # Revision Log / path history

    def test_get_path_history(self):
        history = self.repos.get_path_history(u'/tête/README2.txt', None)
        self.assertEqual((u'tête/README2.txt', 14, 'delete'), history.next())
        self.assertEqual((u'tête/README2.txt', 6, 'copy'), history.next())
        self.assertEqual((u'tête/README.txt', 3, 'unknown'), history.next())
        self.assertRaises(StopIteration, history.next)

    def test_get_path_history_copied_file(self):
        history = self.repos.get_path_history('/tags/v1/README.txt', None)
        self.assertEqual(('tags/v1/README.txt', 7, 'copy'), history.next())
        self.assertEqual((u'tête/README.txt', 3, 'unknown'), history.next())
        self.assertRaises(StopIteration, history.next)

    def test_get_path_history_copied_dir(self):
        history = self.repos.get_path_history('/branches/v1x', None)
        self.assertEqual(('branches/v1x', 12, 'copy'), history.next())
        self.assertEqual(('tags/v1.1', 10, 'unknown'), history.next())
        self.assertEqual(('branches/v1x', 11, 'delete'), history.next())
        self.assertEqual(('branches/v1x', 9, 'edit'), history.next())
        self.assertEqual(('branches/v1x', 8, 'copy'), history.next())
        self.assertEqual(('tags/v1', 7, 'unknown'), history.next())
        self.assertRaises(StopIteration, history.next)

    # Diffs

    def _cmp_diff(self, expected, got):
        if expected[0]:
            old = self.repos.get_node(*expected[0])
            self.assertEqual((old.path, old.rev), (got[0].path, got[0].rev))
        if expected[1]:
            new = self.repos.get_node(*expected[1])
            self.assertEqual((new.path, new.rev), (got[1].path, got[1].rev))
        self.assertEqual(expected[2], (got[2], got[3]))

    def test_diff_file_different_revs(self):
        diffs = self.repos.get_changes(u'tête/README.txt', 2,
                                       u'tête/README.txt', 3)
        self._cmp_diff(((u'tête/README.txt', 2),
                        (u'tête/README.txt', 3),
                        (Node.FILE, Changeset.EDIT)), diffs.next())
        self.assertRaises(StopIteration, diffs.next)

    def test_diff_file_different_files(self):
        diffs = self.repos.get_changes('branches/v1x/README.txt', 12,
                                      'branches/v1x/README2.txt', 12)
        self._cmp_diff((('branches/v1x/README.txt', 12),
                        ('branches/v1x/README2.txt', 12),
                        (Node.FILE, Changeset.EDIT)), diffs.next())
        self.assertRaises(StopIteration, diffs.next)

    def test_diff_file_no_change(self):
        diffs = self.repos.get_changes(u'tête/README.txt', 7,
                                      'tags/v1/README.txt', 7)
        self.assertRaises(StopIteration, diffs.next)

    def test_diff_dir_different_revs(self):
        diffs = self.repos.get_changes(u'tête', 4, u'tête', 8)
        self._cmp_diff((None, (u'tête/README2.txt', 8),
                        (Node.FILE, Changeset.ADD)), diffs.next())
        self._cmp_diff((None, (u'tête/dir1/dir2', 8),
                        (Node.DIRECTORY, Changeset.ADD)), diffs.next())
        self._cmp_diff((None, (u'tête/dir1/dir3', 8),
                        (Node.DIRECTORY, Changeset.ADD)), diffs.next())
        self._cmp_diff(((u'tête/dir2', 4), None,
                        (Node.DIRECTORY, Changeset.DELETE)), diffs.next())
        self._cmp_diff(((u'tête/dir3', 4), None,
                        (Node.DIRECTORY, Changeset.DELETE)), diffs.next())
        self.assertRaises(StopIteration, diffs.next)

    def test_diff_dir_different_dirs(self):
        diffs = self.repos.get_changes(u'tête', 1, 'branches/v1x', 12)
        self._cmp_diff((None, ('branches/v1x/README.txt', 12),
                        (Node.FILE, Changeset.ADD)), diffs.next())
        self._cmp_diff((None, ('branches/v1x/README2.txt', 12),
                        (Node.FILE, Changeset.ADD)), diffs.next())
        self._cmp_diff((None, ('branches/v1x/dir1', 12),
                        (Node.DIRECTORY, Changeset.ADD)), diffs.next())
        self._cmp_diff((None, ('branches/v1x/dir1/dir2', 12),
                        (Node.DIRECTORY, Changeset.ADD)), diffs.next())
        self._cmp_diff((None, ('branches/v1x/dir1/dir3', 12),
                        (Node.DIRECTORY, Changeset.ADD)), diffs.next())
        self.assertRaises(StopIteration, diffs.next)

    def test_diff_dir_no_change(self):
        diffs = self.repos.get_changes(u'tête', 7,
                                      'tags/v1', 7)
        self.assertRaises(StopIteration, diffs.next)

    # Changesets

    def test_changeset_repos_creation(self):
        chgset = self.repos.get_changeset(0)
        self.assertEqual(0, chgset.rev)
        self.assertEqual('', chgset.message)
        self.assertEqual('', chgset.author)
        self.assertEqual(datetime(2005, 4, 1, 9, 57, 41, 312767, utc),
                         chgset.date)
        self.assertRaises(StopIteration, chgset.get_changes().next)

    def test_changeset_added_dirs(self):
        chgset = self.repos.get_changeset(1)
        self.assertEqual(1, chgset.rev)
        self.assertEqual('Initial directory layout.', chgset.message)
        self.assertEqual('john', chgset.author)
        self.assertEqual(datetime(2005, 4, 1, 10, 0, 52, 353248, utc),
                         chgset.date)

        changes = chgset.get_changes()
        self.assertEqual(('branches', Node.DIRECTORY, Changeset.ADD, None, -1),
                         changes.next())
        self.assertEqual(('tags', Node.DIRECTORY, Changeset.ADD, None, -1),
                         changes.next())
        self.assertEqual((u'tête', Node.DIRECTORY, Changeset.ADD, None, -1),
                         changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_changeset_file_edit(self):
        chgset = self.repos.get_changeset(3)
        self.assertEqual(3, chgset.rev)
        self.assertEqual('Fixed README.\n', chgset.message)
        self.assertEqual('kate', chgset.author)
        self.assertEqual(datetime(2005, 4, 1, 13, 24, 58, 234643, utc),
                         chgset.date)

        changes = chgset.get_changes()
        self.assertEqual((u'tête/README.txt', Node.FILE, Changeset.EDIT,
                          u'tête/README.txt', 2), changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_changeset_dir_moves(self):
        chgset = self.repos.get_changeset(5)
        self.assertEqual(5, chgset.rev)
        self.assertEqual('Moved directories.', chgset.message)
        self.assertEqual('kate', chgset.author)
        self.assertEqual(datetime(2005, 4, 1, 16, 25, 39, 658099, utc),
                         chgset.date)

        changes = chgset.get_changes()
        self.assertEqual((u'tête/dir1/dir2', Node.DIRECTORY, Changeset.MOVE,
                          u'tête/dir2', 4), changes.next())
        self.assertEqual((u'tête/dir1/dir3', Node.DIRECTORY, Changeset.MOVE,
                          u'tête/dir3', 4), changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_changeset_file_copy(self):
        chgset = self.repos.get_changeset(6)
        self.assertEqual(6, chgset.rev)
        self.assertEqual('More things to read', chgset.message)
        self.assertEqual('john', chgset.author)
        self.assertEqual(datetime(2005, 4, 1, 18, 56, 46, 985846, utc),
                         chgset.date)

        changes = chgset.get_changes()
        self.assertEqual((u'tête/README2.txt', Node.FILE, Changeset.COPY,
                          u'tête/README.txt', 3), changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_changeset_root_propset(self):
        chgset = self.repos.get_changeset(13)
        self.assertEqual(13, chgset.rev)
        self.assertEqual('Setting property on the repository_dir root',
                         chgset.message)
        changes = chgset.get_changes()
        self.assertEqual(('/', Node.DIRECTORY, Changeset.EDIT, '/', 12),
                         changes.next())
        self.assertEqual((u'tête', Node.DIRECTORY, Changeset.EDIT, u'tête', 6),
                         changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_changeset_base_path_rev(self):
        chgset = self.repos.get_changeset(9)
        self.assertEqual(9, chgset.rev)
        changes = chgset.get_changes()
        self.assertEqual(('branches/v1x/README.txt', Node.FILE,
                          Changeset.EDIT, u'tête/README.txt', 3),
                         changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_changeset_rename_and_edit(self):
        chgset = self.repos.get_changeset(14)
        self.assertEqual(14, chgset.rev)
        changes = chgset.get_changes()
        self.assertEqual((u'tête/README3.txt', Node.FILE,
                          Changeset.MOVE, u'tête/README2.txt', 13),
                         changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_changeset_edit_after_wc2wc_copy__original_deleted(self):
        chgset = self.repos.get_changeset(16)
        self.assertEqual(16, chgset.rev)
        changes = chgset.get_changes()
        self.assertEqual(('branches/v2', Node.DIRECTORY, Changeset.COPY,
                          'tags/v1.1', 14),
                         changes.next())
        self.assertEqual(('branches/v2/README2.txt', Node.FILE,
                          Changeset.EDIT, u'tête/README2.txt', 6),
                         changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_fancy_rename_double_delete(self):
        chgset = self.repos.get_changeset(19)
        self.assertEqual(19, chgset.rev)
        changes = chgset.get_changes()
        self.assertEqual((u'tête/mpp_proc', Node.DIRECTORY,
                          Changeset.MOVE, u'tête/Xprimary_proc', 18),
                         changes.next())
        self.assertEqual((u'tête/mpp_proc/Xprimary_pkg.vhd',
                          Node.FILE, Changeset.DELETE,
                          u'tête/Xprimary_proc/Xprimary_pkg.vhd', 18),
                         changes.next())
        self.assertEqual((u'tête/mpp_proc/Xprimary_proc', Node.DIRECTORY,
                          Changeset.COPY, u'tête/Xprimary_proc', 18),
                         changes.next())
        self.assertEqual((u'tête/mpp_proc/Xprimary_proc/Xprimary_pkg.vhd',
                          Node.FILE, Changeset.DELETE,
                          u'tête/Xprimary_proc/Xprimary_pkg.vhd', 18),
                         changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_copy_with_deletions_below_copy(self):
        """Regression test for #4900."""
        chgset = self.repos.get_changeset(22)
        self.assertEqual(22, chgset.rev)
        changes = chgset.get_changes()
        self.assertEqual((u'branches/v3', 'dir', 'copy',
                          u'tête', 21), changes.next())
        self.assertEqual((u'branches/v3/dir1', 'dir', 'delete',
                          u'tête/dir1', 21), changes.next())
        self.assertEqual((u'branches/v3/mpp_proc', 'dir', 'delete',
                          u'tête/mpp_proc', 21), changes.next())
        self.assertEqual((u'branches/v3/v2', 'dir', 'delete',
                          u'tête/v2', 21), changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_changeset_utf_8(self):
        chgset = self.repos.get_changeset(20)
        self.assertEqual(20, chgset.rev)
        self.assertEqual(u'Chez moi ça marche\n', chgset.message)
        self.assertEqual(u'Jonas Borgström', chgset.author)

    def test_canonical_repos_path(self):
        # Assertion `svn_dirent_is_canonical` with leading double slashes
        # in repository path if os.name == 'posix' (#10390)
        DbRepositoryProvider(self.env).add_repository(
            'canonical-path', '//' + REPOS_PATH.lstrip('/'), 'direct-svnfs')
        repos = self.env.get_repository('canonical-path')
        self.assertEqual(REPOS_PATH, repos.path)

    if os.name != 'posix':
        del test_canonical_repos_path

    def test_merge_prop_renderer_without_deleted_branches(self):
        context = _create_context(self.env)
        context = context(self.repos.get_node('branches/v1x', HEAD).resource)
        renderer = svn_prop.SubversionMergePropertyRenderer(self.env)
        props = {'svn:mergeinfo': u"""\
/tête:1-20,23-26
/branches/v3:22
/branches/v2:16
"""}
        result = Stream(renderer.render_property('svn:mergeinfo', 'browser',
                                                 context, props))

        node = unicode(result.select('//tr[1]//td[1]'))
        self.assertIn(' href="/trac.cgi/browser/repo/branches/v2?rev=%d"'
                      % HEAD, node)
        self.assertIn('>/branches/v2</a>', node)
        node = unicode(result.select('//tr[1]//td[2]'))
        self.assertIn(' title="16"', node)
        self.assertIn('>merged</a>', node)
        node = unicode(result.select('//tr[1]//td[3]'))
        self.assertIn(' title="No revisions"', node)
        self.assertIn('>eligible</span>', node)

        node = unicode(result.select('//tr[3]//td[1]'))
        self.assertIn(' href="/trac.cgi/browser/repo/%s?rev=%d"'
                      % ('t%C3%AAte', HEAD), node)
        self.assertIn(u'>/tête</a>', node)
        node = unicode(result.select('//tr[3]//td[2]'))
        self.assertIn(' title="1-20, 23-26"', node)
        self.assertIn(' href="/trac.cgi/log/repo/t%C3%AAte?revs=1-20%2C23-26"',
                      node)
        self.assertIn('>merged</a>', node)
        node = unicode(result.select('//tr[3]//td[3]'))
        self.assertIn(' title="21"', node)
        self.assertIn(' href="/trac.cgi/changeset/21/repo/t%C3%AAte"', node)
        self.assertIn('>eligible</a>', node)

        self.assertNotIn('(toggle deleted branches)', unicode(result))
        self.assertNotIn('False', unicode(result))  # See #12125

    def test_merge_prop_renderer_with_deleted_branches(self):
        context = _create_context(self.env)
        context = context(self.repos.get_node('branches/v1x', HEAD).resource)
        renderer = svn_prop.SubversionMergePropertyRenderer(self.env)
        props = {'svn:mergeinfo': u"""\
/tête:19
/branches/v3:22
/branches/deleted:1,3-5,22
"""}
        result = Stream(renderer.render_property('svn:mergeinfo', 'browser',
                                                 context, props))

        node = unicode(result.select('//tr[1]//td[1]'))
        self.assertIn(' href="/trac.cgi/browser/repo/branches/v3?rev=%d"'
                      % HEAD, node)
        self.assertIn('>/branches/v3</a>', node)
        node = unicode(result.select('//tr[1]//td[2]'))
        self.assertIn(' title="22"', node)
        self.assertIn('>merged</a>', node)
        node = unicode(result.select('//tr[1]//td[3]'))
        self.assertIn(' title="No revisions"', node)
        self.assertIn('>eligible</span>', node)

        node = unicode(result.select('//tr[2]//td[1]'))
        self.assertIn(' href="/trac.cgi/browser/repo/%s?rev=%d"'
                      % ('t%C3%AAte', HEAD), node)
        self.assertIn(u'>/tête</a>', node)
        node = unicode(result.select('//tr[2]//td[2]'))
        self.assertIn(' title="19"', node)
        self.assertIn(' href="/trac.cgi/changeset/19/repo/t%C3%AAte"', node)
        self.assertIn('>merged</a>', node)
        node = unicode(result.select('//tr[2]//td[3]'))
        self.assertIn(' title="13-14, 17-18, 20-21, 23-26"', node)
        self.assertIn(' href="/trac.cgi/log/repo/t%C3%AAte?revs='
                      '13-14%2C17-18%2C20-21%2C23-26"', node)
        self.assertIn('>eligible</a>', node)

        self.assertIn('(toggle deleted branches)', unicode(result))
        self.assertIn('<td>/branches/deleted</td>',
                      unicode(result.select('//tr[3]//td[1]')))
        self.assertIn(u'<td colspan="2">1,\u200b3-5,\u200b22</td>',
                      unicode(result.select('//tr[3]//td[2]')))

    def test_merge_prop_diff_renderer_added(self):
        context = _create_context(self.env)
        old_context = context(self.repos.get_node(u'tête', 20).resource)
        old_props = {'svn:mergeinfo': u"""\
/branches/v2:1,8-9,12-15
/branches/v1x:12
/branches/deleted:1,3-5,22
"""}
        new_context = context(self.repos.get_node(u'tête', 21).resource)
        new_props = {'svn:mergeinfo': u"""\
/branches/v2:1,8-9,12-16
/branches/v1x:12
/branches/deleted:1,3-5,22
"""}
        options = {}
        renderer = svn_prop.SubversionMergePropertyDiffRenderer(self.env)
        result = Stream(renderer.render_property_diff(
                'svn:mergeinfo', old_context, old_props, new_context,
                new_props, options))

        node = unicode(result.select('//tr[1]//td[1]'))
        self.assertIn(' href="/trac.cgi/browser/repo/branches/v2?rev=21"', node)
        self.assertIn('>/branches/v2</a>', node)
        node = unicode(result.select('//tr[1]//td[2]'))
        self.assertIn(' title="16"', node)
        self.assertIn(' href="/trac.cgi/changeset/16/repo/branches/v2"', node)

    def test_merge_prop_diff_renderer_wrong_mergeinfo(self):
        rev = HEAD
        context = _create_context(self.env)
        old_context = context(self.repos.get_node(u'tête', rev - 1).resource)
        old_mergeinfo = '/missing:12\n'
        new_context = context(self.repos.get_node(u'tête', rev).resource)
        new_mergeinfo = '/missing:12-15\n'
        renderer = svn_prop.SubversionMergePropertyDiffRenderer(self.env)
        result = Stream(renderer.render_property_diff(
            'svn:mergeinfo', old_context, {'svn:mergeinfo': old_mergeinfo},
            new_context, {'svn:mergeinfo': new_mergeinfo}, {}))

        node = unicode(result.select('//tr[1]//td[1]'))
        self.assertIn(' href="/trac.cgi/browser/repo/missing?rev=%d"'
                      % rev, node)
        self.assertIn('>/missing</a>', node)
        node = unicode(result.select('//tr[1]//td[2]'))
        self.assertIn(' title="13-15"', node)
        self.assertIn(' href="/trac.cgi/log/repo/missing?revs=13-15"', node)

    def test_merge_prop_diff_renderer_added_svnmerge_integrated(self):
        """Property diff of svnmerge-integrated property (from
        svnmerge.py, used prior to svn 1.5) is rendered correctly.
        """
        context = _create_context(self.env)
        old_context = context(self.repos.get_node(u'tête', 20).resource)
        old_props = {'svnmerge-integrated': u"""\
        /branches/v2:1,8-9,12-15 /branches/v1x:12 /branches/deleted:1,3-5,22
        """}
        new_context = context(self.repos.get_node(u'tête', 21).resource)
        new_props = {'svnmerge-integrated': u"""\
        /branches/v2:1,8-9,12-16 /branches/v1x:12 /branches/deleted:1,3-5,22
        """}

        renderer = svn_prop.SubversionMergePropertyDiffRenderer(self.env)
        result = Stream(renderer.render_property_diff(
            'svnmerge-integrated', old_context, old_props, new_context,
            new_props, {}))

        node = unicode(result.select('//tr[1]//td[1]'))
        self.assertIn(' href="/trac.cgi/browser/repo/branches/v2?rev=21"',
                      node)
        self.assertIn('>/branches/v2</a>', node)
        node = unicode(result.select('//tr[1]//td[2]'))
        self.assertIn(' title="16"', node)
        self.assertIn(' href="/trac.cgi/changeset/16/repo/branches/v2"',
                      node)

    def test_render_needslock(self):
        htdocs_location = 'http://assets.example.org/common'
        self.env.config.set('trac', 'htdocs_location', htdocs_location)
        context = _create_context(self.env)
        context.req.chrome['htdocs_location'] = htdocs_location
        context = context(self.repos.get_node(u'tête', HEAD).resource)
        renderer = svn_prop.SubversionPropertyRenderer(self.env)
        result = renderer.render_property('svn:needs-lock', None, context,
                                          {'svn:needs-lock': '*'})
        self.assertIn('src="http://assets.example.org/common/lock-locked.png"',
                      unicode(result))


class ScopedTests(object):

    def test_repos_normalize_path(self):
        self.assertEqual('/', self.repos.normalize_path('/'))
        self.assertEqual('/', self.repos.normalize_path(''))
        self.assertEqual('/', self.repos.normalize_path(None))
        self.assertEqual('dir1', self.repos.normalize_path('dir1'))
        self.assertEqual('dir1', self.repos.normalize_path('/dir1'))
        self.assertEqual('dir1', self.repos.normalize_path('dir1/'))
        self.assertEqual('dir1', self.repos.normalize_path('/dir1/'))

    def test_repos_normalize_rev(self):
        self.assertEqual(TETE, self.repos.normalize_rev('latest'))
        self.assertEqual(TETE, self.repos.normalize_rev('head'))
        self.assertEqual(TETE, self.repos.normalize_rev(''))
        self.assertEqual(TETE, self.repos.normalize_rev(None))
        self.assertEqual(5, self.repos.normalize_rev('5'))
        self.assertEqual(5, self.repos.normalize_rev(5))

    def test_rev_navigation(self):
        self.assertEqual(1, self.repos.oldest_rev)
        self.assertIsNone(self.repos.previous_rev(0))
        self.assertEqual(1, self.repos.previous_rev(2))
        self.assertEqual(TETE, self.repos.youngest_rev)
        self.assertEqual(2, self.repos.next_rev(1))
        self.assertEqual(3, self.repos.next_rev(2))
        # ...
        self.assertIsNone(self.repos.next_rev(TETE))

    def test_has_node(self):
        self.assertFalse(self.repos.has_node('/dir1', 3))
        self.assertTrue(self.repos.has_node('/dir1', 4))

    def test_get_node(self):
        node = self.repos.get_node('/dir1')
        self.assertEqual('dir1', node.name)
        self.assertEqual('/dir1', node.path)
        self.assertEqual(Node.DIRECTORY, node.kind)
        self.assertEqual(TETE, node.rev)
        self.assertEqual(5, node.created_rev)
        self.assertEqual(datetime(2005, 4, 1, 16, 25, 39, 658099, utc),
                         node.last_modified)
        node = self.repos.get_node('/README.txt')
        self.assertEqual('README.txt', node.name)
        self.assertEqual('/README.txt', node.path)
        self.assertEqual(Node.FILE, node.kind)
        self.assertEqual(TETE, node.rev)
        self.assertEqual(3, node.created_rev)
        self.assertEqual(datetime(2005, 4, 1, 13, 24, 58, 234643, utc),
                         node.last_modified)

    def test_get_node_specific_rev(self):
        node = self.repos.get_node('/dir1', 4)
        self.assertEqual('dir1', node.name)
        self.assertEqual('/dir1', node.path)
        self.assertEqual(Node.DIRECTORY, node.kind)
        self.assertEqual(4, node.rev)
        self.assertEqual(datetime(2005, 4, 1, 15, 42, 35, 450595, utc),
                         node.last_modified)
        node = self.repos.get_node('/README.txt', 2)
        self.assertEqual('README.txt', node.name)
        self.assertEqual('/README.txt', node.path)
        self.assertEqual(Node.FILE, node.kind)
        self.assertEqual(2, node.rev)
        self.assertEqual(datetime(2005, 4, 1, 13, 12, 18, 216267, utc),
                         node.last_modified)

    def test_get_dir_entries(self):
        node = self.repos.get_node('/')
        entries = node.get_entries()
        self.assertEqual('dir1', entries.next().name)
        self.assertEqual('mpp_proc', entries.next().name)
        self.assertEqual('v2', entries.next().name)
        self.assertEqual('README3.txt', entries.next().name)
        self.assertEqual(u'R\xe9sum\xe9.txt', entries.next().name)
        self.assertEqual('README.txt', entries.next().name)
        self.assertRaises(StopIteration, entries.next)

    def test_get_file_entries(self):
        node = self.repos.get_node('/README.txt')
        entries = node.get_entries()
        self.assertRaises(StopIteration, entries.next)

    def test_get_dir_content(self):
        node = self.repos.get_node('/dir1')
        self.assertIsNone(node.content_length)
        self.assertIsNone(node.content_type)
        self.assertIsNone(node.get_content())

    def test_get_file_content(self):
        node = self.repos.get_node('/README.txt')
        self.assertEqual(8, node.content_length)
        self.assertEqual('text/plain', node.content_type)
        self.assertEqual('A test.\n', node.get_content().read())

    def test_get_dir_properties(self):
        f = self.repos.get_node('/dir1')
        props = f.get_properties()
        self.assertEqual(0, len(props))

    def test_get_file_properties(self):
        f = self.repos.get_node('/README.txt')
        props = f.get_properties()
        self.assertEqual('native', props['svn:eol-style'])
        self.assertEqual('text/plain', props['svn:mime-type'])

    # Revision Log / node history

    def test_get_history_scope(self):
        """Regression test for #9504"""
        node = self.repos.get_node('/')
        history = list(node.get_history())
        self.assertEqual(('/', 1, 'add'), history[-1])
        initial_cset = self.repos.get_changeset(history[-1][1])
        self.assertEqual(1, initial_cset.rev)

    def test_get_node_history(self):
        node = self.repos.get_node('/README3.txt')
        history = node.get_history()
        self.assertEqual(('README3.txt', 14, 'copy'), history.next())
        self.assertEqual(('README2.txt', 6, 'copy'), history.next())
        self.assertEqual(('README.txt', 3, 'edit'), history.next())
        self.assertEqual(('README.txt', 2, 'add'), history.next())
        self.assertRaises(StopIteration, history.next)

    def test_get_node_history_follow_copy(self):
        node = self.repos.get_node('dir1/dir3', )
        history = node.get_history()
        self.assertEqual(('dir1/dir3', 5, 'copy'), history.next())
        self.assertEqual(('dir3', 4, 'add'), history.next())
        self.assertRaises(StopIteration, history.next)

    def test_get_copy_ancestry(self):
        node = self.repos.get_node(u'/README3.txt')
        ancestry = node.get_copy_ancestry()
        self.assertEqual([(u'README2.txt', 13),
                          (u'README.txt', 3)], ancestry)
        for path, rev in ancestry:
            self.repos.get_node(path, rev) # shouldn't raise NoSuchNode

    def test_get_copy_ancestry_for_move(self):
        node = self.repos.get_node(u'/dir1/dir2', 5)
        ancestry = node.get_copy_ancestry()
        self.assertEqual([(u'dir2', 4)], ancestry)
        for path, rev in ancestry:
            self.repos.get_node(path, rev) # shouldn't raise NoSuchNode

    def test_get_branch_origin(self):
        node = self.repos.get_node(u'/README3.txt')
        self.assertEqual(14, node.get_branch_origin())
        node = self.repos.get_node(u'/dir1/dir2', 5)
        self.assertEqual(5, node.get_branch_origin())

    # Revision Log / path history

    def test_get_path_history(self):
        history = self.repos.get_path_history('dir3', None)
        self.assertEqual(('dir3', 5, 'delete'), history.next())
        self.assertEqual(('dir3', 4, 'add'), history.next())
        self.assertRaises(StopIteration, history.next)

    def test_get_path_history_copied_file(self):
        history = self.repos.get_path_history('README3.txt', None)
        self.assertEqual(('README3.txt', 14, 'copy'), history.next())
        self.assertEqual(('README2.txt', 6, 'unknown'), history.next())
        self.assertRaises(StopIteration, history.next)

    def test_get_path_history_copied_dir(self):
        history = self.repos.get_path_history('dir1/dir3', None)
        self.assertEqual(('dir1/dir3', 5, 'copy'), history.next())
        self.assertEqual(('dir3', 4, 'unknown'), history.next())
        self.assertRaises(StopIteration, history.next)

    def test_changeset_repos_creation(self):
        chgset = self.repos.get_changeset(0)
        self.assertEqual(0, chgset.rev)
        self.assertEqual('', chgset.message)
        self.assertEqual('', chgset.author)
        self.assertEqual(datetime(2005, 4, 1, 9, 57, 41, 312767, utc),
                         chgset.date)
        self.assertRaises(StopIteration, chgset.get_changes().next)

    def test_changeset_added_dirs(self):
        chgset = self.repos.get_changeset(4)
        self.assertEqual(4, chgset.rev)
        self.assertEqual('More directories.', chgset.message)
        self.assertEqual('john', chgset.author)
        self.assertEqual(datetime(2005, 4, 1, 15, 42, 35, 450595, utc),
                         chgset.date)

        changes = chgset.get_changes()
        self.assertEqual(('dir1', Node.DIRECTORY, 'add', None, -1),
                         changes.next())
        self.assertEqual(('dir2', Node.DIRECTORY, 'add', None, -1),
                         changes.next())
        self.assertEqual(('dir3', Node.DIRECTORY, 'add', None, -1),
                         changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_changeset_file_edit(self):
        chgset = self.repos.get_changeset(3)
        self.assertEqual(3, chgset.rev)
        self.assertEqual('Fixed README.\n', chgset.message)
        self.assertEqual('kate', chgset.author)
        self.assertEqual(datetime(2005, 4, 1, 13, 24, 58, 234643, utc),
                         chgset.date)

        changes = chgset.get_changes()
        self.assertEqual(('README.txt', Node.FILE, Changeset.EDIT,
                          'README.txt', 2), changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_changeset_dir_moves(self):
        chgset = self.repos.get_changeset(5)
        self.assertEqual(5, chgset.rev)
        self.assertEqual('Moved directories.', chgset.message)
        self.assertEqual('kate', chgset.author)
        self.assertEqual(datetime(2005, 4, 1, 16, 25, 39, 658099, utc),
                         chgset.date)

        changes = chgset.get_changes()
        self.assertEqual(('dir1/dir2', Node.DIRECTORY, Changeset.MOVE,
                          'dir2', 4), changes.next())
        self.assertEqual(('dir1/dir3', Node.DIRECTORY, Changeset.MOVE,
                          'dir3', 4), changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_changeset_file_copy(self):
        chgset = self.repos.get_changeset(6)
        self.assertEqual(6, chgset.rev)
        self.assertEqual('More things to read', chgset.message)
        self.assertEqual('john', chgset.author)
        self.assertEqual(datetime(2005, 4, 1, 18, 56, 46, 985846, utc),
                         chgset.date)

        changes = chgset.get_changes()
        self.assertEqual(('README2.txt', Node.FILE, Changeset.COPY,
                          'README.txt', 3), changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_changeset_root_propset(self):
        chgset = self.repos.get_changeset(13)
        self.assertEqual(13, chgset.rev)
        self.assertEqual('Setting property on the repository_dir root',
                         chgset.message)
        changes = chgset.get_changes()
        self.assertEqual(('/', Node.DIRECTORY, Changeset.EDIT, '/', 6),
                         changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_changeset_copy_from_outside_and_delete(self):
        chgset = self.repos.get_changeset(21)
        self.assertEqual(21, chgset.rev)
        self.assertEqual('copy from outside of the scope + delete',
                         chgset.message)
        changes = chgset.get_changes()
        self.assertEqual(('v2', Node.DIRECTORY, Changeset.ADD, None, -1),
                         changes.next())
        self.assertEqual(('v2/README2.txt', Node.FILE, Changeset.DELETE,
                          None, -1), changes.next())
        self.assertEqual(('v2/dir1', Node.DIRECTORY, Changeset.DELETE,
                          None, -1), changes.next())
        self.assertRaises(StopIteration, changes.next)


class RecentPathScopedTests(object):

    def test_rev_navigation(self):
        self.assertFalse(self.repos.has_node('/', 1))
        self.assertFalse(self.repos.has_node('/', 2))
        self.assertFalse(self.repos.has_node('/', 3))
        self.assertTrue(self.repos.has_node('/', 4))
        # We can't make this work anymore because of #5213.
        # self.assertEqual(4, self.repos.oldest_rev)
        self.assertEqual(1, self.repos.oldest_rev) # should really be 4...
        self.assertIsNone(self.repos.previous_rev(4))


class NonSelfContainedScopedTests(object):

    def test_mixed_changeset(self):
        chgset = self.repos.get_changeset(7)
        self.assertEqual(7, chgset.rev)
        changes = chgset.get_changes()
        self.assertEqual(('/', Node.DIRECTORY, Changeset.ADD, None, -1),
                         changes.next())
        self.assertRaises(TracError, lambda: self.repos.get_node(None, 6))


class AnotherNonSelfContainedScopedTests(object):

    def test_mixed_changeset_with_edit(self):
        chgset = self.repos.get_changeset(9)
        self.assertEqual(9, chgset.rev)
        changes = chgset.get_changes()
        self.assertEqual(('v1x/README.txt', Node.FILE, Changeset.EDIT,
                          'v1x/README.txt', 8),
                         changes.next())


class ExternalsPropertyTests(object):

    def _xpath_text(self, stream, path):
        return unicode(stream.select(path))

    def _modify_repository(self, reponame, changes):
        DbRepositoryProvider(self.env).modify_repository(reponame, changes)

    def _set_tracini_externals(self, *values):
        config = self.env.config
        for idx, value in enumerate(values):
            config.set('svn:externals', str(idx), value)

    def _render(self, *values):
        props = {'svn:externals': '\n'.join(values)}
        renderer = svn_prop.SubversionPropertyRenderer(self.env)
        context = RenderingContext(Resource('repository', REPOS_NAME)
                                   .child('source', 'build/posix', 42))
        return renderer.render_property('svn:externals', None, context, props)

    def _parse_result(self, result):
        result = Stream(result)
        idx = 1
        items = []
        while True:
            if not unicode(result.select('//li[%d]' % idx)):
                break
            items.append(dict((key, unicode(result.select('//li[%d]/a/%s' %
                                                          (idx, key))))
                              for key in ('text()', '@href', '@title')))
            idx += 1
        return items

    def test_match_property(self):
        renderer = svn_prop.SubversionPropertyRenderer(self.env)
        rv = renderer.match_property('svn:externals', None)
        self.assertTrue(1 <= rv < 10000)

    def test_render_property_without_tracini(self):
        result = self._parse_result(self._render(
            'blah svn://server/repos1',
            'vendor http://example.org/svn/eng-soft'))
        self.assertEqual({'text()': 'blah', '@href': '',
                          '@title': 'No svn:externals configured in trac.ini'},
                         result[0])
        self.assertEqual({'text()': 'vendor',
                          '@href': 'http://example.org/svn/eng-soft',
                          # XXX           v should be "//"
                          '@title': 'http:/example.org/svn/eng-soft'},
                         result[1])
        self.assertEqual(2, len(result))

    def test_render_property_non_absolute_url(self):
        externals = ['blah1 ../src', 'blah2 ^/src', 'blah3 /svn/trunk',
                     'blah4 //localhost/svn']
        result = self._parse_result(self._render(*externals))
        self.assertEqual([{'text()': externals[0], '@href': '', '@title': ''},
                          {'text()': externals[1], '@href': '', '@title': ''},
                          {'text()': externals[2], '@href': '', '@title': ''},
                          {'text()': externals[3], '@href': '', '@title': ''}],
                         result)

    def test_render_property_comment(self):
        result = self._parse_result(self._render(
            '   # For blah',
            'blah svn://server/repos1',
            '',
            '   # path rev url .....',
            'vendor http://example.org/svn/eng-soft'))
        self.assertEqual({'text()': '   # For blah', '@href': '',
                          '@title': ''}, result[0])
        self.assertEqual('blah', result[1]['text()'])
        self.assertEqual({'text()': '   # path rev url .....', '@href': '',
                          '@title': ''}, result[2])
        self.assertEqual('vendor', result[3]['text()'])
        self.assertEqual(4, len(result))

    def test_render_property_with_tracini(self):
        self._set_tracini_externals(
            'svn://server/repos1 http://trac/proj1/browser/$path?rev=$rev',
            'http://example.org/svn/eng-soft '
                'http://example.org/trac/eng-soft/browser/$path?rev=$rev')
        result = self._parse_result(self._render(
            'blah          svn://server/repos1',
            'blah-doc      svn://server/repos1/doc',
            'blah-r42 -r42 svn://server/repos1/branches/1.0-stable',
            'vendor        http://example.org/svn/eng-soft'))
        self.assertEqual({'text()': 'blah in svn://server/repos1',
                          '@href': 'http://trac/proj1/browser/?rev=',
                          '@title': ' in svn://server/repos1'}, result[0])
        self.assertEqual({'text()': 'blah-doc in svn://server/repos1',
                          '@href': 'http://trac/proj1/browser/doc?rev=',
                          '@title': 'doc in svn://server/repos1'}, result[1])
        self.assertEqual({'text()': 'blah-r42 at revision 42 in '
                                    'svn://server/repos1',
                          '@href': 'http://trac/proj1/browser/branches/'
                                   '1.0-stable?rev=42',
                          '@title': 'branches/1.0-stable at revision 42 in '
                                    'svn://server/repos1'}, result[2])
        self.assertEqual({
            'text()': 'vendor in http://example.org/svn/eng-soft',
            '@href': 'http://example.org/trac/eng-soft/browser/?rev=',
            '@title': ' in http://example.org/svn/eng-soft'}, result[3])
        self.assertEqual(4, len(result))


# -- Test cases for SubversionRepository

class SubversionRepositoryTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        repositories = self.env.config['repositories']
        dbprovider = DbRepositoryProvider(self.env)
        dbprovider.add_repository(REPOS_NAME, self.path, 'direct-svnfs')
        dbprovider.modify_repository(REPOS_NAME, {'url': URL})
        self.repos = self.env.get_repository(REPOS_NAME)


    def tearDown(self):
        self.repos.close()
        self.repos = None
        # clear cached repositories to avoid TypeError on termination (#11505)
        RepositoryManager(self.env).reload_repositories()
        self.env.reset_db()
        # needed to avoid issue with 'WindowsError: The process cannot access
        # the file ... being used by another process: ...\rep-cache.db'
        self.env.shutdown(get_thread_id())


# -- Test cases for SvnCachedRepository

class SvnCachedRepositoryTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        dbprovider = DbRepositoryProvider(self.env)
        dbprovider.add_repository(REPOS_NAME, self.path, 'svn')
        dbprovider.modify_repository(REPOS_NAME, {'url': URL})
        self.repos = self.env.get_repository(REPOS_NAME)
        self.repos.sync()

    def tearDown(self):
        self.env.reset_db()
        self.repos.close()
        self.repos = None
        # clear cached repositories to avoid TypeError on termination (#11505)
        RepositoryManager(self.env).reload_repositories()


class SubversionConnectorTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.repos_path = tempfile.mkdtemp(prefix='trac-svnrepos-')
        self.dbprovider = DbRepositoryProvider(self.env)
        pool = core.svn_pool_create(None)
        repos.svn_repos_create(self.repos_path, '', '', None, None, pool)
        self.dbprovider.add_repository(REPOS_NAME, self.repos_path, 'svn')

    def tearDown(self):
        self.env.reset_db()
        # clear cached repositories to avoid TypeError on termination (#11505)
        RepositoryManager(self.env).reload_repositories()
        repos.svn_repos_delete(self.repos_path)

    def _svn_version_from_system_info(self):
        svn_version = None
        for name, version in self.env.get_systeminfo():
            if name == 'Subversion':
                svn_version = version
        return svn_version

    def test_get_system_info(self):
        self.assertIsNotNone(self._svn_version_from_system_info())


def test_suite():
    global REPOS_PATH
    suite = unittest.TestSuite()
    if has_svn:
        REPOS_PATH = tempfile.mkdtemp(prefix='trac-svnrepos-')
        os.rmdir(REPOS_PATH)
        tests = [(NormalTests, ''),
                 (ScopedTests, u'/tête'),
                 (RecentPathScopedTests, u'/tête/dir1'),
                 (NonSelfContainedScopedTests, '/tags/v1'),
                 (AnotherNonSelfContainedScopedTests, '/branches'),
                 (ExternalsPropertyTests, ''),
                 ]
        skipped = {
            'SvnCachedRepositoryNormalTests': [
                'test_changeset_repos_creation',
                ],
            'SvnCachedRepositoryScopedTests': [
                'test_changeset_repos_creation',
                'test_rev_navigation',
                ],
            }
        for test, scope in tests:
            tc = new.classobj('SubversionRepository' + test.__name__,
                              (SubversionRepositoryTestCase, test),
                              {'path': REPOS_PATH + scope})
            suite.addTest(unittest.makeSuite(
                tc, suiteClass=SubversionRepositoryTestSetup))
            tc = new.classobj('SvnCachedRepository' + test.__name__,
                              (SvnCachedRepositoryTestCase, test),
                              {'path': REPOS_PATH + scope})
            for skip in skipped.get(tc.__name__, []):
                setattr(tc, skip, lambda self: None) # no skip, so we cheat...
            suite.addTest(unittest.makeSuite(
                tc, suiteClass=SubversionRepositoryTestSetup))
        suite.addTest(unittest.makeSuite(SubversionConnectorTestCase))
    else:
        print("SKIP: tracopt/versioncontrol/svn/tests/svn_fs.py (no svn "
              "bindings)")
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
