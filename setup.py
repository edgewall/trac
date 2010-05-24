#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os
import re

from setuptools import setup, find_packages

extra = {}

try:
    import babel

    from distutils import log
    from distutils.cmd import Command
    from distutils.errors import DistutilsOptionError
    from babel.support import Translations
    class generate_messages_js(Command):
        """Generating message javascripts command for use ``setup.py`` scripts.
        """

        description = 'generate message javascript files from binary MO files'
        user_options = [
            ('domain=', 'D',
             "domain of PO file (default 'messages')"),
            ('input-dir=', 'I',
             'path to base directory containing the catalogs'),
            ('input-file=', 'i',
             'name of the input file'),
            ('output-dir=', 'O',
             "name of the output directory"),
            ('output-file=', 'o',
             "name of the output file (default "
             "'<output_dir>/<locale>.js')"),
            ('locale=', 'l',
             'locale of the catalog to compile'),
        ]

        def initialize_options(self):
            self.domain = 'messages'
            self.input_dir = None
            self.input_file = None
            self.output_dir = None
            self.output_file = None
            self.locale = None

        def finalize_options(self):
            if not self.input_file and not self.input_dir:
                raise DistutilsOptionError('you must specify either the input '
                                           'file or directory')
            if not self.output_file and not self.output_dir:
                raise DistutilsOptionError('you must specify either the '
                                           'output file or directory')

        def run(self):
            mo_files = []
            js_files = []

            def js_path(dir, locale):
                return os.path.join(dir, locale + '.js')

            if not self.input_file:
                if self.locale:
                    mo_files.append((self.locale,
                                     os.path.join(self.input_dir, self.locale,
                                                  'LC_MESSAGES',
                                                  self.domain + '.mo')))
                    js_files.append(js_path(self.output_dir, self.locale))
                else:
                    for locale in os.listdir(self.input_dir):
                        mo_file = os.path.join(self.input_dir, locale,
                                               'LC_MESSAGES',
                                               self.domain + '.mo')
                        if os.path.exists(mo_file):
                            mo_files.append((locale, mo_file))
                            js_files.append(js_path(self.output_dir, locale))
            else:
                mo_files.append((self.locale, self.input_file))
                if self.output_file:
                    js_files.append(self.output_file)
                else:
                    js_files.append(js_path(self.output_dir, locale))

            if not mo_files:
                raise DistutilsOptionError('no compiled catalogs found')

            if not os.path.isdir(self.output_dir):
                os.mkdir(self.output_dir)

            for idx, (locale, mo_file) in enumerate(mo_files):
                js_file = js_files[idx]
                log.info('generating messages javascript %r to %r',
                         mo_file, js_file)

                infile = open(mo_file, 'rb')
                try:
                    t = Translations(infile, self.domain)
                    catalog = t._catalog
                finally:
                    infile.close()

                outfile = open(js_file, 'w')
                try:
                    write_js(outfile, catalog, self.domain, locale)
                finally:
                    outfile.close()

    def write_js(fileobj, catalog, domain, locale):
        data = {'domain': domain, 'locale': locale}

        messages = {}
        for msgid, msgstr in catalog.iteritems():
            if isinstance(msgid, (list, tuple)):
                messages.setdefault(msgid[0], {})
                messages[msgid[0]][msgid[1]] = msgstr
            elif msgid:
                messages[msgid] = msgstr
            else:
                for line in msgstr.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if ':' not in line:
                        continue
                    name, val = line.split(':', 1)
                    name = name.strip().lower()
                    if name == 'plural-forms':
                        data['plural_expr'] = pluralexpr(val)
                        break
        data['messages'] = messages

        fileobj.write('// Generated messages javascript file '
                      'from compiled MO file\n')
        fileobj.write('babel.Translations.load(')
        fileobj.write(to_json(data))
        fileobj.write(').install();\n')

    def pluralexpr(forms):
        match = re.search(r'\bplural\s*=\s*([^;]+)', forms)
        if not match:
            raise ValueError('Failed to parse plural_forms %r' % (forms,))
        return match.group(1)

    def to_json_compat(val, **kwargs):
        if isinstance(val, basestring):
            return _escape_string(val)
        if val is None:
            return 'null'
        if val is True:
            return 'true'
        if val is False:
            return 'false'
        if isinstance(val, (int, long)):
            return str(val)
        if isinstance(val, float):
            return repr(val)
        if isinstance(val, (list, tuple)):
            return '[%s]' % ', '.join([to_json_compat(v) for v in val])
        if isinstance(val, dict):
            return '{%s}' % ', '.join(['%s: %s' % (to_json_compat(k),
                                                   to_json_compat(v))
                                       for k, v in val.iteritems()])

    _json_escape = {'\\': '\\\\', '"': '\\"', '\b': '\\b', '\f': '\\f',
                    '\n': '\\n', '\r': '\\r', '\t': '\\t', "'": "\\'"}
    _json_pattern = re.compile(r'[^\x20-\x7f]')

    def _escape_string(val):
        def replace(match):
            ch = match.group(0)
            if ch in _json_escape:
                return _json_escape[ch]
            return r'\u%04x' % ord(ch)
        return _json_pattern.sub(replace, val)

    try:
        from json import dumps as to_json
    except ImportError:
        try:
            from simplejson.json import dumps as to_json
        except:
            to_json = to_json_compat

    from babel.messages.frontend \
            import extract_messages, init_catalog, compile_catalog, \
                   update_catalog
    extractors = [
        ('**.py',                'python', None),
        ('**/templates/**.html', 'genshi', None),
        ('**/templates/**.txt',  'genshi',
         {'template_class': 'genshi.template:NewTextTemplate'}),
    ]
    extra['message_extractors'] = {
        'trac': extractors,
        'tracopt': extractors,
    }
    cmdclass = {
        'extract_messages_js': extract_messages,
        'init_catalog_js': init_catalog,
        'compile_catalog_js': compile_catalog,
        'update_catalog_js': update_catalog,
        'generate_messages_js': generate_messages_js,
    }
    extra['cmdclass'] = cmdclass

    # 'bdist_wininst' runs a 'build', so make the latter 
    # run a 'compile_catalog' before 'build_py'
    from distutils.command.build import build
    build.sub_commands.insert(0, ('generate_messages_js', lambda x: True))
    build.sub_commands.insert(0, ('compile_catalog_js', lambda x: True))
    build.sub_commands.insert(0, ('compile_catalog', lambda x: True))

    # 'bdist_egg' isn't that nice, all it does is an 'install_lib'
    from setuptools.command.install_lib import install_lib as _install_lib
    class install_lib(_install_lib): # playing setuptools' own tricks ;-)
        def run(self):
            self.run_command('compile_catalog')
            self.run_command('compile_catalog_js')
            self.run_command('generate_messages_js')
            _install_lib.run(self)
    cmdclass['install_lib'] = install_lib
