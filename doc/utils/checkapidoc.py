# -*- coding:  utf-8 -*-

"""Trac API doc checker

Verify that all symbols belonging to modules already documented in the doc/api
Sphinx sources are referenced.

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
    api_files = [rst for rst in os.listdir('doc/api')
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
    for rst in api_files:
        check_api_doc(rst, verbose, only_documented)


def check_api_doc(rst, verbose, only_documented):
    if verbose:
        print "== Checking %s ... " % (rst,)
    module_name = rst.replace('_', '.').replace('.rst', '')
    try:
        module = __import__(module_name, globals(), {}, ['__all__'])
    except ImportError, e:
        print "Skipping %s (%s)" % (rst, e)
        return
    all = getattr(module, '__all__', None)
    if not all:
        print "Warning: %s doesn't define __all__, using exported symbols." % (
            module_name,)
        all = get_default_symbols(module, only_documented)
    symbols, keywords = get_sphinx_documented_symbols(rst)
    for symbol in sorted(all):
        if symbol in symbols:
            if verbose:
                print " - OK %14s :: %s" % (
                    keywords[symbols.index(symbol)], symbol)
        else:
            value = getattr(module, symbol)
            cls = getattr(value, '__class__', None)
            keyword = 'attribute'
            if not cls or cls.__name__ == 'type':
                keyword = 'class'
            elif cls.__name__ in ('function', 'module'):
                keyword = cls.__name__
            print " * .. %14s :: %s" % ('auto' + keyword, symbol)


sphinx_doc_re = re.compile(r'''
^.. \s+ ((?:py:|auto)(?:module|class|function|attribute))  # keyword
                                     \s* :: \s* ([\w\.]+)  # symbol
''', re.MULTILINE | re.VERBOSE)

def get_sphinx_documented_symbols(rst):
    doc = file(os.path.join(api_doc, rst)).read()
    symbols, keywords = [], []
    for k, s in sphinx_doc_re.findall(doc):
        symbols.append(s.split('.')[-1])
        keywords.append(k)
    return symbols, keywords


def get_default_symbols(module, only_documented):
    public = get_public_symbols(module) - get_imported_symbols(module)
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
^from \s+ ([\w\.]+) \s+ import \s+   # module
(                                \*  # all symbols
|       \w+ (?:[\s\\]*,[\s\\]*\w+)*  # list of symbols
| \( \s* \w+ (?:\s*,\s*\w+)* \s* \)  # list of symbols in parenthesis
)
''', re.MULTILINE | re.VERBOSE)

def get_imported_symbols(module):
    src_filename = module.__file__.replace('\\', '/').replace('.pyc', '.py')
    if src_filename.endswith('/__init__.py'):
        return set()
    src = file(src_filename).read()
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
            symbols = set(symbol_list.replace('\\', '').replace(',', ' ')
                          .split())
        imported |= symbols
    return imported


if __name__ == '__main__':
    main(sys.argv)
