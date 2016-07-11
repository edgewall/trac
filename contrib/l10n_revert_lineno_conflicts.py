#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2013 Edgewall Software
# Copyright (C) 2013 Christian Boos <cboos@edgewall.org>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

"""

L10N tool which takes a list of .po in conflicted state and revert
ignorable changes.

It resolve the conflicts for which "theirs" changes consist solely of
line number changes, by reverting to the working copy content.

This makes it easier to merge translation .po files across branches.

"""

import re

ignore_lineno_re = re.compile(r'''
          <<<< .* \n
    ( (?: [^=] .* \n )+ )   # \1 == "working copy"
          ==== .* \n
    ( (?: \#   .* \n )+ )   # \2 == comment only for "theirs"
          >>>> .* \n
    ''', re.MULTILINE | re.VERBOSE)

HEADERS = '''
Project-Id-Version Report-Msgid-Bugs-To POT-Creation-Date PO-Revision-Date
Last-Translator Language-Team Plural-Forms MIME-Version Content-Type
Content-Transfer-Encoding Generated-By
'''.split()

po_headers_re = re.compile(r'''
          <<<< .* \n
    ( (?: "(?:%(header)s): \s [^"]+" \n )+ )  # \1 == "working copy"
          ==== .* \n
    ( (?: "(?:%(header)s): \s [^"]+" \n )+ )  # \2 == another date for "theirs"
          >>>> .* \n
    ''' % dict(header='|'.join(HEADERS)), re. MULTILINE | re.VERBOSE)


def sanitize_file(path):
    with open(path, 'r+') as f:
        sanitized, nsub = ignore_lineno_re.subn(r'\1', f.read())
        sanitized, nsub2 = po_headers_re.subn(r'\1', sanitized)
        nsub += nsub2
        if nsub:
            print("reverted %d ignorable changes in %s" % (nsub, path))
            f.seek(0)
            f.write(sanitized)
            f.truncate()
        else:
            print("no ignorable changes in %s" % (path,))

if __name__ == '__main__':
    import sys
    for path in sys.argv[1:]:
        sanitize_file(path)