except ImportError:
    pass

setup(
    name = 'Trac',
    version = '0.12',
    description = 'Integrated SCM, wiki, issue tracker and project environment',
    long_description = """
Trac is a minimalistic web-based software project management and bug/issue
tracking system. It provides an interface to the Subversion revision control
systems, an integrated wiki, flexible issue tracking and convenient report
facilities.
""",
    author = 'Edgewall Software',
    author_email = 'info@edgewall.com',
    license = 'BSD',
    url = 'http://trac.edgewall.org/',
    download_url = 'http://trac.edgewall.org/wiki/TracDownload',
    classifiers = [
        'Environment :: Web Environment',
        'Framework :: Trac',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Bug Tracking',
        'Topic :: Software Development :: Version Control',
    ],

    packages = find_packages(exclude=['*.tests']),
    package_data = {
        '': ['templates/*'],
        'trac': ['htdocs/*.*', 'htdocs/README', 'htdocs/js/*.*',
                 'htdocs/js/messages/*.*', 'htdocs/css/*.*',
                 'htdocs/guide/*', 'locale/*/LC_MESSAGES/messages.mo'],
        'trac.wiki': ['default-pages/*'],
        'trac.ticket': ['workflows/*.ini'],
    },

    test_suite = 'trac.test.suite',
    zip_safe = True,

    install_requires = [
        'setuptools>=0.6b1',
        'Genshi>=0.6',
    ],
    extras_require = {
        'Babel': ['Babel>=0.9.5'],
        'Pygments': ['Pygments>=0.6'],
        'reST': ['docutils>=0.3'],
        'SilverCity': ['SilverCity>=0.9.4'],
        'Textile': ['textile>=2.0'],
    },

    entry_points = """
        [console_scripts]
        trac-admin = trac.admin.console:run
        tracd = trac.web.standalone:main

        [trac.plugins]
        trac.about = trac.about
        trac.admin.console = trac.admin.console
        trac.admin.web_ui = trac.admin.web_ui
        trac.attachment = trac.attachment
        trac.db.mysql = trac.db.mysql_backend
        trac.db.postgres = trac.db.postgres_backend
        trac.db.sqlite = trac.db.sqlite_backend
        trac.mimeview.patch = trac.mimeview.patch
        trac.mimeview.pygments = trac.mimeview.pygments[Pygments]
        trac.mimeview.rst = trac.mimeview.rst[reST]
        trac.mimeview.silvercity = trac.mimeview.silvercity[SilverCity]
        trac.mimeview.txtl = trac.mimeview.txtl[Textile]
        trac.prefs = trac.prefs.web_ui
        trac.search = trac.search.web_ui
        trac.ticket.admin = trac.ticket.admin
        trac.ticket.query = trac.ticket.query
        trac.ticket.report = trac.ticket.report
        trac.ticket.roadmap = trac.ticket.roadmap
        trac.ticket.web_ui = trac.ticket.web_ui
        trac.timeline = trac.timeline.web_ui
        trac.versioncontrol.admin = trac.versioncontrol.admin
        trac.versioncontrol.svn_authz = trac.versioncontrol.svn_authz
        trac.versioncontrol.svn_fs = trac.versioncontrol.svn_fs
        trac.versioncontrol.svn_prop = trac.versioncontrol.svn_prop
        trac.versioncontrol.web_ui = trac.versioncontrol.web_ui
        trac.web.auth = trac.web.auth
        trac.web.session = trac.web.session
        trac.wiki.admin = trac.wiki.admin
        trac.wiki.interwiki = trac.wiki.interwiki
        trac.wiki.macros = trac.wiki.macros
        trac.wiki.web_ui = trac.wiki.web_ui
        trac.wiki.web_api = trac.wiki.web_api
        tracopt.mimeview.enscript = tracopt.mimeview.enscript
        tracopt.mimeview.php = tracopt.mimeview.php
        tracopt.perm.authz_policy = tracopt.perm.authz_policy
        tracopt.perm.config_perm_provider = tracopt.perm.config_perm_provider
        tracopt.ticket.commit_updater = tracopt.ticket.commit_updater
        tracopt.ticket.deleter = tracopt.ticket.deleter
    """,

    **extra
)
