# Copyright (C) 2014 Edgewall Software
# This file is distributed under the same license as the Trac project.

import StringIO
import warnings

from trac.util.text import print_table, printout

PACKAGES = [
    ("Python",            'sys.version'),
    ("Setuptools",        'setuptools.__version__'),
    ("Genshi",            'genshi.__version__'),
    ("Babel",             'babel.__version__'),
    ("sqlite3",           'sqlite3.version'),
    ("PySqlite",          'pysqlite2.dbapi2.version'),
    ("MySQLdb",           'MySQLdb.__version__'),
    ("Psycopg2",          'psycopg2.__version__'),
    ("SVN bindings",      'svn.core.SVN_VERSION'),
    ("Mercurial",         'mercurial.util.version()'),
    ("Pygments",          'pygments.__version__'),
    ("Pytz",              'pytz.__version__'),
    ("ConfigObj",         'configobj.__version__'),
    ("Docutils",          'docutils.__version__'),
    ("Twill",             'twill.__version__'),
    ("LXML",              'lxml.etree.__version__'),
]

def package_versions(packages, out=None):
    name_version_pairs = []
    for name, accessor in packages:
        module, attr = accessor.rsplit('.', 1)
        version = attr.replace('()', '')
        try:
            version = getattr(__import__(module, {}, {}, [version]), version)
            if attr.endswith('()'):
                version = version()
        except Exception:
            version = "not installed"
        name_version_pairs.append((name, version))
    print_table(name_version_pairs, ("", "Version"), ' : ', out)

def shift(prefix, block):
    return '\n'.join(prefix + line for line in block.split('\n') if line)

def print_status():
    warnings.filterwarnings('ignore', '', DeprecationWarning) # Twill 0.9...
    buf = StringIO.StringIO()
    package_versions(PACKAGES, buf)
    printout(shift('  ', buf.getvalue()))


if __name__ == '__main__':
    print_status()
