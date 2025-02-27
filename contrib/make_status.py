#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2014-2023 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.

import importlib
import io
import pkg_resources
import warnings

from trac.util.text import print_table, printout

def _svn_version():
    from svn import core
    version = (core.SVN_VER_MAJOR, core.SVN_VER_MINOR,
               core.SVN_VER_MICRO)
    return '%d.%d.%d' % version + str(core.SVN_VER_TAG, 'utf-8')

def _pytidylib_version():
    version = pkg_resources.get_distribution('pytidylib').version
    try:
        import tidylib
        tidy = tidylib.Tidy()
    except Exception as e:
        info = 'not installed'
    else:
        import ctypes
        try:
            cdll = tidy._tidy
            try:
                fn = cdll.tidyLibraryVersion
                fn.restype = ctypes.c_char_p
                libver = fn()
                if isinstance(libver, bytes):
                    libver = str(libver, 'utf-8')
            except Exception as e:
                libver = repr(e)
            info = '%s %s' % (libver, cdll._name)
        except Exception as e:
            info = repr(e)
    return '%s (%s)' % (version, info) if info else version

def _pysqlite3_version():
    return pkg_resources.get_distribution('pysqlite3').version


PACKAGES = [
    ("Python",            'sys.version'),
    ("Setuptools",        'setuptools.__version__'),
    ("Pip",               'pip.__version__'),
    ("Wheel",             'wheel.__version__'),
    ("Jinja2",            'jinja2.__version__'),
    ("multipart",         'multipart.__version__'),
    ("Babel",             'babel.__version__'),
    ("sqlite3",           ('sqlite3.version',
                           'sqlite3.sqlite_version')),
    ("PySqlite3",         ('__main__._pysqlite3_version()',
                           'pysqlite3.dbapi2.sqlite_version')),
    ("PyMySQL",           'pymysql.__version__'),
    ("Psycopg2",          'psycopg2.__version__'),
    ("SVN bindings",      '__main__._svn_version()'),
    ("Mercurial",         'mercurial.util.version()'),
    ("Pygments",          'pygments.__version__'),
    ("Textile",           'textile.__version__'),
    ("Pytz",              'pytz.__version__'),
    ("Docutils",          'docutils.__version__'),
    ("aiosmtpd",          'aiosmtpd.__version__'),
    ("Selenium",          'selenium.__version__'),
    ("PyTidyLib",         '__main__._pytidylib_version()'),
    ("LXML",              'lxml.etree.__version__'),
    ("coverage",          'coverage.__version__'),
]

def package_versions(packages, out=None):
    name_version_pairs = []
    for name, accessors in packages:
        version = get_version(accessors)
        name_version_pairs.append((name, version))
    print_table(name_version_pairs, ("Package", "Version"), ' : ', out)

def get_version(accessors):
    if isinstance(accessors, tuple):
        version = resolve_accessor(accessors[0])
        details = resolve_accessor(accessors[1])
        if version:
            return "%s (%s)" % (version, details or '?')
    else:
        version = resolve_accessor(accessors)
    return version or 'not installed'

def resolve_accessor(accessor):
    try:
        module, attr = accessor.rsplit('.', 1)
        version = attr.replace('()', '')
        version = getattr(importlib.import_module(module), version)
        if attr.endswith('()'):
            version = version()
        return version
    except Exception:
        return None

def shift(prefix, block):
    return '\n'.join(prefix + line for line in block.split('\n') if line)

def print_status():
    buf = io.StringIO()
    package_versions(PACKAGES, buf)
    printout(shift('  ', buf.getvalue()))


if __name__ == '__main__':
    print_status()
