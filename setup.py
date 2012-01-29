#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2012 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import sys

from setuptools import setup, find_packages

min_python = (2, 4)
if sys.version_info < min_python:
    print "Trac requires Python %d.%d or later" % min_python
    sys.exit(1)
if sys.version_info >= (3,):
    print "Trac doesn't support Python 3 (yet)"
    sys.exit(1)

extra = {}

try:
    import babel
    
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

    from trac.dist import get_l10n_js_cmdclass
    extra['cmdclass'] = get_l10n_js_cmdclass()

except ImportError:
    pass

try:
    import genshi
except ImportError:
    print "Genshi is needed by Trac setup, pre-installing"
    # give some context to the warnings we might get when installing Genshi


setup(
    name = 'Trac',
    version = '0.12.3',
    description = 'Integrated SCM, wiki, issue tracker and project environment',
    long_description = """
Trac is a minimalistic web-based software project management and bug/issue
tracking system. It provides an interface to the Subversion revision control
systems, an integrated wiki, flexible issue tracking and convenient report
facilities.
""",
    author = 'Edgewall Software',
    author_email = 'trac-dev@googlegroups.com',
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

    setup_requires = [
        'Genshi>=0.6,<0.7dev',
    ],
    install_requires = [
        'setuptools>=0.6b1',
        'Genshi>=0.6,<0.7dev',
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
