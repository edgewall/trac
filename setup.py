#!/usr/bin/env python
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

import sys

from setuptools import setup, find_packages

min_python = (2, 7)
if sys.version_info < min_python:
    print("Trac requires Python %d.%d or later" % min_python)
    sys.exit(1)
if sys.version_info >= (3,):
    print("Trac doesn't support Python 3 (yet)")
    sys.exit(1)

extra = {}

try:
    import babel

    from trac.dist import get_l10n_trac_cmdclass
    extra['cmdclass'] = get_l10n_trac_cmdclass()

except ImportError:
    pass

try:
    import jinja2
except ImportError:
    print("Jinja2 is needed by Trac setup, pre-installing")
    # give some context to the warnings we might get when installing Jinja2


def readme():
    # Don't use context manager (comment:21:ticket:12578)
    f = open('README.rst')
    content = f.read()
    f.close()
    return content


setup(
    name = 'Trac',
    version = '1.3.3',
    description = 'Integrated SCM, wiki, issue tracker and project environment',
    long_description = readme(),
    author = 'Edgewall Software',
    author_email = 'trac-dev@googlegroups.com',
    license = 'BSD',
    url = 'https://trac.edgewall.org/',
    download_url = 'https://trac.edgewall.org/wiki/TracDownload',
    classifiers = [
        'Environment :: Web Environment',
        'Framework :: Trac',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Topic :: Software Development :: Bug Tracking',
        'Topic :: Software Development :: Version Control',
    ],

    packages = find_packages(exclude=['*.tests', 'tests.*', '*.tests.*']),
    package_data = {
        '': ['templates/*.*', 'templates/genshi/*'],
        'trac': ['htdocs/*.*', 'htdocs/README', 'htdocs/js/*.*',
                 'htdocs/js/messages/*.*', 'htdocs/css/*.*',
                 'htdocs/css/jquery-ui/*.*',
                 'htdocs/css/jquery-ui/images/*.*',
                 'htdocs/guide/*', 'locale/*/LC_MESSAGES/messages.mo',
                 'locale/*/LC_MESSAGES/tracini.mo'],
        'trac.wiki': ['default-pages/*'],
        'trac.ticket': ['workflows/*.ini'],
        'tracopt': ['ticket/htdocs/*.js'],
    },

    test_suite = 'trac.test.test_suite',
    zip_safe = True,

    setup_requires = [
        'jinja2>=2.9.3',
        'six>=1.9',
    ],
    install_requires = [
        'setuptools>=0.6',
        'jinja2>=2.9.3',
        'six>=1.9',
    ],
    extras_require = {
        'genshi': ['Genshi>=0.6'],
        'babel': ['Babel>=0.9.5'],
        'mysql': ['PyMySQL'],
        'postgresql': ['psycopg2 >= 2.0'],
        'psycopg2': ['psycopg2 >= 2.0'],
        'psycopg2-binary': ['psycopg2-binary'],
        'pygments': ['Pygments>=1.0'],
        'rest': ['docutils>=0.3.9'],
        'textile': ['textile>=2.0'],
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
        trac.db.mysql = trac.db.mysql_backend[mysql]
        trac.db.postgres = trac.db.postgres_backend
        trac.db.sqlite = trac.db.sqlite_backend
        trac.mimeview.patch = trac.mimeview.patch
        trac.mimeview.pygments = trac.mimeview.pygments[pygments]
        trac.mimeview.rst = trac.mimeview.rst[rest]
        trac.mimeview.txtl = trac.mimeview.txtl[textile]
        trac.notification.api = trac.notification.api
        trac.notification.mail = trac.notification.mail
        trac.notification.prefs = trac.notification.prefs
        trac.prefs = trac.prefs.web_ui
        trac.search = trac.search.web_ui
        trac.ticket.admin = trac.ticket.admin
        trac.ticket.batch = trac.ticket.batch
        trac.ticket.query = trac.ticket.query
        trac.ticket.notification = trac.ticket.notification
        trac.ticket.report = trac.ticket.report
        trac.ticket.roadmap = trac.ticket.roadmap
        trac.ticket.web_ui = trac.ticket.web_ui
        trac.timeline = trac.timeline.web_ui
        trac.versioncontrol.admin = trac.versioncontrol.admin
        trac.versioncontrol.svn_authz = trac.versioncontrol.svn_authz
        trac.versioncontrol.web_ui = trac.versioncontrol.web_ui
        trac.web.auth = trac.web.auth
        trac.web.main = trac.web.main
        trac.web.session = trac.web.session
        trac.wiki.admin = trac.wiki.admin
        trac.wiki.interwiki = trac.wiki.interwiki
        trac.wiki.macros = trac.wiki.macros
        trac.wiki.web_ui = trac.wiki.web_ui
        trac.wiki.web_api = trac.wiki.web_api
        tracopt.perm.authz_policy = tracopt.perm.authz_policy
        tracopt.perm.config_perm_provider = tracopt.perm.config_perm_provider
        tracopt.ticket.clone = tracopt.ticket.clone
        tracopt.ticket.commit_updater = tracopt.ticket.commit_updater
        tracopt.ticket.deleter = tracopt.ticket.deleter
        tracopt.versioncontrol.git.git_fs = tracopt.versioncontrol.git.git_fs
        tracopt.versioncontrol.svn.svn_fs = tracopt.versioncontrol.svn.svn_fs
        tracopt.versioncontrol.svn.svn_prop = tracopt.versioncontrol.svn.svn_prop
    """,

    **extra
)
