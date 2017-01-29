# -*- coding: utf-8 -*-
#
# Copyright (C) 2012-2013 Edgewall Software
# Copyright (C) 2012 Christian Boos <cboos@edgewall.org>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

"""Trac API doc checker

Verify that all symbols belonging to modules already documented in the
doc/api Sphinx sources are referenced.

See http://trac.edgewall.org/wiki/TracDev/ApiDocs

"""

import fnmatch
import os
import re
import sys

excluded_docs = ['index.rst']
api_doc = 'doc/api'

def usage(cmd):
    print "Usage: %s [FILE...]" % (cmd,)
    print
    print "FILE is a %s file and can be a glob pattern." % (api_doc,)
    print "If no files are given, check all."
    exit(0)

def main(argv):
    api_files = rst_files = [rst for rst in os.listdir('doc/api')
                             if fnmatch.fnmatch(rst, '*.rst')
                             and rst not in excluded_docs]
    cmd = argv.pop(0)
    def has(*options):
        for opt in options:
            if opt in argv:
                return argv.pop(argv.index(opt))
    if has('-h', '--help'):
        usage(cmd)
    verbose = has('-v', '--verbose')
    only_documented = not has('-a', '--all')
    if argv:
        given_files = []
        for arg in argv:
            arg = arg.replace('\\', '/').replace(api_doc + '/', '')
            arg = arg.replace('.rst', '') + '.rst'
            if '*' in arg: # glob pattern
                given_files += [rst for rst in api_files
                                if fnmatch.fnmatch(rst, arg)]
            elif arg in api_files:
                given_files.append(arg)
        api_files = given_files
    rst_basenames = sorted(f[:-4] for f in rst_files)
    for rst in api_files:
        basename = rst.replace('.rst', '')
        if verbose or len(api_files) > 1:
            print "== Checking %s ... " % (rst,)
        check_api_doc(basename, verbose, only_documented,
                      any(f.startswith(basename) and f != basename
                          for f in rst_basenames))


def check_api_doc(basename, verbose, only_documented, has_submodules):
    module_name = basename.replace('_', '.')
    try:
        module = __import__(module_name, globals(), {}, ['__all__'])
    except ImportError, e:
        print "Skipping %s (%s)" % (basename, e)
        return
    all = getattr(module, '__all__', None)
    if not all:
        print "Warning: %s doesn't define __all__, using exported symbols." % (
            module_name,)
        all = get_default_symbols(module, only_documented, has_submodules)
    no_apidoc = getattr(module, '__no_apidoc__', None)
    if no_apidoc:
        if isinstance(no_apidoc, basestring):
            no_apidoc = [s.strip() for s in no_apidoc.split()]
        all = list(set(all) - set(no_apidoc))
    symbols, keywords = get_sphinx_documented_symbols(basename + '.rst')
    for symbol in sorted(all):
        if symbol in symbols:
            if verbose:
                print " - OK %14s :: %s" % (
                    keywords[symbols.index(symbol)], symbol)
        else:
            value = getattr(module, symbol)
            cls = getattr(value, '__class__', None)
            keyword = 'data'
            if cls.__name__ in ('function', 'instancemethod'):
                keyword = 'function'
            elif cls.__name__ == 'module':
                keyword = 'module'
            else:
                keyword = 'class'
            print " * .. %14s :: %s" % ('auto' + keyword, symbol)


sphinx_doc_re = re.compile(r'''
^.. \s+ ((?:py:|auto)(?:module|class|function|attribute)|data)  # keyword
                                     \s* :: \s* ([\w\.]+)       # symbol
''', re.MULTILINE | re.VERBOSE)

def get_sphinx_documented_symbols(rst):
    with open(os.path.join(api_doc, rst)) as f:
        doc = f.read()
    symbols, keywords = [], []
    for k, s in sphinx_doc_re.findall(doc):
        symbols.append(s.split('.')[-1])
        keywords.append(k)
    return symbols, keywords


def get_default_symbols(module, only_documented, has_submodules):
    public = get_public_symbols(module) - get_imported_symbols(module,
                                                               has_submodules)
    # eliminate modules
    all = []
    for symbol in public:
        try:
            __import__(symbol)
        except ImportError:
            all.append(symbol)
    # only keep symbols having a docstring
    if only_documented:
        documented = []
        for symbol in all:
            value = getattr(module, symbol)
            if value.__doc__ and (not getattr(value, '__class__', None) or
                                  value.__doc__ != value.__class__.__doc__):
                documented.append(symbol)
        all = documented
    return all

def get_public_symbols(m):
    return set(symbol for symbol in dir(m) if not symbol.startswith('_'))

import_from_re = re.compile(r'''
^ \s* from \s+ ([\w\.]+) \s+ import \s+   # module
(                                \*       # all symbols
|       %s (?: [\s\\]* , [\s\\]* %s)*     # list of symbols
| \( \s* %s (?: \s* , \s* %s)* \s* \)     # list of symbols in parenthesis
)
''' % ((r'(?:\w+|\w+\s+as\s+\w+)',) * 4), re.MULTILINE | re.VERBOSE)

remove_original_re = re.compile(r'\w+\s+as', re.MULTILINE)

def get_imported_symbols(module, has_submodules):
    src_filename = module.__file__.replace('\\', '/').replace('.pyc', '.py')
    if src_filename.endswith('/__init__.py') and not has_submodules:
        return set()
    with open(src_filename) as f:
        src = f.read()
    imported = set()
    for mod, symbol_list in import_from_re.findall(src):
        symbol_list = symbol_list.strip()
        if symbol_list == '*':
            try:
                imported_module = __import__(mod, globals(), {}, ['__all__'])
                symbols = set(getattr(imported_module, '__all__', None) or
                              get_public_symbols(imported_module))
            except ImportError:
                print "Warning: 'from %s import *' couldn't be resolved" % (
                    mod,)
                continue
        else:
            if symbol_list and symbol_list[0] == '(' and symbol_list[-1] == ')':
                symbol_list = symbol_list[1:-1]
            symbols = set(remove_original_re.sub('', symbol_list)
                          .replace('\\', '').replace(',', ' ').split())
        imported |= symbols
    return imported


if __name__ == '__main__':
    main(sys.argv)
